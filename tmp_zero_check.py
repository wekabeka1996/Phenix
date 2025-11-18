from pathlib import Path
raw = Path('apps/reference/domains/execution_position/manage_config.py').read_bytes()
print(any(b == 0 for b in raw))
