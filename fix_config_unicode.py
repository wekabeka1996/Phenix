import re

with open('tests/test_config_migration_validation.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('❌', '[FAIL]')
content = content.replace('✅', '[OK]')

with open('tests/test_config_migration_validation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed unicode in config migration test')
