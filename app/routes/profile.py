# app/routes/profile.py – Profile Blueprint
# Renders the user profile page.

from flask import Blueprint,request, render_template



from app.utils.db import find_user_by_email
from app.decorators.auth import token_required

profile_bp = Blueprint('profile', __name__, url_prefix='/')

@profile_bp.route('/profile')
@token_required
def profile():
    """Render the user profile page."""
    user = find_user_by_email(request.user_email)
    return render_template('profile.html', user=user, user_email=request.user_email)