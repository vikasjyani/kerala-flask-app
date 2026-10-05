import re

with open('clean_cooking_forms.html', 'r') as f:
    content = f.read()

# Re-enable form validation
content = content.replace("if (false && !form.reportValidity()) {", "if (!form.reportValidity()) {")

with open('clean_cooking_forms.html', 'w') as f:
    f.write(content)
