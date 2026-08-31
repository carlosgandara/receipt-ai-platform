# app/services/image_service.py
import os
import hashlib
import boto3
from botocore.exceptions import ClientError
from PIL import Image
import datetime
from app.config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    S3_BUCKET_NAME,
    AWS_ENDPOINT_URL_S3
)

# Initialize S3 client with Neon endpoint
s3_client = boto3.client(
    's3',
    endpoint_url=AWS_ENDPOINT_URL_S3,      # critical for Neon
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

def compress_image(filepath, max_size=(1200, 1200), quality=85):
    try:
        img = Image.open(filepath)
        img.thumbnail(max_size)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        import io
        img_bytes = io.BytesIO()
        img.save(img_bytes, 'JPEG', quality=quality, optimize=True)
        img_bytes.seek(0)
        return img_bytes
    except Exception as e:
        print(f"[ERROR] Compression failed: {e}")
        raise

def compute_image_hash(filepath):
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def upload_to_s3(file_bytes, user_id, filename, content_type='image/jpeg'):
    """Upload compressed image to S3 and return only the object key."""
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    object_key = f"user_{user_id}/{timestamp}_{filename}"
    try:
        s3_client.upload_fileobj(
            file_bytes,
            S3_BUCKET_NAME,
            object_key,
            ExtraArgs={'ContentType': content_type}  # no ACL – not supported
        )
        # Return only the object key (no public URL)
        return object_key
    except ClientError as e:
        print(f"[ERROR] S3 upload failed: {e}")
        raise

def delete_from_s3(object_key):
    try:
        s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=object_key)
        return True
    except ClientError as e:
        print(f"[ERROR] S3 delete failed: {e}")
        return False

def generate_presigned_url(object_key, expires_in=3600):
    try:
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET_NAME, 'Key': object_key},
            ExpiresIn=expires_in
        )
        return response
    except ClientError as e:
        print(f"[ERROR] Presigned URL generation failed: {e}")
        return None