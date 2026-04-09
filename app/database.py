import sqlite3
from pathlib import Path
from config import DB_PATH


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def next_doc_number(conn, prefix: str, date_str: str) -> str:
    """Generate next sequential document number.
    prefix='Q'|'PL'|'INV', date_str='MMDDYYYY' -> e.g. 'Q03152026-001'

    FIX (Bug 3): Previously used COUNT(*) which broke if any doc in the
    sequence was deleted — e.g. deleting -002 after creating -003 would
    re-generate -002 and crash on the PRIMARY KEY constraint.
    Now uses MAX to find the highest existing sequence number so it always
    increments correctly regardless of gaps.
    """
    pattern = f"{prefix}{date_str}-%"
    row = conn.execute(
        "SELECT MAX(doc_number) FROM doc_sequences WHERE doc_number LIKE ?", (pattern,)
    ).fetchone()

    seq = 1
    if row and row[0]:
        # doc_number format is e.g. "Q03152026-007" — parse the trailing digits
        try:
            seq = int(row[0].rsplit("-", 1)[-1]) + 1
        except (ValueError, IndexError):
            seq = 1

    doc_number = f"{prefix}{date_str}-{seq:03d}"
    conn.execute("INSERT INTO doc_sequences VALUES (?)", (doc_number,))
    return doc_number


SCHEMA = """
CREATE TABLE IF NOT EXISTS doc_sequences (
    doc_number TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS Vendor (
    name TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS PartNumber (
    parts_number    TEXT PRIMARY KEY,
    description     TEXT,
    cost_price      REAL,
    resale_price    REAL,
    rental_price    REAL,
    weight          REAL,
    dimensions      TEXT,
    vendor_name     TEXT REFERENCES Vendor(name)
);
CREATE TABLE IF NOT EXISTS Product (
    serial_number                   TEXT PRIMARY KEY,
    parts_number                    TEXT NOT NULL REFERENCES PartNumber(parts_number),
    status                          TEXT CHECK(status IN (
                                         'Available','Pending Certification','On Loan',
                                         'Sold','Damaged','In Repair',
                                         'Retired / Decommissioned','Lost')),
    location                        TEXT,
    receiving_date                  TEXT,
    certification_expiration_date   TEXT,
    mtr_filename                    TEXT,
    drawing_filename                TEXT
);
CREATE TABLE IF NOT EXISTS Clients (
    client_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    department      TEXT,
    company         TEXT,
    phone           TEXT,
    email           TEXT,
    site_address    TEXT,
    billing_address TEXT
);
CREATE TABLE IF NOT EXISTS Warehouse (
    warehouse_id TEXT PRIMARY KEY,
    ship_from    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS Location (
    name TEXT PRIMARY KEY,
    address TEXT
);
CREATE TABLE IF NOT EXISTS Quote (
    quote_number          TEXT PRIMARY KEY,
    quote_date            TEXT NOT NULL,
    quote_expiration_date TEXT,
    payment_term          TEXT,
    ship_to               TEXT,
    ship_from             TEXT,
    sales_tax_rate        REAL DEFAULT 0,
    client_id             TEXT REFERENCES Clients(client_id)
);
CREATE TABLE IF NOT EXISTS Quote_Items (
    item_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_number  TEXT    NOT NULL REFERENCES Quote(quote_number) ON DELETE CASCADE,
    parts_number  TEXT    NOT NULL REFERENCES PartNumber(parts_number),
    quantity      INTEGER NOT NULL DEFAULT 1,
    quoted_price  REAL,
    lead_time     TEXT
);
CREATE TABLE IF NOT EXISTS Packing_Slip (
    packing_slip_number  TEXT PRIMARY KEY,
    quote_number         TEXT REFERENCES Quote(quote_number),
    packing_slip_date    TEXT,
    po_number            TEXT,
    ship_via             TEXT,
    delivered_by         TEXT,
    ship_from            TEXT,
    ship_to              TEXT,
    client_id            TEXT REFERENCES Clients(client_id)
);
CREATE TABLE IF NOT EXISTS Invoice (
    invoice_number      TEXT PRIMARY KEY,
    packing_slip_number TEXT REFERENCES Packing_Slip(packing_slip_number),
    purchase_number     TEXT,
    payment_term        TEXT,
    invoice_date        TEXT,
    client_id           TEXT REFERENCES Clients(client_id)
);
CREATE TABLE IF NOT EXISTS Transaction_External (
    transaction_ext_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    packing_slip_id     TEXT REFERENCES Packing_Slip(packing_slip_number),
    outbound_date       TEXT,
    inbound_date        TEXT,
    signature           TEXT,
    delivered_by        TEXT,
    discount            REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS Transaction_External_Items (
    item_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_ext_id INTEGER NOT NULL REFERENCES Transaction_External(transaction_ext_id) ON DELETE CASCADE,
    serial_number      TEXT    NOT NULL REFERENCES Product(serial_number)
);
CREATE TABLE IF NOT EXISTS Transaction_Internal (
    transaction_int_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    from_location       TEXT,
    to_location         TEXT,
    move_date           TEXT,
    receive_date        TEXT,
    moved_by            TEXT,
    reason              TEXT
);
CREATE TABLE IF NOT EXISTS Transaction_Internal_Items (
    item_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_int_id INTEGER NOT NULL REFERENCES Transaction_Internal(transaction_int_id) ON DELETE CASCADE,
    serial_number      TEXT    NOT NULL REFERENCES Product(serial_number)
);
CREATE TABLE IF NOT EXISTS Email_Log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type        TEXT NOT NULL CHECK(doc_type IN ('quote','packing_slip','invoice')),
    doc_number      TEXT NOT NULL,
    to_email        TEXT NOT NULL,
    subject         TEXT,
    sent_at         TEXT DEFAULT (datetime('now')),
    status          TEXT NOT NULL CHECK(status IN ('sent','failed')),
    error_message   TEXT
);
CREATE TABLE IF NOT EXISTS Product_Lifecycle (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    serial_number   TEXT NOT NULL REFERENCES Product(serial_number),
    change_date     TEXT NOT NULL,
    old_status      TEXT,
    new_status      TEXT,
    old_location    TEXT,
    new_location    TEXT,
    transaction_type TEXT NOT NULL CHECK(transaction_type IN ('INTERNAL','EXTERNAL'))
);
"""
