import sqlite3
conn = sqlite3.connect('data/srt.db')
conn.execute('ALTER TABLE Quote_Items ADD COLUMN status TEXT DEFAULT "In Stock"')
conn.commit()
print("Done")
conn.close()