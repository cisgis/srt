import requests
import re
import json

resp = requests.get("http://localhost:8000/quotes/new")
print("Status:", resp.status_code)

# Find partnumbers_json in the response
match = re.search(r'const partnumbers = (\[.*?\]);', resp.text, re.DOTALL)
if match:
    data = match.group(1)
    try:
        partnumbers = json.loads(data)
        for pn in partnumbers:
            if pn.get('parts_number') == 'SRT-SS-96':
                print("Keys in SRT-SS-96:", list(pn.keys()))
    except Exception as e:
        print("Error:", e)