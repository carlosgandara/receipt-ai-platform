# app/decorators/auth.py – Shared authentication helpers
# Contains token_required decorator and JWT generation function.

from functools import wraps
import datetime
import jwt
from flask import request, jsonify

from app.config import JWT_SECRET, JWT_EXPIRATION

def generate_jwt(email):
    """Generate an access token (JWT)."""
    payload = {"sub": email, "exp": datetime.datetime.utcnow() + JWT_EXPIRATION}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def token_required(f):
    """Decorator to protect routes – validates JWT from HttpOnly cookie."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("access_token")
        if not token:
            return jsonify({"error": "Missing access token"}), 401
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.user_email = payload["sub"]
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return jsonify({"error": "Invalid or expired access token"}), 401
        return f(*args, **kwargs)
    return decorated