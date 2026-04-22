from jinja2 import Environment, FileSystemLoader

# Load the template
env = Environment(loader=FileSystemLoader('app/templates/quotes'))
template = env.get_template('edit.html')

# Simulate the context
context = {
    'quote': {'contact_person': 'John Smith'},
    'selected_company': 'Shell',
    'clients_by_company': {'Shell': [{'name': 'John Smith'}]},
}

# Render a portion to see what it produces
result = template.render(**context)

# Find the JS section
import re
match = re.search(r'const savedContact = "(.*?)"', result)
print("savedContact:", repr(match.group(1)) if match else "NOT FOUND")

match2 = re.search(r'initialCompany && clientsByCompany\[initialCompany\]\) \{', result)
print("Condition exists:", match2 is not None)