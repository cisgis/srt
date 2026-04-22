import sqlite3
import json
conn = sqlite3.connect('data/srt.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check PL items
cur.execute("SELECT * FROM Packing_Slip_Items WHERE packing_slip_number='PL04192026-002'")
items = cur.fetchall()
print("PL Items:")
for r in items:
    print(dict(r))

# Check products for SRT-SS-96
cur.execute("SELECT * FROM Product WHERE parts_number='SRT-SS-96'")
prods = cur.fetchall()
print("\nProducts for SRT-SS-96:")
for r in prods:
    print(dict(r))