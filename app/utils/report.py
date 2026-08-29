# app/utils/report.py

import datetime
from collections import defaultdict
from flask import render_template
import weasyprint
import io

from app.utils.db import get_user_receipts

def generate_report_pdf(user_id, month_str, year_str, user_email):
    """
    Generate a PDF report for a given month and year.
    month_str: '2026-08'
    year_str: '2026'
    """
    # Parse month/year
    year = int(year_str)
    month = int(month_str.split('-')[1])  # assumes format "2026-08"

    # Build date range for the month
    start_date = datetime.date(year, month, 1)
    if month == 12:
        end_date = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        end_date = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    # 1. Fetch all receipts for the month
    month_receipts = get_user_receipts(
        user_id,
        start_date=start_str,
        end_date=end_str,
        include_deleted=False
    )

    # 2. Fetch YTD receipts (Jan 1 to end of month)
    ytd_start = datetime.date(year, 1, 1).strftime('%Y-%m-%d')
    ytd_receipts = get_user_receipts(
        user_id,
        start_date=ytd_start,
        end_date=end_str,
        include_deleted=False
    )

    # ---- Aggregations ----

    # Monthly merchant totals
    merchant_totals = defaultdict(float)
    merchant_counts = defaultdict(int)
    for r in month_receipts:
        merchant = r.merchant or 'Unknown'
        merchant_totals[merchant] += r.total
        merchant_counts[merchant] += 1

    # Monthly category totals
    category_totals = defaultdict(float)
    for r in month_receipts:
        cat = r.category or 'OTHER'
        category_totals[cat] += r.total

    # YTD category totals
    ytd_category_totals = defaultdict(float)
    for r in ytd_receipts:
        cat = r.category or 'OTHER'
        ytd_category_totals[cat] += r.total

    # YTD merchant totals (top merchants)
    ytd_merchant_totals = defaultdict(float)
    for r in ytd_receipts:
        merchant = r.merchant or 'Unknown'
        ytd_merchant_totals[merchant] += r.total

    # Sort merchant lists by total descending
    sorted_merchants = sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)
    sorted_ytd_merchants = sorted(ytd_merchant_totals.items(), key=lambda x: x[1], reverse=True)

    # Monthly totals
    month_total = sum(r.total for r in month_receipts)
    month_count = len(month_receipts)
    daily_avg = month_total / month_count if month_count else 0

    # Previous month comparison
    prev_month = (start_date - datetime.timedelta(days=1)).replace(day=1)
    prev_start = prev_month.strftime('%Y-%m-%d')
    prev_end = (start_date - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    prev_receipts = get_user_receipts(
        user_id,
        start_date=prev_start,
        end_date=prev_end,
        include_deleted=False
    )
    prev_total = sum(r.total for r in prev_receipts)
    change = month_total - prev_total
    change_pct = (change / prev_total * 100) if prev_total else 0

    # YTD total
    ytd_total = sum(r.total for r in ytd_receipts)

    # Build context for the template
    context = {
        'user_email': user_email,        
        'generated_date': datetime.datetime.now().strftime('%B %d, %Y'),
        'month_year': start_date.strftime('%B %Y'),
        'month_total': month_total,
        'month_count': month_count,
        'daily_avg': daily_avg,
        'change': change,
        'change_pct': change_pct,
        'merchant_summary': sorted_merchants,   # list of (merchant, total)
        'merchant_counts': merchant_counts,      # dict merchant -> count
        'category_summary': sorted(category_totals.items(), key=lambda x: x[1], reverse=True),
        'ytd_category_summary': sorted(ytd_category_totals.items(), key=lambda x: x[1], reverse=True),
        'ytd_merchant_summary': sorted_ytd_merchants[:10],  # top 10 YTD merchants
        'ytd_total': ytd_total,
        'receipts': month_receipts,               # full list for detailed table
        'prev_total': prev_total,
    }

    # Render HTML template
    html = render_template('report.html', **context)

    # Generate PDF
    pdf_bytes = weasyprint.HTML(string=html).write_pdf()

    return pdf_bytes