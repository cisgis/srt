import sqlite3
conn = sqlite3.connect('data/srt.db')
c = conn.cursor()

c.execute('PRAGMA foreign_keys=OFF')

c.execute('DROP TABLE IF EXISTS Invoice_new')
c.execute('''CREATE TABLE Invoice_new (
    invoice_number      TEXT PRIMARY KEY,
    packing_slip_number TEXT REFERENCES Packing_Slip(packing_slip_number),
    purchase_number   TEXT,
    po_attachment_path TEXT,
    payment_term      TEXT,
    invoice_date      TEXT,
    client_id         TEXT,
    created_by TEXT,
    created_at TEXT,
    modified_by TEXT,
    modified_at TEXT,
    status TEXT DEFAULT 'OPEN'
)''')

c.execute('INSERT INTO Invoice_new SELECT * FROM Invoice')
c.execute('DROP TABLE Invoice')
c.execute('ALTER TABLE Invoice_new RENAME TO Invoice')

c.execute('PRAGMA foreign_keys=ON')
conn.commit()
print('Fixed Invoice table - removed Clients_old FK')
conn.close()