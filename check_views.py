import sqlite3
conn = sqlite3.connect('data/srt.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='view'")
print("Views:", cur.fetchall())
conn.close()