# Python Flask JWT Authentication with Email Verification

A secure, production-ready authentication system built with **Flask**, **JWT**, and **email verification**. Provides registration, email verification, login (JWT), protected routes, and password reset – all with a JSON file database and a simple web UI.

## Features
- 🔐 Register with email + password
- 📧 Email verification (expires in 24h)
- 🔑 JWT login (expires in 1h)
- 🔒 Protected routes (token required)
- 📨 Password reset (expires in 15min)
- 🖥️ Web forms (AJAX, no reload)
- 📁 JSON database (ready to swap for real DB)

## Tech Stack
- **Backend**: Flask (Python)
- **Auth**: PyJWT + bcrypt
- **Email**: SMTP (Brevo / Sendinblue)
- **DB**: JSON file
- **Frontend**: HTML + vanilla JS

## Project Structure
```
python-flask-jwt-auth/
├── app.py
├── config.py
├── .env (ignored)
├── .gitignore
├── user_db.json (auto‑created, ignored)
├── requirements.txt
├── utils/
│   ├── db.py
│   └── mail_service.py
└── templates/
    ├── base.html
    ├── login.html
    ├── register.html
    ├── forgot_password.html
    ├── reset_password.html
    ├── verify_success.html
    └── verify_error.html
```

## Setup
1. Clone: `git clone https://github.com/carlosgandara/python-flask-jwt-auth.git`
2. Create virtual env: `python -m venv venv`
3. Activate: `source venv/bin/activate` (Windows: `venv\Scripts\activate`)
4. Install: `pip install -r requirements.txt`
5. Create `.env` (see example below)
6. Run: `python app.py`

## .env Example (your SMTP credentials)
```
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_USER=your-smtp-username
EMAIL_PASS=your-smtp-password
EMAIL_FROM=your-email@example.com
JWT_SECRET_KEY=your-very-long-secret-min-32-chars
```

## API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /register | Create user + send verification |
| GET | /verify-email | Verify email with token |
| POST | /login | Get JWT token |
| GET | /protected | Protected route (requires token) |
| POST | /forgot-password | Request reset link |
| POST | /reset-password | Reset password with token |
| GET | /login, /register, /forgot-password, /reset-password | HTML pages |

## Testing with curl (Windows CMD one‑liners)
**Register**:
```
curl -X POST http://localhost:5000/register -H "Content-Type: application/json" -d "{\"email\":\"test@example.com\",\"password\":\"123456\"}"
```
**Login**:
```
curl -X POST http://localhost:5000/login -H "Content-Type: application/json" -d "{\"email\":\"test@example.com\",\"password\":\"123456\"}"
```
**Protected** (replace token):
```
curl -X GET http://localhost:5000/protected -H "Authorization: Bearer <your-token>"
```
**Forgot Password**:
```
curl -X POST http://localhost:5000/forgot-password -H "Content-Type: application/json" -d "{\"email\":\"test@example.com\"}"
```
**Reset Password** (replace token):
```
curl -X POST http://localhost:5000/reset-password -H "Content-Type: application/json" -d "{\"token\":\"RESET_TOKEN\",\"new_password\":\"newpass\"}"
```

## Full Flow One‑Liner (requires jq)
```
curl -s -X POST http://localhost:5000/register -H "Content-Type: application/json" -d "{\"email\":\"test@example.com\",\"password\":\"123456\"}" && curl -s "http://localhost:5000/verify-email?token=$(jq -r '.users[] | select(.email=="test@example.com") | .verification_token' user_db.json)" && curl -s -X POST http://localhost:5000/login -H "Content-Type: application/json" -d "{\"email\":\"test@example.com\",\"password\":\"123456\"}"
```

## Email Configuration
Works with any SMTP provider (Brevo, Gmail, SendGrid, etc.). For Gmail, use an App Password.

## Security
- Passwords hashed with bcrypt (12 rounds)
- JWT signed with secret key
- Reset tokens hashed before storage
- Verification tokens stored plain (can be upgraded)
- **Important**: `.env` and `user_db.json` are ignored by Git.

## Web UI
Visit in your browser:
- http://localhost:5000/login
- http://localhost:5000/register
- http://localhost:5000/forgot-password
- http://localhost:5000/reset-password?token=...

All forms use AJAX – no page reload.

## Future Improvements
- Switch to SQLite/PostgreSQL
- Refresh tokens
- Rate limiting
- Change password endpoint
- Hashed verification tokens
- Unit tests

## License
MIT License

Copyright (c) 2024 Carlos Gandara

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Author
Carlos Gandara – [GitHub](https://github.com/carlosgandara)
