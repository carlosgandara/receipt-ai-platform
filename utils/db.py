# utils/db.py – Complete Database Layer
# Combines User/RefreshToken models with Receipt model.
# Uses PostgreSQL (or SQLite fallback) with SQLAlchemy.

import os
import datetime
import hashlib
import bcrypt
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime,
    ForeignKey, Index, Text, Float, func
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, joinedload
from sqlalchemy.exc import IntegrityError

load_dotenv()

# ---------- Database Configuration ----------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./test.db"
    print("⚠️  DATABASE_URL not found. Using SQLite for development.")
else:
    print("✅ Connected to Neon PostgreSQL")

# ---------- SQLAlchemy Setup ----------
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ================================================================
# MODELS
# ================================================================

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    
    # Email verification
    verified = Column(Boolean, default=False)
    verification_token = Column(String, nullable=True)
    verification_expiry = Column(DateTime, nullable=True)
    
    # Password reset
    reset_token = Column(String, nullable=True)
    reset_expiry = Column(DateTime, nullable=True)
    
    # Security & Lockout
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    
    # Relationships
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    receipts = relationship("Receipt", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # 🔐 DUAL-HASH STRATEGY
    token_hash_sha256 = Column(String(64), nullable=False)  # Index defined below
    token_hash_bcrypt = Column(String, nullable=False)
    
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)  # None = active

    # Relationship back to user
    user = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (
        Index('ix_refresh_tokens_token_hash_sha256', 'token_hash_sha256'),
    )

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, revoked={self.revoked_at is not None})>"


class Receipt(Base):
    __tablename__ = "receipts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Core receipt data
    submission_id = Column(String(32), nullable=False, index=True)   # no global unique
    image_name = Column(String(255), nullable=False)
    image_path = Column(String(512), nullable=False)
    
    merchant = Column(String(255), nullable=True)
    date = Column(String(10), nullable=True)   # YYYY-MM-DD
    time = Column(String(20), nullable=True)
    subtotal = Column(Float, nullable=True)
    tax = Column(Float, nullable=True)
    total = Column(Float, nullable=False)
    payment_method = Column(String(50), nullable=True)
    category = Column(String(50), nullable=True)
    comment = Column(String(500), nullable=True)
    
    # AI raw description
    raw_description = Column(Text, nullable=True)
    
    # Image hash for duplicate detection
    image_hash = Column(String(32), nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    
    # Relationship back to user
    user = relationship("User", back_populates="receipts")
    
    __table_args__ = (
        Index('ix_receipts_user_date', 'user_id', 'date'),
        Index('ix_receipts_user_category', 'user_id', 'category'),
        Index('ix_receipts_user_merchant', 'user_id', 'merchant'),
    )

    def __repr__(self):
        return f"<Receipt(id={self.id}, user_id={self.user_id}, merchant={self.merchant}, total={self.total})>"


# ---------- Create Tables ----------
Base.metadata.create_all(bind=engine)


# ================================================================
# USER CRUD FUNCTIONS
# ================================================================

def get_all_users():
    db = SessionLocal()
    try:
        return db.query(User).all()
    finally:
        db.close()


def find_user_by_email(email):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == email).first()
    finally:
        db.close()


def find_user_by_verification_token(token):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.verification_token == token).first()
    finally:
        db.close()


def find_user_by_reset_token(token):
    db = SessionLocal()
    try:
        users = db.query(User).all()
        for user in users:
            if user.reset_token and bcrypt.checkpw(token.encode("utf-8"), user.reset_token.encode("utf-8")):
                return user
        return None
    finally:
        db.close()


def create_user(email, password_hash):
    db = SessionLocal()
    try:
        new_user = User(email=email, password=password_hash)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def update_user(email, updates):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return None
        for key, value in updates.items():
            if hasattr(user, key):
                setattr(user, key, value)
        db.commit()
        db.refresh(user)
        return user
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_user_by_id(user_id):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()


# ================================================================
# REFRESH TOKEN CRUD FUNCTIONS (Dual-Hash Strategy)
# ================================================================

def create_refresh_token(user_id, raw_token, expires_at):
    sha256_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    bcrypt_hash = bcrypt.hashpw(raw_token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    db = SessionLocal()
    try:
        rt = RefreshToken(
            user_id=user_id,
            token_hash_sha256=sha256_hash,
            token_hash_bcrypt=bcrypt_hash,
            expires_at=expires_at
        )
        db.add(rt)
        db.commit()
        db.refresh(rt)
        return rt
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def find_refresh_token_by_raw(raw_token):
    """
    Look up a refresh token by raw token.
    Uses SHA256 index for O(1) lookup, then verifies with bcrypt.
    Eagerly loads the associated user to avoid DetachedInstanceError.
    """
    sha256_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    db = SessionLocal()
    try:
        token_record = db.query(RefreshToken).options(
            joinedload(RefreshToken.user)
        ).filter(
            RefreshToken.token_hash_sha256 == sha256_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.datetime.utcnow()
        ).first()
        if not token_record:
            return None
        # Verify with bcrypt
        if bcrypt.checkpw(raw_token.encode("utf-8"), token_record.token_hash_bcrypt.encode("utf-8")):
            return token_record
        return None
    finally:
        db.close()


def revoke_refresh_token(token_id):
    db = SessionLocal()
    try:
        rt = db.query(RefreshToken).filter(RefreshToken.id == token_id).first()
        if rt:
            rt.revoked_at = datetime.datetime.utcnow()
            db.commit()
            return True
        return False
    finally:
        db.close()


def revoke_all_user_tokens(user_id):
    db = SessionLocal()
    try:
        db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None)
        ).update({"revoked_at": datetime.datetime.utcnow()})
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_active_refresh_tokens(user_id):
    db = SessionLocal()
    try:
        return db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.datetime.utcnow()
        ).all()
    finally:
        db.close()


# ================================================================
# RECEIPT CRUD FUNCTIONS
# ================================================================

def create_receipt(user_id, receipt_data):
    """
    Insert a new receipt for a user.
    receipt_data is a dict containing all fields except user_id and created_at.
    Raises ValueError if submission_id already exists (duplicate).
    """
    db = SessionLocal()
    try:
        receipt = Receipt(
            user_id=user_id,
            submission_id=receipt_data.get('submission_id'),
            image_name=receipt_data.get('image_name'),
            image_path=receipt_data.get('image_path'),
            merchant=receipt_data.get('merchant'),
            date=receipt_data.get('date'),
            time=receipt_data.get('time'),
            subtotal=receipt_data.get('subtotal'),
            tax=receipt_data.get('tax'),
            total=receipt_data.get('total'),
            payment_method=receipt_data.get('payment_method'),
            category=receipt_data.get('category'),
            comment=receipt_data.get('comment'),
            raw_description=receipt_data.get('raw_description'),
            image_hash=receipt_data.get('image_hash'),
            processed_at=datetime.datetime.utcnow()
        )
        db.add(receipt)
        db.commit()
        db.refresh(receipt)
        return receipt
    except IntegrityError as e:
        db.rollback()
        raise ValueError("Duplicate receipt: submission_id already exists") from e
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_user_receipts(user_id, start_date=None, end_date=None, category=None, merchant=None):
    """
    Get all receipts for a user with optional filters.
    Returns a list of Receipt objects.
    """
    db = SessionLocal()
    try:
        query = db.query(Receipt).filter(Receipt.user_id == user_id)
        
        if start_date:
            try:
                start = datetime.datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Receipt.date >= start.strftime('%Y-%m-%d'))
            except ValueError:
                pass
        
        if end_date:
            try:
                end = datetime.datetime.strptime(end_date, '%Y-%m-%d')
                query = query.filter(Receipt.date <= end.strftime('%Y-%m-%d'))
            except ValueError:
                pass
        
        if category and category != 'ALL':
            query = query.filter(Receipt.category == category)
        
        if merchant:
            query = query.filter(Receipt.merchant.ilike(f'%{merchant}%'))
        
        return query.order_by(Receipt.created_at.desc()).all()
    finally:
        db.close()


def get_receipt_by_id(receipt_id, user_id):
    """
    Get a single receipt by ID, ensuring it belongs to the specified user.
    Returns Receipt object or None.
    """
    db = SessionLocal()
    try:
        return db.query(Receipt).filter(
            Receipt.id == receipt_id,
            Receipt.user_id == user_id
        ).first()
    finally:
        db.close()


def get_receipt_by_image_path(image_path, user_id):
    """
    Get a receipt by its image_path, ensuring it belongs to the user.
    Used for ownership verification when serving images.
    """
    db = SessionLocal()
    try:
        return db.query(Receipt).filter(
            Receipt.image_path == image_path,
            Receipt.user_id == user_id
        ).first()
    finally:
        db.close()


def delete_receipt(receipt_id, user_id):
    """
    Delete a receipt, ensuring it belongs to the user.
    Also should delete the associated image file – handled in app.py.
    Returns True if deleted, False if not found.
    """
    db = SessionLocal()
    try:
        receipt = db.query(Receipt).filter(
            Receipt.id == receipt_id,
            Receipt.user_id == user_id
        ).first()
        if not receipt:
            return False
        db.delete(receipt)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def is_duplicate(user_id, merchant, date, total, image_hash=None):
    """
    Check if a receipt already exists for this user.
    Checks by:
    1. Exact image hash (if provided)
    2. Normalized merchant, date, and total (case-insensitive)
    Returns True if duplicate found, False otherwise.
    """
    db = SessionLocal()
    try:
        # 1. Hash check – exact file duplicate
        if image_hash:
            existing = db.query(Receipt).filter(
                Receipt.user_id == user_id,
                Receipt.image_hash == image_hash
            ).first()
            if existing:
                return True
        
        # 2. Content check (normalized) – using func.lower()
        existing = db.query(Receipt).filter(
            Receipt.user_id == user_id,
            Receipt.date == date,
            Receipt.total == total
        ).filter(
            func.lower(Receipt.merchant) == merchant.lower()
        ).first()
        
        return existing is not None
    finally:
        db.close()


def count_user_receipts(user_id):
    """Count total receipts for a user."""
    db = SessionLocal()
    try:
        return db.query(Receipt).filter(Receipt.user_id == user_id).count()
    finally:
        db.close()


# ================================================================
# COMPATIBILITY STUBS (keep for backward compatibility)
# ================================================================

def _read_db():
    return {"users": []}

def _write_db(data):
    pass