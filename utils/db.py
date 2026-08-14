import json
import threading
from pathlib import Path

DB_PATH = Path("user_db.json")
DB_LOCK = threading.Lock()

def _read_db():
    if not DB_PATH.exists():
        return {"users": []}
    try:
        with open(DB_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # If file is empty or corrupt, reset to default
        return {"users": []}

def _write_db(data):
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2)

def find_user_by_email(email):
    with DB_LOCK:
        data = _read_db()
        for user in data["users"]:
            if user["email"] == email:
                return user
        return None

def create_user(email, password_hash):
    with DB_LOCK:
        data = _read_db()
        for u in data["users"]:
            if u["email"] == email:
                raise ValueError("User exists")
        user = {
            "id": len(data["users"]) + 1,
            "email": email,
            "password": password_hash,
            "verified": False,
            "verification_token": None,
            "verification_expiry": None,
            "reset_token": None,
            "reset_expiry": None
        }
        data["users"].append(user)
        _write_db(data)
        return user

def update_user(email, updates):
    with DB_LOCK:
        data = _read_db()
        for user in data["users"]:
            if user["email"] == email:
                user.update(updates)
                _write_db(data)
                return user
        return None