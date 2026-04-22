import json
from app.database import get_db, close_db

db = get_db()

# Simulate NEW route query
yards = db.execute('SELECT name FROM Location WHERE is_yard=1 ORDER BY name').fetchall()
yards_list = [y['name'] for y in yards]

print("=== YARDS ===")
print(yards_list)

# NEW route approach
yard_case = ", ".join([
    f"COALESCE(SUM(CASE WHEN p.location = '{y['name']}' AND p.status = 'In Stock' THEN 1 ELSE 0 END), 0) as {y['name'].lower().replace(' ', '_')}_in_stock, "
    f"COALESCE(SUM(CASE WHEN p.location = '{y['name']}' AND p.status = 'Inbound in Transit' THEN 1 ELSE 0 END), 0) as {y['name'].lower().replace(' ', '_')}_in_transit"
    for y in yards
])

new_route_pns = db.execute(f"""
    SELECT 
        pn.parts_number,
        pn.description,
        pn.resale_price,
        pn.rental_price,
        {yard_case}
    FROM PartNumber pn
    LEFT JOIN Product p ON pn.parts_number = p.parts_number
    GROUP BY pn.parts_number
""").fetchall()

# EDIT route approach (separate queries)
edit_route_pns = db.execute('SELECT parts_number, description, resale_price, rental_price FROM PartNumber ORDER BY parts_number').fetchall()

print("\n=== Checking SRT-SS-96 ===")
print("NEW route:")
for pn in new_route_pns:
    if pn['parts_number'] == 'SRT-SS-96':
        pn_dict = dict(pn)
        print(f"  keys: {list(pn_dict.keys())}")
        for y in yards_list:
            col = y.lower().replace(' ', '_')
            print(f"  {col}_in_stock: {pn_dict.get(col + '_in_stock', 'NOT FOUND')}")
            print(f"  {col}_in_transit: {pn_dict.get(col + '_in_transit', 'NOT FOUND')}")
        break

print("\nEDIT route:")
locations = db.execute('SELECT name FROM Location WHERE is_yard=1 ORDER BY name').fetchall()
availability = {}
in_transit = {}
for pn in edit_route_pns:
    if pn['parts_number'] == 'SRT-SS-96':
        pn_name = pn['parts_number']
        availability[pn_name] = {}
        in_transit[pn_name] = {}
        for loc in locations:
            loc_name = loc['name']
            in_stock_count = db.execute(
                'SELECT COUNT(*) as cnt FROM Product WHERE parts_number=? AND location=? AND status=?',
                (pn_name, loc_name, 'In Stock'),
            ).fetchone()['cnt']
            transit_count = db.execute(
                'SELECT COUNT(*) as cnt FROM Product WHERE parts_number=? AND location=? AND status=?',
                (pn_name, loc_name, 'Inbound in Transit'),
            ).fetchone()['cnt']
            availability[pn_name][loc_name] = in_stock_count
            in_transit[pn_name][loc_name] = transit_count
        
        print(f"  availability: {availability[pn_name]}")
        print(f"  in_transit: {in_transit[pn_name]}")

close_db()
