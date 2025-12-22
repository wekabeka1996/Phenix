#!/usr/bin/env python3
"""
auroractl — minimal CLI utilities for Aurora.

TASK47: Provide `config-validate` entrypoint used by ops/docs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.reference.config_loader import ConfigLoader  # noqa: E402


def cmd_config_validate(args: argparse.Namespace) -> int:
    loader = ConfigLoader(config_dir=Path(args.config_dir) if args.config_dir else None)
    loader.load_config()
    print("CONFIG_OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="auroractl")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser("config-validate", help="Load and validate SSOT config (fail-fast).")
    p_validate.add_argument(
        "--config-dir",
        default=None,
        help="Override config directory (default: config/aurora or tests/config/aurora if present).",
    )
    p_validate.set_defaults(func=cmd_config_validate)

    ns = parser.parse_args(argv)
    return int(ns.func(ns))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
