"""Validation pipeline for SSOT v1.0 trading configuration.

Steps performed:
1. Load `system.yaml` and `trading.yaml` with duplicate-key detection.
2. Merge and normalise environment overrides.
3. Validate configuration against `SSOTConfig` schema.
4. Execute canonical resolvers to ensure compatibility & fallback logic.
5. Emit a validation report (JSON or human-readable summary) for CI.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

from config_schema_v1 import SSOTConfig  # type: ignore[attr-defined]
from apps.reference.domains.execution_position.manage_config import (
    resolve_execution_manage_config,
)
from apps.reference.domains.execution_position.brackets_config import (
    resolve_brackets_config,
)
from apps.reference.config_exposure_policy import resolve_exposure_policy
from apps.reference.utils.trade_cooldowns import get_trade_cooldown_sec_for_symbol
from apps.reference.utils.trading_modes import compute_effective_trading_modes
from apps.reference.domains.risk_management.daily_gate import DailyRiskState


class DuplicateKeyLoader(yaml.SafeLoader):
    """YAML loader that raises on duplicate mapping keys."""


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.Node, deep: bool = False):
    mapping: Dict[Any, Any] = {}
    for key_node, value_node in node.value:  # type: ignore[attr-defined]
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"Duplicate key '{key}' detected in YAML mapping")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


DuplicateKeyLoader.add_constructor(  # type: ignore[attr-defined]
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _deep_merge(source: Dict[str, Any], destination: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(destination.get(key), dict):
            _deep_merge(value, destination[key])
        elif isinstance(value, dict):
            destination[key] = _deep_merge(value, {})
        else:
            destination[key] = value
    return destination


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        data = yaml.load(handle, Loader=DuplicateKeyLoader)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError(
            f"Expected mapping in {path}, got {type(data).__name__}")
    return data


def _resolve_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        key = value[2:-1].strip()
        return os.environ.get(key, value)
    return value


def _maybe_asdict(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value


def _collect_trade_cooldowns(config: Dict[str, Any]) -> Dict[str, float]:
    instruments = (
        config.get("trading", {})
        .get("instruments", {})
        if isinstance(config.get("trading"), dict)
        else {}
    )
    results: Dict[str, float] = {}
    for symbol in instruments.keys():
        cooldown = get_trade_cooldown_sec_for_symbol(config, symbol)
        if cooldown < 0:
            cooldown = 0.0
        results[symbol] = cooldown
    return results


def _validate_daily_limits(config: Dict[str, Any]) -> Dict[str, Any]:
    trading = config.get("trading", {})
    if not isinstance(trading, dict):
        trading = {}
    state = DailyRiskState({"risk": trading.get("risk", {})})
    cfg = state.cfg
    payload = {
        "max_realized_loss_usd": cfg.max_realized_loss_usd,
        "max_drawdown_pct": cfg.max_drawdown_pct,
        "reset_h": cfg.reset_h,
        "reset_m": cfg.reset_m,
    }
    return payload


def _run_resolver_suite(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    manage_cfg = resolve_execution_manage_config(config_dict)
    exposure_policy = resolve_exposure_policy(config_dict)
    brackets = resolve_brackets_config(config_dict)
    trading_modes = compute_effective_trading_modes(config_dict)
    trade_cooldowns = _collect_trade_cooldowns(config_dict)
    daily_limits = _validate_daily_limits(config_dict)

    return {
        "manage": _maybe_asdict(manage_cfg),
        "exposure_policy": _maybe_asdict(exposure_policy),
        "brackets": _maybe_asdict(brackets),
        "trading_modes": {
            "profile": trading_modes.profile,
            "domain_modes": trading_modes.domain_modes,
        },
        "trade_cooldowns": trade_cooldowns,
        "daily_limits": daily_limits,
    }


def _validate_schema(merged: Dict[str, Any]) -> Tuple[SSOTConfig, Dict[str, Any]]:
    try:
        model = SSOTConfig.model_validate(merged)  # type: ignore[attr-defined]
    except AttributeError:
        model = SSOTConfig(**merged)  # Fallback for older Pydantic
    return model, model.model_dump(mode="python")


def load_and_validate(config_dir: Path) -> Dict[str, Any]:
    system_yaml = _load_yaml(config_dir / "system.yaml")
    trading_yaml = _load_yaml(config_dir / "trading.yaml")

    merged: Dict[str, Any] = {}
    _deep_merge(system_yaml, merged)
    _deep_merge(trading_yaml, merged)

    merged = _resolve_env(merged)

    schema_model, normalized = _validate_schema(merged)
    resolvers = _run_resolver_suite(normalized)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config_dir": str(config_dir),
        "schema": {
            "status": "success",
            "trading_mode": schema_model.trading_mode,
            "profile": resolvers["trading_modes"]["profile"],
        },
        "resolvers": resolvers,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate SSOT configuration contract")
    parser.add_argument(
        "--config-dir",
        default=str(Path(__file__).resolve().parent / "config" / "aurora"),
        help="Directory containing system.yaml and trading.yaml",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    parser.add_argument("--ci", action="store_true",
                        help="CI mode (rich summary + JSON)")
    args = parser.parse_args()

    config_dir = Path(args.config_dir)
    if not config_dir.exists():
        print(f"Config directory not found: {config_dir}")
        return 2

    try:
        report = load_and_validate(config_dir)
    except Exception as exc:
        print(f"CONFIG VALIDATION FAILED: {exc}")
        return 1

    if args.json or args.ci:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))

    if not args.ci and not args.json:
        schema = report["schema"]
        print("SSOT CONFIG VALIDATION PASSED")
        print(f"  Trading mode  : {schema['trading_mode']}")
        print(f"  Mode profile  : {schema['profile']}")
        print(
            f"  Trade symbols : {len(report['resolvers']['trade_cooldowns'])}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
