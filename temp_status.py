import sqlite3
conn = sqlite3.connect('data/srt.db')
cur = conn.cursor()

# Update status name from Available to In Stock
cur.execute("UPDATE Status SET name='In Stock' WHERE name='Available'")
conn.commit()
print("Status name updated")

# Update product status in Product table
cur.execute("UPDATE Product SET status='In Stock' WHERE status='Available'")
conn.commit()
print("Product status updated")

# Verify
cur.execute("SELECT * FROM Status ORDER BY display_order")
rows = cur.fetchall()
print("\nUpdated statuses:")
for r in rows:
    print(r)

conn.close()