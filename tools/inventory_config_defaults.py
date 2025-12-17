#!/usr/bin/env python3
"""
Inventory Config Defaults Tool

Parses config_models.py via AST to inventory all defaults and extra='allow' in BaseModel classes.
Generates reports and provides CI gate for zero defaults policy.

Usage:
    python tools/inventory_config_defaults.py --out-md reports/TASK20_defaults_inventory.md --out-json reports/TASK20_defaults_inventory.json
    python tools/inventory_config_defaults.py --check  # exits 1 if any defaults found
"""

import ast
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional


class ConfigDefaultsVisitor(ast.NodeVisitor):
    """AST visitor to find defaults in Pydantic BaseModel classes."""

    def __init__(self):
        self.current_class: Optional[str] = None
        self.is_basemodel: bool = False
        self.defaults: List[Dict[str, Any]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Check if this class inherits from BaseModel
        self.is_basemodel = any(
            (isinstance(base, ast.Name) and base.id == 'BaseModel') or
            (isinstance(base, ast.Attribute) and base.attr == 'BaseModel')
            for base in node.bases
        )

        if self.is_basemodel:
            old_class = self.current_class
            self.current_class = node.name
            self.generic_visit(node)
            self.current_class = old_class
        else:
            self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if not self.is_basemodel or not self.current_class:
            return

        # Check for model_config = ConfigDict(extra='allow')
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'model_config':
            if self._is_configdict_extra_allow(node.value):
                self.defaults.append({
                    'class': self.current_class,
                    'field': 'model_config',
                    'type': 'ConfigDict',
                    'default': 'extra=allow',
                    'line': node.lineno
                })

        # Check for field assignments with Field(default=...)
        elif len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            field_name = node.targets[0].id
            if self._is_field_with_default(node.value):
                default_value = self._extract_field_default(node.value)
                self.defaults.append({
                    'class': self.current_class,
                    'field': field_name,
                    'type': 'Field',
                    'default': default_value,
                    'line': node.lineno
                })

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not self.is_basemodel or not self.current_class:
            return

        if node.value is not None:  # Has a default value
            field_name = node.target.id if isinstance(node.target, ast.Name) else str(node.target)
            default_value = self._extract_value(node.value)
            self.defaults.append({
                'class': self.current_class,
                'field': field_name,
                'type': 'AnnAssign',
                'default': default_value,
                'line': node.lineno
            })

        self.generic_visit(node)

    def _is_configdict_extra_allow(self, node: ast.AST) -> bool:
        """Check if node is ConfigDict(extra='allow')"""
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'ConfigDict':
            for keyword in node.keywords:
                if keyword.arg == 'extra' and isinstance(keyword.value, ast.Constant) and keyword.value.value == 'allow':
                    return True
        return False

    def _is_field_with_default(self, node: ast.AST) -> bool:
        """Check if node is Field(...) with default or default_factory"""
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Field':
            for keyword in node.keywords:
                if keyword.arg in ('default', 'default_factory'):
                    return True
        return False

    def _extract_field_default(self, node: ast.Call) -> str:
        """Extract default value from Field(...)"""
        for keyword in node.keywords:
            if keyword.arg in ('default', 'default_factory'):
                return self._extract_value(keyword.value)
        return 'unknown'

    def _extract_value(self, node: ast.AST) -> str:
        """Extract string representation of AST value"""
        if isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                args = [self._extract_value(arg) for arg in node.args]
                kwargs = [f"{kw.arg}={self._extract_value(kw.value)}" for kw in node.keywords]
                return f"{func_name}({', '.join(args + kwargs)})"
            return 'call'
        elif isinstance(node, ast.List):
            return f"[{', '.join(self._extract_value(elt) for elt in node.elts)}]"
        elif isinstance(node, ast.Dict):
            return f"{{{', '.join(f'{self._extract_value(k)}: {self._extract_value(v)}' for k, v in zip(node.keys, node.values) if k and v)}}}"
        elif isinstance(node, ast.Attribute):
            return f"{node.attr}"
        else:
            return str(type(node).__name__)


def inventory_defaults(file_path: str) -> List[Dict[str, Any]]:
    """Parse file and return list of defaults found."""
    with open(file_path, 'r', encoding='utf-8') as f:
        source = f.read()

    tree = ast.parse(source, filename=file_path)
    visitor = ConfigDefaultsVisitor()
    visitor.visit(tree)
    return visitor.defaults


def generate_md_report(defaults: List[Dict[str, Any]], output_path: str) -> None:
    """Generate Markdown report."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('# TASK20 Config Defaults Inventory\n\n')
        f.write('Inventory of all defaults and extra=\'allow\' in config_models.py BaseModel classes.\n\n')
        f.write('| Class | Field | Type | Default | Line |\n')
        f.write('|-------|-------|------|---------|------|\n')

        for d in sorted(defaults, key=lambda x: (x['class'], x['field'])):
            f.write(f"| {d['class']} | {d['field']} | {d['type']} | {d['default']} | {d['line']} |\n")

        f.write(f'\nTotal defaults found: {len(defaults)}\n')


def generate_json_report(defaults: List[Dict[str, Any]], output_path: str) -> None:
    """Generate JSON report."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(defaults, f, indent=2, ensure_ascii=False)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Inventory config defaults')
    parser.add_argument('--file', default='apps/reference/config_models.py', help='File to parse')
    parser.add_argument('--out-md', help='Output Markdown file')
    parser.add_argument('--out-json', help='Output JSON file')
    parser.add_argument('--check', action='store_true', help='Exit 1 if any defaults found')

    args = parser.parse_args()

    file_path = args.file
    if not Path(file_path).exists():
        print(f"Error: File {file_path} not found", file=sys.stderr)
        sys.exit(1)

    defaults = inventory_defaults(file_path)

    if args.out_md:
        generate_md_report(defaults, args.out_md)
        print(f"Generated {args.out_md}")

    if args.out_json:
        generate_json_report(defaults, args.out_json)
        print(f"Generated {args.out_json}")

    if args.check:
        if defaults:
            print(f"❌ Found {len(defaults)} defaults/extra='allow' - violating zero defaults policy", file=sys.stderr)
            for d in defaults:
                print(f"  {d['class']}.{d['field']}: {d['default']}", file=sys.stderr)
            sys.exit(1)
        else:
            print("✅ No defaults found - zero defaults policy satisfied")

    if not args.out_md and not args.out_json and not args.check:
        # Default: print to stdout
        for d in defaults:
            print(f"{d['class']}.{d['field']}: {d['default']}")


if __name__ == '__main__':
    main()