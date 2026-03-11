import os
import re
import yaml
from pathlib import Path

# 1. Load config keys from YAMLs
config_dir = Path("config/aurora")
strategies_dir = config_dir / "strategies"
yaml_files = list(config_dir.glob("*.yaml")) + list(strategies_dir.glob("*.yaml"))

yaml_keys = set()
def extract_keys(data, prefix=""):
    if isinstance(data, dict):
        for k, v in data.items():
            k_str = str(k)
            full_key = f"{prefix}.{k_str}" if prefix else k_str
            yaml_keys.add(full_key)
            yaml_keys.add(k_str) # Also add naked keys for grepping
            extract_keys(v, full_key)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            extract_keys(item, f"{prefix}[{i}]")

for yaml_file in yaml_files:
    try:
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f)
            extract_keys(data)
    except Exception as e:
        print(f"Error parsing {yaml_file}: {e}")

# 2. Extract accessed keys from python code
code_dir = Path("apps/reference")
py_files = list(code_dir.rglob("*.py"))

# simple regex for attributes config.xxx.yyy or dict access config['xxx']
attr_regex = re.compile(r'config(?:\.[a-zA-Z0-9_]+)+')
dict_regex = re.compile(r'config\[[\"\']([^\"\']+)[\"\']\]')

accessed_keys = set()
for py_file in py_files:
    try:
        with open(py_file, "r", encoding="utf-8") as f:
            content = f.read()
            for match in attr_regex.finditer(content):
                parts = match.group(0).split('.')
                accessed_keys.update(parts[1:]) 
            
            for match in dict_regex.finditer(content):
                key = str(match.group(1))
                accessed_keys.add(key)
    except Exception as e:
        print(f"Error reading {py_file}: {e}")

# 3. Read Pydantic models for declared keys
pydantic_keys = set()
pydantic_file = Path("apps/reference/config_models.py")
if pydantic_file.exists():
    with open(pydantic_file, "r", encoding="utf-8") as f:
         content = f.read()
         for line in content.split("\n"):
             if ":" in line and "=" in line and "Field(" in line:
                 key = str(line.split(":")[0].strip())
                 pydantic_keys.add(key)

print(f"Found {len(yaml_keys)} unique keys across {len(yaml_files)} YAML configs")
print(f"Found {len(accessed_keys)} unique keys accessed in {len(py_files)} python files")
print(f"Found {len(pydantic_keys)} unique keys declared in Pydantic models")


# 4. Drift Analysis
yaml_only = {k for k in yaml_keys if k not in accessed_keys and k not in pydantic_keys and "." not in k}
pydantic_only = pydantic_keys - yaml_keys - accessed_keys

print("\n--- Potential Drift (YAML keys with no obvious code consumer or Pydantic model) ---")
for key in sorted(yaml_only):
    # filter out top level / obvious structural keys
    if key not in ['version', 'testnet', 'production']:
        print(f"- {key}")

print("\n--- Potential Drift (Pydantic models with no YAML data or code consumers) ---")
for key in sorted(pydantic_only):
   print(f"- {key}")

