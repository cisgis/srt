import requests
s = requests.Session()
s.post("http://127.0.0.1:8000/login", data={"username": "admin", "password": "admin"})
r = s.get("http://127.0.0.1:8000/quotes/Q04202026-003")

# Find lines containing "Add Item"
lines = r.text.split('\n')
for i, line in enumerate(lines):
    if 'Add Item' in line:
        print(f"Line {i}: {line.strip()}")