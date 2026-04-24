import sqlite3
conn = sqlite3.connect('srt.db')
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:")
for r in c.fetchall():
    print(f"  {r[0]}")

c.execute("SELECT name FROM sqlite_master WHERE type='view'")
print("\nViews:")
for r in c.fetchall():
    print(f"  {r[0]}")

c.execute("PRAGMA foreign_key_list(Invoice)")
print("\nInvoice FKs:")
for r in c.fetchall():
    print(f"  {r}")

conn.close()