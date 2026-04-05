"""
Email service — sends PDF documents via SMTP.
Uses Python stdlib smtplib. Credentials come from .env file.
"""

import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config


def validate_email(email: str) -> bool:
    """Basic RFC 5322-ish email validation."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email.strip()))


def send_document_email(
    to_address: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> dict:
    """
    Send an email with a PDF attachment via SMTP.
    Returns {"ok": True} or {"ok": False, "error": "..."}
    """
    if not config.SMTP_USER:
        return {
            "ok": False,
            "error": "SMTP_USER not configured. Add SMTP credentials to .env file.",
        }

    if not config.SMTP_PASSWORD:
        return {
            "ok": False,
            "error": "SMTP_PASSWORD not configured. Add SMTP credentials to .env file.",
        }

    if not config.SMTP_FROM:
        return {
            "ok": False,
            "error": "SMTP_FROM not configured. Set it to your business email in .env",
        }

    if not validate_email(to_address):
        return {"ok": False, "error": f"Invalid email address: {to_address}"}

    try:
        msg = EmailMessage()
        msg["From"] = config.SMTP_FROM
        msg["To"] = to_address.strip()
        msg["Subject"] = subject
        msg.set_content(body)
        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=pdf_filename,
        )

        ctx = ssl.create_default_context()
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)

        return {"ok": True}
    except smtplib.SMTPAuthenticationError:
        return {
            "ok": False,
            "error": "SMTP authentication failed. Check your username and password (or app password).",
        }
    except smtplib.SMTPConnectError:
        return {
            "ok": False,
            "error": f"Could not connect to {config.SMTP_HOST}:{config.SMTP_PORT}. Check SMTP host and port.",
        }
    except smtplib.SMTPException as e:
        return {"ok": False, "error": f"SMTP error: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
