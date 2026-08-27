# app.py – Complete Merged Application with Pagination & Soft Delete
# Combines JWT authentication with Receipt AI.
# Uses PostgreSQL (via utils.db) for receipts, utils.session for temp storage.

import os
import json
import secrets
import datetime
import time
import threading
import hashlib
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template, redirect,
    make_response, send_from_directory, flash, url_for
)
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import bcrypt
import jwt
from werkzeug.utils import secure_filename
from PIL import Image

# ---------- Configuration ----------
from config import (
    JWT_SECRET,
    JWT_EXPIRATION,
    RESET_TOKEN_EXPIRATION,
    VERIFICATION_EXPIRATION,
    COOKIE_SECURE,
    BASE_URL,
    UPLOAD_FOLDER,
    IMAGE_FOLDER,
    ALLOWED_EXTENSIONS,
    MAX_CONTENT_LENGTH,
    PORT
)

# ---------- Database and Helpers ----------
from utils.db import (
    find_user_by_email,
    create_user,
    update_user,
    get_all_users,
    find_user_by_reset_token,
    create_refresh_token,
    find_refresh_token_by_raw,
    revoke_refresh_token,
    revoke_all_user_tokens,
    get_user_by_id,
    create_receipt,
    get_user_receipts,
    is_duplicate,
    get_receipt_by_image_path,
    soft_delete_receipt,      # ✅ Fixed: was delete_receipt
    restore_receipt,          # optional
    hard_delete_receipt       # optional
)
from utils.mail_service import send_email

# ---------- Session and Helper Functions ----------
from utils.session import (
    generate_token,
    save_temp_data,
    load_temp_data,
    delete_temp_data,
    validate_token,
    normalize_date,
    get_submission_id,
    cleanup_expired_temp_files
)

# ---------- AI Service ----------
from ai_service import process_image

# ---------- Flask App ----------
app = Flask(__name__)
app.config["SECRET_KEY"] = JWT_SECRET
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Ensure required folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(IMAGE_FOLDER, exist_ok=True)
os.makedirs('results/temp', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)

# ---------- Security Headers (Talisman) ----------
Talisman(
    app,
    force_https=False,
    frame_options='DENY',
    x_xss_protection=True,
    x_content_type_options='nosniff',
    content_security_policy={
        'default-src': "'self'",
        'script-src': ["'self'", "https://cdn.jsdelivr.net"],
        'style-src': ["'self'", "'unsafe-inline'"],   # <-- allow inline styles (needed for Chart.js)
        'img-src': ["'self'", "data:"],
        'connect-src': ["'self'", "https://cdn.jsdelivr.net"],
    }
)
# ---------- Rate Limiter ----------
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Too many requests. Please slow down."}), 429

# ---------- IP + User Combo Tracking (in-memory) ----------
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

# ---------- JWT Helper ----------
def generate_jwt(email):
    payload = {"sub": email, "exp": datetime.datetime.utcnow() + JWT_EXPIRATION}
    return jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")

# ---------- Authentication Decorator ----------
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

# ---------- Helpers for Receipt Routes ----------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def compress_image(filepath, output_folder=None, max_size=(1200, 1200), quality=85):
    if output_folder is None:
        output_folder = UPLOAD_FOLDER
    os.makedirs(output_folder, exist_ok=True)
    try:
        img = Image.open(filepath)
        img.thumbnail(max_size)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        base, _ = os.path.splitext(os.path.basename(filepath))
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        new_filename = f"{base}_{timestamp}.jpg"
        new_path = os.path.join(output_folder, new_filename)
        img.save(new_path, 'JPEG', quality=quality, optimize=True)
        return new_path
    except Exception as e:
        print(f"[DEBUG] Compression fallback: {e}")
        base, ext = os.path.splitext(os.path.basename(filepath))
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        new_filename = f"{base}_{timestamp}{ext}"
        new_path = os.path.join(output_folder, new_filename)
        with open(filepath, 'rb') as src, open(new_path, 'wb') as dst:
            dst.write(src.read())
        return new_path

def compute_image_hash(filepath):
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def get_user_id_from_email(email):
    user = find_user_by_email(email)
    return user.id if user else None

# ---------- AUTH ROUTES ----------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "database": "connected",
        "timestamp": datetime.datetime.utcnow().isoformat()
    }), 200

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

@app.route("/")
def home():
    return redirect("/login")

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

@app.route("/verify-email", methods=["GET"])
def verify_email():
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

@app.route("/protected", methods=["GET"])
@token_required
def protected():
    return jsonify({"message": f"Hello {request.user_email}!"}), 200

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

# ---------- PROFILE ROUTE ----------
@app.route("/profile")
@token_required
def profile():
    user = find_user_by_email(request.user_email)
    return render_template("profile.html", user=user, user_email=request.user_email)

# ---------- RECEIPT DELETION (SOFT DELETE) ----------
@app.route('/receipts/<int:receipt_id>', methods=['DELETE'])
@token_required
def delete_receipt(receipt_id):
    user = find_user_by_email(request.user_email)
    if not user:
        return jsonify({"error": "User not found"}), 401
    user_id = user.id

    try:
        deleted = soft_delete_receipt(receipt_id, user_id)
        if not deleted:
            return jsonify({"error": "Receipt not found or already deleted"}), 404
        return jsonify({"message": "Receipt deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------- RECEIPT AI ROUTES ----------

# GET /upload – Display upload form
@app.route("/upload", methods=["GET"])
@token_required
def upload_page():
    return render_template("upload.html", user_email=request.user_email)

# POST /upload – Process uploaded image
@app.route("/upload", methods=["POST"])
@token_required
def upload():
    print("[DEBUG] POST /upload called")
    user = find_user_by_email(request.user_email)
    if not user:
        print("[ERROR] User not found")
        return jsonify({"error": "User not found"}), 401
    user_id = user.id
    print(f"[DEBUG] User ID: {user_id}")

    if 'image' not in request.files:
        flash('No file part')
        return redirect(url_for('home'))

    file = request.files['image']
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('home'))

    if not allowed_file(file.filename):
        flash('File type not allowed. Use PNG, JPG, JPEG, or GIF.')
        return redirect(url_for('home'))

    filename = secure_filename(file.filename)
    temp_original = os.path.join(UPLOAD_FOLDER, filename)
    file.save(temp_original)
    print(f"[DEBUG] Original saved: {temp_original}")

    compressed_temp = compress_image(temp_original, output_folder=UPLOAD_FOLDER)
    if os.path.exists(temp_original):
        os.remove(temp_original)
    print(f"[DEBUG] Compressed temp: {compressed_temp}")

    image_hash = compute_image_hash(compressed_temp)
    print(f"[DEBUG] Image hash: {image_hash}")

    token = generate_token()
    print(f"[DEBUG] Generated token: {token}")

    temp_data = {
        'token': token,
        'status': 'processing',
        'temp_image_path': compressed_temp,
        'image_name': filename,
        'image_hash': image_hash,
        'user_id': user_id,
        'created_at': datetime.datetime.now().isoformat()
    }
    save_temp_data(token, temp_data)
    print(f"[DEBUG] Temp file saved: results/temp/{token}.json")
    print(f"[DEBUG] File exists? {os.path.exists(os.path.join('results/temp', token + '.json'))}")

    # ---------- Background AI Processing ----------
    def process_ai():
        print(f"[DEBUG] Thread started for token {token} at {datetime.datetime.now().isoformat()}")
        try:
            print("[DEBUG] Step 1: Reading compressed image...")
            with open(compressed_temp, 'rb') as f:
                image_bytes = f.read()
            print(f"[DEBUG] Step 2: Image read, bytes: {len(image_bytes)}")

            print("[DEBUG] Step 3: Calling AI service...")
            start = time.time()
            extracted = process_image(image_bytes, filename)
            elapsed = time.time() - start
            print(f"[DEBUG] Step 4: AI returned in {elapsed:.2f}s")
            print(f"[DEBUG] AI extracted: {extracted}")

            extracted['image_path'] = None

            if extracted.get('date'):
                extracted['date'] = normalize_date(extracted['date'])
                print(f"[DEBUG] Normalized date: {extracted['date']}")

            merchant = extracted.get('merchant', '')
            date = extracted.get('date', '')
            total = extracted.get('total', 0)
            print(f"[DEBUG] Step 5: Merchant='{merchant}', Date='{date}', Total={total}")

            print("[DEBUG] Step 6: Checking duplicate...")
            try:
                duplicate = is_duplicate(user_id, merchant, date, total, image_hash)
                print(f"[DEBUG] Duplicate check result: {duplicate}")
            except Exception as dup_e:
                print(f"[ERROR] Duplicate check threw exception: {dup_e}")
                import traceback
                traceback.print_exc()
                temp = load_temp_data(token)
                if temp:
                    temp['status'] = 'error'
                    temp['error'] = f"Duplicate check failed: {str(dup_e)}"
                    save_temp_data(token, temp)
                return

            if duplicate:
                print("[DEBUG] DUPLICATE FOUND. Deleting temp file.")
                if os.path.exists(compressed_temp):
                    os.remove(compressed_temp)
                    print("[DEBUG] Temp file deleted.")
                temp = load_temp_data(token)
                if temp:
                    temp['status'] = 'duplicate'
                    save_temp_data(token, temp)
                    print("[DEBUG] Status set to duplicate")
                return

            print("[DEBUG] NOT DUPLICATE. Moving to permanent storage.")
            user_folder = os.path.join(IMAGE_FOLDER, str(user_id))
            os.makedirs(user_folder, exist_ok=True)
            base, _ = os.path.splitext(os.path.basename(compressed_temp))
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            final_filename = f"{base}_{timestamp}.jpg"
            final_path = os.path.join(user_folder, final_filename)
            print(f"[DEBUG] Moving to {final_path}")
            os.rename(compressed_temp, final_path)

            # ---- FIX: Normalize path to forward slashes ----
            final_path = final_path.replace('\\', '/')
            print(f"[DEBUG] Normalized path: {final_path}")

            print("[DEBUG] File moved.")
            extracted['image_path'] = final_path

            temp = load_temp_data(token)
            if temp:
                temp['status'] = 'complete'
                temp['extracted'] = extracted
                temp['image_path'] = final_path
                save_temp_data(token, temp)
                print("[DEBUG] Status set to complete")
            else:
                print("[DEBUG] WARNING: Temp data lost!")

        except Exception as e:
            print(f"[ERROR] AI processing thread exception: {e}")
            import traceback
            traceback.print_exc()
            if os.path.exists(compressed_temp):
                os.remove(compressed_temp)
                print("[DEBUG] Temp file deleted due to error.")
            temp = load_temp_data(token)
            if temp:
                temp['status'] = 'error'
                temp['error'] = str(e)
                save_temp_data(token, temp)
                print("[DEBUG] Status set to error")
            else:
                print("[DEBUG] Could not set error status: temp missing")

    thread = threading.Thread(target=process_ai)
    thread.daemon = True
    thread.start()
    print("[DEBUG] Thread started, redirecting to processing page")

    # FIX: Redirect to processing page so browser actually shows it
    return redirect(url_for('processing', token=token))

@app.route('/status/<token>')
def status(token):
    temp = load_temp_data(token)
    if not temp:
        return jsonify({'status': 'not_found'})
    status = temp.get('status', 'processing')
    response = {'status': status}
    if status == 'complete':
        response['redirect'] = url_for('review', token=token)
    elif status == 'duplicate':
        response['redirect'] = url_for('duplicate', token=token)
    elif status == 'error':
        response['error'] = temp.get('error', 'Unknown error')
    return jsonify(response)

@app.route('/review/<token>')
@token_required
def review(token):
    temp = load_temp_data(token)
    if not temp:
        flash('Session expired. Please upload again.')
        return redirect(url_for('home'))

    if temp.get('user_id') != get_user_id_from_email(request.user_email):
        flash('Unauthorized.')
        return redirect(url_for('home'))

    if temp.get('status') != 'complete':
        flash('AI processing not complete yet.')
        return redirect(url_for('processing', token=token))

    data = temp.get('extracted', {})
    return render_template('review.html', token=token, data=data)

@app.route('/processing/<token>')
def processing(token):
    return render_template('processing.html', token=token)

@app.route('/duplicate/<token>')
@token_required
def duplicate(token):
    temp = load_temp_data(token)
    if not temp:
        flash('Session expired.')
        return redirect(url_for('home'))
    temp_path = temp.get('temp_image_path')
    if temp_path and os.path.exists(temp_path):
        os.remove(temp_path)
    return render_template('duplicate.html', token=token)

@app.route('/confirm', methods=['POST'])
@token_required
def confirm():
    print("[DEBUG] ====== /confirm called ======")
    token = request.form.get('token')
    print(f"[DEBUG] Token from form: {token}")

    temp_file = os.path.join('results/temp', f'{token}.json') if token else None
    print(f"[DEBUG] Temp file path: {temp_file}")
    print(f"[DEBUG] Temp file exists? {os.path.exists(temp_file) if temp_file else 'No token'}")

    user = find_user_by_email(request.user_email)
    if not user:
        print("[DEBUG] User not found")
        flash('User not found.')
        return redirect(url_for('home'))
    user_id = user.id
    print(f"[DEBUG] Authenticated user ID: {user_id}")

    if not token or not validate_token(token):
        print(f"[DEBUG] Token validation failed (token: {token})")
        flash('Session expired. Please upload again.')
        return redirect(url_for('home'))

    temp_data = load_temp_data(token)
    print(f"[DEBUG] Temp data loaded: {temp_data}")
    if not temp_data:
        print("[DEBUG] Temp data is None")
        flash('Session data not found.')
        return redirect(url_for('home'))

    stored_user_id = temp_data.get('user_id')
    print(f"[DEBUG] Stored user_id in temp: {stored_user_id}")
    if stored_user_id != user_id:
        print(f"[DEBUG] User ID mismatch: stored={stored_user_id}, current={user_id}")
        flash('Unauthorized.')
        return redirect(url_for('home'))

    print("[DEBUG] Starting form validation...")
    merchant = request.form.get('merchant', '').strip()
    date = request.form.get('date', '').strip()
    time = request.form.get('time', '').strip()
    subtotal_str = request.form.get('subtotal', '').strip()
    tax_str = request.form.get('tax', '').strip()
    total_str = request.form.get('total', '').strip()
    payment_method = request.form.get('payment_method', '').strip()
    category = request.form.get('category', '').strip()
    comment = request.form.get('comment', '').strip()
    image_path = temp_data.get('image_path')
    image_name = temp_data.get('image_name')
    image_hash = temp_data.get('image_hash')
    extracted = temp_data.get('extracted', {})

    print(f"[DEBUG] total_str = '{total_str}'")
    if not total_str:
        print("[DEBUG] total_str is empty – redirecting")
        flash('Total amount is required.')
        return render_template('review.html', token=token, data=extracted)

    print("[DEBUG] Parsing numbers...")
    try:
        subtotal = float(subtotal_str) if subtotal_str else None
        tax = float(tax_str) if tax_str else None
        total = float(total_str)
        print(f"[DEBUG] subtotal={subtotal}, tax={tax}, total={total}")
    except ValueError as e:
        print(f"[DEBUG] Number parsing failed: {e}")
        flash('Amounts must be numeric.')
        return render_template('review.html', token=token, data=extracted)

    print("[DEBUG] Normalizing date...")
    date = normalize_date(date)
    print(f"[DEBUG] date = {date}")

    print("[DEBUG] Checking duplicate...")
    if is_duplicate(user_id, merchant, date, total, image_hash):
        print("[DEBUG] Duplicate found – redirecting")
        flash('⚠️ This receipt appears to be already saved. Duplicate rejected.')
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
        delete_temp_data(token)
        return redirect(url_for('home'))

    print("[DEBUG] Duplicate not found. Building cleaned data...")
    submission_id = get_submission_id({'date': date, 'merchant': merchant, 'total': total})
    cleaned = {
        'submission_id': submission_id,
        'image_name': image_name,
        'image_path': image_path,
        'merchant': merchant or None,
        'date': date or None,
        'time': time or None,
        'subtotal': subtotal,
        'tax': tax,
        'total': total,
        'payment_method': payment_method or None,
        'category': category,
        'comment': comment,
        'image_hash': image_hash,
        'raw_description': extracted.get('raw_description', '')
    }

    print("[DEBUG] Creating receipt in database...")
    try:
        create_receipt(user_id, cleaned)
        print("[DEBUG] Receipt created successfully.")
    except ValueError as e:
        print(f"[DEBUG] ValueError in create_receipt: {e}")
        flash(f'Duplicate rejected: {e}')
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
        delete_temp_data(token)
        return redirect(url_for('home'))

    delete_temp_data(token)
    print("[DEBUG] /confirm completed successfully, rendering success page.")
    return render_template('success.html', record=cleaned)

# ---------- DASHBOARD (with Pagination & JSON support) ----------
@app.route('/dashboard')
@token_required
def dashboard():
    user = find_user_by_email(request.user_email)
    if not user:
        return redirect(url_for('home'))
    user_id = user.id

    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category = request.args.get('category')
    merchant = request.args.get('merchant')

    # Get pagination parameters
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 25))
    if page < 1:
        page = 1
    if limit < 1:
        limit = 25
    if limit > 100:
        limit = 100  # max page size

    # Fetch all filtered receipts (we need total count and stats)
    all_filtered = get_user_receipts(
        user_id,
        start_date=start_date,
        end_date=end_date,
        category=category,
        merchant=merchant,
        include_deleted=False  # exclude soft-deleted
    )

    # Compute summary stats from all filtered (not paginated)
    total_receipts = len(all_filtered)
    total_spent = sum(r.total for r in all_filtered) if all_filtered else 0
    avg_spent = total_spent / total_receipts if total_receipts else 0
    max_receipt = max(all_filtered, key=lambda x: x.total) if all_filtered else None
    min_receipt = min(all_filtered, key=lambda x: x.total) if all_filtered else None

    # Paginate the list
    offset = (page - 1) * limit
    paginated = all_filtered[offset:offset + limit]

    # Convert to dicts for template/JSON
    records_list = []
    for r in paginated:
        records_list.append({
            'id': r.id,
            'merchant': r.merchant,
            'date': r.date,
            'time': r.time,
            'total': r.total,
            'category': r.category,
            'comment': r.comment,
            'image_path': r.image_path,
            'created_at': r.created_at
        })

    total_pages = (total_receipts + limit - 1) // limit if total_receipts > 0 else 1

    # Chart data (from all filtered, not paginated)
    from collections import defaultdict
    cat_totals = defaultdict(float)
    for r in all_filtered:
        cat = r.category or 'OTHER'
        cat_totals[cat] += r.total

    weekly = defaultdict(float)
    for r in all_filtered:
        if r.date:
            try:
                dt = datetime.datetime.strptime(r.date, '%Y-%m-%d')
                week_start = dt - datetime.timedelta(days=dt.weekday())
                key = week_start.strftime('%Y-%m-%d')
                weekly[key] += r.total
            except:
                pass
    sorted_weekly = sorted(weekly.items())
    dates = [item[0] for item in sorted_weekly]
    weekly_totals = [item[1] for item in sorted_weekly]

    chart_data = {
        'categories': list(cat_totals.keys()),
        'cat_values': [cat_totals[c] for c in cat_totals],
        'dates': dates,
        'weekly_totals': weekly_totals
    }

    # Get unique merchants for filter dropdown (from all receipts, excluding deleted)
    all_user_receipts = get_user_receipts(user_id, include_deleted=False)
    merchants = sorted(set(r.merchant for r in all_user_receipts if r.merchant))

    # Prepare template/response data
    template_data = {
        'records': records_list,
        'chart_data_json': chart_data,
        'total_receipts': total_receipts,
        'total_spent': total_spent,
        'avg_spent': avg_spent,
        'max_receipt': max_receipt,
        'min_receipt': min_receipt,
        'merchants': merchants,
        'selected_category': category or 'ALL',
        'selected_merchant': merchant or '',
        'start_date': start_date or '',
        'end_date': end_date or '',
        'user_email': request.user_email,
        'page': page,
        'limit': limit,
        'total_pages': total_pages
    }

    # If AJAX request (X-Requested-With header), return JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'records': records_list,
            'total_receipts': total_receipts,
            'total_spent': total_spent,
            'avg_spent': avg_spent,
            'max_receipt': max_receipt,
            'min_receipt': min_receipt,
            'page': page,
            'limit': limit,
            'total_pages': total_pages
        })

    # Otherwise render HTML
    return render_template('dashboard.html', **template_data)

@app.route('/export')
@token_required
def export_json():
    user = find_user_by_email(request.user_email)
    if not user:
        return jsonify({"error": "User not found"}), 401
    user_id = user.id

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category = request.args.get('category')
    merchant = request.args.get('merchant')

    # Exclude soft-deleted receipts
    records = get_user_receipts(
        user_id,
        start_date=start_date,
        end_date=end_date,
        category=category,
        merchant=merchant,
        include_deleted=False
    )

    data = [{
        'id': r.id,
        'merchant': r.merchant,
        'date': r.date,
        'time': r.time,
        'subtotal': r.subtotal,
        'tax': r.tax,
        'total': r.total,
        'payment_method': r.payment_method,
        'category': r.category,
        'comment': r.comment,
        'created_at': r.created_at.isoformat() if r.created_at else None
    } for r in records]

    return jsonify(data)

@app.route('/images/<path:filename>')
@token_required
def serve_image(filename):
    user = find_user_by_email(request.user_email)
    if not user:
        return "Forbidden", 403
    user_id = user.id

    full_path = os.path.join(IMAGE_FOLDER, filename).replace('\\', '/')
    receipt = get_receipt_by_image_path(full_path, user_id)
    if not receipt:
        return "Forbidden", 403

    return send_from_directory(IMAGE_FOLDER, filename)

# ---------- Main ----------
if __name__ == "__main__":
    cleanup_expired_temp_files()
    app.run(debug=False, host='0.0.0.0', port=PORT)