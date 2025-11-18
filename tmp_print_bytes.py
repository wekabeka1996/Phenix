from pathlib import Path
raw = Path('apps/reference/domains/execution_position/manage_config.py').read_bytes()
print(raw[:10])
print(len(raw))
