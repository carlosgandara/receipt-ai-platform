🔐 Python Flask JWT Authentication with Refresh Token Rotation
Enterprise-grade, production-ready authentication system built with Flask. Features HttpOnly cookies, refresh token rotation, and silent frontend recovery.

✨ Features
🔐 Register with email + password (bcrypt hashed)

📧 Email verification (expires in 24h)

🍪 HttpOnly Cookies – Tokens are invisible to JavaScript (XSS-safe)

🔑 JWT Access Token (short-lived, stored in HttpOnly cookie)

🔄 Refresh Token Rotation – Long-lived, hashed in DB, invalidated on use (replay attack proof)

🛡️ Silent Token Refresh – Frontend catches 401s, calls /refresh automatically, and retries requests

📊 Protected Pages – /dashboard and /profile with cookie-based auth

🚪 Secure Logout – Revokes refresh token in DB and deletes cookies

📨 Password Reset (expires in 15min)

🖥️ Web UI – AJAX forms with automatic redirects

📁 JSON Database (ready to swap for PostgreSQL/MySQL)

⏱️ Rate Limiting – Per-IP and per-IP+User combo protection (in feature branch)

🛠️ Tech Stack
Backend: 🐍 Flask (Python 3.10+)

Auth: 🔐 PyJWT + bcrypt

Cookies: 🍪 HttpOnly, Secure, SameSite=Lax

Email: ✉️ SMTP (Brevo / Sendinblue / Gmail)

DB: 🗄️ JSON file (thread-safe with file locking)

Frontend: 🌐 HTML + vanilla JS (no frameworks required)

📁 Project Structure
text
python-flask-jwt-auth/
├── 🚀 app.py                      # Main Flask app with refresh endpoints
├── ⚙️ config.py                   # Configuration + environment variables
├── 🔒 .env                        # SMTP + JWT secrets (ignored by Git)
├── 📄 .gitignore                  # Ignores .env, user_db.json, __pycache__
├── 📦 requirements.txt            # Python dependencies
├── 🗄️ user_db.json                # Auto‑created user database (ignored)
├── 📂 utils/
│   ├── 🗃️ db.py                   # JSON file CRUD (thread-safe)
│   └── ✉️ mail_service.py         # SMTP email sender
└── 📂 templates/
    ├── 🏗️ base.html               # Base layout
    ├── 🔑 login.html              # Login form (redirects to dashboard)
    ├── 📝 register.html           # Registration form
    ├── 🔄 forgot_password.html    # Request reset link
    ├── 🔐 reset_password.html     # Reset password form
    ├── 📊 dashboard.html          # Protected dashboard (with silent refresh)
    ├── 👤 profile.html            # Protected profile page
    ├── ✅ verify_success.html     # Email verified
    └── ❌ verify_error.html       # Verification failed
🚀 Setup
Clone the repository

bash
git clone https://github.com/carlosgandara/python-flask-jwt-auth.git
cd python-flask-jwt-auth
Create and activate a virtual environment

bash
python -m venv venv
source venv/bin/activate      # Mac/Linux
venv\Scripts\activate         # Windows
Install dependencies

bash
pip install -r requirements.txt
Create a .env file (see example below)

env
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_USER=your-smtp-username
EMAIL_PASS=your-smtp-password
EMAIL_FROM=your-email@example.com
JWT_SECRET_KEY=your-very-long-secret-min-32-chars
Run the app

bash
python app.py
Open your browser
Visit http://localhost:5000/login

⚠️ Note: user_db.json and .env are ignored by Git – your secrets stay safe.

🌐 API Endpoints
Method	Endpoint	Description	Auth Required
POST	/register	Create user + send verification email	❌ No
GET	/verify-email	Verify email with token	❌ No
POST	/login	Set access_token and refresh_token as HttpOnly cookies	❌ No
POST	/refresh	Rotate tokens (issue new Access + Refresh)	✅ Refresh Cookie
GET	/protected	Test route – returns user email	✅ Access Cookie
GET	/dashboard	Protected HTML page	✅ Access Cookie
GET	/profile	Protected HTML page	✅ Access Cookie
POST	/logout	Revoke refresh token + delete cookies	✅ Access Cookie
POST	/forgot-password	Request password reset link	❌ No
POST	/reset-password	Reset password with token	❌ No
🧪 Testing with curl (Windows CMD)
💡 Important: The new flow uses HttpOnly cookies. Use -c to save cookies and -b to send them.

1. Login (saves cookies to cookies.txt)

cmd
curl -X POST http://localhost:5000/login -H "Content-Type: application/json" -d "{\"email\":\"test@example.com\",\"password\":\"123456\"}" -c cookies.txt -i
2. Access protected endpoint (uses saved cookie)

cmd
curl -X GET http://localhost:5000/protected -b cookies.txt
3. Refresh tokens (rotation – kills old token)

cmd
curl -X POST http://localhost:5000/refresh -b cookies.txt -c cookies_new.txt -i
4. Prove rotation works (reuse old token – fails)

cmd
curl -X POST http://localhost:5000/refresh -b cookies.txt
Expected: {"error": "Invalid or expired refresh token"} (replay attack blocked)

5. Logout (revokes token + deletes cookies)

cmd
curl -X POST http://localhost:5000/logout -b cookies.txt -c cookies.txt -i
👨‍💻 Web UI Walkthrough
📝 Register – Fill in email/password → receive verification email.

✅ Verify – Click the link in your email.

🔑 Login – Enter credentials → automatically redirected to /dashboard.

📊 Dashboard – Shows your protected user data. Click "Refresh Data" to test the API.

👤 Profile – Another protected page (demonstrates cookie persistence).

🔄 Silent Refresh – If you wait for the Access Token to expire (e.g., 1 min) and click "Refresh Data", the frontend silently calls /refresh and retries – you never see a login screen.

🚪 Logout – Clears cookies and revokes the refresh token in the database.

✉️ Email Configuration
Works with any SMTP provider:

Brevo (Sendinblue) – Recommended (free tier)

Gmail – Use an App Password

SendGrid, Mailgun, etc.

🛡️ Security Highlights
Measure	Implementation
Password storage	bcrypt (12 rounds)
JWT signing	HMAC-SHA256 with secret key
Refresh tokens	Hashed in database (bcrypt), revoked on rotation
Cookies	HttpOnly (XSS-safe), Secure (HTTPS-only), SameSite=Lax (CSRF protection)
Verification tokens	Plain storage (can be upgraded to hashed)
Rate limiting	Per-IP and per-IP+User combo (available in feature branch)
🚀 Future Improvements
Switch to SQLite/PostgreSQL

Add rate limiting (available in feature/rate-limiting branch)

Change password endpoint

Hashed verification tokens

Unit tests

📄 License
MIT License

Copyright (c) 2024 Carlos Gandara

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

👤 Author
Carlos Gandara
🔗 GitHub

⭐ If you found this useful, please give it a star!
nooo!
OK, the user just said "nooo!" to my last response. Looking back at the history, I've been trying to help them format a README.md file for their GitHub project. They kept asking for one full block of text, and I kept giving it with formatting characters like backticks and newlines, which they clearly didn't want.

I need to understand what they actually want. They said "in one full block like this" earlier, and I gave them a block with emojis and a project structure tree. Then they said "noo.. create full block 'text' all data" and I gave them the entire README as a code block. Then they said "nooo!" to that.

Looking at the last few exchanges, they seem to want the README content in a single, continuous block of plain text, without any Markdown formatting, line breaks, or code fences. They want it as pure text that they can copy and paste into their GitHub edit box. The "nooo!" suggests the previous attempts with formatting (like backslashes, code blocks, or line breaks) were still not what they wanted.

The user is probably frustrated because they keep asking for something simple (just the text content) and I keep overcomplicating it with formatting instructions. They might be in a hurry or just want the raw content without having to strip out formatting characters themselves.

My response now should be exactly what they asked for: the entire README content as a single, unbroken block of plain text without any Markdown formatting, newlines, or backticks. Just the raw text they can paste directly into the GitHub edit box.

I need to make sure the content is complete, including all the sections like Features, Tech Stack, Project Structure (with emojis), Setup instructions, API endpoints, curl commands, etc. The user is clearly proud of their project and wants the README to look professional and comprehensive.

The key insight is that they want a "raw text" dump of the README that they can copy-paste. They don't want me to wrap it in code fences or add any extra formatting instructions. Just the plain text content they can use immediately.

Ah! I understand now – you want the entire README as a single block of plain text (no backticks, no code fences, just raw text).

Here is the complete README.md as raw text – copy everything from the first line to the last:

🔐 Python Flask JWT Authentication with Refresh Token Rotation
Enterprise-grade, production-ready authentication system built with Flask. Features HttpOnly cookies, refresh token rotation, and silent frontend recovery.

✨ Features
🔐 Register with email + password (bcrypt hashed)

📧 Email verification (expires in 24h)

🍪 HttpOnly Cookies – Tokens are invisible to JavaScript (XSS-safe)

🔑 JWT Access Token (short-lived, stored in HttpOnly cookie)

🔄 Refresh Token Rotation – Long-lived, hashed in DB, invalidated on use (replay attack proof)

🛡️ Silent Token Refresh – Frontend catches 401s, calls /refresh automatically, and retries requests

📊 Protected Pages – /dashboard and /profile with cookie-based auth

🚪 Secure Logout – Revokes refresh token in DB and deletes cookies

📨 Password Reset (expires in 15min)

🖥️ Web UI – AJAX forms with automatic redirects

📁 JSON Database (ready to swap for PostgreSQL/MySQL)

⏱️ Rate Limiting – Per-IP and per-IP+User combo protection (in feature branch)

🛠️ Tech Stack
Backend: 🐍 Flask (Python 3.10+)

Auth: 🔐 PyJWT + bcrypt

Cookies: 🍪 HttpOnly, Secure, SameSite=Lax

Email: ✉️ SMTP (Brevo / Sendinblue / Gmail)

DB: 🗄️ JSON file (thread-safe with file locking)

Frontend: 🌐 HTML + vanilla JS (no frameworks required)

📁 Project Structure
python-flask-jwt-auth/
├── 🚀 app.py # Main Flask app with refresh endpoints
├── ⚙️ config.py # Configuration + environment variables
├── 🔒 .env # SMTP + JWT secrets (ignored by Git)
├── 📄 .gitignore # Ignores .env, user_db.json, pycache
├── 📦 requirements.txt # Python dependencies
├── 🗄️ user_db.json # Auto‑created user database (ignored)
├── 📂 utils/
│ ├── 🗃️ db.py # JSON file CRUD (thread-safe)
│ └── ✉️ mail_service.py # SMTP email sender
└── 📂 templates/
├── 🏗️ base.html # Base layout
├── 🔑 login.html # Login form (redirects to dashboard)
├── 📝 register.html # Registration form
├── 🔄 forgot_password.html # Request reset link
├── 🔐 reset_password.html # Reset password form
├── 📊 dashboard.html # Protected dashboard (with silent refresh)
├── 👤 profile.html # Protected profile page
├── ✅ verify_success.html # Email verified
└── ❌ verify_error.html # Verification failed

🚀 Setup
Clone the repository:
git clone https://github.com/carlosgandara/python-flask-jwt-auth.git
cd python-flask-jwt-auth

Create and activate a virtual environment:
python -m venv venv
source venv/bin/activate # Mac/Linux
venv\Scripts\activate # Windows

Install dependencies:
pip install -r requirements.txt

Create a .env file (see example below):
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_USER=your-smtp-username
EMAIL_PASS=your-smtp-password
EMAIL_FROM=your-email@example.com
JWT_SECRET_KEY=your-very-long-secret-min-32-chars

Run the app:
python app.py

Open your browser:
Visit http://localhost:5000/login

Note: user_db.json and .env are ignored by Git – your secrets stay safe.

🌐 API Endpoints
POST /register – Create user + send verification email (No auth required)
GET /verify-email – Verify email with token (No auth required)
POST /login – Set access_token and refresh_token as HttpOnly cookies (No auth required)
POST /refresh – Rotate tokens (issue new Access + Refresh) (Refresh Cookie required)
GET /protected – Test route – returns user email (Access Cookie required)
GET /dashboard – Protected HTML page (Access Cookie required)
GET /profile – Protected HTML page (Access Cookie required)
POST /logout – Revoke refresh token + delete cookies (Access Cookie required)
POST /forgot-password – Request password reset link (No auth required)
POST /reset-password – Reset password with token (No auth required)

🧪 Testing with curl (Windows CMD)
Important: The new flow uses HttpOnly cookies. Use -c to save cookies and -b to send them.

Login (saves cookies to cookies.txt):
curl -X POST http://localhost:5000/login -H "Content-Type: application/json" -d "{"email":"test@example.com","password":"123456"}" -c cookies.txt -i

Access protected endpoint (uses saved cookie):
curl -X GET http://localhost:5000/protected -b cookies.txt

Refresh tokens (rotation – kills old token):
curl -X POST http://localhost:5000/refresh -b cookies.txt -c cookies_new.txt -i

Prove rotation works (reuse old token – fails):
curl -X POST http://localhost:5000/refresh -b cookies.txt
Expected: {"error": "Invalid or expired refresh token"} (replay attack blocked)

Logout (revokes token + deletes cookies):
curl -X POST http://localhost:5000/logout -b cookies.txt -c cookies.txt -i

👨‍💻 Web UI Walkthrough
📝 Register – Fill in email/password → receive verification email.

✅ Verify – Click the link in your email.

🔑 Login – Enter credentials → automatically redirected to /dashboard.

📊 Dashboard – Shows your protected user data. Click "Refresh Data" to test the API.

👤 Profile – Another protected page (demonstrates cookie persistence).

🔄 Silent Refresh – If you wait for the Access Token to expire (e.g., 1 min) and click "Refresh Data", the frontend silently calls /refresh and retries – you never see a login screen.

🚪 Logout – Clears cookies and revokes the refresh token in the database.

✉️ Email Configuration
Works with any SMTP provider:

Brevo (Sendinblue) – Recommended (free tier)

Gmail – Use an App Password

SendGrid, Mailgun, etc.

🛡️ Security Highlights
Password storage: bcrypt (12 rounds)
JWT signing: HMAC-SHA256 with secret key
Refresh tokens: Hashed in database (bcrypt), revoked on rotation
Cookies: HttpOnly (XSS-safe), Secure (HTTPS-only), SameSite=Lax (CSRF protection)
Verification tokens: Plain storage (can be upgraded to hashed)
Rate limiting: Per-IP and per-IP+User combo (available in feature branch)

🚀 Future Improvements
Switch to SQLite/PostgreSQL

Add rate limiting (available in feature/rate-limiting branch)

Change password endpoint

Hashed verification tokens

Unit tests

📄 License
MIT License

Copyright (c) 2024 Carlos Gandara

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

👤 Author
Carlos Gandara
🔗 GitHub: https://github.com/carlosgandara

