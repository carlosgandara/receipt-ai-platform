# utils.py – Keeps session/temp and helper functions only
# JSON DB functions have been moved to db.py

import os
import json
import uuid
import hashlib
import re
from datetime import datetime, timedelta
import portalocker

# ---------- Constants ----------
TEMP_FOLDER = 'results/temp'

# Ensure temp folder exists at module load
os.makedirs(TEMP_FOLDER, exist_ok=True)

# ================================================================
# SESSION / TEMP DATA FUNCTIONS
# ================================================================

def generate_token():
    return str(uuid.uuid4())

def save_temp_data(token, data):
    """Store extracted data in a temp JSON file with expiry (30 min)."""
    os.makedirs(TEMP_FOLDER, exist_ok=True)
    data['expires_at'] = (datetime.now() + timedelta(minutes=30)).isoformat()
    path = os.path.join(TEMP_FOLDER, f'{token}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_temp_data(token):
    path = os.path.join(TEMP_FOLDER, f'{token}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    expiry = datetime.fromisoformat(data['expires_at'])
    if datetime.now() > expiry:
        os.remove(path)
        return None
    return data

def delete_temp_data(token):
    path = os.path.join(TEMP_FOLDER, f'{token}.json')
    if os.path.exists(path):
        os.remove(path)

def validate_token(token):
    return load_temp_data(token) is not None

# ================================================================
# DATE NORMALIZATION
# ================================================================

def normalize_date(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    formats = [
        '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y',
        '%b %d, %Y', '%B %d, %Y', '%d-%b-%Y',
        '%Y/%m/%d', '%m-%d-%Y', '%d.%m.%Y',
        '%b. %d, %Y', '%d %b %Y'
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return date_str

# ================================================================
# SUBMISSION ID GENERATOR
# ================================================================

def get_submission_id(record):
    date = record.get('date', '')
    merchant = record.get('merchant', '')
    total = record.get('total', '')
    raw = f"{date}_{merchant}_{total}".lower().strip()
    return hashlib.md5(raw.encode('utf-8')).hexdigest()

# ================================================================
# CLEANUP (Optional)
# ================================================================

def cleanup_expired_temp_files():
    now = datetime.now()
    for fname in os.listdir(TEMP_FOLDER):
        if fname.endswith('.json'):
            path = os.path.join(TEMP_FOLDER, fname)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                expiry = datetime.fromisoformat(data.get('expires_at', now.isoformat()))
                if now > expiry:
                    os.remove(path)
            except (json.JSONDecodeError, KeyError, OSError):
                os.remove(path)