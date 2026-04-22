import sqlite3
conn = sqlite3.connect('data/srt.db')
cur = conn.cursor()
cur.execute("SELECT name FROM Location WHERE is_yard=1 ORDER BY name")
print(cur.fetchall())
conn.close()