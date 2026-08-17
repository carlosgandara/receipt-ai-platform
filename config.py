import os
from dotenv import load_dotenv
import datetime

load_dotenv()

# SMTP
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_DISPLAY_NAME = "wolfchad"          # optional

# JWT
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "dev-secret")

# Expirations
JWT_EXPIRATION = datetime.timedelta(minutes=1)
RESET_TOKEN_EXPIRATION = datetime.timedelta(minutes=15)
VERIFICATION_EXPIRATION = datetime.timedelta(days=1)

# Check required variables
REQUIRED_ENV = ["EMAIL_HOST", "EMAIL_PORT", "EMAIL_USER", "EMAIL_PASS", "EMAIL_FROM"]
missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
if missing:
    raise EnvironmentError(f"Missing env: {', '.join(missing)}")