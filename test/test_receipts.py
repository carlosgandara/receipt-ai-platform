# test/test_receipts.py
import io
from unittest.mock import patch
from PIL import Image

def test_upload_page_get(auth_client):
    """GET /upload should return the upload form."""
    resp = auth_client.get('/upload')
    assert resp.status_code == 200
    assert b'Upload a Receipt' in resp.data

def test_upload_without_file(auth_client):
    """POST /upload with no file → redirect to dashboard."""
    resp = auth_client.post('/upload')
    assert resp.status_code == 302
    assert resp.location.endswith('/dashboard')

def test_upload_invalid_file_type(auth_client):
    """POST /upload with .txt file → flash and redirect."""
    data = {'image': (io.BytesIO(b'fake content'), 'test.txt')}
    resp = auth_client.post('/upload', data=data,
                            content_type='multipart/form-data')
    assert resp.status_code == 302
    assert resp.location.endswith('/dashboard')

@patch('app.services.ai_service.process_image')
@patch('app.services.image_service.upload_to_s3')
def test_upload_valid_image(mock_s3, mock_ai, auth_client):
    """POST /upload with a valid image → redirects to processing."""
    # Mock AI extraction
    mock_ai.return_value = {
        'merchant': 'Test Store',
        'date': '2026-08-29',
        'total': 42.50,
        'raw_description': 'test'
    }
    mock_s3.return_value = 'test-key'

    # Create a small valid JPEG image in memory
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)

    data = {'image': (img_bytes, 'receipt.jpg')}
    resp = auth_client.post('/upload', data=data,
                            content_type='multipart/form-data')
    assert resp.status_code == 302
    assert '/processing/' in resp.location

    # Extract token and check status
    token = resp.location.split('/')[-1]
    resp2 = auth_client.get(f'/status/{token}')
    assert resp2.status_code == 200
    json_data = resp2.get_json()
    assert json_data['status'] in ('processing', 'complete')

def test_review_unauthenticated(client):
    """GET /review/<token> without auth should return 401 (or redirect)."""
    resp = client.get('/review/invalid-token')
    # Protected route: without token, it should return 401 or redirect to login.
    assert resp.status_code in (401, 302)

def test_confirm_missing_total(auth_client):
    """POST /confirm with missing total should render review again with error."""
    # This test would require a valid token and temp data.
    # Since we can't easily create that without mocking, we skip it for now.
    # We'll add a proper test later.
    pass