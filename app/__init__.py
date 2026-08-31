# app/__init__.py – Application factory

import os
from flask import Flask, jsonify, session, request, redirect, url_for
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.config import JWT_SECRET, MAX_CONTENT_LENGTH
import jwt

# Create Flask app with explicit template and static folder paths
app = Flask(
    __name__,
    template_folder='../templates',   # go up one level from app/ to root
    static_folder='../static'         # same for static
)
app.config["SECRET_KEY"] = JWT_SECRET
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Ensure required folders exist
os.makedirs('uploads', exist_ok=True)
os.makedirs('images', exist_ok=True)
os.makedirs('results/temp', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)

# ================================================================
# CONTEXT PROCESSOR – Injects user_email for all templates
# ================================================================
@app.context_processor
def inject_user():
    """Inject user_email into all templates for conditional nav display."""
    user_email = None
    
    # First, check if we have it in the session
    if session.get('user_email'):
        user_email = session.get('user_email')
    
    # If not in session, try to extract from the Authorization header
    if not user_email:
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                # Decode the JWT token
                payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
                user_email = payload.get('email')
                # Store in session for future requests
                if user_email:
                    session['user_email'] = user_email
            except:
                pass
    
    return dict(user_email=user_email)

# ================================================================
# TALISMAN – Security headers
# ================================================================
Talisman(
    app,
    force_https=False,  # Set to True in production with HTTPS
    frame_options='DENY',
    x_xss_protection=True,
    x_content_type_options='nosniff',
    content_security_policy={
        'default-src': "'self'",
        'script-src': ["'self'", "https://cdn.jsdelivr.net"],
        'style-src': ["'self'", "'unsafe-inline'"],
        'img-src': ["'self'", "data:", "https://br-super-forest-axp0cd8i.storage.c-4.us-east-2.aws.neon.tech"],
        'connect-src': ["'self'", "https://cdn.jsdelivr.net"],
    }
)

# ================================================================
# LIMITER – Rate limiting
# ================================================================
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Too many requests. Please slow down."}), 429

# ================================================================
# ROOT ROUTE – Redirect to login or dashboard
# ================================================================
@app.route('/')
def index():
    """Redirect to login or dashboard based on session."""
    if session.get('user_id'):
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('auth.login_page'))

# ================================================================
# HEALTH CHECK ENDPOINT
# ================================================================
@app.route('/health')
def health():
    """Health check endpoint for monitoring."""
    return jsonify({"status": "healthy", "message": "Receipt AI is running"})

# ================================================================
# IMPORT AND REGISTER BLUEPRINTS
# ================================================================
from app.routes.auth import auth_bp
from app.routes.receipts import receipts_bp
from app.routes.dashboard import dashboard_bp
from app.routes.images import images_bp
from app.routes.profile import profile_bp
from app.routes.expenditure import expenditure_bp

app.register_blueprint(auth_bp)
app.register_blueprint(receipts_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(images_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(expenditure_bp)

# ================================================================
# ERROR HANDLERS
# ================================================================
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

# ================================================================
# OPTIONAL: Log startup
# ================================================================
print("✅ Connected to Neon PostgreSQL")
print("🚀 Receipt AI Platform initialized")