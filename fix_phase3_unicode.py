import re

with open('tests/test_phase3_psi_vector.py', 'r', encoding='utf-8') as f:
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
    '📋': '[LIST]',
    '✓': '[V]',
    '✗': '[X]',
}

for emoji, text in replacements.items():
    content = content.replace(emoji, text)

with open('tests/test_phase3_psi_vector.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed unicode in phase3 test')
