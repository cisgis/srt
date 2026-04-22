import sqlite3
conn = sqlite3.connect('data/srt.db')
cur = conn.cursor()
cur.execute("SELECT quote_number, COUNT(*) as cnt FROM Quote_Items GROUP BY quote_number ORDER BY quote_number DESC LIMIT 10")
print("Quotes with items:")
for row in cur.fetchall():
    print(row)
conn.close()