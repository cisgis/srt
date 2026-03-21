from pathlib import Path

# ── Paths ────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
DATA_DIR      = BASE_DIR / "data"
UPLOAD_DIR    = DATA_DIR / "uploads"
DB_PATH       = DATA_DIR / "srt.db"
LOGO_PATH     = BASE_DIR / "app" / "static" / "img" / "logo.png"

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

# ── Company ──────────────────────────────────────────────────
COMPANY_NAME    = "STEEL RIVER TECHNOLOGIES"
COMPANY_ADDRESS = "8810 E CR-95, Midland, TX 79706"
COMPANY_PHONE   = "432-618-0169"
COMPANY_EMAIL_CONTACT   = "contact@steelriver-tech.com"
COMPANY_EMAIL_ACCOUNTING = "accounting@steelriver-tech.com"

# ── Gmail SMTP ───────────────────────────────────────────────
# Fill these in before running. Use an App Password, not your real password.
# https://support.google.com/accounts/answer/185833
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "your@gmail.com"        # ← change
SMTP_PASSWORD = "your-app-password"     # ← change
SMTP_FROM     = "your@gmail.com"        # ← change

# ── Document number formats ──────────────────────────────────
# Q[MMDDYYYY]-[SEQ]    e.g. Q03152026-001
# PL[MMDDYYYY]-[SEQ]   e.g. PL03152026-001
# INV[MMDDYYYY]-[SEQ]  e.g. INV03152026-001
