# 📄 Receipt AI

**AI‑powered receipt scanning, bookkeeping & tax deduction tracking.**

Upload a photo of any receipt. The app extracts merchant, date, total, and category – and automatically suggests the best 1099 deduction category for tax purposes. See your weekly, monthly, and year‑to‑date spending and deductions in one clean dashboard.

---

## ✨ Key Features

- **📸 One‑click upload** – snap a photo or pick an image from your phone
- **🧠 AI extraction** – merchant, date, amounts, category, and deduction suggestion
- **✅ Review & confirm** – correct any AI mistakes before saving
- **📊 Dashboard** – summary cards, filters, charts, and a full receipt table
- **💸 1099 Deduction Tracker** – 27 IRS categories with weekly/monthly/YTD totals
- **⬇️ Export** – download your deduction data as CSV or PDF
- **🔒 Secure** – JWT with HttpOnly cookies, refresh token rotation, CSP, rate limiting
- **📱 Mobile‑friendly** – works on phones, tablets, and desktops

---

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/carlosgandara/receipt-ai-platform.git
cd receipt-ai-platform

# Set up a virtual environment
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env
# Edit .env with your DATABASE_URL, NOVITA_API_KEY, etc.

# Run the app
python app.py
