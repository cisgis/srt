import sqlite3

conn = sqlite3.connect("data/srt.db")
cur = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%old%'"
)
print("Old tables:", [r[0] for r in cur.fetchall()])
# Also check schema
cur = conn.execute("SELECT sql FROM sqlite_master WHERE name='Packing_Slip'")
print("Schema:", cur.fetchone())
conn.close()
