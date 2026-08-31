# test/conftest.py

import os
import uuid
import pytest
import bcrypt
from app import app as flask_app
from app import limiter  # <-- import the limiter
from app.utils.db import Base, engine, SessionLocal, create_user, update_user

# Override environment variables for testing
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-secret"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["BASE_URL"] = "http://localhost"
os.environ["COOKIE_SECURE"] = "False"

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    """Create a Flask app instance for testing."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    flask_app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    # Disable rate limiting for all tests
    limiter.enabled = False

    yield flask_app

    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture
def auth_client(client, db_session):
    """Create a verified user with a unique email and return a logged‑in test client."""
    unique_id = uuid.uuid4().hex[:8]
    email = f"testuser_{unique_id}@example.com"
    password = "ValidPass123!"

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = create_user(email, hashed.decode("utf-8"))
    update_user(email, {"verified": True})

    resp = client.post('/login', json={"email": email, "password": password})
    assert resp.status_code == 200, "Login failed during fixture setup"
    return client

@pytest.fixture
def auth_headers():
    return {}