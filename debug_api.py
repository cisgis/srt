import requests

resp = requests.get("http://localhost:8000/quotes/new")

# Check for duplicate IDs
import re
ids = re.findall(r'id="[^"]*"', resp.text)
from collections import Counter
dupes = [id for id, count in Counter(ids).items() if count > 1]
print("Duplicate IDs:", dupes)

# Check for onchange
onchanges = re.findall(r'onchange="[^"]*"', resp.text)
print("onchange attributes:", onchanges)