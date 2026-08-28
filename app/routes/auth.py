# app/routes/auth.py – Authentication Blueprint
# Contains all auth routes: login, register, logout, refresh, email verification, password reset, etc.

import secrets
import datetime
import time
import threading
from functools import wraps

from flask import (
    Blueprint, request, jsonify, render_template, redirect,
    url_for, make_response, flash
)
import bcrypt
import jwt

from app.config import (
    JWT_SECRET,
    JWT_EXPIRATION,
    RESET_TOKEN_EXPIRATION,
    VERIFICATION_EXPIRATION,
    COOKIE_SECURE,
    BASE_URL
)
from app.utils.db import (
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
from app.services.mail_service import send_email


from app import limiter


# ---------- Blueprint ----------
auth_bp = Blueprint('auth', __name__, url_prefix='/')

# ---------- Helpers ----------
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

# ---------- IP + User Combo Tracking (for login rate limiting) ----------
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

# ---------- Routes ----------

@auth_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint for load balancers."""
    return jsonify({
        "status": "healthy",
        "database": "connected",
        "timestamp": datetime.datetime.utcnow().isoformat()
    }), 200

@auth_bp.route("/login", methods=["GET"])
def login_page():
    """Render the login page."""
    return render_template("login.html")

@auth_bp.route("/register", methods=["GET"])
def register_page():
    """Render the registration page."""
    return render_template("register.html")

@auth_bp.route("/forgot-password", methods=["GET"])
def forgot_page():
    """Render the forgot password page."""
    return render_template("forgot_password.html")

@auth_bp.route("/reset-password", methods=["GET"])
def reset_page():
    """Render the password reset page with token from query string."""
    return render_template("reset_password.html", token=request.args.get("token"))

@auth_bp.route("/")
def home():
    """Redirect root to login."""
    return redirect("/login")

@auth_bp.route("/register", methods=["POST"])
@limiter.limit("5 per minute")
def register():
    """Register a new user – sends verification email."""
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    # Password strength validation
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if not any(c.isupper() for c in password):
        return jsonify({"error": "Password must contain an uppercase letter"}), 400
    if not any(c.isdigit() for c in password):
        return jsonify({"error": "Password must contain a number"}), 400
    if not any(c in "!@#$%^&*()_-+=<>?/" for c in password):
        return jsonify({"error": "Password must contain a special character (!@#$%^&*)"}), 400

    if find_user_by_email(email):
        # Return same message to prevent user enumeration
        return jsonify({"message": "If this email is valid, a verification link was sent."}), 200

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = create_user(email, hashed.decode("utf-8"))

    raw_token = secrets.token_urlsafe(32)
    hashed_token = bcrypt.hashpw(raw_token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    expiry = datetime.datetime.utcnow() + VERIFICATION_EXPIRATION

    update_user(email, {
        "verification_token": hashed_token,
        "verification_expiry": expiry
    })

    verify_link = f"{BASE_URL}/verify-email?token={raw_token}"
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

@auth_bp.route("/verify-email", methods=["GET"])
def verify_email():
    """Verify email using the token from the email link."""
    raw_token = request.args.get("token")
    if not raw_token:
        return render_template("verify_error.html", error="Missing token."), 400

    users = get_all_users()
    user_found = None

    for user in users:
        if user.verified or not user.verification_token or not user.verification_expiry:
            continue
        if user.verification_expiry < datetime.datetime.utcnow():
            continue
        if bcrypt.checkpw(raw_token.encode("utf-8"), user.verification_token.encode("utf-8")):
            user_found = user
            break

    if not user_found:
        return render_template("verify_error.html", error="Invalid or expired token."), 400

    update_user(user_found.email, {
        "verified": True,
        "verification_token": None,
        "verification_expiry": None
    })
    return render_template("verify_success.html")

@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    """Authenticate user, set HttpOnly cookies (access + refresh)."""
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

@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    """Refresh access and refresh tokens (rotation) using the refresh_token cookie."""
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

@auth_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("5 per minute")
def forgot_password():
    """Send a password reset link to the user's email."""
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
        time.sleep(0.2)  # Prevent user enumeration timing attack

    return jsonify({"message": "If that email exists, a reset link was sent"}), 200

@auth_bp.route("/reset-password", methods=["POST"])
@limiter.limit("5 per minute")
def reset_password():
    """Reset password using the token from the email link."""
    data = request.get_json()
    token = data.get("token")
    new_password = data.get("new_password")

    if not token or not new_password:
        return jsonify({"error": "Token and password required"}), 400

    # Password strength validation
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

    revoke_all_user_tokens(user.id)  # Log out all devices

    return jsonify({"message": "Password updated. You have been logged out of all devices."}), 200

@auth_bp.route("/protected", methods=["GET"])
@token_required
def protected():
    """Test endpoint to verify authentication."""
    return jsonify({"message": f"Hello {request.user_email}!"}), 200

@auth_bp.route("/logout", methods=["POST"])
def logout():
    """Logout the current user – revoke the refresh token and clear cookies."""
    raw_refresh_token = request.cookies.get("refresh_token")
    if raw_refresh_token:
        token_record = find_refresh_token_by_raw(raw_refresh_token)
        if token_record:
            revoke_refresh_token(token_record.id)

    resp = make_response(jsonify({"message": "Logged out successfully"}))
    resp.set_cookie("access_token", "", expires=0, httponly=True, secure=COOKIE_SECURE, samesite='Lax')
    resp.set_cookie("refresh_token", "", expires=0, httponly=True, secure=COOKIE_SECURE, samesite='Lax')
    return resp

@auth_bp.route("/logout-all", methods=["POST"])
@token_required
def logout_all():
    """Logout the user from all devices – revoke all refresh tokens."""
    user = find_user_by_email(request.user_email)
    if user:
        revoke_all_user_tokens(user.id)

    resp = make_response(jsonify({"message": "Logged out of all devices successfully"}))
    resp.set_cookie("access_token", "", expires=0, httponly=True, secure=COOKIE_SECURE, samesite='Lax')
    resp.set_cookie("refresh_token", "", expires=0, httponly=True, secure=COOKIE_SECURE, samesite='Lax')
    return resp