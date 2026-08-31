import os
import smtplib
import email.utils
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASS, EMAIL_FROM, EMAIL_DISPLAY_NAME

def send_email(to, subject, text, html=None):
    from_formatted = f"{EMAIL_DISPLAY_NAME} <{EMAIL_FROM}>"

    msg = MIMEMultipart("alternative")
    msg["From"] = from_formatted
    msg["To"] = to
    msg["Subject"] = subject
    part1 = MIMEText(text, "plain")
    msg.attach(part1)
    if html:
        part2 = MIMEText(html, "html")
        msg.attach(part2)

    try:
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_FROM, [to], msg.as_string())
        server.quit()
        print(f"✅ Email sent to {to}")
    except Exception as e:
        print(f"❌ Email failed: {e}")
        raise