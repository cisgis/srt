import sqlite3
conn = sqlite3.connect('data/srt.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

yards = cur.execute("SELECT name FROM Location WHERE is_yard=1 ORDER BY name").fetchall()
yards_list = [y["name"] for y in yards]

# Try the query that should work
yard_case = ", ".join(
    [
        f"COALESCE(SUM(CASE WHEN p.location = '{y['name']}' AND p.status = 'In Stock' THEN 1 ELSE 0 END), 0) as {y['name'].lower().replace(' ', '_')}_in_stock, "
        f"COALESCE(SUM(CASE WHEN p.location = '{y['name']}' AND p.status = 'Inbound in Transit' THEN 1 ELSE 0 END), 0) as {y['name'].lower().replace(' ', '_')}_in_transit"
        for y in yards
    ]
)

query = f"""
SELECT 
    pn.parts_number,
    pn.description,
    pn.resale_price,
    pn.rental_price,
    {yard_case}
FROM PartNumber pn
LEFT JOIN Product p ON pn.parts_number = p.parts_number
GROUP BY pn.parts_number
ORDER BY pn.parts_number
"""

try:
    cur.execute(query)
    print("Query succeeded!")
    rows = cur.fetchall()
    print("Got", len(rows), "rows")
except Exception as e:
    print("Error:", e)

conn.close()