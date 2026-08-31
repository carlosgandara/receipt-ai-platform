from flask import Blueprint, render_template, request, redirect, url_for
from app.categories import DEDUCTION_CATEGORIES
from app.utils.db import SessionLocal, Receipt, find_user_by_email
from app.decorators.auth import token_required
from datetime import datetime, timedelta

expenditure_bp = Blueprint('expenditure', __name__, url_prefix='/expenditure')

@expenditure_bp.route('/')
@token_required
def expenditure():
    # Get the user from the email provided by the token
    user = find_user_by_email(request.user_email)
    if not user:
        return redirect(url_for('auth.login'))
    
    user_id = user.id

    # Use SQLAlchemy session
    db = SessionLocal()
    try:
        receipts = db.query(Receipt).filter(
            Receipt.user_id == user_id,
            Receipt.deduction_category.isnot(None),
            Receipt.deduction_category != '',
            Receipt.deleted_at.is_(None)
        ).all()
    finally:
        db.close()

    # Initialize data structure for all categories
    data = {cat: {'week': 0.0, 'month': 0.0, 'ytd': 0.0} for cat in DEDUCTION_CATEGORIES}

    total_week = 0.0
    total_month = 0.0
    total_ytd = 0.0

    today = datetime.today()
    start_of_week = today - timedelta(days=today.weekday())   # Monday
    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)

    for receipt in receipts:
        cat = receipt.deduction_category
        if cat not in data:
            continue

        amt = float(receipt.total)
        date_str = receipt.date
        if not date_str:
            continue

        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            continue

        if date_obj >= start_of_year:
            data[cat]['ytd'] += amt
            total_ytd += amt

        if date_obj >= start_of_month:
            data[cat]['month'] += amt
            total_month += amt

        if date_obj >= start_of_week:
            data[cat]['week'] += amt
            total_week += amt

    return render_template(
        'expenditure.html',
        categories=DEDUCTION_CATEGORIES,
        data=data,
        total_week=total_week,
        total_month=total_month,
        total_ytd=total_ytd
    )