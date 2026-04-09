import re

with open('c:/Users/asanu/OneDrive/Desktop/dating-bot/bot2.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'Hey � Welcome!', '**Hey 😉 Welcome!**', content)

with open('c:/Users/asanu/OneDrive/Desktop/dating-bot/bot2.py', 'w', encoding='utf-8') as f:
    f.write(content)