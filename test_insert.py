import sqlite3
from datetime import datetime
from config import DB_PATH

print("DB_PATH:", DB_PATH)
conn = sqlite3.connect(DB_PATH)
now = datetime.now().isoformat()
try:
    conn.execute(
        """
INSERT INTO Packing_Slip 
(packing_slip_number, quote_number, packing_slip_date, po_number, ship_via, delivered_by, ship_from, ship_to, client_id, created_by, created_at, modified_by, modified_at, tracking_number)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "TEST456",
            None,
            "2026-04-16",
            None,
            None,
            None,
            "Test",
            "Test",
            4,
            "admin",
            now,
            "admin",
            now,
            None,
        ),
    )
    conn.commit()
    print("Success")
except Exception as e:
    print("Error:", e)
conn.close()
