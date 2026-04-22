import sqlite3
conn = sqlite3.connect('data/srt.db')
cur = conn.cursor()

cur.execute("SELECT name FROM Location WHERE is_yard=1 ORDER BY name")
yards = cur.fetchall()

cur.execute("SELECT parts_number FROM PartNumber WHERE parts_number='SRT-SS-96'")
partnumbers = cur.fetchall()

for pn in partnumbers:
    print(f"Partnumber: {pn[0]}")
    for yard in yards:
        yard_name = yard[0]
        cur.execute(
            "SELECT COUNT(*) FROM Product WHERE parts_number=? AND location=? AND status=?",
            (pn[0], yard_name, 'Inbound in Transit')
        )
        transit_count = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM Product WHERE parts_number=? AND location=? AND status=?",
            (pn[0], yard_name, 'In Stock')
        )
        in_stock_count = cur.fetchone()[0]
        print(f"  {yard_name}: in_stock={in_stock_count}, in_transit={transit_count}")

conn.close()