from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.analysis.order_reconstruction_tp_sl_common import (
    load_strategy_context,
    load_yaml_file,
    payload_get,
    stringify,
    to_float,
)


def _assets_from_aurora_cfg(aurora_cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    strategies = aurora_cfg.get("strategies") or {}
    aurora = strategies.get("aurora") or {}
    assets = aurora.get("assets") or {}
    resolved: dict[str, dict[str, Any]] = {}
    for symbol, asset_cfg in assets.items():
        if not isinstance(asset_cfg, dict):
            continue
        exit_cfg = asset_cfg.get("exit") or {}
        take_profit = asset_cfg.get("take_profit") or {}
        resolved[str(symbol)] = {
            "enabled": bool(asset_cfg.get("enabled", True)),
            "allowed_regimes": [str(item) for item in asset_cfg.get("allowed_regimes") or []],
            "exit": exit_cfg,
            "take_profit": take_profit,
            "sl_pct": to_float(exit_cfg.get("sl_pct")),
            "tp_low_ratio": to_float(take_profit.get("tp_low_ratio")),
            "partial_exit_pct": to_float(take_profit.get("partial_exit_pct")),
            "regime_tpsl": exit_cfg.get("regime_tpsl") or {},
        }
    return resolved


def load_backtest_config(root: Path) -> dict[str, Any]:
    domains_cfg = load_yaml_file(root / "config" / "aurora" / "domains.yaml") or {}
    aurora_cfg = load_yaml_file(root / "config" / "aurora" / "strategies" / "aurora.yaml") or {}
    strategy_context = load_strategy_context(root)
    directional_sanity = payload_get(domains_cfg, "decision_making.directional_sanity") or {}
    price_motion_sanity = payload_get(domains_cfg, "decision_making.price_motion_sanity") or {}
    return {
        "directional_sanity": directional_sanity,
        "price_motion_sanity": price_motion_sanity,
        "fees": strategy_context.get("fees") or {},
        "allowed_regimes": strategy_context.get("allowed_regimes") or {},
        "assets": _assets_from_aurora_cfg(aurora_cfg),
        "regime_config": strategy_context.get("regime_config") or {},
        "strategy_id": stringify(payload_get(aurora_cfg, "strategies.aurora.strategy_id")) or "aurora",
    }


def resolve_asset_config(config: dict[str, Any], symbol: str) -> dict[str, Any]:
    assets = config.get("assets") or {}
    return dict(assets.get(symbol) or {})
