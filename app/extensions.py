# app/extensions.py
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = None

def init_extensions(app):
    global limiter
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
            'img-src': [
                "'self'",
                "data:",
                "https://br-super-forest-axp0cd8i.storage.c-4.us-east-2.aws.neon.tech"
            ],
            'connect-src': ["'self'", "https://cdn.jsdelivr.net"],
        }
    )
    limiter = Limiter(
        app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"]
    )
    return limiter