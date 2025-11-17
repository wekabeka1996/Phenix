from pathlib import Path
path = Path('tests/test_config_symbols.py')
data = path.read_bytes()
marker = b'AuroraConfig Tests'
idx = data.index(marker)
print(idx)
print(data[idx-40:idx+40])
