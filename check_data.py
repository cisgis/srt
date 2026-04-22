import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/srt.db')
db = conn.cursor()

locations = db.execute("SELECT name FROM Location WHERE is_yard=1 ORDER BY name").fetchall()
yards_list = [y[0] for y in locations]

print("Yards:", yards_list)

partnumbers = db.execute("SELECT parts_number, description, resale_price, rental_price FROM PartNumber ORDER BY parts_number LIMIT 5").fetchall()

availability = {}
in_transit = {}
for pn in partnumbers:
    pn_name = pn[0]
    availability[pn_name] = {}
    in_transit[pn_name] = {}
    for loc in locations:
        loc_name = loc[0]
        in_stock_count = db.execute(
            "SELECT COUNT(*) as cnt FROM Product WHERE parts_number=? AND location=? AND status='In Stock'",
            (pn_name, loc_name),
        ).fetchone()[0]
        transit_count = db.execute(
            "SELECT COUNT(*) as cnt FROM Product WHERE parts_number=? AND location=? AND status='Inbound in Transit'",
            (pn_name, loc_name),
        ).fetchone()[0]
        availability[pn_name][loc_name] = in_stock_count
        in_transit[pn_name][loc_name] = transit_count

print("\nPartNumber data:")
for pn in partnumbers:
    pn_name = pn[0]
    print(f"  {pn_name}:")
    print(f"    In Stock: {availability[pn_name]}")
    print(f"    In Transit: {in_transit[pn_name]}")

conn.close()