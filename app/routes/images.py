# app/routes/images.py – Image Serving Blueprint
# Serves local images (fallback) – S3 images are served via presigned URLs.

import os

from flask import Blueprint, request, send_from_directory

from app.config import IMAGE_FOLDER
from app.utils.db import find_user_by_email, get_receipt_by_image_path
from app.decorators.auth import token_required

images_bp = Blueprint('images', __name__, url_prefix='/')

@images_bp.route('/images/<path:filename>')
@token_required
def serve_image(filename):
    """Serve a local receipt image (fallback for S3 failures)."""
    user = find_user_by_email(request.user_email)
    if not user:
        return "Forbidden", 403
    user_id = user.id

    full_path = os.path.join(IMAGE_FOLDER, filename).replace('\\', '/')
    receipt = get_receipt_by_image_path(full_path, user_id)
    if not receipt:
        return "Forbidden", 403

    return send_from_directory(IMAGE_FOLDER, filename)