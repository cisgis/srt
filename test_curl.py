import requests
import re

session = requests.Session()
session.post("http://127.0.0.1:8000/login", data={"username": "admin", "password": "admin"})
r = session.get("http://127.0.0.1:8000/quotes/Q04202026-003")

# Find the button
match = re.search(r'<button[^>]*Add Item[^>]*>', r.text)
if match:
    print("Button HTML:", match.group(0))
else:
    print("Button not found")

# Check for the test-add-btn
if 'test-add-btn' in r.text:
    print("test-add-btn found in page")
    
# Check for onclick
if 'onclick="addLineItem()"' in r.text:
    print("onclick still exists!")
else:
    print("onclick removed")