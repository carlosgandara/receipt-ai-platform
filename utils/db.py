import os
import datetime
import bcrypt
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Boolean, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ---------- Load Environment Variables ----------
load_dotenv()

# ---------- Database Configuration ----------
DATABASE_URL = os.getenv("DATABASE_URL")

# Fallback to SQLite for local testing if DATABASE_URL is not set
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./test.db"
    print("⚠️  DATABASE_URL not found. Using SQLite for development.")
else:
    print("✅ Connected to Neon PostgreSQL")

# ---------- SQLAlchemy Setup ----------
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------- User Model ----------
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    
    # Email verification
    verified = Column(Boolean, default=False)
    verification_token = Column(String, nullable=True)
    verification_expiry = Column(TIMESTAMP, nullable=True)
    
    # Password reset
    reset_token = Column(String, nullable=True)
    reset_expiry = Column(TIMESTAMP, nullable=True)
    
    # Security & Lockout
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(TIMESTAMP, nullable=True)
    
    # Refresh Token (hashed)
    refresh_token_hash = Column(String, nullable=True)

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"

# ---------- Create Tables ----------
# This creates the table in Neon if it doesn't already exist
Base.metadata.create_all(bind=engine)

# ================================================================
# CRUD FUNCTIONS (Used by app.py)
# ================================================================

def get_all_users():
    """Return all users (used for refresh token scanning)."""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        return users
    finally:
        db.close()

def find_user_by_email(email):
    """Find a user by email. Returns None if not found."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        return user
    finally:
        db.close()

def find_user_by_verification_token(token):
    """Find a user by verification token (plain text)."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.verification_token == token).first()
        return user
    finally:
        db.close()

def find_user_by_reset_token(token):
    """
    Find a user by reset token.
    The reset_token is stored as a bcrypt hash, so we check each user.
    """
    db = SessionLocal()
    try:
        users = db.query(User).all()
        for user in users:
            if user.reset_token:
                # Check if the provided token matches the stored hash
                if bcrypt.checkpw(token.encode("utf-8"), user.reset_token.encode("utf-8")):
                    return user
        return None
    finally:
        db.close()

def create_user(email, password_hash):
    """Create a new user. Returns the created user object."""
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
    """
    Update a user with the given dictionary of fields.
    Returns the updated user object, or None if user not found.
    
    Example:
        update_user("test@example.com", {"verified": True, "refresh_token_hash": "abc123"})
    """
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
# COMPATIBILITY STUBS (Keep these so old code doesn't break)
# ================================================================

def _read_db():
    """Placeholder for JSON compatibility. Not used with PostgreSQL."""
    return {"users": []}

def _write_db(data):
    """Placeholder for JSON compatibility. Not used with PostgreSQL."""
    pass