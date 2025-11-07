import re

with open('tests/test_phase5_regression.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace all unicode emojis with text
replacements = {
    '✅': '[OK]',
    '❌': '[FAIL]',
    '📊': '[CHART]',
    '📈': '[TREND]',
    '⚠️': '[WARN]',
    '⭐': '[STAR]',
    '🔥': '[FIRE]',
    '✓': '[V]',
    '✗': '[X]',
    '→': '->',
    '←': '<-',
    '∼': '~',
    '±': '+/-',
}

for emoji, text in replacements.items():
    content = content.replace(emoji, text)

with open('tests/test_phase5_regression.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed unicode in phase5 regression test')
