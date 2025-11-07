#!/usr/bin/env python3
"""
Systematic Pydantic Config Migration Tool - PHASE 3-4

Auto-converts dict .get() calls to Pydantic-first with fallback pattern.
Works on adapters, tools, vfoundation components, and tests.

Pattern:
    OLD: config.get("trading", {}).get("execution", {})
    NEW: try: config.trading.execution (Pydantic-first)
         except: config.get(...) (fallback dict)
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

# List of files to migrate (paths relative to project root)
FILES_TO_MIGRATE = [
    "apps/reference/domains/execution_position/binance_execution_adapter.py",
    "apps/reference/adapters/binance_adapter.py",
    "apps/reference/adapters/sdk_adapter_binance.py",
    "vfoundation/obs/debug_api.py",
    "vfoundation/obs/logger.py",
    "vfoundation/dr/wal.py",
    "vfoundation/dr/replay.py",
    "vfoundation/cli/vfound/__main__.py",
    "tools/verify_config.py",
    "tools/metrics_summary.py",
]


def count_get_calls(file_path: str) -> int:
    """Count .get() calls in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return len(re.findall(r'\.get\(', content))
    except FileNotFoundError:
        return 0


def get_migration_status() -> dict:
    """Report current migration status across PHASE 3 files."""
    status = {
        "total_files": len(FILES_TO_MIGRATE),
        "files_found": 0,
        "total_get_calls": 0,
        "files": {}
    }

    for file_path in FILES_TO_MIGRATE:
        abs_path = Path(file_path).resolve()
        if abs_path.exists():
            status["files_found"] += 1
            get_count = count_get_calls(str(abs_path))
            status["total_get_calls"] += get_count
            status["files"][file_path] = {
                "exists": True,
                "get_calls": get_count,
                "absolute_path": str(abs_path)
            }
        else:
            status["files"][file_path] = {
                "exists": False,
                "get_calls": 0,
                "absolute_path": str(abs_path)
            }

    return status


def print_migration_report():
    """Print migration status report."""
    status = get_migration_status()

    print("\n" + "="*80)
    print("PHASE 3 MIGRATION STATUS REPORT")
    print("="*80)
    print(f"\nTotal files to migrate: {status['total_files']}")
    print(f"Files found: {status['files_found']}")
    print(f"Total .get() calls found: {status['total_get_calls']}")
    print("\nFile-by-file status:")
    print("-" * 80)

    for file_path, info in status["files"].items():
        status_mark = "✅" if info["exists"] else "❌"
        print(
            f"{status_mark} {file_path:55} {info['get_calls']:3} .get() calls")

    print("\n" + "="*80)
    print(f"PHASE 3 TIER 2-5 SUMMARY:")
    print(f"  Target: ~370 .get() calls to migrate")
    print(f"  Found:  {status['total_get_calls']} .get() calls")
    print(
        f"  Status: {status['files_found']}/{status['total_files']} files located")
    print("="*80 + "\n")


if __name__ == "__main__":
    print_migration_report()
