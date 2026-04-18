import sqlite3

conn = sqlite3.connect("data/srt.db")
cur = conn.execute(
    "SELECT doc_number FROM doc_sequences WHERE doc_number LIKE 'PL%' ORDER BY doc_number DESC LIMIT 10"
)
print([r[0] for r in cur.fetchall()])
cur = conn.execute(
    "SELECT packing_slip_number FROM Packing_Slip ORDER BY created_at DESC LIMIT 10"
)
print([r[0] for r in cur.fetchall()])
conn.close()
