import sqlite3
import threading
import time
from pathlib import Path
from datetime import datetime
from config import DB_PATH


_thread_local = threading.local()
_write_lock = threading.Lock()


def get_db():
    if not hasattr(_thread_local, "conn") or _thread_local.conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level="EXCLUSIVE")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout = 60000")
        _thread_local.conn = conn

    return _thread_local.conn


def get_write_lock():
    return _write_lock


def get_current_db():
    return getattr(_thread_local, "conn", None)


def close_db(conn=None):
    if conn is None:
        if hasattr(_thread_local, "conn") and _thread_local.conn:
            try:
                _thread_local.conn.rollback()
            except:
                pass
            try:
                _thread_local.conn.close()
            except:
                pass
            _thread_local.conn = None
    elif hasattr(_thread_local, "conn") and conn == _thread_local.conn:
        try:
            conn.rollback()
        except:
            pass
        try:
            conn.close()
        except:
            pass
        _thread_local.conn = None


def get_current_user(request):
    return request.session.get("username", "unknown") if request else "system"


def timestamp():
    return datetime.now().isoformat()


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()

    if conn.execute("SELECT COUNT(*) FROM Location").fetchone()[0] == 0:
        conn.execute("INSERT INTO Location (name, is_yard) VALUES ('Midland Yard', 1)")
        conn.execute("INSERT INTO Location (name, is_yard) VALUES ('Houston Yard', 1)")
        conn.commit()

    if conn.execute("SELECT COUNT(*) FROM Status").fetchone()[0] == 0:
        statuses = [
            ("Available", 1),
            ("Pending Cert", 2),
            ("On Loan", 3),
            ("Sold", 4),
            ("Damaged", 5),
            ("In Repair", 6),
            ("Retired / Decommissioned", 7),
            ("Lost", 8),
        ]
        for name, order in statuses:
            conn.execute(
                "INSERT INTO Status (name, display_order) VALUES (?,?)", (name, order)
            )
        conn.commit()

    if conn.execute("SELECT COUNT(*) FROM Users").fetchone()[0] == 0:
        now = timestamp()
        users = [
            ("admin", "srt123", "Administrator", now),
            ("john", "john123", "John Smith", now),
            ("jane", "jane123", "Jane Doe", now),
        ]
        for username, password, display_name, created_at in users:
            conn.execute(
                "INSERT INTO Users (username, password, display_name, created_by, created_at, modified_by, modified_at) VALUES (?,?,?,?,?,?,?)",
                (username, password, display_name, "system", now, "system", now),
            )
        conn.commit()

    conn.close()


def next_doc_number(conn, prefix: str, date_str: str) -> str:
    """Generate next sequential document number.
    prefix='Q'|'PL'|'INV', date_str='MMDDYYYY' -> e.g. 'Q03152026-001'
    """
    pattern = f"{prefix}{date_str}-%"

    for attempt in range(100):
        row = conn.execute(
            "SELECT MAX(doc_number) FROM doc_sequences WHERE doc_number LIKE ?",
            (pattern,),
        ).fetchone()

        seq = 1
        if row and row[0]:
            try:
                seq = int(row[0].rsplit("-", 1)[-1]) + 1
            except (ValueError, IndexError):
                seq = 1

        doc_number = f"{prefix}{date_str}-{seq:03d}"

        try:
            conn.execute("INSERT INTO doc_sequences VALUES (?)", (doc_number,))
            conn.commit()
            return doc_number
        except sqlite3.IntegrityError:
            conn.rollback()
            continue

    raise ValueError(f"Could not generate unique document number after 100 attempts")


SCHEMA = """
CREATE TABLE IF NOT EXISTS doc_sequences (
    doc_number TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS Users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    display_name TEXT,
    is_active INTEGER DEFAULT 1,
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT
);
CREATE TABLE IF NOT EXISTS Vendor (
    name TEXT PRIMARY KEY,
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT
);
CREATE TABLE IF NOT EXISTS PartNumber (
    parts_number    TEXT PRIMARY KEY,
    description     TEXT,
    cost_price      REAL,
    resale_price    REAL,
    rental_price    REAL,
    weight          REAL,
    dimensions      TEXT,
    vendor_name     TEXT REFERENCES Vendor(name),
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT
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
    drawing_filename                TEXT,
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT
);
CREATE TABLE IF NOT EXISTS Clients (
    client_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    department      TEXT,
    company         TEXT,
    phone           TEXT,
    email           TEXT,
    site_address    TEXT,
    billing_address TEXT,
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT
);
CREATE TABLE IF NOT EXISTS Warehouse (
    warehouse_id TEXT PRIMARY KEY,
    ship_from    TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT
);
CREATE TABLE IF NOT EXISTS Location (
    name TEXT PRIMARY KEY,
    address TEXT,
    is_yard INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT
);
CREATE TABLE IF NOT EXISTS Quote (
    quote_number          TEXT PRIMARY KEY,
    quote_date            TEXT NOT NULL,
    quote_expiration_date TEXT,
    payment_term          TEXT,
    ship_to               TEXT,
    ship_from             TEXT,
    sales_tax_rate        REAL DEFAULT 0,
    client_id             TEXT REFERENCES Clients(client_id),
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT
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
    client_id            TEXT REFERENCES Clients(client_id),
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT,
    tracking_number TEXT
);
CREATE TABLE IF NOT EXISTS Invoice (
    invoice_number      TEXT PRIMARY KEY,
    packing_slip_number TEXT REFERENCES Packing_Slip(packing_slip_number),
    purchase_number     TEXT,
    payment_term        TEXT,
    invoice_date        TEXT,
    client_id           TEXT REFERENCES Clients(client_id),
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT
);
CREATE TABLE IF NOT EXISTS Transaction_External (
    transaction_ext_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    packing_slip_id     TEXT REFERENCES Packing_Slip(packing_slip_number),
    outbound_date       TEXT,
    inbound_date        TEXT,
    signature           TEXT,
    delivered_by        TEXT,
    discount            REAL DEFAULT 0,
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT
);
CREATE TABLE IF NOT EXISTS Transaction_Internal (
    transaction_int_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    from_location       TEXT,
    to_location         TEXT,
    move_date           TEXT,
    receive_date        TEXT,
    moved_by            TEXT,
    reason              TEXT,
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT
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
    address TEXT,
    is_yard INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS Status (
    name TEXT PRIMARY KEY,
    display_order INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS Quote (
    quote_number          TEXT PRIMARY KEY,
    quote_type            TEXT CHECK(quote_type IN ('SALE','RENTAL')),
    quote_date            TEXT NOT NULL,
    quote_expiration_date TEXT,
    payment_term          TEXT,
    ship_to               TEXT,
    ship_from             TEXT,
    sales_tax_rate        REAL DEFAULT 0,
    rental_days           INTEGER,
    discount              REAL DEFAULT 0,
    shipping_cost         REAL DEFAULT 0,
    client_id             TEXT,
    contact_person        TEXT,
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT
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
    client_id            TEXT REFERENCES Clients(client_id),
    tracking_number TEXT
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
CREATE TABLE IF NOT EXISTS Packing_Slip_Items (
    item_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    packing_slip_number  TEXT NOT NULL REFERENCES Packing_Slip(packing_slip_number) ON DELETE CASCADE,
    parts_number         TEXT NOT NULL,
    serial_number        TEXT NOT NULL
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
