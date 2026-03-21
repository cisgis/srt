# Steel River Technologies — Inventory & Billing System

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Add your logo
Place your logo image as:
```
app/static/img/logo.png
```
(PNG or JPG, recommended ~200x200px. Used on all PDF documents.)

### 3. Configure Gmail
Open `config.py` and fill in:
```python
SMTP_USER     = "your@gmail.com"
SMTP_PASSWORD = "your-app-password"   # Gmail App Password (not your login password)
SMTP_FROM     = "your@gmail.com"
```

To create a Gmail App Password:
1. Go to https://myaccount.google.com/security
2. Enable 2-Factor Authentication
3. Go to App Passwords → create one for "Mail"
4. Paste the 16-character password into config.py

### 4. Run
```bash
python main.py
```
Then open: http://127.0.0.1:8000

---

## Project Structure
```
srt/
├── main.py                         # FastAPI app entry point
├── config.py                       # SMTP, paths, company info
├── requirements.txt
├── data/
│   ├── srt.db                      # SQLite database (auto-created)
│   └── uploads/                    # MTR and Drawing PDFs
└── app/
    ├── database.py                 # DB connection + schema
    ├── routes/
    │   ├── inventory.py            # Inventory CRUD
    │   ├── quotes.py               # Quotes + PDF + email
    │   ├── packing_slips.py        # Packing slips + PDF + email
    │   ├── invoices.py             # Invoices + PDF + email
    │   └── other.py                # Clients, Vendors, Transactions
    ├── services/
    │   ├── pdf_service.py          # ReportLab PDF generation
    │   └── email_service.py        # Gmail SMTP sending
    ├── templates/
    │   ├── base.html               # Sidebar layout
    │   ├── dashboard.html
    │   ├── inventory/
    │   ├── quotes/
    │   ├── packing_slips/
    │   ├── invoices/
    │   ├── clients/
    │   ├── vendors/
    │   └── transactions/
    └── static/
        ├── css/main.css
        └── img/logo.png            # ← place your logo here
```

---

## Document Number Formats
| Document     | Format               | Example             |
|--------------|----------------------|---------------------|
| Quote        | Q[MMDDYYYY]-[SEQ]    | Q03152026-001       |
| Packing Slip | PL[MMDDYYYY]-[SEQ]   | PL03152026-001      |
| Invoice      | INV[MMDDYYYY]-[SEQ]  | INV03152026-001     |

---

## Billing Workflow
```
Quote  →  Packing Slip  →  Invoice
  ↓             ↓              ↓
PDF+Email    PDF+Email     PDF+Email
```
Each stage has a "→ Create" button that pre-fills data from the previous stage.

---

## Status Values (Product)
- Available
- Pending Certification
- On Loan
- Sold
- Damaged
- In Repair
- Retired / Decommissioned
- Lost

---

## Notes
- Database file is `data/srt.db` — back this up regularly
- Uploaded PDFs (MTR, Drawing) are stored in `data/uploads/`
- Sales tax is stored as a decimal (e.g. 0.08 = 8%) — entered as % in the UI
- quoted_price is a snapshot locked at time of quote creation
