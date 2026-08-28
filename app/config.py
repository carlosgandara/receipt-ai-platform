import os
from dotenv import load_dotenv
import datetime

load_dotenv()

# ---------- Server ----------
PORT = int(os.getenv("PORT", 3000))

# ---------- SMTP ----------
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_DISPLAY_NAME = os.getenv("EMAIL_DISPLAY_NAME", "wolfchad")

# ---------- Security ----------
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "False").lower() == "true"
BASE_URL = os.getenv("BASE_URL", "http://localhost:3000")

# ---------- JWT ----------
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "dev-secret")
JWT_EXPIRATION = datetime.timedelta(days=1)
RESET_TOKEN_EXPIRATION = datetime.timedelta(minutes=15)
VERIFICATION_EXPIRATION = datetime.timedelta(days=1)

# ---------- Receipt AI (File Uploads) ----------
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
IMAGE_FOLDER = os.getenv("IMAGE_FOLDER", "images")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024   # 16 MB

# ---------- Neon Object Storage (S3-compatible) ----------
AWS_ENDPOINT_URL_S3 = os.getenv("AWS_ENDPOINT_URL_S3")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# Check if S3 is configured
USE_S3 = all([AWS_ENDPOINT_URL_S3, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME])
if USE_S3:
    print(f"✅ Neon Object Storage configured – bucket: {S3_BUCKET_NAME}")
else:
    print("⚠️ Neon Object Storage credentials not found. Images will be stored locally.")

    
# ---------- Database ----------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./test.db"
    print("⚠️ DATABASE_URL not found. Using SQLite for development.")
else:
    print("✅ Connected to Neon PostgreSQL")

# ---------- Optional: check for missing env (warn, don't crash in dev) ----------
REQUIRED_ENV = ["EMAIL_HOST", "EMAIL_PORT", "EMAIL_USER", "EMAIL_PASS", "EMAIL_FROM"]
missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
if missing:
    print(f"⚠️ Missing env variables: {', '.join(missing)} – email features will not work.")