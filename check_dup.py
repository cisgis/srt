import sqlite3
conn = sqlite3.connect('data/srt.db')
cur = conn.cursor()
cur.execute("SELECT parts_number, location, status, COUNT(*) as cnt FROM Product GROUP BY parts_number, location, status ORDER BY parts_number, location")
rows = cur.fetchall()
for r in rows[:15]:
    print(r)
conn.close()