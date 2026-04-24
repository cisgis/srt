import sqlite3
conn = sqlite3.connect('srt.db')
c = conn.cursor()
c.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
for r in c.fetchall():
    print(r)
conn.close()