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
    token_hash_sha256 = Column(String(64), nullable=False)
    token_hash_bcrypt = Column(String, nullable=False)
    
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)

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
    receipt_hash = Column(String(32), nullable=False, index=True)
    image_name = Column(String(255), nullable=False)
    image_path = Column(String(512), nullable=True)
    merchant = Column(String(255), nullable=True)
    date = Column(String(10), nullable=True)
    time = Column(String(20), nullable=True)
    subtotal = Column(Float, nullable=True)
    tax = Column(Float, nullable=True)
    total = Column(Float, nullable=False)
    payment_method = Column(String(50), nullable=True)
    category = Column(String(50), nullable=True)
    deduction_category = Column(String(100), nullable=True)   # <-- NEW: 1099 deduction type
    comment = Column(String(500), nullable=True)
    
    # AI raw description
    raw_description = Column(Text, nullable=True)
    
    # Image hash for duplicate detection
    image_hash = Column(String(32), nullable=True, index=True)
    
    # S3 object key
    s3_key = Column(String(512), nullable=True)
    
    # Soft delete
    deleted_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    
    # Relationship back to user
    user = relationship("User", back_populates="receipts")
    
    __table_args__ = (
        Index('ix_receipts_user_date', 'user_id', 'date'),
        Index('ix_receipts_user_category', 'user_id', 'category'),
        Index('ix_receipts_user_merchant', 'user_id', 'merchant'),
        Index('ix_receipts_deleted_at', 'deleted_at'),
        Index('ix_receipts_s3_key', 's3_key'),
        Index('ix_receipts_deduction_category', 'deduction_category'),  # <-- NEW index
    )

    def __repr__(self):
        return f"<Receipt(id={self.id}, user_id={self.user_id}, merchant={self.merchant}, total={self.total}, deleted={self.deleted_at is not None})>"


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
# REFRESH TOKEN CRUD FUNCTIONS
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
    db = SessionLocal()
    receipt = Receipt(
        user_id=user_id,
        receipt_hash=receipt_data.get('receipt_hash'),
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
        deduction_category=receipt_data.get('deduction_category'),  # <-- NEW
        comment=receipt_data.get('comment'),
        raw_description=receipt_data.get('raw_description'),
        image_hash=receipt_data.get('image_hash'),
        s3_key=receipt_data.get('s3_key'),
        processed_at=datetime.datetime.utcnow()
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    db.close()
    return receipt


def get_user_receipts(user_id, start_date=None, end_date=None, category=None, merchant=None, include_deleted=False):
    db = SessionLocal()
    try:
        query = db.query(Receipt).filter(Receipt.user_id == user_id)
        
        if not include_deleted:
            query = query.filter(Receipt.deleted_at.is_(None))
        
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


def get_receipt_by_id(receipt_id, user_id, include_deleted=False):
    db = SessionLocal()
    try:
        query = db.query(Receipt).filter(
            Receipt.id == receipt_id,
            Receipt.user_id == user_id
        )
        if not include_deleted:
            query = query.filter(Receipt.deleted_at.is_(None))
        return query.first()
    finally:
        db.close()


def get_receipt_by_image_path(image_path, user_id):
    db = SessionLocal()
    try:
        return db.query(Receipt).filter(
            Receipt.image_path == image_path,
            Receipt.user_id == user_id,
            Receipt.deleted_at.is_(None)
        ).first()
    finally:
        db.close()


def soft_delete_receipt(receipt_id, user_id):
    db = SessionLocal()
    try:
        receipt = db.query(Receipt).filter(
            Receipt.id == receipt_id,
            Receipt.user_id == user_id,
            Receipt.deleted_at.is_(None)
        ).first()
        if not receipt:
            return False
        receipt.deleted_at = datetime.datetime.utcnow()
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def restore_receipt(receipt_id, user_id):
    db = SessionLocal()
    try:
        receipt = db.query(Receipt).filter(
            Receipt.id == receipt_id,
            Receipt.user_id == user_id,
            Receipt.deleted_at.is_not(None)
        ).first()
        if not receipt:
            return False
        receipt.deleted_at = None
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def hard_delete_receipt(receipt_id, user_id):
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


def hard_delete_old_receipts(days=30):
    db = SessionLocal()
    try:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        receipts = db.query(Receipt).filter(
            Receipt.deleted_at <= cutoff
        ).all()
        count = len(receipts)
        for r in receipts:
            db.delete(r)
        db.commit()
        return count
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def is_duplicate(user_id, merchant, date, total, image_hash=None):
    db = SessionLocal()
    try:
        if image_hash:
            existing = db.query(Receipt).filter(
                Receipt.user_id == user_id,
                Receipt.image_hash == image_hash,
                Receipt.deleted_at.is_(None)
            ).first()
            if existing:
                return True
        
        existing = db.query(Receipt).filter(
            Receipt.user_id == user_id,
            Receipt.date == date,
            Receipt.total == total,
            Receipt.deleted_at.is_(None)
        ).filter(
            func.lower(Receipt.merchant) == merchant.lower()
        ).first()
        
        return existing is not None
    finally:
        db.close()


def count_user_receipts(user_id, include_deleted=False):
    db = SessionLocal()
    try:
        query = db.query(Receipt).filter(Receipt.user_id == user_id)
        if not include_deleted:
            query = query.filter(Receipt.deleted_at.is_(None))
        return query.count()
    finally:
        db.close()


# ================================================================
# COMPATIBILITY STUBS
# ================================================================

def _read_db():
    return {"users": []}

def _write_db(data):
    pass