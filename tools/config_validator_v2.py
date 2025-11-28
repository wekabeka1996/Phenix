#!/usr/bin/env python3
"""
Centralized config v2 validation pipeline.

Loads full AuroraConfig, runs all major resolvers (execution/risk/sizing/decision/instruments/modes),
checks basic invariants, generates JSON report.

Usage:
    python tools/config_validator_v2.py
    python tools/config_validator_v2.py --config-root /path/to/config --output report.json
"""

import argparse
import json
import logging
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.reference.config_loader import load_config, reload_config
from apps.reference.config_exposure_policy import resolve_exposure_policy
from apps.reference.config_models import ConfigV2
from apps.reference.config_symbols import get_trading_symbols, resolve_instrument_profile
from apps.reference.config_risk import (
    resolve_daily_risk_state,
    resolve_risk_soft_limits,
    resolve_risk_score_weights,
    resolve_trading_allowed_thresholds,
)
from apps.reference.config_sizing import resolve_sizing_policy
from apps.reference.config_decision import resolve_decision_policy
from apps.reference.config_modes import compute_effective_trading_modes, get_domain_mode_from_mapping
from apps.reference.config_features import resolve_feature_engineering_config
from apps.reference.domains.execution_position.brackets_config import (
    DEFAULT_SL_BPS,
    DEFAULT_TP_BPS,
    resolve_brackets_config,
)
from apps.reference.config.execution_position import resolve_execution_position_config
from pydantic import ValidationError as PydanticValidationError
from jsonschema import SchemaError, ValidationError, validate
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = logging.getLogger(__name__)

DEFAULT_PENDING_TTL_SEC = 90
DEFAULT_POST_FILL_HOLD_TTL_SEC = 5
DEFAULT_POSITIONS_STALE_TTL_SEC = 5

_CONFIG_V2_SCHEMA_PATH = Path(__file__).resolve(
).parent.parent / "config" / "_schemas" / "config_v2.schema.json"
try:
    with _CONFIG_V2_SCHEMA_PATH.open("r", encoding="utf-8") as schema_handle:
        _CONFIG_V2_SCHEMA = json.load(schema_handle)
except FileNotFoundError:
    _CONFIG_V2_SCHEMA = None


_SYMBOL_OVERRIDE_FORBIDDEN_FIELDS = {
    "max_leverage": "limits.max_leverage",
    "max_position_size": "limits.max_position_size",
    "min_notional": "limits.min_notional",
    "min_qty": "limits.min_qty",
    "min_price": "limits.min_price",
}


def _detect_dead_symbol_override_fields(cfg: Any) -> List[str]:
    """Return list of invalid override keys that should live under limits.*."""
    errors: List[str] = []
    config_v2 = getattr(cfg, "config_v2", None)
    if not config_v2 or not getattr(config_v2, "overrides", None):
        return errors

    symbols_overrides = getattr(config_v2, "overrides", {}).get("symbols", {})
    if not isinstance(symbols_overrides, dict):
        return errors

    for symbol, override in symbols_overrides.items():
        if not isinstance(override, dict):
            continue
        for field, target in _SYMBOL_OVERRIDE_FORBIDDEN_FIELDS.items():
            if field in override:
                errors.append(
                    f"overrides.symbols.{symbol}.{field} must move under {target}"
                )
    return errors


def format_validation_summary(result: Dict[str, Any]) -> str:
    """Return a human-readable summary of validation domains and status."""
    lines: List[str] = []
    overall_status = result.get("status", "error")
    lines.append(f"Config validator status: {overall_status}")

    global_error = result.get("global_error")
    if global_error:
        lines.append(f"  Global error: {global_error}")

    domains = result.get("domains", {})
    if not domains:
        lines.append("  No domain reports emitted.")
        return "\n".join(lines)

    ordered_domains = list(domains.keys())
    if "schema" in domains:
        ordered_domains = ["schema"] + \
            [d for d in ordered_domains if d != "schema"]

    for domain_name in ordered_domains:
        domain = domains[domain_name]
        status = domain.get("status", "unknown")
        lines.append(f"  {domain_name}: {status}")

        for field_name in ("errors", "warnings"):
            items = domain.get(field_name) or []
            if not items:
                continue
            preview = "; ".join(str(item) for item in items[:2])
            suffix = "…" if len(items) > 2 else ""
            lines.append(f"    {field_name}: {preview}{suffix}")

    return "\n".join(lines)


def validate_config_v2_schema(config_v2_payload: Optional[ConfigV2]) -> List[str]:
    """Run config v2 JSON Schema validation and return a list of error messages."""
    if _CONFIG_V2_SCHEMA is None:
        return [f"Config v2 schema not found: {_CONFIG_V2_SCHEMA_PATH}"]

    if config_v2_payload is None or not is_dataclass(config_v2_payload):
        return []

    payload = asdict(config_v2_payload)
    try:
        validate(instance=payload, schema=_CONFIG_V2_SCHEMA)
        return []
    except ValidationError as exc:
        return [str(exc)]
    except SchemaError as exc:
        return [f"Schema definition error: {exc}"]
    except Exception as exc:  # pragma: no cover - unexpected failure
        return [f"Unexpected schema validation failure: {exc}"]


def validate_config_v2(config_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load AuroraConfig, run all major domain resolvers, check invariants, return JSON report.

    Report structure:
    {
        "status": "ok" / "error",
        "domains": {
            "execution": {"status": "ok", "errors": [], "warnings": []},
            "risk": {"status": "ok", ...},
            ...
        }
    }
    """
    try:
        # Load config (allow overriding root, e.g., in bootstrap/CI)
        cfg = load_config(str(config_root)) if config_root else reload_config()

        domains_report = {}
        overall_status = "ok"
        schema_errors = validate_config_v2_schema(
            getattr(cfg, "config_v2", None))
        schema_status = "error" if schema_errors else "ok"
        domains_report["schema"] = {
            "status": schema_status,
            "errors": schema_errors,
            "warnings": [],
        }
        if schema_errors:
            overall_status = "error"

        # Define domains to validate
        domains_to_validate = [
            "execution",
            "risk",
            "sizing",
            "decision",
            "features",
            "instruments",
            "modes"
        ]

        # Execution domain
        try:
            exposure_policy = resolve_exposure_policy(cfg)
            brackets_config = resolve_brackets_config(cfg)

            errors = []
            warnings_execution: List[str] = []

            # Check if ExecutionPositionConfig (V2 SSOT) is present
            ep_cfg_v2_present = False
            try:
                # resolve_execution_position_config потребує Dict, не AuroraConfig
                raw_exec_dict = cfg.model_dump().get("execution", {})
                ep_cfg = resolve_execution_position_config(raw_exec_dict)
                if ep_cfg is not None:
                    ep_cfg_v2_present = True
                    # Validate ExecutionPositionConfig invariants
                    if not (0 < ep_cfg.aggregated_oco.sl_pct <= 1):
                        errors.append(
                            f"ExecutionPositionConfig.aggregated_oco.sl_pct {ep_cfg.aggregated_oco.sl_pct} out of range (0, 1]"
                        )
                    if ep_cfg.aggregated_oco.tp_rr <= 0:
                        errors.append(
                            f"ExecutionPositionConfig.aggregated_oco.tp_rr {ep_cfg.aggregated_oco.tp_rr} must be > 0"
                        )
                    if ep_cfg.aggregated_oco.max_sl_legs < 1 or ep_cfg.aggregated_oco.max_tp_legs < 1:
                        errors.append(
                            f"ExecutionPositionConfig.aggregated_oco max_sl_legs/max_tp_legs must be >= 1"
                        )
            except PydanticValidationError as pyd_exc:
                errors.append(
                    f"ExecutionPositionConfig validation failed: {pyd_exc}")
            except Exception as ep_exc:
                # If resolver fails, we'll treat it as V2 not present (fallback to legacy checks)
                warnings_execution.append(
                    f"resolve_execution_position_config failed (V2 config may be absent): {ep_exc}"
                )

            # Invariants for exposure
            caps = exposure_policy.caps
            if not (0 < caps.max_equity_utilization_ratio <= 1000):  # Allow up to 1000% for testnet
                errors.append(
                    f"max_equity_utilization_ratio {caps.max_equity_utilization_ratio} out of range (0, 1000]")
            if not (0 <= caps.max_portfolio_fraction):  # Allow any positive value
                errors.append(
                    f"max_portfolio_fraction {caps.max_portfolio_fraction} must be >= 0")
            if not (0 <= caps.max_directional_ratio):
                errors.append(
                    f"max_directional_ratio {caps.max_directional_ratio} must be >= 0")

            reservations = getattr(exposure_policy, 'reservations', None)
            if reservations is not None:
                if getattr(exposure_policy, 'source', 'legacy') != "config_v2":
                    warnings_execution.append(
                        "resolve_exposure_policy did not return config_v2 source; execution exposure still legacy-first"
                    )
                if getattr(reservations, 'pending_ttl_sec', DEFAULT_PENDING_TTL_SEC) == DEFAULT_PENDING_TTL_SEC:
                    warnings_execution.append(
                        "pending_ttl_sec equals default 90s; ensure config/domains/execution.yaml overrides it"
                    )
                if getattr(reservations, 'post_fill_hold_ttl_sec', DEFAULT_POST_FILL_HOLD_TTL_SEC) == DEFAULT_POST_FILL_HOLD_TTL_SEC:
                    warnings_execution.append(
                        "post_fill_hold_ttl_sec equals default 5s; consider setting explicit v2 value"
                    )
                if getattr(reservations, 'positions_stale_ttl_sec', DEFAULT_POSITIONS_STALE_TTL_SEC) == DEFAULT_POSITIONS_STALE_TTL_SEC:
                    warnings_execution.append(
                        "positions_stale_ttl_sec equals default 5s; consider setting explicit v2 value"
                    )

            # Invariants for brackets
            # If ExecutionPositionConfig V2 is present and valid, brackets_config.source=legacy is acceptable (hybrid mode)
            if not ep_cfg_v2_present:
                # V2 SSOT not present, brackets_config must be from config_v2
                if getattr(brackets_config, 'source', 'legacy') != "config_v2":
                    errors.append(
                        f"resolve_brackets_config returned source={brackets_config.source}, expected config_v2 (ExecutionPositionConfig not present)"
                    )
            else:
                # V2 SSOT present, brackets_config.source=legacy is OK (hybrid adapter mode)
                if getattr(brackets_config, 'source', 'legacy') == "legacy":
                    warnings_execution.append(
                        "resolve_brackets_config returned source=legacy, but ExecutionPositionConfig V2 is present (hybrid mode)"
                    )
            if getattr(brackets_config, 'tp_bps', DEFAULT_TP_BPS) <= 0:
                errors.append(
                    f"tp.fixed_bps {brackets_config.tp_bps} must be > 0")
            if getattr(brackets_config, 'sl_bps', DEFAULT_SL_BPS) <= 0:
                errors.append(
                    f"sl.fixed_bps {brackets_config.sl_bps} must be > 0")

            status = "error" if errors else "ok"
            domains_report["execution"] = {
                "status": status, "errors": errors, "warnings": warnings_execution}
            if status == "error":
                overall_status = "error"

        except Exception as e:
            domains_report["execution"] = {
                "status": "error", "errors": [str(e)], "warnings": []}
            overall_status = "error"

        # Risk domain
        try:
            risk_state = resolve_daily_risk_state(cfg)
            errors = []
            warnings_risk: List[str] = []

            # Invariants for risk
            if hasattr(risk_state, 'cfg'):
                max_loss = getattr(
                    risk_state.cfg, 'max_realized_loss_usd', None)
                max_drawdown = getattr(
                    risk_state.cfg, 'max_drawdown_pct', None)
                if max_loss is not None and max_loss < 0:
                    errors.append(
                        f"max_realized_loss_usd {max_loss} must be >= 0")
                if max_drawdown is not None and not (0 <= max_drawdown <= 100):
                    errors.append(
                        f"max_drawdown_pct {max_drawdown} out of range [0, 100]")
                # Note: max_loss_usd and max_drawdown_pct are different units, no direct comparison

            try:
                soft_limits = resolve_risk_soft_limits(cfg)
                if soft_limits.clip_min_notional_usdt <= 0:
                    errors.append(
                        "soft_limits.clip_min_notional_usdt must be > 0")
                if soft_limits.directional_ratio_max < 1:
                    errors.append(
                        "soft_limits.directional_ratio_max must be >= 1")
                if soft_limits.side_exposure_usdt <= 0 or soft_limits.margin_exposure_usdt <= 0:
                    errors.append("soft_limits exposure caps must be > 0")
            except Exception as soft_exc:
                errors.append(f"soft_limits resolver error: {soft_exc}")

            try:
                score_weights = resolve_risk_score_weights(cfg)
                for name, value in score_weights.__dict__.items():
                    if name == "source":
                        continue
                    if value < 0:
                        errors.append(
                            f"score_weights.{name} must be non-negative (got {value})")
            except Exception as weights_exc:
                errors.append(f"score_weights resolver error: {weights_exc}")

            try:
                thresholds = resolve_trading_allowed_thresholds(cfg)
                if not 0 <= thresholds.max_risk_score <= 1:
                    errors.append(
                        f"trading_allowed_thresholds.max_risk_score must be within [0, 1], got {thresholds.max_risk_score}")
                if thresholds.overrides:
                    for profile, value in thresholds.overrides.items():
                        if not 0 <= value <= 1:
                            errors.append(
                                f"trading_allowed_thresholds.overrides[{profile}] must be within [0, 1], got {value}")
            except Exception as thresholds_exc:
                errors.append(
                    f"trading_allowed_thresholds resolver error: {thresholds_exc}")

            status = "error" if errors else "ok"
            domains_report["risk"] = {"status": status,
                                      "errors": errors, "warnings": warnings_risk}
            if status == "error":
                overall_status = "error"

        except Exception as e:
            domains_report["risk"] = {
                "status": "error", "errors": [str(e)], "warnings": []}
            overall_status = "error"

        # Sizing domain
        try:
            # Use first symbol for sizing
            symbols = get_trading_symbols()
            symbol = symbols[0] if symbols else "BTCUSDT"
            sizing_policy = resolve_sizing_policy(cfg, symbol)

            errors = []
            warnings_sizing: List[str] = []

            # Invariants for sizing
            if not (0 < sizing_policy.max_risk_pct <= 100):
                errors.append(
                    f"max_risk_pct {sizing_policy.max_risk_pct} out of range (0, 100]")
            if sizing_policy.max_risk_usd < 0:
                errors.append(
                    f"max_risk_usd {sizing_policy.max_risk_usd} must be >= 0")
            if not (0 < sizing_policy.min_notional_usd <= sizing_policy.max_notional_usd):
                errors.append(
                    f"min_notional_usd {sizing_policy.min_notional_usd} > max_notional_usd {sizing_policy.max_notional_usd} or <= 0")

            status = "error" if errors else "ok"
            domains_report["sizing"] = {
                "status": status, "errors": errors, "warnings": warnings_sizing}
            if status == "error":
                overall_status = "error"

        except Exception as e:
            domains_report["sizing"] = {
                "status": "error", "errors": [str(e)], "warnings": []}
            overall_status = "error"

        # Decision domain
        try:
            decision_policy = resolve_decision_policy(cfg)

            errors = []
            warnings_decision: List[str] = []

            # Invariants for decision
            if not (0 <= decision_policy.signal_threshold <= 1):
                errors.append(
                    f"signal_threshold {decision_policy.signal_threshold} out of range [0, 1]")
            if not (0 <= decision_policy.neutral_threshold <= 1):
                errors.append(
                    f"neutral_threshold {decision_policy.neutral_threshold} out of range [0, 1]")
            if decision_policy.neutral_threshold < decision_policy.signal_threshold:
                errors.append(
                    f"neutral_threshold {decision_policy.neutral_threshold} < signal_threshold {decision_policy.signal_threshold}")

            status = "error" if errors else "ok"
            domains_report["decision"] = {
                "status": status, "errors": errors, "warnings": warnings_decision}
            if status == "error":
                overall_status = "error"

        except Exception as e:
            domains_report["decision"] = {
                "status": "error", "errors": [str(e)], "warnings": []}
            overall_status = "error"

        # Feature engineering domain
        try:
            features_cfg = resolve_feature_engineering_config(cfg)

            errors = []
            warnings_features: List[str] = []

            source = getattr(features_cfg, 'source', 'legacy')
            if source != "config_v2":
                errors.append(
                    f"resolve_feature_engineering_config returned source={source}, expected config_v2"
                )

            status = "error" if errors else "ok"
            domains_report["features"] = {
                "status": status, "errors": errors, "warnings": warnings_features}
            if status == "error":
                overall_status = "error"

        except Exception as e:
            domains_report["features"] = {
                "status": "error", "errors": [str(e)], "warnings": []}
            overall_status = "error"

        # Instruments domain
        try:
            symbols = get_trading_symbols()
            errors = []
            warnings_instruments: List[str] = []

            errors.extend(_detect_dead_symbol_override_fields(cfg))

            for symbol in symbols[:5]:  # Check first 5 symbols to avoid too many
                try:
                    profile = resolve_instrument_profile(cfg, symbol)
                    # Invariants for instruments
                    if profile.min_notional <= 0:
                        errors.append(
                            f"{symbol}: min_notional {profile.min_notional} must be > 0")
                    if profile.min_qty <= 0:
                        errors.append(
                            f"{symbol}: min_qty {profile.min_qty} must be > 0")
                    if profile.min_price < 0:
                        errors.append(
                            f"{symbol}: min_price {profile.min_price} must be >= 0")
                    if profile.max_leverage < 1:
                        errors.append(
                            f"{symbol}: max_leverage {profile.max_leverage} must be >= 1")
                except Exception as e:
                    errors.append(f"{symbol}: {str(e)}")

            status = "error" if errors else "ok"
            domains_report["instruments"] = {
                "status": status, "errors": errors, "warnings": warnings_instruments}
            if status == "error":
                overall_status = "error"

        except Exception as e:
            domains_report["instruments"] = {
                "status": "error", "errors": [str(e)], "warnings": []}
            overall_status = "error"

        # Modes domain
        try:
            effective_modes = compute_effective_trading_modes(cfg)
            errors = []
            warnings_modes: List[str] = []

            # Invariants for modes
            if not effective_modes or not hasattr(effective_modes, 'for_domain'):
                errors.append("Invalid effective modes structure")
            else:
                # Check that profile is not empty
                if not effective_modes.profile or not isinstance(effective_modes.profile, str):
                    errors.append("Profile must be a non-empty string")
                else:
                    # Check that profile is one of allowed
                    allowed_profiles = {"full_testnet",
                                        "shadow_live", "full_live"}
                    if effective_modes.profile not in allowed_profiles:
                        warnings_modes.append(
                            f"Profile '{effective_modes.profile}' not in standard set {allowed_profiles}")

                # Check domain modes
                allowed_domain_modes = {"live", "testnet", "disabled"}
                for domain in ["market_data", "feature_engineering", "decision_making", "risk_management", "execution_position", "audit_trail"]:
                    mode = effective_modes.for_domain(domain)
                    if mode not in allowed_domain_modes:
                        errors.append(
                            f"Domain {domain} mode '{mode}' not in allowed set {allowed_domain_modes}")

            status = "error" if errors else "ok"
            domains_report["modes"] = {
                "status": status, "errors": errors, "warnings": warnings_modes}
            if status == "error":
                overall_status = "error"

        except Exception as e:
            domains_report["modes"] = {
                "status": "error", "errors": [str(e)], "warnings": []}
            overall_status = "error"

        return {
            "status": overall_status,
            "domains": domains_report
        }

    except Exception as e:
        return {
            "status": "error",
            "domains": {},
            "global_error": str(e)
        }


def _write_validation_report(result: Dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)


def _cli_entry(args: argparse.Namespace) -> int:
    config_root = Path(args.config_root) if args.config_root else None
    result = validate_config_v2(config_root)

    output_path = Path(args.output)
    _write_validation_report(result, output_path)

    summary = format_validation_summary(result)
    print(summary)

    if result.get("status") != "ok":
        sys.exit(1)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for CLI use."""
    parser = argparse.ArgumentParser(description="Validate config v2")
    parser.add_argument("--config-root", type=str, default=None,
                        help="Path to config root directory")
    parser.add_argument(
        "--output", type=str, default="docs/config_v2/validation_report.json", help="Output JSON file path")
    args = parser.parse_args(argv)
    return _cli_entry(args)


if __name__ == "__main__":
    sys.exit(main())
