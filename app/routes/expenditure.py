from flask import Blueprint, render_template, request, redirect, url_for, make_response, send_file
from app.categories import DEDUCTION_CATEGORIES
from app.utils.db import SessionLocal, Receipt, find_user_by_email
from app.decorators.auth import token_required
from datetime import datetime, timedelta
import csv
from io import StringIO, BytesIO
from weasyprint import HTML

expenditure_bp = Blueprint('expenditure', __name__, url_prefix='/expenditure')

@expenditure_bp.route('/')
@token_required
def expenditure():
    """Show the 1099 deduction tracker table."""
    user = find_user_by_email(request.user_email)
    if not user:
        return redirect(url_for('auth.login'))
    user_id = user.id

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

    # Initialize data structure
    data = {cat: {'week': 0.0, 'month': 0.0, 'ytd': 0.0} for cat in DEDUCTION_CATEGORIES}

    total_week = 0.0
    total_month = 0.0
    total_ytd = 0.0

    today = datetime.today()
    start_of_week = today - timedelta(days=today.weekday())
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


@expenditure_bp.route('/export')
@token_required
def export_csv():
    """Export deduction data as CSV."""
    user = find_user_by_email(request.user_email)
    if not user:
        return redirect(url_for('auth.login'))
    user_id = user.id

    db = SessionLocal()
    try:
        receipts = db.query(Receipt).filter(
            Receipt.user_id == user_id,
            Receipt.deduction_category.isnot(None),
            Receipt.deduction_category != '',
            Receipt.deleted_at.is_(None)
        ).order_by(Receipt.date.desc()).all()
    finally:
        db.close()

    # Build CSV data
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Date', 'Merchant', 'Total', 'Category', 'Deduction Category', 'Comment'])

    for r in receipts:
        cw.writerow([
            r.date or '',
            r.merchant or '',
            f"{float(r.total):.2f}",
            r.category or '',
            r.deduction_category or '',
            r.comment or ''
        ])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=deductions.csv"
    output.headers["Content-type"] = "text/csv"
    return output


@expenditure_bp.route('/pdf')
@token_required
def export_pdf():
    """Export deduction data as PDF."""
    user = find_user_by_email(request.user_email)
    if not user:
        return redirect(url_for('auth.login'))
    user_id = user.id

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

    # Calculate totals
    data = {cat: {'week': 0.0, 'month': 0.0, 'ytd': 0.0} for cat in DEDUCTION_CATEGORIES}
    total_week = total_month = total_ytd = 0.0

    today = datetime.today()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)

    for r in receipts:
        cat = r.deduction_category
        if cat not in data:
            continue
        amt = float(r.total)
        date_str = r.date
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

    # Render HTML template for PDF
    html_content = render_template(
        'expenditure_pdf.html',
        categories=DEDUCTION_CATEGORIES,
        data=data,
        total_week=total_week,
        total_month=total_month,
        total_ytd=total_ytd,
        user_email=request.user_email,
        generated_date=datetime.now().strftime('%Y-%m-%d %H:%M')
    )

    # Generate PDF
    pdf = HTML(string=html_content).write_pdf()

    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name='deductions.pdf'
    )