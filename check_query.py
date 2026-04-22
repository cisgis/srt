import sqlite3
conn = sqlite3.connect('data/srt.db')
conn.row_factory = sqlite3.Row
db = conn.cursor()

yards = db.execute("SELECT name FROM Location WHERE is_yard=1 ORDER BY name").fetchall()
yards_list = [y[0] for y in yards]

yard_case = ", ".join(
    [
        f"COALESCE(SUM(CASE WHEN p.location = '{y[0]}' AND p.status = 'In Stock' THEN 1 ELSE 0 END), 0) as {y[0].lower().replace(' ', '_')}_in_stock, "
        f"COALESCE(SUM(CASE WHEN p.location = '{y[0]}' AND p.status = 'Inbound in Transit' THEN 1 ELSE 0 END), 0) as {y[0].lower().replace(' ', '_')}_in_transit"
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
    WHERE pn.parts_number = 'SRT-SS-96'
    GROUP BY pn.parts_number
"""

partnumbers = db.execute(query).fetchall()
for pn in partnumbers:
    pn_dict = dict(pn)
    print("Raw row keys:", list(pn_dict.keys()))
    
    avail = {}
    in_transit = {}
    for yard in yards_list:
        col_name = yard.lower().replace(" ", "_")
        avail[yard] = pn_dict.get(f"{col_name}_in_stock", 0)
        in_transit[yard] = pn_dict.get(f"{col_name}_in_transit", 0)
    
    print(f"Availability for SRT-SS-96:")
    print(f"  In Stock: {avail}")
    print(f"  In Transit: {in_transit}")

conn.close()