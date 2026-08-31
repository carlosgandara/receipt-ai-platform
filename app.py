# app.py – Entry point
from app import app

if __name__ == "__main__":
    from app.utils.session import cleanup_expired_temp_files
    cleanup_expired_temp_files()
    app.run(host='0.0.0.0', port=3000)