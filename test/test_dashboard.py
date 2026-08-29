# test/test_dashboard.py

import uuid
from unittest.mock import patch

import pytest
import bcrypt

from app.utils.db import create_user, update_user, create_receipt, SessionLocal, engine


# ------------------------------------------------------------------
# Helper fixture: authenticated client + user_id
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

    resp = client.post('/login', json={"email": email, "password": password})
    assert resp.status_code == 200
    return client, user.id, email


# ------------------------------------------------------------------
# Tests for /dashboard
# ------------------------------------------------------------------

def test_dashboard_requires_login(client):
    resp = client.get('/dashboard')
    assert resp.status_code in (302, 401)


def test_dashboard_loads(auth_client_with_user):
    client, user_id, _ = auth_client_with_user
    # Insert a receipt using the app's engine (so it's visible)
    with SessionLocal() as session:
        from app.utils.db import Receipt
        receipt = Receipt(
            user_id=user_id,
            merchant='Test Store',
            date='2026-08-29',
            total=42.50,
            category='FOOD',
            image_name='test.jpg',
            image_hash='abc123',
            receipt_hash='hash123'
        )
        session.add(receipt)
        session.commit()

    resp = client.get('/dashboard')
    assert resp.status_code == 200
    assert b'Total Receipts' in resp.data
    assert b'Total Spent' in resp.data


def test_dashboard_filters(auth_client_with_user):
    client, user_id, _ = auth_client_with_user
    # Insert two receipts
    with SessionLocal() as session:
        from app.utils.db import Receipt
        r1 = Receipt(
            user_id=user_id,
            merchant='Coffee Shop',
            date='2026-08-01',
            total=5.00,
            category='FOOD',
            image_name='coffee.jpg',
            image_hash='hash1',
            receipt_hash='hash1'
        )
        r2 = Receipt(
            user_id=user_id,
            merchant='Gas Station',
            date='2026-08-15',
            total=30.00,
            category='TRANSPORTATION',
            image_name='gas.jpg',
            image_hash='hash2',
            receipt_hash='hash2'
        )
        session.add_all([r1, r2])
        session.commit()

    headers = {'X-Requested-With': 'XMLHttpRequest'}

    resp = client.get('/dashboard?category=FOOD', headers=headers)
    data = resp.get_json()
    assert data is not None
    assert len(data['records']) == 1
    assert data['records'][0]['merchant'] == 'Coffee Shop'

    resp = client.get('/dashboard?merchant=Coffee', headers=headers)
    data = resp.get_json()
    assert len(data['records']) == 1
    assert data['records'][0]['merchant'] == 'Coffee Shop'

    resp = client.get('/dashboard?start_date=2026-08-10', headers=headers)
    data = resp.get_json()
    assert len(data['records']) == 1
    assert data['records'][0]['merchant'] == 'Gas Station'


def test_dashboard_pagination(auth_client_with_user):
    client, user_id, _ = auth_client_with_user
    with SessionLocal() as session:
        from app.utils.db import Receipt
        for i in range(5):
            session.add(Receipt(
                user_id=user_id,
                merchant=f'Store {i}',
                date='2026-08-29',
                total=10.00 + i,
                category='OTHER',
                image_name=f'store{i}.jpg',
                image_hash=f'hash{i}',
                receipt_hash=f'rhash{i}'
            ))
        session.commit()

    headers = {'X-Requested-With': 'XMLHttpRequest'}

    resp = client.get('/dashboard?page=1&limit=2', headers=headers)
    data = resp.get_json()
    assert data['page'] == 1
    assert data['limit'] == 2
    assert data['total_pages'] == 3
    assert len(data['records']) == 2
    assert data['records'][0]['merchant'] == 'Store 0'

    resp = client.get('/dashboard?page=2&limit=2', headers=headers)
    data = resp.get_json()
    assert data['page'] == 2
    assert len(data['records']) == 2
    assert data['records'][0]['merchant'] == 'Store 2'

    # Invalid page -> defaults to 1
    resp = client.get('/dashboard?page=0&limit=2', headers=headers)
    data = resp.get_json()
    assert data['page'] == 1

    # Limit > 100 -> caps at 100
    resp = client.get('/dashboard?page=1&limit=200', headers=headers)
    data = resp.get_json()
    assert data['limit'] == 100


def test_dashboard_ajax(auth_client_with_user):
    client, user_id, _ = auth_client_with_user
    with SessionLocal() as session:
        from app.utils.db import Receipt
        session.add(Receipt(
            user_id=user_id,
            merchant='AJAX Test',
            date='2026-08-29',
            total=99.99,
            category='SHOPPING',
            image_name='ajax.jpg',
            image_hash='ajaxhash',
            receipt_hash='ajhash'
        ))
        session.commit()

    headers = {'X-Requested-With': 'XMLHttpRequest'}
    resp = client.get('/dashboard', headers=headers)
    data = resp.get_json()
    assert data is not None
    assert 'records' in data
    assert len(data['records']) == 1
    assert data['records'][0]['merchant'] == 'AJAX Test'
    assert data['total_receipts'] == 1
    assert data['total_spent'] == 99.99


def test_dashboard_user_not_found(auth_client_with_user):
    client, _, _ = auth_client_with_user
    with patch('app.routes.dashboard.find_user_by_email') as mock:
        mock.return_value = None
        resp = client.get('/dashboard')
        assert resp.status_code == 302
        assert resp.location.endswith('/login')


@patch('app.routes.dashboard.generate_presigned_url')
def test_dashboard_with_s3_key(mock_presign, auth_client_with_user):
    mock_presign.return_value = 'https://s3.example.com/image.jpg'
    client, user_id, _ = auth_client_with_user
    with SessionLocal() as session:
        from app.utils.db import Receipt
        session.add(Receipt(
            user_id=user_id,
            s3_key='user_1/test.jpg',
            merchant='S3 Store',
            total=10.00,
            image_name='test.jpg',
            image_hash='hash',
            receipt_hash='r'
        ))
        session.commit()

    headers = {'X-Requested-With': 'XMLHttpRequest'}
    resp = client.get('/dashboard', headers=headers)
    data = resp.get_json()
    assert data['records'][0]['image_path'] == 'https://s3.example.com/image.jpg'


# ------------------------------------------------------------------
# Tests for /export
# ------------------------------------------------------------------

def test_export_json(auth_client_with_user):
    client, user_id, _ = auth_client_with_user
    with SessionLocal() as session:
        from app.utils.db import Receipt
        session.add(Receipt(
            user_id=user_id,
            merchant='Export Store',
            date='2026-08-29',
            total=12.34,
            category='FOOD',
            image_name='export.jpg',
            image_hash='exporthash',
            receipt_hash='exporth'
        ))
        session.commit()

    resp = client.get('/export')
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]['merchant'] == 'Export Store'

    resp = client.get('/export?category=TRANSPORTATION')
    data = resp.get_json()
    assert len(data) == 0


def test_export_user_not_found(auth_client_with_user):
    client, _, _ = auth_client_with_user
    with patch('app.routes.dashboard.find_user_by_email') as mock:
        mock.return_value = None
        resp = client.get('/export')
        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'User not found'


# ------------------------------------------------------------------
# Tests for /report (PDF)
# ------------------------------------------------------------------

@patch('app.routes.dashboard.generate_report_pdf')
def test_report_download(mock_pdf, auth_client_with_user):
    mock_pdf.return_value = b'%PDF-1.4 fake pdf'
    client, user_id, email = auth_client_with_user

    resp = client.get('/report?month=2026-08&year=2026')
    assert resp.status_code == 200
    assert resp.content_type == 'application/pdf'
    assert resp.headers['Content-Disposition'] == 'attachment; filename=report-2026-08.pdf'
    assert resp.data == b'%PDF-1.4 fake pdf'

    resp = client.get('/report')  # no params -> current month
    assert resp.status_code == 200
    assert 'report-' in resp.headers['Content-Disposition']
    mock_pdf.assert_any_call(user_id, '2026-08', '2026', email)


def test_report_requires_auth(client):
    resp = client.get('/report')
    assert resp.status_code in (302, 401)


def test_report_user_not_found(auth_client_with_user):
    client, _, _ = auth_client_with_user
    with patch('app.routes.dashboard.find_user_by_email') as mock:
        mock.return_value = None
        resp = client.get('/report')
        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'User not found'