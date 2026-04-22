import sqlite3
conn = sqlite3.connect('data/srt.db')
cur = conn.cursor()
cur.execute("PRAGMA table_info(Quote_Items)")
print("Quote_Items columns:", [r[1] for r in cur.fetchall()])
conn.close()