import secrets
import datetime
import time
import threading
from functools import wraps
from flask import Flask, request, jsonify, render_template, redirect, make_response
import bcrypt
import jwt

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import (
    JWT_SECRET, JWT_EXPIRATION, RESET_TOKEN_EXPIRATION, VERIFICATION_EXPIRATION
)
from utils.db import find_user_by_email, create_user, update_user, _read_db
from utils.mail_service import send_email

app = Flask(__name__)
app.config["SECRET_KEY"] = JWT_SECRET

# ---------- Rate Limiter (IP‑based) ----------
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Too many requests. Please slow down."}), 429

# ---------- IP + User combo tracking (in‑memory) ----------
ip_user_attempts = {}          # key: "ip:email", value: list of timestamps
IP_USER_LIMIT = 5              # max attempts
IP_USER_WINDOW = 300           # 5 minutes (in seconds)
IP_USER_LOCK = threading.Lock()

def get_client_ip():
    """Get the real client IP, handling proxies."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

def cleanup_old_attempts():
    """Remove expired entries to keep memory usage low."""
    now = time.time()
    with IP_USER_LOCK:
        for key in list(ip_user_attempts.keys()):
            ip_user_attempts[key] = [ts for ts in ip_user_attempts[key] if now - ts < IP_USER_WINDOW]
            if not ip_user_attempts[key]:
                del ip_user_attempts[key]

def is_ip_user_rate_limited(ip, email):
    """Check if (ip, email) exceeds the allowed attempts."""
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
    """Record a failed attempt for (ip, email)."""
    key = f"{ip}:{email}"
    now = time.time()
    with IP_USER_LOCK:
        if key not in ip_user_attempts:
            ip_user_attempts[key] = []
        ip_user_attempts[key].append(now)
        ip_user_attempts[key] = [ts for ts in ip_user_attempts[key] if now - ts < IP_USER_WINDOW]

def clear_ip_user_attempts(ip, email):
    """Clear failed attempts on successful login."""
    key = f"{ip}:{email}"
    with IP_USER_LOCK:
        if key in ip_user_attempts:
            del ip_user_attempts[key]

# ---------- Helper functions ----------
def generate_jwt(email):
    """Generate a short-lived access token."""
    payload = {"sub": email, "exp": datetime.datetime.utcnow() + JWT_EXPIRATION}
    return jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")

# ================================================================
# HTML PAGES (Protected via Cookie Check)
# ================================================================

def is_authenticated():
    """Check if the user has a valid access token in their cookie."""
    token = request.cookies.get("access_token")
    if not token:
        return False
    try:
        jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        return True
    except:
        return False

@app.route("/dashboard")
def dashboard_page():
    """Protected dashboard HTML page."""
    if not is_authenticated():
        return redirect("/login")
    return render_template("dashboard.html")

@app.route("/profile")
def profile_page():
    """Protected profile HTML page."""
    if not is_authenticated():
        return redirect("/login")
    return render_template("profile.html")

# ---------- HTML Pages ----------
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

# ================================================================
# API Endpoints
# ================================================================

@app.route("/register", methods=["POST"])
@limiter.limit("5 per minute")
def register():
    data = request.get_json()
    email, password = data.get("email"), data.get("password")
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    if find_user_by_email(email):
        return jsonify({"error": "User already exists"}), 409

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = create_user(email, hashed.decode("utf-8"))

    token = secrets.token_urlsafe(32)
    expiry = datetime.datetime.utcnow() + VERIFICATION_EXPIRATION
    update_user(email, {
        "verification_token": token,
        "verification_expiry": expiry.isoformat()
    })

    verify_link = f"http://localhost:5000/verify-email?token={token}"
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

    return jsonify({"message": "User created. Verification email sent."}), 201

@app.route("/verify-email", methods=["GET"])
def verify_email():
    token = request.args.get("token")
    if not token:
        return render_template("verify_error.html", error="Missing token."), 400

    db_data = _read_db()
    user_found = None
    for user in db_data["users"]:
        stored_token = user.get("verification_token")
        expiry_str = user.get("verification_expiry")
        if not stored_token or not expiry_str:
            continue
        expiry = datetime.datetime.fromisoformat(expiry_str)
        if expiry < datetime.datetime.utcnow():
            continue
        if token == stored_token:
            user_found = user
            break

    if not user_found:
        return render_template("verify_error.html", error="Invalid or expired token."), 400

    update_user(user_found["email"], {
        "verified": True,
        "verification_token": None,
        "verification_expiry": None
    })
    return render_template("verify_success.html")

# ================================================================
# CORPORATE-STANDARD LOGIN (ACCESS + REFRESH TOKENS AS HTTPONLY COOKIES)
# ================================================================
@app.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    data = request.get_json()
    email, password = data.get("email"), data.get("password")
    ip = get_client_ip()

    cleanup_old_attempts()

    if is_ip_user_rate_limited(ip, email):
        return jsonify({
            "error": "Too many failed login attempts from this IP for this user. Please wait 5 minutes."
        }), 429

    user = find_user_by_email(email)
    if not user:
        add_ip_user_attempt(ip, email)
        return jsonify({"error": "Invalid credentials"}), 401

    locked_until_str = user.get("locked_until")
    if locked_until_str:
        locked_until = datetime.datetime.fromisoformat(locked_until_str)
        if locked_until > datetime.datetime.utcnow():
            remaining = int((locked_until - datetime.datetime.utcnow()).total_seconds() / 60)
            return jsonify({
                "error": f"Account locked. Try again in {remaining} minute(s)."
            }), 403

    if not bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8")):
        add_ip_user_attempt(ip, email)
        attempts = user.get("failed_login_attempts", 0) + 1
        updates = {"failed_login_attempts": attempts}
        if attempts >= 5:
            locked_until = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
            updates["locked_until"] = locked_until.isoformat()
        update_user(email, updates)
        return jsonify({"error": "Invalid credentials"}), 401

    if not user.get("verified", False):
        return jsonify({"error": "Please verify your email first."}), 403

    # ---- SUCCESS: Reset counters ----
    update_user(email, {
        "failed_login_attempts": 0,
        "locked_until": None
    })
    clear_ip_user_attempts(ip, email)

    # --- GENERATE ACCESS TOKEN (short-lived) ---
    access_token = generate_jwt(email)

    # --- GENERATE REFRESH TOKEN (long-lived, hashed in DB) ---
    raw_refresh_token = secrets.token_urlsafe(32)  # 32 bytes = 43 chars, safe for bcrypt
    hashed_refresh = bcrypt.hashpw(raw_refresh_token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    update_user(email, {"refresh_token_hash": hashed_refresh})

    # --- Set BOTH as HttpOnly cookies ---
    resp = make_response(jsonify({"message": "Login successful"}))
    
    # Access Token cookie (expires same as JWT_EXPIRATION)
    access_max_age = int(JWT_EXPIRATION.total_seconds())
    resp.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite='Lax',
        max_age=access_max_age
    )
    
    # Refresh Token cookie (30 days)
    resp.set_cookie(
        key="refresh_token",
        value=raw_refresh_token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite='Lax',
        max_age=2592000
    )
    
    return resp

# ================================================================
# REFRESH ENDPOINT (WITH ROTATION - CORPORATE STANDARD)
# ================================================================
@app.route("/refresh", methods=["POST"])
def refresh():
    # 1. Read the Refresh Token from the HttpOnly cookie
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "Missing refresh token"}), 401

    # 2. Find the user who owns this refresh token
    db_data = _read_db()
    user_found = None
    for user in db_data["users"]:
        stored_hash = user.get("refresh_token_hash")
        if stored_hash and bcrypt.checkpw(refresh_token.encode("utf-8"), stored_hash.encode("utf-8")):
            user_found = user
            break

    if not user_found:
        return jsonify({"error": "Invalid or expired refresh token"}), 401

    # 3. ROTATE: Invalidate the old refresh token, issue a new one
    new_raw_refresh = secrets.token_urlsafe(32)
    new_hashed_refresh = bcrypt.hashpw(new_raw_refresh.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    new_access_token = generate_jwt(user_found["email"])

    update_user(user_found["email"], {"refresh_token_hash": new_hashed_refresh})

    # 4. Set the new tokens as HttpOnly cookies
    resp = make_response(jsonify({"message": "Tokens refreshed successfully"}))
    
    access_max_age = int(JWT_EXPIRATION.total_seconds())
    resp.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=False,
        samesite='Lax',
        max_age=access_max_age
    )
    
    resp.set_cookie(
        key="refresh_token",
        value=new_raw_refresh,
        httponly=True,
        secure=False,
        samesite='Lax',
        max_age=2592000
    )
    
    return resp

# ================================================================
# FORGOT / RESET PASSWORD
# ================================================================
@app.route("/forgot-password", methods=["POST"])
@limiter.limit("5 per minute")
def forgot_password():
    data = request.get_json()
    email = data.get("email")
    user = find_user_by_email(email)
    if not user:
        return jsonify({"message": "If that email exists, a reset link was sent"}), 200

    token = secrets.token_urlsafe(32)
    hashed_token = bcrypt.hashpw(token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    expiry = datetime.datetime.utcnow() + RESET_TOKEN_EXPIRATION
    update_user(email, {"reset_token": hashed_token, "reset_expiry": expiry.isoformat()})

    reset_link = f"http://localhost:5000/reset-password?token={token}"
    subject = "Password Reset"
    text = f"Click: {reset_link}"
    html = f'''
    <p>Click the button to reset:</p>
    <p><a href="{reset_link}" style="display:inline-block;padding:12px 24px;background:#28a745;color:#fff;text-decoration:none;border-radius:6px;">Reset Password</a></p>
    <p>Expires in 15 min.</p>
    '''
    try:
        send_email(email, subject, text, html)
    except Exception as e:
        print("Email error:", e)
    return jsonify({"message": "If that email exists, a reset link was sent"}), 200

@app.route("/reset-password", methods=["POST"])
@limiter.limit("5 per minute")
def reset_password():
    data = request.get_json()
    token, new_password = data.get("token"), data.get("new_password")
    if not token or not new_password:
        return jsonify({"error": "Token and password required"}), 400

    db_data = _read_db()
    user_found = None
    for user in db_data["users"]:
        stored_hash = user.get("reset_token")
        expiry_str = user.get("reset_expiry")
        if not stored_hash or not expiry_str:
            continue
        expiry = datetime.datetime.fromisoformat(expiry_str)
        if expiry < datetime.datetime.utcnow():
            continue
        if bcrypt.checkpw(token.encode("utf-8"), stored_hash.encode("utf-8")):
            user_found = user
            break

    if not user_found:
        return jsonify({"error": "Invalid or expired token"}), 400

    new_hashed = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    update_user(user_found["email"], {
        "password": new_hashed,
        "reset_token": None,
        "reset_expiry": None
    })
    return jsonify({"message": "Password updated"}), 200

# ================================================================
# PROTECTED ROUTE (READS ACCESS TOKEN FROM HTTPONLY COOKIE)
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
# LOGOUT (REVOKE REFRESH TOKEN + DELETE BOTH COOKIES)
# ================================================================
@app.route("/logout", methods=["POST"])
def logout():
    token = request.cookies.get("access_token")
    email = None
    if token:
        try:
            payload = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            email = payload["sub"]
        except:
            pass
    
    if email:
        update_user(email, {"refresh_token_hash": None})
    
    resp = make_response(jsonify({"message": "Logged out successfully"}))
    resp.set_cookie("access_token", "", expires=0, httponly=True, secure=False, samesite='Lax')
    resp.set_cookie("refresh_token", "", expires=0, httponly=True, secure=False, samesite='Lax')
    
    return resp

# ================================================================
# RUN THE APP
# ================================================================
if __name__ == "__main__":
    app.run(debug=True)