import yaml
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional


def load_yaml_files() -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Loads specified YAML config files and returns a dict of {path: content_dict or None}.
    """
    files_to_load = [
        "config/core.yaml",
        "config/instruments.yaml",
        "config/modes.yaml",
        "config/overrides.yaml",
        "config/domains/decision.yaml",
        "config/domains/execution.yaml",
        "config/domains/risk.yaml",
        "config/domains/sizing.yaml",
        "configs/master_config_v1.yaml",
    ]
    result = {}
    for file_path in files_to_load:
        full_path = Path(file_path)
        if full_path.exists():
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = yaml.safe_load(f)
                    result[full_path.as_posix()] = content
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
                result[full_path.as_posix()] = None
        else:
            result[full_path.as_posix()] = None
    return result


def flatten_keys(data: Any, prefix: str = "") -> List[str]:
    """
    Recursively flattens dict and list structures into a list of dot-notation keys.
    Handles dict, list, and scalars.
    """
    keys = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_prefix = f"{prefix}.{k}" if prefix else k
            keys.extend(flatten_keys(v, new_prefix))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_prefix = f"{prefix}[{i}]"
            keys.extend(flatten_keys(item, new_prefix))
    else:
        # Scalar value, add the key
        keys.append(prefix)
    return keys


def build_inventory() -> Dict[str, Dict[str, List[str]]]:
    """
    Builds inventory of flattened keys for each YAML file.
    Returns {file_path: {"keys": [list of flattened keys]}}
    """
    yaml_data = load_yaml_files()
    inventory = {}
    for file_path, data in yaml_data.items():
        if data is not None:
            keys = flatten_keys(data)
            inventory[file_path] = {"keys": keys}
        else:
            inventory[file_path] = {"keys": []}
    return inventory


def dump_inventory_json(path: str):
    """
    Builds inventory and dumps it to a JSON file at the given path.
    """
    inventory = build_inventory()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(inventory, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    output_path = "docs/config_analysis/config_inventory_raw.json"
    dump_inventory_json(output_path)
    inventory = build_inventory()
    print(f"Inventory built for {len(inventory)} files:")
    for file_path, data in inventory.items():
        print(f"  {file_path}: {len(data['keys'])} keys")
