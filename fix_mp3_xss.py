#!/usr/bin/env python3
"""Fix XSS bug in mp3.js escHtml function"""

with open('public/js/mp3.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and fix line 360 (index 359)
for i, line in enumerate(lines):
    if i == 359 and "replace(/&/g, '&')" in line:
        lines[i] = "    return String(str).replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>');\n"
        print(f"Fixed line {i+1}")
        break

with open('public/js/mp3.js', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("XSS bug fixed in mp3.js")