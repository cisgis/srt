import json
from app.database import get_db, close_db
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# Login first
login_response = client.post("/login", data={"username": "admin", "password": "admin"})
print(f"Login: {login_response.status_code}")

# Access an edit page
response = client.get("/quotes/Q04202026-003")
print(f"Edit page: {response.status_code}")

# Check if response contains in_transit data
content = response.text

# Find the partnumbers JSON
import re
match = re.search(r'const partnumbers = (\[\{.*?\});', content, re.DOTALL)
if match:
    # Try to parse a small portion
    try:
        pn_match = re.search(r'"parts_number": "SRT-SS-96"', content)
        if pn_match:
            # Find surrounding context
            start = max(0, pn_match.start() - 500)
            end = min(len(content), pn_match.end() + 500)
            print("Context around SRT-SS-96:")
            print(content[start:end])
    except Exception as e:
        print(f"Error: {e}")

# Also check the JavaScript variables
yards_match = re.search(r'const yards = (\[[\w, "\s]+\]);', content)
if yards_match:
    print("\nyards variable:")
    print(yards_match.group())

# Check what's being logged in console
if "in_transit" in content:
    print("\n'in_transit' found in response")
else:
    print("\n'in_transit' NOT found in response")