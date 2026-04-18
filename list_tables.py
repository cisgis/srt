import sqlite3

conn = sqlite3.connect("data/srt.db")
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
print([r[0] for r in cur.fetchall()])
conn.close()
