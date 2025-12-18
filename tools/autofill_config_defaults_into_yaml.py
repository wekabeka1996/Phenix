#!/usr/bin/env python3
"""
Auto-fill Config Defaults into YAML Tool

Migrates defaults from config_models.py to canonical YAML SSOT.
Ensures no behavior change by adding missing keys with default values.

TASK21A: Auto-fill canonical YAML from model defaults (NO behavior change)

TASK23A: Optional-null autofill for Optional[T] required fields (Field(...))
"""

import argparse
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Iterable, Tuple, get_args
from copy import deepcopy
import sys


# Ensure repository root is importable when running this script directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pydantic import BaseModel



MISSING = object()


def load_mapping(mapping_file: Path) -> Dict[str, Dict[str, str]]:
    """Load the default path mapping."""
    with open(mapping_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_inventory(inventory_file: Path) -> List[Dict[str, Any]]:
    """Load the defaults inventory."""
    with open(inventory_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_nested_value(data: Dict[str, Any], path: str) -> Any:
    """Get value from nested dict using dot path.

    Returns MISSING if any key is absent.
    """
    keys = path.split('.')
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return MISSING
    return current


def set_nested_value(data: Dict[str, Any], path: str, value: Any) -> None:
    """Set value in nested dict using dot path."""
    keys = path.split('.')
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def process_default(default: Dict[str, Any], mapping: Dict[str, Dict[str, str]], dry_run: bool) -> Dict[str, Any]:
    """Process a single default: check if needs to be added to YAML."""
    key = f"{default['class']}.{default['field']}"
    
    if key not in mapping:
        raise ValueError(f"No mapping found for {key}")
    
    map_info = mapping[key]
    yaml_file = Path(map_info['file'])
    yaml_path = map_info['path']
    
    # Load YAML
    if yaml_file.exists():
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            data = {}
    else:
        data = {}
    
    # Check if path exists
    existing_value = get_nested_value(data, yaml_path)
    if existing_value is not MISSING:
        return {
            'key': key,
            'action': 'skip',
            'reason': 'already exists',
            'existing_value': existing_value,
            'file': str(yaml_file),
            'path': yaml_path
        }
    
    # Determine value to add
    default_str = default['default']
    
    # Parse the default value
    value = parse_default_value(default_str)
    
    if not dry_run:
        # Add to data
        set_nested_value(data, yaml_path, value)
        
        # Save YAML
        with open(yaml_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
    
    return {
        'key': key,
        'action': 'add_default',
        'value': value,
        'file': str(yaml_file),
        'path': yaml_path
    }


def _is_optional(annotation: Any) -> bool:
    args = get_args(annotation)
    if not args:
        return False
    return any(a is type(None) for a in args)


def _iter_model_types(root: type[BaseModel]) -> Iterable[type[BaseModel]]:
    seen: set[type[BaseModel]] = set()
    stack: list[type[BaseModel]] = [root]

    while stack:
        model = stack.pop()
        if model in seen:
            continue
        seen.add(model)
        yield model

        for field in model.model_fields.values():
            ann = field.annotation
            args = get_args(ann)
            for a in args:
                if isinstance(a, type) and issubclass(a, BaseModel):
                    stack.append(a)
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                stack.append(ann)


def _strip_optional(annotation: Any) -> Any:
    args = get_args(annotation)
    if not args:
        return annotation
    non_none = [a for a in args if a is not type(None)]
    if len(non_none) == 1:
        return non_none[0]
    return annotation


def iter_optional_required_paths() -> Iterable[Tuple[str, str]]:
    """Yield (key, dotted_path) for Optional-required fields in the merged AuroraConfig schema."""
    from apps.reference.config_models import AuroraConfig

    exclude_toplevel = {
        # Runtime-injected/service namespace; never write into YAML.
        "system_meta",
    }

    def walk(model: type[BaseModel], prefix: list[str]) -> Iterable[Tuple[str, str]]:
        for field_name, field_info in model.model_fields.items():
            if prefix == [] and field_name in exclude_toplevel:
                continue

            path_parts = [*prefix, field_name]
            dotted_path = ".".join(path_parts)
            key = f"{model.__name__}.{field_name}"

            if field_info.is_required() and _is_optional(field_info.annotation):
                yield key, dotted_path
                continue  # If key is missing, we only add null at this level.

            inner = _strip_optional(field_info.annotation)
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                yield from walk(inner, path_parts)

    yield from walk(AuroraConfig, [])


def apply_optional_null_autofill(
    *,
    mapping: Dict[str, Dict[str, str]],
    dry_run: bool,
) -> List[Dict[str, Any]]:
    """Add explicit null for missing Optional-required keys."""
    changes: List[Dict[str, Any]] = []

    top_level_to_file = {
        # Trading bundle
        "trading": "config/aurora/trading.yaml",
        "binance_api": "config/aurora/trading.yaml",

        # System bundle
        "system": "config/aurora/system.yaml",
        "ops": "config/aurora/system.yaml",
        "bridge": "config/aurora/system.yaml",
        "logging": "config/aurora/system.yaml",
        "account_observer": "config/aurora/system.yaml",

        # SSOT bundles
        "domains": "config/aurora/domains.yaml",
        "instruments": "config/aurora/instruments.yaml",
        "aurora_instruments": "config/aurora/aurora_instruments.yaml",
        "strategies_registry": "config/aurora/strategies.yaml",
        "models": "config/aurora/regime.yaml",
        "hmm": "config/aurora/regime.yaml",
        "features": "config/aurora/regime.yaml",
        "hotreload_whitelist": "config/aurora/regime.yaml",
    }

    for key, dotted_path in iter_optional_required_paths():
        top = dotted_path.split(".", 1)[0]
        file_rel = top_level_to_file.get(top)
        if not file_rel:
            continue

        yaml_file = Path(file_rel)
        yaml_path = dotted_path

        if yaml_file.exists():
            with open(yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                data = {}
        else:
            data = {}

        existing_value = get_nested_value(data, yaml_path)
        if existing_value is not MISSING:
            changes.append({
                'key': key,
                'action': 'skip',
                'reason': 'already exists',
                'existing_value': existing_value,
                'file': str(yaml_file),
                'path': yaml_path,
            })
            continue

        if not dry_run:
            set_nested_value(data, yaml_path, None)
            with open(yaml_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

        changes.append({
            'key': key,
            'action': 'add_null',
            'value': None,
            'file': str(yaml_file),
            'path': yaml_path,
        })

    return changes


def parse_default_value(default_str: str) -> Any:
    """Parse default value string into Python value."""
    # Handle common cases
    if default_str == 'None':
        return None
    elif default_str == 'True':
        return True
    elif default_str == 'False':
        return False
    elif default_str.startswith("'") and default_str.endswith("'"):
        return default_str[1:-1]
    elif default_str.startswith('"') and default_str.endswith('"'):
        return default_str[1:-1]
    elif default_str.isdigit():
        return int(default_str)
    elif default_str.replace('.', '').isdigit():
        return float(default_str)
    elif default_str == '{}':
        return {}
    elif default_str == '[]':
        return []
    elif default_str.startswith('Field(default='):
        # Extract the value from Field(default=...)
        start = default_str.find('default=') + 8
        end = default_str.find(',', start)
        if end == -1:
            end = default_str.find(')', start)
        inner = default_str[start:end].strip()
        return parse_default_value(inner)
    elif default_str.startswith('Field(default_factory='):
        # For default_factory, assume empty collection
        if 'dict' in default_str:
            return {}
        elif 'list' in default_str:
            return []
        else:
            # Lambda or other, skip for now
            return None
    else:
        # Try to eval simple expressions
        try:
            return eval(default_str)
        except:
            return default_str  # Keep as string


def generate_plan_report(changes: List[Dict[str, Any]], output_file: Path) -> None:
    """Generate the patch plan report."""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('# TASK23A Optional-null YAML Patch Plan\n\n')
        f.write('Plan for adding missing config keys into canonical YAML SSOT.\n')
        f.write('- `add_default`: add missing model default values (TASK21A compatibility)\n')
        f.write('- `add_null`: add explicit `null` for Optional-required fields (TASK23A)\n\n')
        f.write('| Key | Action | Value | File | Path |\n')
        f.write('|-----|--------|-------|------|------|\n')
        
        for change in changes:
            value_str = str(change.get('value', change.get('existing_value', 'N/A')))
            f.write(f"| {change['key']} | {change['action']} | {value_str} | {change['file']} | {change['path']} |\n")
        
        added = len([c for c in changes if c['action'] in ('add_default', 'add_null')])
        skipped = len([c for c in changes if c['action'] == 'skip'])
        f.write(f'\nSummary: {added} to add, {skipped} already exist\n')


def main():
    parser = argparse.ArgumentParser(description='Auto-fill config defaults into YAML')
    parser.add_argument('--inventory', default='reports/TASK20_defaults_inventory.json', help='Inventory JSON file')
    parser.add_argument('--mapping', default='tools/config_default_path_map.yaml', help='Mapping YAML file')
    parser.add_argument('--include-inventory-defaults', action='store_true', default=False, help='Also apply TASK21A-style default autofill from inventory (unsafe for TASK23 unless inventory is clean)')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    parser.add_argument('--apply', action='store_true', help='Apply changes')
    parser.add_argument('--fail-on-unknown-mapping', action='store_true', help='Fail if mapping missing')
    parser.add_argument('--optional-null-required', action='store_true', default=True, help='Autofill explicit null for Optional-required fields (TASK23A)')
    parser.add_argument('--no-optional-null-required', action='store_false', dest='optional_null_required', help='Disable Optional-required null autofill')
    parser.add_argument('--plan-report', default='reports/TASK23A_optional_null_patch_plan.md', help='Plan report output')
    parser.add_argument('--applied-report', default='reports/TASK23A_optional_null_patch_applied.md', help='Applied report output')
    
    args = parser.parse_args()
    
    if not (args.dry_run or args.apply):
        print("Must specify --dry-run or --apply")
        return
    
    inventory_file = Path(args.inventory)
    mapping_file = Path(args.mapping)
    
    if args.include_inventory_defaults and not inventory_file.exists():
        print(f"Inventory file not found: {inventory_file}")
        return
    
    if not mapping_file.exists():
        print(f"Mapping file not found: {mapping_file}")
        return
    
    inventory = load_inventory(inventory_file) if args.include_inventory_defaults else []
    mapping = load_mapping(mapping_file)
    
    changes = []
    errors = []
    
    if args.include_inventory_defaults:
        for default in inventory:
            try:
                change = process_default(default, mapping, not args.apply)
                changes.append(change)
            except ValueError as e:
                if args.fail_on_unknown_mapping:
                    errors.append(str(e))
                else:
                    print(f"Warning: {e}")

    if args.optional_null_required:
        changes.extend(apply_optional_null_autofill(mapping=mapping, dry_run=not args.apply))
    
    if errors:
        for error in errors:
            print(f"Error: {error}")
        return
    
    # Generate plan report
    generate_plan_report(changes, Path(args.plan_report))
    print(f"Generated plan report: {args.plan_report}")
    
    if args.apply:
        # Generate applied report (same as plan for now)
        generate_plan_report(changes, Path(args.applied_report))
        print(f"Generated applied report: {args.applied_report}")
        print("Changes applied to YAML files")
    else:
        print("Dry run completed")


if __name__ == '__main__':
    main()