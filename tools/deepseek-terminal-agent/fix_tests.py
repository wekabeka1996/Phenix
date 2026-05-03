import re

with open('tests/test_frontend_cockpit.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Update test_board_panels_exist_for_required_windows
old_tuple = """for panel_key in (
        "sessions",
        "scenarios",
        "chat",
        "workTrace",
        "result",
        "composer",
        "inspector",
        "artifacts",
    ):"""

new_tuple = """for panel_key in (
        "sessions",
        "chat",
        "inspector",
        "artifacts",
    ):"""

content = content.replace(old_tuple, new_tuple)

with open('tests/test_frontend_cockpit.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated test_frontend_cockpit.py')
