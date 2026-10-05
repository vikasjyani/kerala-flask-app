import re

with open('clean_cooking_forms.html', 'r') as f:
    content = f.read()

# Fix the quotes directly in the HTML file
content = content.replace("opt.trim() !== 'None ('Select an option' prompt)'", "opt.trim() !== 'None (\\'Select an option\\' prompt)'")
content = content.replace("opt.trim() !== 'None ('Select District' prompt)'", "opt.trim() !== 'None (\\'Select District\\' prompt)'")

with open('clean_cooking_forms.html', 'w') as f:
    f.write(content)
