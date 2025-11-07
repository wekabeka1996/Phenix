import re

# Read with UTF-8
with open('tests/test_features_and_signals_live.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace Unicode emoji with text
replacements = {
    '📊': '[CHART]',
    '✅': '[OK]',
    '📈': '[TREND]',
    '📋': '[LIST]',
    '📉': '[DOWN]',
    '⚡': '[FLASH]',
    '🎯': '[TARGET]',
    '💰': '[MONEY]',
    '🔥': '[FIRE]',
    '📢': '[ANNOUNCE]',
    '🚀': '[ROCKET]',
    '⚠️': '[WARN]',
}

for emoji, text in replacements.items():
    content = content.replace(emoji, text)

# Write with UTF-8
with open('tests/test_features_and_signals_live.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed unicode characters')
