#!/usr/bin/env python3
"""
Runner for execution_position dependency analysis.

Steps:
  1) Build dependency graph and reports (text/JSON/Mermaid).
  2) Emit paths to generated artifacts.
"""

import subprocess
import sys
from pathlib import Path


def run_analysis() -> bool:
    tools_dir = Path(__file__).parent

    print("=" * 70)
    print("Execution Position dependency analysis (main + shadow)")
    print("=" * 70)

    print("\n[1/1] Building dependency graph and reports...")
    result = subprocess.run(
        [sys.executable, str(tools_dir / "analyze_execution_position_deps.py")],
        capture_output=False,
    )

    if result.returncode != 0:
        print("[ERR] Dependency analysis failed")
        return False

    print("\n[OK] Dependency analysis complete.")
    return True


if __name__ == "__main__":
    success = run_analysis()
    sys.exit(0 if success else 1)
