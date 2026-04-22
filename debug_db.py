import sqlite3
import json

# First manually run the query as done in quotes.py to see what we get
from app.database import get_db, close_db

db = get_db()

yards = db.execute("SELECT name FROM Location WHERE is_yard=1 ORDER BY name").fetchall()
yards_list = [y["name"] for y in yards]

yard_case = ", ".join(
    [
        f"COALESCE(SUM(CASE WHEN p.location = '{y['name']}' AND p.status = 'In Stock' THEN 1 ELSE 0 END), 0) as {y['name'].lower().replace(' ', '_')}_in_stock, "
        f"COALESCE(SUM(CASE WHEN p.location = '{y['name']}' AND p.status = 'Inbound in Transit' THEN 1 ELSE 0 END), 0) as {y['name'].lower().replace(' ', '_')}_in_transit"
        for y in yards
    ]
)

partnumbers = db.execute(f"""
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
""").fetchall()

# Check SRT-SS-96
partnumbers_json = []
for pn in partnumbers:
    pn_dict = dict(pn)
    if pn_dict.get('parts_number') == 'SRT-SS-96':
        print("Raw pn_dict for SRT-SS-96:", pn_dict)
    
    avail = {}
    in_transit = {}
    for yard in yards_list:
        col_name = yard.lower().replace(" ", "_")
        avail[yard] = pn_dict.get(f"{col_name}_in_stock", 0)
        in_transit[yard] = pn_dict.get(f"{col_name}_in_transit", 0)
        for key in [f"{col_name}_in_stock", f"{col_name}_in_transit"]:
            if key in pn_dict:
                del pn_dict[key]
    pn_dict["availability"] = avail
    pn_dict["in_transit"] = in_transit
    partnumbers_json.append(pn_dict)

# Find SRT-SS-96 in result
for pn in partnumbers_json:
    if pn.get('parts_number') == 'SRT-SS-96':
        print("\nFinal JSON for SRT-SS-96:")
        print(json.dumps(pn, indent=2))

close_db()