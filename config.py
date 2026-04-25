from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

# ── Paths ────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "srt.db"
LOGO_PATH = BASE_DIR / "app" / "static" / "img" / "logo.webp"

# Attachment subfolders
PO_ATTACHMENTS_DIR = UPLOAD_DIR / "po_attachments"
PL_ATTACHMENTS_DIR = UPLOAD_DIR / "pl_attachments"
MTR_DIR = UPLOAD_DIR / "mtr"
DRAWINGS_DIR = UPLOAD_DIR / "drawings"

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
PO_ATTACHMENTS_DIR.mkdir(exist_ok=True)
PL_ATTACHMENTS_DIR.mkdir(exist_ok=True)
MTR_DIR.mkdir(exist_ok=True)
DRAWINGS_DIR.mkdir(exist_ok=True)

# ── Company ──────────────────────────────────────────────────
COMPANY_NAME = "STEEL RIVER TECHNOLOGIES"
COMPANY_ADDRESS = "8810 E CR-95, Midland, TX 79706"
COMPANY_PHONE = "432-618-0169"
COMPANY_EMAIL_CONTACT = "contact@steelriver-tech.com"
COMPANY_EMAIL_ACCOUNTING = "accounting@steelriver-tech.com"

# ── SMTP Email ───────────────────────────────────────────────
# Use your existing business email's SMTP settings.
# Common providers:
#   Google Workspace:    smtp.gmail.com          :587
#   Microsoft 365:       smtp.office365.com      :587
#   cPanel / Hostinger:  mail.yourdomain.com     :587
#   GoDaddy:             smtpout.secureserver.net:465
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")

# ── Document number formats ──────────────────────────────────
# Q[MMDDYYYY]-[SEQ]    e.g. Q03152026-001
# PL[MMDDYYYY]-[SEQ]   e.g. PL03152026-001
# INV[MMDDYYYY]-[SEQ]  e.g. INV03152026-001
