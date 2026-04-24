with open('app/routes/packing_slips.py', 'r') as f:
    content = f.read()

# Fix the status variable bug in pl_detail (line ~219)
content = content.replace(
    '            yard = pd.get("location", "")\n            if status not in products_by_status:',
    '            prod_status = pd.get("status", "")\n            if prod_status not in products_by_status:'
)
content = content.replace(
    '                products_by_status[status] = []\n            products_by_status[status].append(pd)',
    '                products_by_status[prod_status] = []\n            products_by_status[prod_status].append(pd)'
)

with open('app/routes/packing_slips.py', 'w') as f:
    f.write(content)
print('Fixed')