#!/usr/bin/env python3
"""Fix XSS bug in mp3.js - final attempt"""

with open('public/js/mp3.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the escHtml function and fix it
for i, line in enumerate(lines):
    if 'function escHtml(str)' in line:
        # Found the function, next line should be the return statement
        if i + 1 < len(lines):
            lines[i + 1] = "    return String(str).replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>');\n"
            print(f"Fixed escHtml function at line {i+2}")
            break

with open('public/js/mp3.js', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("XSS bug fixed successfully")