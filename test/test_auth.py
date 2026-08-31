# test/test_auth.py

import json
import bcrypt
from app.utils.db import find_user_by_email, create_user, update_user

def test_register(client):
    """POST /register – valid user should get 200."""
    resp = client.post('/register',
                       json={"email": "test@example.com", "password": "Test123!"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["message"] == "If this email is valid, a verification link was sent."

def test_register_duplicate(client):
    """POST /register with same email should return the same message (no user enumeration)."""
    # First registration
    client.post('/register', json={"email": "test2@example.com", "password": "Test123!"})
    # Second attempt
    resp = client.post('/register', json={"email": "test2@example.com", "password": "Test123!"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["message"] == "If this email is valid, a verification link was sent."

def test_register_weak_password(client):
    """Password strength validation."""
    resp = client.post('/register', json={"email": "test@example.com", "password": "weak"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "Password must be at least 8 characters" in data["error"]

def test_login_valid_credentials(client, db_session):
    """POST /login – valid credentials sets cookies and returns 200."""
    email = "loginuser@example.com"
    password = "ValidPass123!"
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = create_user(email, hashed.decode("utf-8"))
    update_user(email, {"verified": True})

    resp = client.post('/login', json={"email": email, "password": password})
    assert resp.status_code == 200

    # FIX: use getlist to get all Set-Cookie headers
    cookies = resp.headers.getlist('Set-Cookie')
    assert any('access_token' in c for c in cookies)
    assert any('refresh_token' in c for c in cookies)

def test_login_invalid_credentials(client):
    """POST /login with wrong password returns 401."""
    resp = client.post('/login', json={"email": "any@example.com", "password": "wrong"})
    assert resp.status_code == 401
    data = resp.get_json()
    assert data["error"] == "Invalid credentials"

def test_login_unverified_email(client, db_session):
    """POST /login with unverified email returns 403."""
    email = "unverified@example.com"
    password = "ValidPass123!"
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    create_user(email, hashed.decode("utf-8"))  # verified defaults to False

    resp = client.post('/login', json={"email": email, "password": password})
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["error"] == "Please verify your email first."

def test_protected_route_without_token(client):
    """GET /protected – missing token returns 401."""
    resp = client.get('/protected')
    assert resp.status_code == 401
    data = resp.get_json()
    assert data["error"] == "Missing access token"

def test_protected_route_with_token(client, db_session):
    """GET /protected – valid token returns user email."""
    email = "prottest@example.com"
    password = "ValidPass123!"
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = create_user(email, hashed.decode("utf-8"))
    update_user(email, {"verified": True})

    # Login to get cookies
    client.post('/login', json={"email": email, "password": password})
    resp2 = client.get('/protected')
    assert resp2.status_code == 200
    data = resp2.get_json()
    assert data["message"] == f"Hello {email}!"

def test_refresh_token_flow(client, db_session):
    """POST /refresh – rotates tokens."""
    email = "refreshtest@example.com"
    password = "ValidPass123!"
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = create_user(email, hashed.decode("utf-8"))
    update_user(email, {"verified": True})

    # Login to get initial refresh token
    client.post('/login', json={"email": email, "password": password})

    # Refresh
    resp = client.post('/refresh')
    assert resp.status_code == 200

    # FIX: use getlist to get all Set-Cookie headers
    cookies = resp.headers.getlist('Set-Cookie')
    assert any('access_token' in c for c in cookies)
    assert any('refresh_token' in c for c in cookies)

def test_logout(client, db_session):
    """POST /logout – clears cookies and revokes token."""
    email = "logouttest@example.com"
    password = "ValidPass123!"
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = create_user(email, hashed.decode("utf-8"))
    update_user(email, {"verified": True})

    client.post('/login', json={"email": email, "password": password})
    resp = client.post('/logout')
    assert resp.status_code == 200

    # The refresh token should be revoked; try refreshing
    resp_refresh = client.post('/refresh')
    assert resp_refresh.status_code == 401   # refresh token revoked