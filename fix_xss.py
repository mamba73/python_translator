import sys

# Fix mp3.js XSS bug
with open('public/js/mp3.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the incorrect HTML entities with correct ones
content = content.replace(
    "return String(str).replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>');",
    "return String(str).replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>');"
)

with open('public/js/mp3.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed mp3.js XSS bug")