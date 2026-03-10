#!/usr/bin/env python3
"""
Alpha Search Standalone Domain — Entry Point
=============================================

Launches the alpha search standalone domain as an independent process.
No dependency on apps/reference/main.py.

Usage:
    python scripts/run_alpha_search_domain.py
    python scripts/run_alpha_search_domain.py --matrix config/alpha_search/scenario_matrix.yaml
    python scripts/run_alpha_search_domain.py --log-level DEBUG
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure project root is in path BEFORE any local imports
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from apps.reference.domains.alpha_search.runtime.launcher import run


def main():
    parser = argparse.ArgumentParser(
        description="Alpha Search Standalone Domain",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default matrix (config/alpha_search/scenario_matrix.yaml)
  python scripts/run_alpha_search_domain.py

  # Run with custom matrix
  python scripts/run_alpha_search_domain.py --matrix path/to/matrix.yaml

  # Debug mode
  python scripts/run_alpha_search_domain.py --log-level DEBUG
        """,
    )
    parser.add_argument(
        "--matrix",
        type=str,
        default=None,
        help="Path to scenario_matrix.yaml (default: config/alpha_search/scenario_matrix.yaml)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )

    args = parser.parse_args()

    try:
        asyncio.run(run(
            matrix_path=args.matrix,
            log_level=args.log_level,
        ))
    except KeyboardInterrupt:
        print("\nAlpha Search Domain stopped.")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
