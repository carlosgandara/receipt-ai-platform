import os
from dotenv import load_dotenv

# Load .env and print the database URL for debugging
load_dotenv()
print(f"🔍 app.py DATABASE_URL: {os.getenv('DATABASE_URL')}")

import secrets
import datetime
import time
import threading
import re
from functools import wraps
from flask import Flask, request, jsonify, render_template, redirect, make_response
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import bcrypt
import jwt

from config import (
    JWT_SECRET,
    JWT_EXPIRATION,
    RESET_TOKEN_EXPIRATION,
    VERIFICATION_EXPIRATION,
    COOKIE_SECURE,
    BASE_URL
)
from utils.db import (
    find_user_by_email,
    create_user,
    update_user,
    get_all_users,
    find_user_by_reset_token,
    create_refresh_token,
    find_refresh_token_by_raw,
    revoke_refresh_token,
    revoke_all_user_tokens
)
from utils.mail_service import send_email

app = Flask(__name__)
app.config["SECRET_KEY"] = JWT_SECRET

# ================================================================
# 🔐 SECURITY HEADERS (Flask-Talisman) – STRICT CSP
# ================================================================
Talisman(
    app,
    force_https=False,
    frame_options='DENY',
    x_xss_protection=True,
    x_content_type_options='nosniff',
    content_security_policy={
        'default-src': "'self'",
        'script-src': "'self'",
        'style-src': "'self'",
        'img-src': ["'self'", "data:"],
    }
)

# ================================================================
# 📊 RATE LIMITER
# ================================================================
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Too many requests. Please slow down."}), 429

# ================================================================
# 🛡️ IP + USER COMBO TRACKING (in-memory)
# ================================================================
ip_user_attempts = {}
IP_USER_LIMIT = 5
IP_USER_WINDOW = 300
IP_USER_LOCK = threading.Lock()

def get_client_ip():
    return request.remote_addr

def cleanup_old_attempts():
    now = time.time()
    with IP_USER_LOCK:
        for key in list(ip_user_attempts.keys()):
            ip_user_attempts[key] = [ts for ts in ip_user_attempts[key] if now - ts < IP_USER_WINDOW]
            if not ip_user_attempts[key]:
                del ip_user_attempts[key]

def is_ip_user_rate_limited(ip, email):
    key = f"{ip}:{email}"
    now = time.time()
    with IP_USER_LOCK:
        if key in ip_user_attempts:
            ip_user_attempts[key] = [ts for ts in ip_user_attempts[key] if now - ts < IP_USER_WINDOW]
            if not ip_user_attempts[key]:
                del ip_user_attempts[key]
                return False
            if len(ip_user_attempts[key]) >= IP_USER_LIMIT:
                return True
        return False

def add_ip_user_attempt(ip, email):
    key = f"{ip}:{email}"
    now = time.time()
    with IP_USER_LOCK:
        if key not in ip_user_attempts:
            ip_user_attempts[key] = []
        ip_user_attempts[key].append(now)
        ip_user_attempts[key] = [ts for ts in ip_user_attempts[key] if now - ts < IP_USER_WINDOW]

def clear_ip_user_attempts(ip, email):
    key = f"{ip}:{email}"
    with IP_USER_LOCK:
        if key in ip_user_attempts:
            del ip_user_attempts[key]

# ================================================================
# 🔑 JWT HELPER
# ================================================================
def generate_jwt(email):
    payload = {"sub": email, "exp": datetime.datetime.utcnow() + JWT_EXPIRATION}
    return jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")

# ================================================================
# 🩺 HEALTH CHECK
# ================================================================
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "database": "connected",
        "timestamp": datetime.datetime.utcnow().isoformat()
    }), 200

# ================================================================
# 🌐 HTML PAGES (Protected via Cookie Check)
# ================================================================
def is_authenticated():
    token = request.cookies.get("access_token")
    if not token:
        return False
    try:
        jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        return True
    except:
        return False

@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")

@app.route("/register", methods=["GET"])
def register_page():
    return render_template("register.html")

@app.route("/forgot-password", methods=["GET"])
def forgot_page():
    return render_template("forgot_password.html")

@app.route("/reset-password", methods=["GET"])
def reset_page():
    return render_template("reset_password.html", token=request.args.get("token"))

@app.route("/dashboard")
def dashboard_page():
    if not is_authenticated():
        return redirect("/login")
    return render_template("dashboard.html")

@app.route("/profile")
def profile_page():
    if not is_authenticated():
        return redirect("/login")
    return render_template("profile.html")

# ================================================================
# 📝 REGISTER (HASHED VERIFICATION TOKEN)
# ================================================================
@app.route("/register", methods=["POST"])
@limiter.limit("5 per minute")
def register():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if not any(c.isupper() for c in password):
        return jsonify({"error": "Password must contain an uppercase letter"}), 400
    if not any(c.isdigit() for c in password):
        return jsonify({"error": "Password must contain a number"}), 400
    if not any(c in "!@#$%^&*()_-+=<>?/" for c in password):
        return jsonify({"error": "Password must contain a special character (!@#$%^&*)"}), 400

    if find_user_by_email(email):
        return jsonify({"message": "If this email is valid, a verification link was sent."}), 200

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = create_user(email, hashed.decode("utf-8"))

    # 🔐 SECURITY FIX: Hash the verification token before storing it in the database
    raw_token = secrets.token_urlsafe(32)
    hashed_token = bcrypt.hashpw(raw_token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    expiry = datetime.datetime.utcnow() + VERIFICATION_EXPIRATION

    update_user(email, {
        "verification_token": hashed_token,  # ✅ Stored as bcrypt hash
        "verification_expiry": expiry
    })

    verify_link = f"{BASE_URL}/verify-email?token={raw_token}"  # Send the RAW token in the email
    subject = "Verify your email"
    text = f"Welcome! Click the link to verify: {verify_link}"
    html = f'''
    <p>Welcome!</p>
    <p>Click the button below to verify:</p>
    <p><a href="{verify_link}" style="display:inline-block;padding:12px 24px;background:#007bff;color:#fff;text-decoration:none;border-radius:6px;">Verify Email</a></p>
    <p>Expires in 24h.</p>
    '''
    try:
        send_email(email, subject, text, html)
    except Exception as e:
        print("Verification email failed:", e)

    return jsonify({"message": "If this email is valid, a verification link was sent."}), 200

# ================================================================
# ✅ VERIFY EMAIL (BCRYPT VERIFICATION)
# ================================================================
@app.route("/verify-email", methods=["GET"])
def verify_email():
    raw_token = request.args.get("token")
    if not raw_token:
        return render_template("verify_error.html", error="Missing token."), 400

    # Get all unverified users with a valid expiry
    users = get_all_users()
    user_found = None

    for user in users:
        # Skip if already verified or no token
        if user.verified or not user.verification_token or not user.verification_expiry:
            continue

        # Check if token has expired
        if user.verification_expiry < datetime.datetime.utcnow():
            continue

        # 🔐 SECURITY FIX: Verify the raw token against the stored bcrypt hash
        if bcrypt.checkpw(raw_token.encode("utf-8"), user.verification_token.encode("utf-8")):
            user_found = user
            break

    if not user_found:
        return render_template("verify_error.html", error="Invalid or expired token."), 400

    # Mark user as verified and clear the token
    update_user(user_found.email, {
        "verified": True,
        "verification_token": None,
        "verification_expiry": None
    })
    return render_template("verify_success.html")

# ================================================================
# 🔑 LOGIN
# ================================================================
@app.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    ip = get_client_ip()

    cleanup_old_attempts()

    if is_ip_user_rate_limited(ip, email):
        return jsonify({
            "error": "Too many failed login attempts from this IP for this user. Please wait 5 minutes."
        }), 429

    user = find_user_by_email(email)

    if not user:
        time.sleep(0.3)
        add_ip_user_attempt(ip, email)
        return jsonify({"error": "Invalid credentials"}), 401

    if user.locked_until and user.locked_until > datetime.datetime.utcnow():
        remaining = int((user.locked_until - datetime.datetime.utcnow()).total_seconds() / 60)
        return jsonify({
            "error": f"Account locked. Try again in {remaining} minute(s)."
        }), 403

    if not bcrypt.checkpw(password.encode("utf-8"), user.password.encode("utf-8")):
        time.sleep(0.3)
        add_ip_user_attempt(ip, email)
        attempts = (user.failed_login_attempts or 0) + 1
        updates = {"failed_login_attempts": attempts}
        if attempts >= 5:
            locked_until = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
            updates["locked_until"] = locked_until
        update_user(email, updates)
        return jsonify({"error": "Invalid credentials"}), 401

    if not user.verified:
        return jsonify({"error": "Please verify your email first."}), 403

    update_user(email, {
        "failed_login_attempts": 0,
        "locked_until": None
    })
    clear_ip_user_attempts(ip, email)

    access_token = generate_jwt(email)
    raw_refresh_token = secrets.token_urlsafe(32)
    refresh_expiry = datetime.datetime.utcnow() + datetime.timedelta(seconds=2592000)

    create_refresh_token(user.id, raw_refresh_token, refresh_expiry)

    resp = make_response(jsonify({"message": "Login successful"}))

    access_max_age = int(JWT_EXPIRATION.total_seconds())
    resp.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite='Lax',
        max_age=access_max_age
    )

    resp.set_cookie(
        key="refresh_token",
        value=raw_refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite='Lax',
        max_age=2592000
    )

    return resp

# ================================================================
# 🔄 REFRESH
# ================================================================
@app.route("/refresh", methods=["POST"])
def refresh():
    raw_refresh_token = request.cookies.get("refresh_token")
    if not raw_refresh_token:
        return jsonify({"error": "Missing refresh token"}), 401

    token_record = find_refresh_token_by_raw(raw_refresh_token)
    if not token_record:
        return jsonify({"error": "Invalid or expired refresh token"}), 401

    user = token_record.user

    revoke_refresh_token(token_record.id)

    new_access_token = generate_jwt(user.email)
    new_raw_refresh = secrets.token_urlsafe(32)
    refresh_expiry = datetime.datetime.utcnow() + datetime.timedelta(seconds=2592000)

    create_refresh_token(user.id, new_raw_refresh, refresh_expiry)

    resp = make_response(jsonify({"message": "Tokens refreshed successfully"}))

    access_max_age = int(JWT_EXPIRATION.total_seconds())
    resp.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite='Lax',
        max_age=access_max_age
    )

    resp.set_cookie(
        key="refresh_token",
        value=new_raw_refresh,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite='Lax',
        max_age=2592000
    )

    return resp

# ================================================================
# 📨 FORGOT PASSWORD
# ================================================================
@app.route("/forgot-password", methods=["POST"])
@limiter.limit("5 per minute")
def forgot_password():
    data = request.get_json()
    email = data.get("email")

    token = secrets.token_urlsafe(32)
    hashed_token = bcrypt.hashpw(token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    user = find_user_by_email(email)
    if user:
        expiry = datetime.datetime.utcnow() + RESET_TOKEN_EXPIRATION
        update_user(email, {"reset_token": hashed_token, "reset_expiry": expiry})

        reset_link = f"{BASE_URL}/reset-password?token={token}"
        subject = "Password Reset"
        text = f"Click the link to reset your password: {reset_link}"
        html = f'''
        <p>Click the button to reset your password:</p>
        <p><a href="{reset_link}" style="display:inline-block;padding:12px 24px;background:#28a745;color:#fff;text-decoration:none;border-radius:6px;">Reset Password</a></p>
        <p>Expires in 15 min.</p>
        '''
        try:
            send_email(email, subject, text, html)
        except Exception as e:
            print("Email error:", e)
    else:
        time.sleep(0.2)

    return jsonify({"message": "If that email exists, a reset link was sent"}), 200

# ================================================================
# 🔐 RESET PASSWORD
# ================================================================
@app.route("/reset-password", methods=["POST"])
@limiter.limit("5 per minute")
def reset_password():
    data = request.get_json()
    token = data.get("token")
    new_password = data.get("new_password")

    if not token or not new_password:
        return jsonify({"error": "Token and password required"}), 400

    if len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if not any(c.isupper() for c in new_password):
        return jsonify({"error": "Password must contain an uppercase letter"}), 400
    if not any(c.isdigit() for c in new_password):
        return jsonify({"error": "Password must contain a number"}), 400
    if not any(c in "!@#$%^&*()_-+=<>?/" for c in new_password):
        return jsonify({"error": "Password must contain a special character (!@#$%^&*)"}), 400

    user = find_user_by_reset_token(token)
    if not user:
        return jsonify({"error": "Invalid or expired token"}), 400

    if user.reset_expiry and user.reset_expiry < datetime.datetime.utcnow():
        return jsonify({"error": "Token has expired"}), 400

    new_hashed = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    update_user(user.email, {
        "password": new_hashed,
        "reset_token": None,
        "reset_expiry": None
    })

    revoke_all_user_tokens(user.id)

    return jsonify({"message": "Password updated. You have been logged out of all devices."}), 200

# ================================================================
# 🛡️ PROTECTED ROUTE DECORATOR
# ================================================================
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("access_token")
        if not token:
            return jsonify({"error": "Missing access token"}), 401
        try:
            payload = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            request.user_email = payload["sub"]
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return jsonify({"error": "Invalid or expired access token"}), 401
        return f(*args, **kwargs)
    return decorated

@app.route("/protected", methods=["GET"])
@token_required
def protected():
    return jsonify({"message": f"Hello {request.user_email}!"}), 200

# ================================================================
# 🚪 LOGOUT
# ================================================================
@app.route("/logout", methods=["POST"])
def logout():
    raw_refresh_token = request.cookies.get("refresh_token")
    if raw_refresh_token:
        token_record = find_refresh_token_by_raw(raw_refresh_token)
        if token_record:
            revoke_refresh_token(token_record.id)

    resp = make_response(jsonify({"message": "Logged out successfully"}))
    resp.set_cookie("access_token", "", expires=0, httponly=True, secure=COOKIE_SECURE, samesite='Lax')
    resp.set_cookie("refresh_token", "", expires=0, httponly=True, secure=COOKIE_SECURE, samesite='Lax')
    return resp

# ================================================================
# 🚪 LOGOUT ALL
# ================================================================
@app.route("/logout-all", methods=["POST"])
@token_required
def logout_all():
    user = find_user_by_email(request.user_email)
    if user:
        revoke_all_user_tokens(user.id)

    resp = make_response(jsonify({"message": "Logged out of all devices successfully"}))
    resp.set_cookie("access_token", "", expires=0, httponly=True, secure=COOKIE_SECURE, samesite='Lax')
    resp.set_cookie("refresh_token", "", expires=0, httponly=True, secure=COOKIE_SECURE, samesite='Lax')
    return resp

# ================================================================
# 🚀 RUN THE APP
# ================================================================
if __name__ == "__main__":
    app.run(debug=True)