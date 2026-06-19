# ============================================================
#   core/mailer.py — Send results by email via the teacher's Gmail
#   Uses Gmail SMTP + a 16-char App Password (NOT the real password).
#   One connection is reused for bulk sending (fast + Gmail-friendly).
# ============================================================

import ssl
import smtplib
import logging
import mimetypes
from pathlib import Path
from email.message import EmailMessage

logger = logging.getLogger("mailer")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL


class GmailSender:
    def __init__(self, address: str, app_password: str, sender_name: str = ""):
        self.address = (address or "").strip()
        # App passwords are shown as "abcd efgh ijkl mnop" — spaces are not part of it.
        self.password = (app_password or "").replace(" ", "")
        self.sender_name = (sender_name or "Smart Paper Checker").strip()
        self.server = None

    def connect(self):
        ctx = ssl.create_default_context()
        self.server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=30)
        self.server.login(self.address, self.password)
        logger.info("Gmail SMTP login OK.")
        return self.server

    def send(self, to_addr: str, subject: str, body: str,
             attachments=None, html_body: str = None):
        msg = EmailMessage()
        msg["From"] = f"{self.sender_name} <{self.address}>"
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")

        for path in (attachments or []):
            p = Path(path)
            if not p.exists():
                continue
            ctype, _ = mimetypes.guess_type(str(p))
            ctype = ctype or "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            msg.add_attachment(p.read_bytes(), maintype=maintype,
                               subtype=subtype, filename=p.name)

        if not self.server:
            self.connect()
        self.server.send_message(msg)
        logger.info(f"Email sent to {to_addr}")

    def close(self):
        try:
            if self.server:
                self.server.quit()
        except Exception:
            pass
        self.server = None


def _friendly_error(e: Exception) -> str:
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return ("Login failed. Use a Gmail App Password (16 characters), NOT your normal "
                "password, and make sure 2-Step Verification is turned ON for the account.")
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return "The recipient email address was rejected. Check it is spelled correctly."
    return f"Email error: {e}"


def verify_login(address: str, app_password: str):
    """Just check the credentials work. Returns (ok, message)."""
    if not address or not app_password:
        return False, "Enter both the Gmail address and the App Password."
    s = GmailSender(address, app_password)
    try:
        s.connect()
        return True, "Gmail login successful — sending is ready."
    except Exception as e:
        return False, _friendly_error(e)
    finally:
        s.close()


def send_test(address: str, app_password: str, sender_name: str = ""):
    """Send a real test email to the teacher's own address (full end-to-end check)."""
    if not address or not app_password:
        return False, "Enter both the Gmail address and the App Password."
    s = GmailSender(address, app_password, sender_name)
    try:
        s.connect()
        s.send(address, "Smart Paper Checker — Test Email ✅",
               "This is a test email from Smart Paper Checker.\n\n"
               "If you can read this, email sending is working correctly!\n\n"
               "— Smart Paper Checker")
        return True, f"Test email sent to {address}. Check your inbox (and Spam, just in case)."
    except Exception as e:
        return False, _friendly_error(e)
    finally:
        s.close()
