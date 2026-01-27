#!/usr/bin/env python3
"""
auroractl — minimal CLI utilities for Aurora.

TASK47: Provide `config-validate` entrypoint used by ops/docs.
"""

from __future__ import annotations

import argparse
import sys
import json
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.reference.config_loader import ConfigLoader  # noqa: E402


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal objects."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def cmd_config_validate(args: argparse.Namespace) -> int:
    loader = ConfigLoader(config_dir=Path(args.config_dir) if args.config_dir else None)
    # Run with LIVE fail-closed checks enabled (execution + sizing SSOT).
    loader.load_config(is_live_execution=True)
    print("CONFIG_OK")
    return 0


def cmd_config_provenance(args: argparse.Namespace) -> int:
    loader = ConfigLoader(config_dir=Path(args.config_dir) if args.config_dir else None)
    config = loader.load_config()
    
    provenance = []
    flat_config = ConfigLoader._flatten_leaf_paths(config.model_dump())
    
    for key, val in flat_config.items():
        # Heuristic for merge stage
        stage = "override"
        src = loader.provenance_map.get(key, "unknown")
        if "system.yaml" in src: stage = "system"
        elif "trading.yaml" in src: stage = "trading"
        elif "domains.yaml" in src: stage = "domains"
        elif "instruments.yaml" in src: stage = "instruments"
        elif "strategies/" in src: stage = "strategy"
        
        provenance.append({
            "key": key,
            "effective_value": val,
            "source_file": src,
            "merge_stage": stage,  # legacy name (kept)
            "stage": stage,
            "notes": ""
        })
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(provenance, f, indent=2, cls=DecimalEncoder)
    
    print(f"PROVENANCE_DUMPED: {out_path}")
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

    p_prov = sub.add_parser("config-provenance", help="Dump effective config with provenance.")
    p_prov.add_argument("--config", default="aurora", help="Config name (default: aurora)")
    p_prov.add_argument("--out", required=True, help="Output file path")
    p_prov.add_argument("--config-dir", default=None, help="Override config directory")
    p_prov.set_defaults(func=cmd_config_provenance)

    ns = parser.parse_args(argv)
    return int(ns.func(ns))


if __name__ == "__main__":
    main(sys.argv[1:])
