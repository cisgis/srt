import sqlite3

conn = sqlite3.connect("data/srt.db")
conn.execute("DROP TABLE IF EXISTS Packing_Slip")
conn.execute("""
CREATE TABLE Packing_Slip (
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
)
""")
conn.commit()
# Verify
cur = conn.execute("SELECT sql FROM sqlite_master WHERE name='Packing_Slip'")
print("Schema:", cur.fetchone()[0][:100])
conn.close()
print("Fixed")
