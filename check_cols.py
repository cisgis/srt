import sqlite3
conn = sqlite3.connect('data/srt.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("PRAGMA table_info(Product)")
print("Product columns:", [r['name'] for r in cur.fetchall()])
conn.close()