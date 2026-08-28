# app/__init__.py – Application factory

import os
from flask import Flask, jsonify
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.config import JWT_SECRET, MAX_CONTENT_LENGTH

# Create Flask app with explicit template and static folder paths
app = Flask(
    __name__,
    template_folder='../templates',   # go up one level from app/ to root
    static_folder='../static'         # same for static
)
app.config["SECRET_KEY"] = JWT_SECRET
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Ensure required folders exist
os.makedirs('uploads', exist_ok=True)
os.makedirs('images', exist_ok=True)
os.makedirs('results/temp', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)

# Talisman
Talisman(
    app,
    force_https=False,
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

# Limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Too many requests. Please slow down."}), 429

# Import and register blueprints
from app.routes.auth import auth_bp
from app.routes.receipts import receipts_bp
from app.routes.dashboard import dashboard_bp
from app.routes.images import images_bp
from app.routes.profile import profile_bp

app.register_blueprint(auth_bp)
app.register_blueprint(receipts_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(images_bp)
app.register_blueprint(profile_bp)