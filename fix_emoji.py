#!/usr/bin/env python3
import os
os.chdir(r'c:\Users\asanu\OneDrive\Desktop\dating-bot')

# Read file
with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the corrupted replacement character with proper key emoji
# \ufffd is the Unicode replacement character
content = content.replace('\ufffd Unlock Chat', '🔑 Unlock Chat')

# Write back
with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ Emoji fixed: All 🔑 emojis are now correct')
