# app/routes/receipts.py – Receipt AI Blueprint
# Contains all receipt upload, processing, review, confirmation, and deletion routes.

import os
import time
import threading
import datetime
from io import BytesIO

from flask import (
    Blueprint, request, jsonify, render_template, redirect,
    url_for, flash
)
from werkzeug.utils import secure_filename
from PIL import Image

from app.config import (
    UPLOAD_FOLDER,
    IMAGE_FOLDER,
    ALLOWED_EXTENSIONS,
    USE_S3
)
from app.utils.db import (
    find_user_by_email,
    create_receipt,
    get_user_receipts,
    is_duplicate,
    get_receipt_by_image_path,
    soft_delete_receipt,
    get_receipt_by_id
)
from app.utils.session import (
    generate_token,
    save_temp_data,
    load_temp_data,
    delete_temp_data,
    validate_token,
    normalize_date,
    get_submission_id
)
from app.decorators.auth import token_required
from app.services.ai_service import process_image
from app.services.image_service import (
    compress_image,
    compute_image_hash,
    upload_to_s3,
    delete_from_s3,
    generate_presigned_url
)

# ---------- Blueprint ----------
receipts_bp = Blueprint('receipts', __name__, url_prefix='/')

# ---------- Helper Functions ----------
def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_user_id_from_email(email):
    """Return the user ID for the given email."""
    user = find_user_by_email(email)
    return user.id if user else None

# ---------- Routes ----------

@receipts_bp.route("/upload", methods=["GET"])
@token_required
def upload_page():
    """Render the upload form."""
    return render_template("upload.html", user_email=request.user_email)

@receipts_bp.route("/upload", methods=["POST"])
@token_required
def upload():
    """Handle image upload, compress, start AI processing, and redirect to processing page."""
    print("[DEBUG] POST /upload called")
    user = find_user_by_email(request.user_email)
    if not user:
        print("[ERROR] User not found")
        return jsonify({"error": "User not found"}), 401
    user_id = user.id
    print(f"[DEBUG] User ID: {user_id}")

    if 'image' not in request.files:
        flash('No file part')
        return redirect(url_for('home'))

    file = request.files['image']
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('home'))

    if not allowed_file(file.filename):
        flash('File type not allowed. Use PNG, JPG, JPEG, or GIF.')
        return redirect(url_for('home'))

    filename = secure_filename(file.filename)
    temp_original = os.path.join(UPLOAD_FOLDER, filename)
    file.save(temp_original)

    # Compress image and get bytes
    compressed_bytes = compress_image(temp_original)
    image_hash = compute_image_hash(temp_original)
    if os.path.exists(temp_original):
        os.remove(temp_original)

    token = generate_token()
    print(f"[DEBUG] Generated token: {token}")

    # Save compressed bytes to a temp file for later processing
    compressed_temp = os.path.join(UPLOAD_FOLDER, f"compressed_{token}.jpg")
    with open(compressed_temp, 'wb') as f:
        f.write(compressed_bytes.getvalue())

    temp_data = {
        'token': token,
        'status': 'processing',
        'temp_image_path': compressed_temp,
        'image_name': filename,
        'image_hash': image_hash,
        'user_id': user_id,
        'created_at': datetime.datetime.now().isoformat()
    }
    save_temp_data(token, temp_data)

    # ---------- Background AI Processing ----------
    def process_ai():
        print(f"[DEBUG] Thread started for token {token} at {datetime.datetime.now().isoformat()}")
        try:
            print("[DEBUG] Step 1: Reading compressed image...")
            with open(compressed_temp, 'rb') as f:
                image_bytes = f.read()
            print(f"[DEBUG] Step 2: Image read, bytes: {len(image_bytes)}")

            print("[DEBUG] Step 3: Calling AI service...")
            start = time.time()
            extracted = process_image(image_bytes, filename)
            elapsed = time.time() - start
            print(f"[DEBUG] Step 4: AI returned in {elapsed:.2f}s")
            print(f"[DEBUG] AI extracted: {extracted}")

            merchant = extracted.get('merchant', '')
            date = extracted.get('date', '')
            total = extracted.get('total', 0)
            print(f"[DEBUG] Step 5: Merchant='{merchant}', Date='{date}', Total={total}")

            print("[DEBUG] Step 6: Checking duplicate...")
            try:
                duplicate = is_duplicate(user_id, merchant, date, total, image_hash)
                print(f"[DEBUG] Duplicate check result: {duplicate}")
            except Exception as dup_e:
                print(f"[ERROR] Duplicate check threw exception: {dup_e}")
                import traceback
                traceback.print_exc()
                temp = load_temp_data(token)
                if temp:
                    temp['status'] = 'error'
                    temp['error'] = f"Duplicate check failed: {str(dup_e)}"
                    save_temp_data(token, temp)
                return

            if duplicate:
                print("[DEBUG] DUPLICATE FOUND. Deleting temp file.")
                if os.path.exists(compressed_temp):
                    os.remove(compressed_temp)
                temp = load_temp_data(token)
                if temp:
                    temp['status'] = 'duplicate'
                    save_temp_data(token, temp)
                return

            # NOT duplicate – upload to S3 or local
            print("[DEBUG] NOT DUPLICATE. Uploading to S3...")
            if USE_S3:
                try:
                    # Re‑read compressed bytes for upload
                    with open(compressed_temp, 'rb') as f:
                        upload_bytes = f.read()
                    upload_stream = BytesIO(upload_bytes)
                    s3_key = upload_to_s3(upload_stream, user_id, filename)
                    print(f"[DEBUG] Uploaded to S3 with key: {s3_key}")
                    if os.path.exists(compressed_temp):
                        os.remove(compressed_temp)
                    extracted['s3_key'] = s3_key
                    extracted['image_path'] = None
                except Exception as e:
                    print(f"[ERROR] S3 upload failed: {e}")
                    # Fallback to local storage
                    user_folder = os.path.join(IMAGE_FOLDER, str(user_id))
                    os.makedirs(user_folder, exist_ok=True)
                    base, _ = os.path.splitext(os.path.basename(compressed_temp))
                    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    final_filename = f"{base}_{timestamp}.jpg"
                    final_path = os.path.join(user_folder, final_filename)
                    os.rename(compressed_temp, final_path)
                    final_path = final_path.replace('\\', '/')
                    extracted['image_path'] = final_path
                    extracted['s3_key'] = None
                    print(f"[DEBUG] S3 failed, stored locally: {final_path}")
            else:
                # Fallback to local storage
                user_folder = os.path.join(IMAGE_FOLDER, str(user_id))
                os.makedirs(user_folder, exist_ok=True)
                base, _ = os.path.splitext(os.path.basename(compressed_temp))
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                final_filename = f"{base}_{timestamp}.jpg"
                final_path = os.path.join(user_folder, final_filename)
                os.rename(compressed_temp, final_path)
                final_path = final_path.replace('\\', '/')
                extracted['image_path'] = final_path
                extracted['s3_key'] = None
                print(f"[DEBUG] Stored locally: {final_path}")

            if extracted.get('date'):
                extracted['date'] = normalize_date(extracted['date'])

            temp = load_temp_data(token)
            if temp:
                temp['status'] = 'complete'
                temp['extracted'] = extracted
                if extracted.get('s3_key'):
                    temp['s3_key'] = extracted['s3_key']
                else:
                    temp['image_path'] = extracted['image_path']
                save_temp_data(token, temp)
                print("[DEBUG] Status set to complete")
            else:
                print("[DEBUG] WARNING: Temp data lost!")

        except Exception as e:
            print(f"[ERROR] AI processing thread exception: {e}")
            import traceback
            traceback.print_exc()
            if os.path.exists(compressed_temp):
                os.remove(compressed_temp)
            temp = load_temp_data(token)
            if temp:
                temp['status'] = 'error'
                temp['error'] = str(e)
                save_temp_data(token, temp)

    thread = threading.Thread(target=process_ai)
    thread.daemon = True
    thread.start()
    print("[DEBUG] Thread started, redirecting to processing page")

    return redirect(url_for('receipts.processing', token=token))

@receipts_bp.route('/status/<token>')
def status(token):
    """Return the processing status as JSON for the processing page to poll."""
    temp = load_temp_data(token)
    if not temp:
        return jsonify({'status': 'not_found'})
    status = temp.get('status', 'processing')
    response = {'status': status}
    if status == 'complete':
        response['redirect'] = url_for('receipts.review', token=token)
    elif status == 'duplicate':
        response['redirect'] = url_for('receipts.duplicate', token=token)
    elif status == 'error':
        response['error'] = temp.get('error', 'Unknown error')
    return jsonify(response)

@receipts_bp.route('/review/<token>')
@token_required
def review(token):
    """Show the review form with pre-filled AI data."""
    temp = load_temp_data(token)
    if not temp:
        flash('Session expired. Please upload again.')
        return redirect(url_for('home'))

    if temp.get('user_id') != get_user_id_from_email(request.user_email):
        flash('Unauthorized.')
        return redirect(url_for('home'))

    if temp.get('status') != 'complete':
        flash('AI processing not complete yet.')
        return redirect(url_for('receipts.processing', token=token))

    data = temp.get('extracted', {})
    # Generate presigned URL if S3 key exists
    if data.get('s3_key'):
        data['image_url'] = generate_presigned_url(data['s3_key'])
    else:
        data['image_url'] = data.get('image_path')
    return render_template('review.html', token=token, data=data)

@receipts_bp.route('/processing/<token>')
def processing(token):
    """Show the processing spinner page."""
    return render_template('processing.html', token=token)

@receipts_bp.route('/duplicate/<token>')
@token_required
def duplicate(token):
    """Show the duplicate detected page."""
    temp = load_temp_data(token)
    if not temp:
        flash('Session expired.')
        return redirect(url_for('home'))
    temp_path = temp.get('temp_image_path')
    if temp_path and os.path.exists(temp_path):
        os.remove(temp_path)
    return render_template('duplicate.html', token=token)

@receipts_bp.route('/confirm', methods=['POST'])
@token_required
def confirm():
    """Save the reviewed (and possibly edited) receipt data."""
    print("[DEBUG] ====== /confirm called ======")
    token = request.form.get('token')
    print(f"[DEBUG] Token from form: {token}")

    temp_file = os.path.join('results/temp', f'{token}.json') if token else None
    print(f"[DEBUG] Temp file path: {temp_file}")
    print(f"[DEBUG] Temp file exists? {os.path.exists(temp_file) if temp_file else 'No token'}")

    user = find_user_by_email(request.user_email)
    if not user:
        print("[DEBUG] User not found")
        flash('User not found.')
        return redirect(url_for('home'))
    user_id = user.id
    print(f"[DEBUG] Authenticated user ID: {user_id}")

    if not token or not validate_token(token):
        print(f"[DEBUG] Token validation failed (token: {token})")
        flash('Session expired. Please upload again.')
        return redirect(url_for('home'))

    temp_data = load_temp_data(token)
    print(f"[DEBUG] Temp data loaded: {temp_data}")
    if not temp_data:
        print("[DEBUG] Temp data is None")
        flash('Session data not found.')
        return redirect(url_for('home'))

    stored_user_id = temp_data.get('user_id')
    print(f"[DEBUG] Stored user_id in temp: {stored_user_id}")
    if stored_user_id != user_id:
        print(f"[DEBUG] User ID mismatch: stored={stored_user_id}, current={user_id}")
        flash('Unauthorized.')
        return redirect(url_for('home'))

    print("[DEBUG] Starting form validation...")
    merchant = request.form.get('merchant', '').strip()
    date = request.form.get('date', '').strip()
    time = request.form.get('time', '').strip()
    subtotal_str = request.form.get('subtotal', '').strip()
    tax_str = request.form.get('tax', '').strip()
    total_str = request.form.get('total', '').strip()
    payment_method = request.form.get('payment_method', '').strip()
    category = request.form.get('category', '').strip()
    comment = request.form.get('comment', '').strip()

    extracted = temp_data.get('extracted', {})
    s3_key = temp_data.get('s3_key') or extracted.get('s3_key')
    image_path = temp_data.get('image_path') or extracted.get('image_path')
    image_name = temp_data.get('image_name')
    image_hash = temp_data.get('image_hash')

    print(f"[DEBUG] total_str = '{total_str}'")
    if not total_str:
        print("[DEBUG] total_str is empty – redirecting")
        flash('Total amount is required.')
        return render_template('review.html', token=token, data=extracted)

    print("[DEBUG] Parsing numbers...")
    try:
        subtotal = float(subtotal_str) if subtotal_str else None
        tax = float(tax_str) if tax_str else None
        total = float(total_str)
        print(f"[DEBUG] subtotal={subtotal}, tax={tax}, total={total}")
    except ValueError as e:
        print(f"[DEBUG] Number parsing failed: {e}")
        flash('Amounts must be numeric.')
        return render_template('review.html', token=token, data=extracted)

    print("[DEBUG] Normalizing date...")
    date = normalize_date(date)
    print(f"[DEBUG] date = {date}")

    print("[DEBUG] Checking duplicate...")
    if is_duplicate(user_id, merchant, date, total, image_hash):
        print("[DEBUG] Duplicate found – redirecting")
        flash('⚠️ This receipt appears to be already saved. Duplicate rejected.')
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
        delete_temp_data(token)
        return redirect(url_for('home'))

    print("[DEBUG] Duplicate not found. Building cleaned data...")
    receipt_hash = get_submission_id({'date': date, 'merchant': merchant, 'total': total}, user_id)
    cleaned = {
        'receipt_hash': receipt_hash,
        'image_name': image_name,
        'image_path': image_path,
        's3_key': s3_key,
        'merchant': merchant or None,
        'date': date or None,
        'time': time or None,
        'subtotal': subtotal,
        'tax': tax,
        'total': total,
        'payment_method': payment_method or None,
        'category': category,
        'comment': comment,
        'image_hash': image_hash,
        'raw_description': extracted.get('raw_description', '')
    }

    print("[DEBUG] Creating receipt in database...")
    try:
        create_receipt(user_id, cleaned)
        print("[DEBUG] Receipt created successfully.")
    except ValueError as e:
        print(f"[DEBUG] ValueError in create_receipt: {e}")
        flash(f'Duplicate rejected: {e}')
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
        delete_temp_data(token)
        return redirect(url_for('home'))

    delete_temp_data(token)
    print("[DEBUG] /confirm completed successfully, rendering success page.")
    return render_template('success.html', record=cleaned)

@receipts_bp.route('/receipts/<int:receipt_id>', methods=['DELETE'])
@token_required
def delete_receipt(receipt_id):
    """Soft delete a receipt (and remove the image from S3 if applicable)."""
    user = find_user_by_email(request.user_email)
    if not user:
        return jsonify({"error": "User not found"}), 401
    user_id = user.id

    try:
        # Fetch the receipt to get the S3 key
        receipt = get_receipt_by_id(receipt_id, user_id, include_deleted=False)
        if receipt and receipt.s3_key:
            delete_from_s3(receipt.s3_key)

        deleted = soft_delete_receipt(receipt_id, user_id)
        if not deleted:
            return jsonify({"error": "Receipt not found or already deleted"}), 404
        return jsonify({"message": "Receipt deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500