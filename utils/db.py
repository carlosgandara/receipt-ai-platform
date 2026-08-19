import os
import datetime
import hashlib
import bcrypt
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, joinedload

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
    
    # Relationship to refresh tokens
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

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
            joinedload(RefreshToken.user)  # ✅ Eagerly load user
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
# COMPATIBILITY STUBS
# ================================================================

def _read_db():
    return {"users": []}

def _write_db(data):
    pass