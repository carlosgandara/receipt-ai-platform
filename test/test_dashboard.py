# test/test_dashboard.py

import io
import uuid
import json
from unittest.mock import patch

import pytest
import bcrypt

from app.utils.db import create_user, update_user, create_receipt, find_user_by_email


# ------------------------------------------------------------------
# Helper fixture: authenticated client with a user ID
# ------------------------------------------------------------------
@pytest.fixture
def auth_client_with_user(client, db_session):
    """
    Create a verified user, log in, and return (client, user_id, email).
    """
    unique_id = uuid.uuid4().hex[:8]
    email = f"dashuser_{unique_id}@example.com"
    password = "ValidPass123!"

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = create_user(email, hashed.decode("utf-8"))
    update_user(email, {"verified": True})

    # Log in
    resp = client.post('/login', json={"email": email, "password": password})
    assert resp.status_code == 200

    return client, user.id, email


# ------------------------------------------------------------------
# Tests for /dashboard
# ------------------------------------------------------------------

def test_dashboard_requires_login(client):
    """GET /dashboard without authentication redirects to login."""
    resp = client.get('/dashboard')
    # Our app redirects to /login (or returns 401)
    assert resp.status_code in (302, 401)


def test_dashboard_loads(auth_client_with_user, db_session):
    """GET /dashboard returns 200 and contains summary cards."""
    client, user_id, email = auth_client_with_user

    # Add a receipt
    create_receipt(user_id, {
        'merchant': 'Test Store',
        'date': '2026-08-29',
        'total': 42.50,
        'category': 'FOOD',
        'image_name': 'test.jpg',
        'image_hash': 'abc123',
        'receipt_hash': 'hash123'
    })

    resp = client.get('/dashboard')
    assert resp.status_code == 200
    assert b'Total Receipts' in resp.data
    assert b'Total Spent' in resp.data
    # Table rows are populated by AJAX, so we don't check them here


def test_dashboard_filters(auth_client_with_user, db_session):
    """GET /dashboard with filters returns only matching receipts (AJAX)."""
    client, user_id, email = auth_client_with_user

    create_receipt(user_id, {
        'merchant': 'Coffee Shop',
        'date': '2026-08-01',
        'total': 5.00,
        'category': 'FOOD',
        'image_name': 'coffee.jpg',
        'image_hash': 'hash1',
        'receipt_hash': 'hash1'
    })
    create_receipt(user_id, {
        'merchant': 'Gas Station',
        'date': '2026-08-15',
        'total': 30.00,
        'category': 'TRANSPORTATION',
        'image_name': 'gas.jpg',
        'image_hash': 'hash2',
        'receipt_hash': 'hash2'
    })

    headers = {'X-Requested-With': 'XMLHttpRequest'}

    # Filter by category=FOOD
    resp = client.get('/dashboard?category=FOOD', headers=headers)
    data = resp.get_json()
    assert len(data['records']) == 1
    assert data['records'][0]['merchant'] == 'Coffee Shop'

    # Filter by merchant search
    resp = client.get('/dashboard?merchant=Coffee', headers=headers)
    data = resp.get_json()
    assert len(data['records']) == 1
    assert data['records'][0]['merchant'] == 'Coffee Shop'

    # Filter by date range (start_date only)
    resp = client.get('/dashboard?start_date=2026-08-10', headers=headers)
    data = resp.get_json()
    assert len(data['records']) == 1
    assert data['records'][0]['merchant'] == 'Gas Station'


def test_dashboard_pagination(auth_client_with_user, db_session):
    """GET /dashboard with page/limit parameters works (AJAX)."""
    client, user_id, email = auth_client_with_user

    # Insert 5 receipts
    for i in range(5):
        create_receipt(user_id, {
            'merchant': f'Store {i}',
            'date': '2026-08-29',
            'total': 10.00 + i,
            'category': 'OTHER',
            'image_name': f'store{i}.jpg',
            'image_hash': f'hash{i}',
            'receipt_hash': f'rhash{i}'
        })

    headers = {'X-Requested-With': 'XMLHttpRequest'}

    # First page with limit 2
    resp = client.get('/dashboard?page=1&limit=2', headers=headers)
    data = resp.get_json()
    assert data['page'] == 1
    assert data['limit'] == 2
    assert data['total_pages'] == 3
    assert len(data['records']) == 2
    assert data['records'][0]['merchant'] == 'Store 0'
    assert data['records'][1]['merchant'] == 'Store 1'

    # Second page with limit 2
    resp = client.get('/dashboard?page=2&limit=2', headers=headers)
    data = resp.get_json()
    assert data['page'] == 2
    assert len(data['records']) == 2
    assert data['records'][0]['merchant'] == 'Store 2'
    assert data['records'][1]['merchant'] == 'Store 3'

    # Third page (only one record)
    resp = client.get('/dashboard?page=3&limit=2', headers=headers)
    data = resp.get_json()
    assert data['page'] == 3
    assert len(data['records']) == 1
    assert data['records'][0]['merchant'] == 'Store 4'

    # Invalid page -> defaults to 1
    resp = client.get('/dashboard?page=0&limit=2', headers=headers)
    data = resp.get_json()
    assert data['page'] == 1

    # Invalid limit -> defaults to 25
    resp = client.get('/dashboard?page=1&limit=0', headers=headers)
    data = resp.get_json()
    assert data['limit'] == 25

    # Limit > 100 -> caps at 100
    resp = client.get('/dashboard?page=1&limit=200', headers=headers)
    data = resp.get_json()
    assert data['limit'] == 100


def test_dashboard_ajax(auth_client_with_user, db_session):
    """GET /dashboard with X-Requested-With header returns JSON."""
    client, user_id, email = auth_client_with_user

    # Add a receipt
    create_receipt(user_id, {
        'merchant': 'AJAX Test',
        'date': '2026-08-29',
        'total': 99.99,
        'category': 'SHOPPING',
        'image_name': 'ajax.jpg',
        'image_hash': 'ajaxhash',
        'receipt_hash': 'ajhash'
    })

    headers = {'X-Requested-With': 'XMLHttpRequest'}
    resp = client.get('/dashboard', headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data is not None
    assert 'records' in data
    assert len(data['records']) == 1
    assert data['records'][0]['merchant'] == 'AJAX Test'
    assert data['total_receipts'] == 1
    assert data['total_spent'] == 99.99


def test_dashboard_user_not_found(auth_client_with_user):
    """Mock find_user_by_email returning None -> redirect to login."""
    client, _, _ = auth_client_with_user
    with patch('app.routes.dashboard.find_user_by_email') as mock_find:
        mock_find.return_value = None
        resp = client.get('/dashboard')
        # The route redirects to /login (or 302)
        assert resp.status_code == 302
        assert resp.location.endswith('/login')


@patch('app.routes.dashboard.generate_presigned_url')
def test_dashboard_with_s3_key(mock_presign, auth_client_with_user):
    """Receipt with s3_key uses generate_presigned_url."""
    mock_presign.return_value = 'https://s3.example.com/image.jpg'
    client, user_id, _ = auth_client_with_user
    create_receipt(user_id, {
        's3_key': 'user_1/test.jpg',
        'merchant': 'S3 Store',
        'total': 10.00,
        'image_name': 'test.jpg',
        'image_hash': 'hash',
        'receipt_hash': 'r'
    })
    resp = client.get('/dashboard', headers={'X-Requested-With': 'XMLHttpRequest'})
    data = resp.get_json()
    assert data['records'][0]['image_path'] == 'https://s3.example.com/image.jpg'


# ------------------------------------------------------------------
# Tests for /export
# ------------------------------------------------------------------

def test_export_json(auth_client_with_user, db_session):
    """GET /export returns JSON with filtered data."""
    client, user_id, email = auth_client_with_user

    create_receipt(user_id, {
        'merchant': 'Export Store',
        'date': '2026-08-29',
        'total': 12.34,
        'category': 'FOOD',
        'image_name': 'export.jpg',
        'image_hash': 'exporthash',
        'receipt_hash': 'exporth'
    })

    resp = client.get('/export')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]['merchant'] == 'Export Store'
    assert data[0]['total'] == 12.34

    # Test with filter
    resp = client.get('/export?category=FOOD')
    data = resp.get_json()
    assert len(data) == 1

    resp = client.get('/export?category=TRANSPORTATION')
    data = resp.get_json()
    assert len(data) == 0


def test_export_user_not_found(auth_client_with_user):
    """Mock find_user_by_email returning None -> 401."""
    client, _, _ = auth_client_with_user
    with patch('app.routes.dashboard.find_user_by_email') as mock_find:
        mock_find.return_value = None
        resp = client.get('/export')
        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'User not found'


# ------------------------------------------------------------------
# Tests for /report (PDF)
# ------------------------------------------------------------------

@patch('app.routes.dashboard.generate_report_pdf')
def test_report_download(mock_generate_pdf, auth_client_with_user):
    """GET /report returns a PDF file as attachment."""
    mock_generate_pdf.return_value = b'%PDF-1.4 fake pdf content'

    client, user_id, email = auth_client_with_user

    # Provide month/year
    resp = client.get('/report?month=2026-08&year=2026')
    assert resp.status_code == 200
    assert resp.content_type == 'application/pdf'
    assert resp.headers['Content-Disposition'] == 'attachment; filename=report-2026-08.pdf'
    assert resp.data == b'%PDF-1.4 fake pdf content'

    # Test fallback to current month (no params)
    resp = client.get('/report')
    assert resp.status_code == 200
    assert resp.content_type == 'application/pdf'
    assert 'report-' in resp.headers['Content-Disposition']

    # Verify mock was called correctly
    mock_generate_pdf.assert_any_call(user_id, '2026-08', '2026', email)
    assert mock_generate_pdf.call_count >= 2


def test_report_requires_auth(client):
    """GET /report without authentication returns 401 or redirect."""
    resp = client.get('/report')
    assert resp.status_code in (302, 401)


def test_report_user_not_found(auth_client_with_user):
    """Mock find_user_by_email returning None -> 401."""
    client, _, _ = auth_client_with_user
    with patch('app.routes.dashboard.find_user_by_email') as mock_find:
        mock_find.return_value = None
        resp = client.get('/report?month=2026-08&year=2026')
        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'User not found'