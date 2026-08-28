# app/routes/dashboard.py – Dashboard & Export Blueprint
# Contains /dashboard and /export routes with pagination, filters, charts, and JSON export.

import datetime
from collections import defaultdict

from flask import (
    Blueprint, request, jsonify, render_template, redirect, url_for, flash
)

from app.utils.db import (
    find_user_by_email,
    get_user_receipts
)
from app.decorators.auth import token_required
from app.services.image_service import generate_presigned_url

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/')

@dashboard_bp.route('/dashboard')
@token_required
def dashboard():
    """Dashboard with filters, pagination, charts, and table."""
    user = find_user_by_email(request.user_email)
    if not user:
        return redirect(url_for('home'))
    user_id = user.id

    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category = request.args.get('category')
    merchant_search = request.args.get('merchant')

    # Pagination parameters
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 25))
    if page < 1:
        page = 1
    if limit < 1:
        limit = 25
    if limit > 100:
        limit = 100

    # Fetch all filtered receipts (we need total count and stats)
    all_filtered = get_user_receipts(
        user_id,
        start_date=start_date,
        end_date=end_date,
        category=category,
        merchant=merchant_search,
        include_deleted=False
    )

    # Summary stats
    total_receipts = len(all_filtered)
    total_spent = sum(r.total for r in all_filtered) if all_filtered else 0
    avg_spent = total_spent / total_receipts if total_receipts else 0
    max_receipt = max(all_filtered, key=lambda x: x.total) if all_filtered else None
    min_receipt = min(all_filtered, key=lambda x: x.total) if all_filtered else None

    # Paginate
    offset = (page - 1) * limit
    paginated = all_filtered[offset:offset + limit]

    # Build records list with presigned URLs for S3 images
    records_list = []
    for r in paginated:
        image_url = None
        if r.s3_key:
            image_url = generate_presigned_url(r.s3_key)
        else:
            image_url = r.image_path
        records_list.append({
            'id': r.id,
            'merchant': r.merchant,
            'date': r.date,
            'time': r.time,
            'total': r.total,
            'category': r.category,
            'comment': r.comment,
            'image_path': image_url,
            'created_at': r.created_at
        })

    total_pages = (total_receipts + limit - 1) // limit if total_receipts > 0 else 1

    # Chart data (from all filtered, not paginated)
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

    # Get unique merchants for filter dropdown
    all_user_receipts = get_user_receipts(user_id, include_deleted=False)
    merchants = sorted(set(r.merchant for r in all_user_receipts if r.merchant))

    # Template data
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
        'selected_merchant': merchant_search or '',
        'start_date': start_date or '',
        'end_date': end_date or '',
        'user_email': request.user_email,
        'page': page,
        'limit': limit,
        'total_pages': total_pages
    }

    # If AJAX request, return JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        json_records = []
        for r in paginated:
            image_url = None
            if r.s3_key:
                image_url = generate_presigned_url(r.s3_key)
            else:
                image_url = r.image_path
            json_records.append({
                'id': r.id,
                'merchant': r.merchant,
                'date': r.date,
                'time': r.time,
                'total': r.total,
                'category': r.category,
                'comment': r.comment,
                'image_path': image_url,
                'created_at': r.created_at
            })
        return jsonify({
            'records': json_records,
            'total_receipts': total_receipts,
            'total_spent': total_spent,
            'avg_spent': avg_spent,
            'max_receipt': max_receipt,
            'min_receipt': min_receipt,
            'page': page,
            'limit': limit,
            'total_pages': total_pages
        })

    return render_template('dashboard.html', **template_data)

@dashboard_bp.route('/export')
@token_required
def export_json():
    """Export filtered data as JSON (same filters as dashboard)."""
    user = find_user_by_email(request.user_email)
    if not user:
        return jsonify({"error": "User not found"}), 401
    user_id = user.id

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category = request.args.get('category')
    merchant_search = request.args.get('merchant')

    records = get_user_receipts(
        user_id,
        start_date=start_date,
        end_date=end_date,
        category=category,
        merchant=merchant_search,
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