"""
Email service — sends PDF documents via Gmail SMTP.
Uses Python stdlib smtplib (no aiosmtplib needed).
"""
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config


def send_document_email(
    to_address: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> dict:
    """
    Send an email with a PDF attachment via Gmail SMTP.
    Returns {"ok": True} or {"ok": False, "error": "..."}
    """
    try:
        msg = EmailMessage()
        msg["From"]    = config.SMTP_FROM
        msg["To"]      = to_address
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
    except Exception as e:
        return {"ok": False, "error": str(e)}
