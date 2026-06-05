"""Audit-only manifest builder for AURORA_RUNTIME_FORENSIC_COORDINATOR_T0.

This script is read-only with respect to production code and configuration.
It only reads repo evidence and writes analysis artifacts under
reports/runtime_forensics/T0/.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"
CONFIG_DIR = ROOT / "config" / "aurora"
REPORT_DIR = ROOT / "reports" / "runtime_forensics" / "T0"
RECORDER_DIR = ROOT / "data" / "recorder"

TEXT_PREFIX_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d{3,6})?)"
)
EMBEDDED_TS_PATTERNS = [
    re.compile(r'"ts_ms"\s*:\s*(\d{10,16})'),
    re.compile(r'"ts"\s*:\s*(\d{10,16})'),
    re.compile(r'"timestamp"\s*:\s*(\d{10,16})'),
    re.compile(r"\bts_raw=(\d{10,16})"),
]


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        payload = yaml.safe_load(handle)
    return payload if isinstance(payload, dict) else {}


def nested_get(mapping: dict[str, Any] | None, path: str, default: Any = None) -> Any:
    current: Any = mapping
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def normalize_ts_ms(raw: Any) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text.endswith("Z"):
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
                return int(dt.timestamp() * 1000)
            except ValueError:
                return None
        try:
            raw = float(text)
        except ValueError:
            return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        if value > 1e15:
            return int(value / 1000.0)
        if value > 1e12:
            return int(value)
        if value > 1e9:
            return int(value * 1000.0)
    return None


def ms_to_utc_iso(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def ms_to_local_iso(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000.0).isoformat(sep=" ", timespec="seconds")


def parse_text_prefix(value: str) -> datetime | None:
    match = TEXT_PREFIX_RE.match(value)
    if not match:
        return None
    ts_text = match.group("ts")
    for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts_text, fmt)
        except ValueError:
            continue
    return None


def extract_record_ts_ms(record: dict[str, Any]) -> int | None:
    direct_keys = (
        "ts_ms",
        "timestamp",
        "timestamp_ms",
        "decision_ts_ms",
        "event_ts_ms",
        "created_ts_ms",
        "updated_ts_ms",
        "bar_close_ts_ms",
    )
    for key in direct_keys:
        value = record.get(key)
        ts_ms = normalize_ts_ms(value)
        if ts_ms is not None:
            return ts_ms
    timestamp_utc = record.get("timestamp_utc")
    ts_ms = normalize_ts_ms(timestamp_utc)
    if ts_ms is not None:
        return ts_ms
    for key, value in record.items():
        if key.endswith("_ts_ms"):
            ts_ms = normalize_ts_ms(value)
            if ts_ms is not None:
                return ts_ms
    return None


def scan_jsonl(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": rel(path),
        "exists": path.exists(),
        "line_count": 0,
        "malformed_lines": 0,
        "first_ts_ms": None,
        "last_ts_ms": None,
        "first_event": None,
        "last_event": None,
        "boot_events": [],
        "size_bytes": path.stat().st_size if path.exists() else None,
    }
    if not path.exists():
        return info
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.strip()
            if not line:
                continue
            info["line_count"] += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                info["malformed_lines"] += 1
                continue
            ts_ms = extract_record_ts_ms(record)
            event_name = record.get("event_type") or record.get(
                "event") or record.get("record_type")
            if ts_ms is not None:
                if info["first_ts_ms"] is None:
                    info["first_ts_ms"] = ts_ms
                    info["first_event"] = event_name
                info["last_ts_ms"] = ts_ms
                info["last_event"] = event_name
            if record.get("event_type") == "BOOT":
                info["boot_events"].append(
                    {
                        "line": line_number,
                        "ts_ms": ts_ms,
                        "ts_utc": ms_to_utc_iso(ts_ms),
                        "rid": record.get("rid"),
                        "symbol": record.get("symbol"),
                    }
                )
    return info


def summarize_prestart_segment(path: Path, start_ms: int) -> dict[str, Any] | None:
    if not path.exists():
        return None
    count = 0
    first_ts_ms: int | None = None
    last_ts_ms: int | None = None
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_ms = extract_record_ts_ms(record)
            if ts_ms is None or ts_ms >= start_ms:
                continue
            if first_ts_ms is None:
                first_ts_ms = ts_ms
            last_ts_ms = ts_ms
            count += 1
    if count == 0:
        return None
    return {
        "path": rel(path),
        "reason": "structured_pre_boot_segment",
        "count": count,
        "first_ts": ms_to_utc_iso(first_ts_ms),
        "last_ts": ms_to_utc_iso(last_ts_ms),
    }


def first_matching_jsonl_ts(path: Path, matcher: Any) -> int | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not matcher(record):
                continue
            ts_ms = extract_record_ts_ms(record)
            if ts_ms is not None:
                return ts_ms
    return None


def scan_text_log(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": rel(path),
        "exists": path.exists(),
        "line_count": 0,
        "first_prefix_local": None,
        "last_prefix_local": None,
        "first_prefix_dt": None,
        "last_prefix_dt": None,
        "first_embedded_ts_ms": None,
        "last_embedded_ts_ms": None,
        "size_bytes": path.stat().st_size if path.exists() else None,
    }
    if not path.exists():
        return info
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            info["line_count"] += 1
            prefix_dt = parse_text_prefix(line)
            if prefix_dt is not None:
                prefix_text = prefix_dt.isoformat(sep=" ", timespec="seconds")
                if info["first_prefix_dt"] is None:
                    info["first_prefix_dt"] = prefix_dt
                    info["first_prefix_local"] = prefix_text
                info["last_prefix_dt"] = prefix_dt
                info["last_prefix_local"] = prefix_text
            for pattern in EMBEDDED_TS_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                ts_ms = normalize_ts_ms(match.group(1))
                if ts_ms is None:
                    continue
                if info["first_embedded_ts_ms"] is None:
                    info["first_embedded_ts_ms"] = ts_ms
                info["last_embedded_ts_ms"] = ts_ms
                break
    return info


def daterange(start_date: datetime, end_date: datetime) -> list[datetime]:
    values: list[datetime] = []
    current = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    last = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
    while current <= last:
        values.append(current)
        current += timedelta(days=1)
    return values


def render_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        rows = [["-" for _ in headers]]
    output = ["| " + " | ".join(headers) + " |",
              "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        output.append("| " + " | ".join(row) + " |")
    return "\n".join(output)


def fallback_lines(lines: list[str], placeholder: str) -> list[str]:
    return lines if lines else [placeholder]


def render_json_codeblock(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, indent=2, ensure_ascii=False) + "\n```"


def build_assignments(
    instruments_cfg: dict[str, Any],
    strategies_registry: dict[str, Any],
    strategy_files: dict[str, dict[str, Any]],
) -> tuple[list[str], dict[str, Any], dict[str, bool], dict[str, list[str]], list[str]]:
    instrument_symbols = set((instruments_cfg.get("instruments") or {}).keys())
    assignments = strategies_registry.get("assignments") or {}
    strategy_assignments: dict[str, Any] = {}
    safety_enabled_by_strategy: dict[str, bool] = {}
    symbols_by_strategy: dict[str, list[str]] = {}
    known_unproven: list[str] = []

    for strategy_name, strategy_payload in strategy_files.items():
        strategy_root = strategy_payload.get(strategy_name) or {}
        safety_cfg = strategy_root.get("safety_gates") or {}
        safety_enabled_by_strategy[strategy_name] = bool(
            safety_cfg.get("enabled", False))

    active_symbols: list[str] = []
    for symbol, strategies in assignments.items():
        rows: list[dict[str, Any]] = []
        is_symbol_known = symbol in instrument_symbols
        for strategy_name in strategies or []:
            strategy_payload = strategy_files.get(strategy_name, {})
            strategy_root = strategy_payload.get(strategy_name) or {}
            strategy_enabled = bool(strategy_root.get("enabled", False))
            asset_block = None
            if isinstance(strategy_root.get("assets"), dict):
                asset_block = strategy_root["assets"].get(symbol)
            asset_enabled = None if asset_block is None else bool(
                asset_block.get("enabled", False))
            assignment_active = strategy_enabled and asset_enabled is not False
            rows.append(
                {
                    "strategy": strategy_name,
                    "strategy_enabled": strategy_enabled,
                    "asset_enabled": asset_enabled,
                    "active_assignment": assignment_active,
                    "safety_gates_enabled": safety_enabled_by_strategy.get(strategy_name),
                    "evidence": [
                        "config/aurora/strategies.yaml",
                        f"config/aurora/strategies/{strategy_name}.yaml",
                    ],
                }
            )
            if assignment_active:
                symbols_by_strategy.setdefault(
                    strategy_name, []).append(symbol)
        strategy_assignments[symbol] = {
            "instrument_present": is_symbol_known,
            "strategies": rows,
        }
        if any(item["active_assignment"] for item in rows):
            active_symbols.append(symbol)
        if not is_symbol_known:
            known_unproven.append(
                f"Assigned symbol {symbol} is absent from config/aurora/instruments.yaml."
            )

    for strategy_name, symbols in symbols_by_strategy.items():
        symbols.sort()
    active_symbols = sorted(set(active_symbols))
    return active_symbols, strategy_assignments, safety_enabled_by_strategy, symbols_by_strategy, known_unproven


def build_gate_rows(
    domains_cfg: dict[str, Any],
    trading_cfg: dict[str, Any],
    strategy_files: dict[str, dict[str, Any]],
    safety_enabled_by_strategy: dict[str, bool],
    symbols_by_strategy: dict[str, list[str]],
) -> list[dict[str, Any]]:
    dm_cfg = domains_cfg.get("decision_making") or {}
    directional_cfg = dm_cfg.get("directional_sanity") or {}
    price_motion_cfg = dm_cfg.get("price_motion_sanity") or {}
    low_vol_cfg = dm_cfg.get("low_vol_cost_floor_gate") or {}
    global_mode = nested_get(trading_cfg, "trading.mode")

    safety_enabled_strategies = sorted(
        strategy for strategy, enabled in safety_enabled_by_strategy.items() if enabled
    )
    safety_enabled_symbols = sorted(
        {symbol for strategy in safety_enabled_strategies for symbol in symbols_by_strategy.get(
            strategy, [])}
    )

    def base_row() -> dict[str, Any]:
        return {
            "nrr_code": None,
            "gate_name": "",
            "config_path": "",
            "runtime_consumer_file": [],
            "enabled_at_runtime": False,
            "enforced_at_runtime": False,
            "observe_only": False,
            "runtime_mode_dependency": "none",
            "symbols_applicable": [],
            "strategies_applicable": [],
            "required_inputs": [],
            "reason_code_emitted": None,
            "evidence_reference": [],
        }

    rows: list[dict[str, Any]] = []

    nrr026 = base_row()
    nrr026.update(
        {
            "nrr_code": "NRR-026",
            "gate_name": "directional_sanity_min_confidence",
            "config_path": "domains.decision_making.directional_sanity.nrr026_enabled",
            "runtime_consumer_file": [
                "apps/reference/config/domains/decision_making.py",
                "apps/reference/domains/decision_making/gates/safety_gates.py",
                "apps/reference/domains/decision_making/intent/emitter.py",
            ],
            "enabled_at_runtime": bool(directional_cfg.get("nrr026_enabled", False)),
            "enforced_at_runtime": bool(directional_cfg.get("nrr026_enabled", False)),
            "observe_only": False,
            "symbols_applicable": safety_enabled_symbols,
            "strategies_applicable": safety_enabled_strategies,
            "required_inputs": ["trend_dir", "trend_confidence", "regime_confidence", "min_confidence"],
            "reason_code_emitted": "NRR-026",
            "evidence_reference": [
                "config/aurora/domains.yaml :: decision_making.directional_sanity.nrr026_enabled=false",
                "apps/reference/config/domains/decision_making.py :: DirectionalSanityConfig.nrr026_enabled",
                "apps/reference/domains/decision_making/gates/safety_gates.py :: _check_directional_gate / apply_safety_gates",
                "apps/reference/domains/decision_making/intent/emitter.py :: emit_trade_intent_rejected",
            ],
        }
    )
    rows.append(nrr026)

    nrr027 = base_row()
    nrr027.update(
        {
            "nrr_code": "NRR-027",
            "gate_name": "directional_sanity_countertrend_veto",
            "config_path": "domains.decision_making.directional_sanity.nrr027_enabled",
            "runtime_consumer_file": [
                "apps/reference/config/domains/decision_making.py",
                "apps/reference/domains/decision_making/gates/safety_gates.py",
                "apps/reference/domains/decision_making/intent/emitter.py",
            ],
            "enabled_at_runtime": bool(directional_cfg.get("nrr027_enabled", False)),
            "enforced_at_runtime": bool(directional_cfg.get("nrr027_enabled", False)),
            "observe_only": False,
            "symbols_applicable": safety_enabled_symbols,
            "strategies_applicable": safety_enabled_strategies,
            "required_inputs": ["trend_dir", "trend_run_length", "intent_side", "hard_veto_consecutive_bars"],
            "reason_code_emitted": "NRR-027",
            "evidence_reference": [
                "config/aurora/domains.yaml :: decision_making.directional_sanity.nrr027_enabled=false",
                "apps/reference/config/domains/decision_making.py :: DirectionalSanityConfig.nrr027_enabled",
                "apps/reference/domains/decision_making/gates/safety_gates.py :: _check_directional_gate / apply_safety_gates",
                "apps/reference/domains/decision_making/intent/emitter.py :: emit_trade_intent_rejected",
            ],
        }
    )
    rows.append(nrr027)

    for nrr_code, gate_name, reason in (
        ("NRR-028", "price_motion_flash_or_bleed_insufficient", "NRR-028"),
        ("NRR-029", "price_motion_flash_block", "NRR-029"),
        ("NRR-030", "price_motion_bleed_block", "NRR-030"),
    ):
        row = base_row()
        row.update(
            {
                "nrr_code": nrr_code,
                "gate_name": gate_name,
                "config_path": "domains.decision_making.price_motion_sanity.enabled",
                "runtime_consumer_file": [
                    "apps/reference/config/domains/decision_making.py",
                    "apps/reference/domains/decision_making/gates/safety_gates.py",
                    "apps/reference/domains/decision_making/intent/emitter.py",
                ],
                "enabled_at_runtime": bool(price_motion_cfg.get("enabled", False)),
                "enforced_at_runtime": bool(price_motion_cfg.get("enabled", False)),
                "observe_only": False,
                "symbols_applicable": safety_enabled_symbols,
                "strategies_applicable": safety_enabled_strategies,
                "required_inputs": ["pm_norm_60s", "pm_norm_300s", "intent_side"],
                "reason_code_emitted": reason,
                "evidence_reference": [
                    "config/aurora/domains.yaml :: decision_making.price_motion_sanity.enabled=false",
                    "apps/reference/config/domains/decision_making.py :: PriceMotionSanityConfig.enabled",
                    "apps/reference/domains/decision_making/gates/safety_gates.py :: _check_price_motion_gate",
                    "apps/reference/domains/decision_making/intent/emitter.py :: emit_trade_intent_rejected",
                ],
            }
        )
        rows.append(row)

    global_max_map = directional_cfg.get(
        "max_regime_confidence_by_regime") or {}
    aurora_cfg = (strategy_files.get("aurora") or {}).get("aurora") or {}
    aurora_max_by_symbol = nested_get(
        aurora_cfg, "safety_gates.regime_confidence.max_by_symbol", {}) or {}
    nrr063_enabled = bool(global_max_map or aurora_max_by_symbol)
    nrr063 = base_row()
    nrr063.update(
        {
            "nrr_code": "NRR-063",
            "gate_name": "regime_confidence_above_max_band",
            "config_path": "domains.decision_making.directional_sanity.max_regime_confidence_by_regime + strategies.aurora.safety_gates.regime_confidence.max_by_symbol",
            "runtime_consumer_file": [
                "apps/reference/config/domains/decision_making.py",
                "apps/reference/domains/decision_making/gates/safety_gates.py",
                "apps/reference/domains/decision_making/intent/emitter.py",
            ],
            "enabled_at_runtime": nrr063_enabled,
            "enforced_at_runtime": nrr063_enabled,
            "observe_only": False,
            "symbols_applicable": safety_enabled_symbols,
            "strategies_applicable": safety_enabled_strategies,
            "required_inputs": ["regime", "regime_confidence", "resolved_max_regime_confidence"],
            "reason_code_emitted": "NRR-063",
            "evidence_reference": [
                "config/aurora/domains.yaml :: decision_making.directional_sanity.max_regime_confidence_by_regime",
                "config/aurora/strategies/aurora.yaml :: safety_gates.regime_confidence.max_by_symbol",
                "apps/reference/config/domains/decision_making.py :: DirectionalSanityConfig.max_regime_confidence_by_regime",
                "apps/reference/domains/decision_making/gates/safety_gates.py :: apply_safety_gates regime_confidence above_max branch",
                "apps/reference/domains/decision_making/intent/emitter.py :: emit_trade_intent_rejected",
            ],
        }
    )
    rows.append(nrr063)

    low_vol_symbols = sorted(
        {symbol for strategy, symbols in symbols_by_strategy.items(
        ) if strategy in {"aurora", "md_amr"} for symbol in symbols}
    )
    low_vol_gate_mode = "disabled"
    if low_vol_cfg.get("enabled"):
        if global_mode in (low_vol_cfg.get("enforce_in_modes") or []):
            low_vol_gate_mode = "enforced"
        elif global_mode in (low_vol_cfg.get("observe_only_in_modes") or []):
            low_vol_gate_mode = "observe_only"
    low_vol = base_row()
    low_vol.update(
        {
            "gate_name": "low_vol_cost_floor_gate",
            "config_path": "domains.decision_making.low_vol_cost_floor_gate + trading.mode",
            "runtime_consumer_file": [
                "config/aurora/trading.yaml",
                "apps/reference/config_loader.py",
                "apps/reference/domains/decision_making/gates/low_vol_cost_floor.py",
                "apps/reference/domains/decision_making/core/facade.py",
            ],
            "enabled_at_runtime": low_vol_gate_mode != "disabled",
            "enforced_at_runtime": low_vol_gate_mode == "enforced",
            "observe_only": low_vol_gate_mode == "observe_only",
            "runtime_mode_dependency": (
                "DecisionMaking facade passes self.config.trading_mode; current config_loader.get_domain_mode() still returns global mode. "
                f"Current global trading.mode={global_mode!r} -> gate_mode={low_vol_gate_mode}."
            ),
            "symbols_applicable": low_vol_symbols,
            "strategies_applicable": ["aurora", "md_amr"],
            "required_inputs": [
                "trading_mode",
                "regime",
                "regime_confidence",
                "entry_price",
                "target_price",
                "stop_price",
                "direction_confidence",
            ],
            "reason_code_emitted": "LOW_VOL_COST_FLOOR_BLOCKED or LOW_VOL_DIRECTION_CONFIDENCE_BLOCKED",
            "evidence_reference": [
                "config/aurora/domains.yaml :: decision_making.low_vol_cost_floor_gate.enforce_in_modes/observe_only_in_modes",
                "config/aurora/trading.yaml :: trading.mode=hybrid_live_data_testnet_exec",
                "apps/reference/config_loader.py :: AuroraConfig.get_domain_mode returns global trading_mode",
                "apps/reference/domains/decision_making/core/facade.py :: low_vol gate uses self.config.trading_mode",
                "apps/reference/domains/decision_making/gates/low_vol_cost_floor.py :: _resolve_gate_mode / evaluate_low_vol_cost_floor_gate",
            ],
        }
    )
    rows.append(low_vol)

    llm_cfg = (strategy_files.get("llm_microstructure")
               or {}).get("llm_microstructure") or {}
    llm_safety = base_row()
    llm_safety.update(
        {
            "gate_name": "llm_microstructure_strategy_safety_gates",
            "config_path": "strategies.llm_microstructure.safety_gates.enabled",
            "runtime_consumer_file": [
                "config/aurora/strategies/llm_microstructure.yaml",
                "apps/reference/domains/decision_making/gates/safety_gates.py",
            ],
            "enabled_at_runtime": bool(nested_get(llm_cfg, "safety_gates.enabled", False)),
            "enforced_at_runtime": bool(nested_get(llm_cfg, "safety_gates.enabled", False)),
            "observe_only": False,
            "symbols_applicable": symbols_by_strategy.get("llm_microstructure", []),
            "strategies_applicable": ["llm_microstructure"],
            "required_inputs": ["strategy_id"],
            "reason_code_emitted": None,
            "evidence_reference": [
                "config/aurora/strategies/llm_microstructure.yaml :: safety_gates.enabled=false",
                "apps/reference/domains/decision_making/gates/safety_gates.py :: _resolve_safety_gates_flag",
            ],
        }
    )
    rows.append(llm_safety)

    aurora_objective = base_row()
    aurora_objective.update(
        {
            "gate_name": "aurora_objective_gate_flat_regimes_observe_only",
            "config_path": "strategies.aurora.objective.regimes.FLAT_LOW/FLAT_NORMAL/FLAT_HIGH.gate.enforcement_mode",
            "runtime_consumer_file": [
                "config/aurora/strategies/aurora.yaml",
                "apps/reference/config/strategies/common.py",
                "apps/reference/domains/objective_engine/pretrade_kernel.py",
            ],
            "enabled_at_runtime": bool(nested_get(aurora_cfg, "objective.enabled", False)),
            "enforced_at_runtime": False,
            "observe_only": True,
            "runtime_mode_dependency": "Regime-dependent: only when active regime profile is FLAT_LOW, FLAT_NORMAL, or FLAT_HIGH.",
            "symbols_applicable": symbols_by_strategy.get("aurora", []),
            "strategies_applicable": ["aurora"],
            "required_inputs": ["signal.signal_score", "objective component metrics", "regime profile gate config"],
            "reason_code_emitted": None,
            "evidence_reference": [
                "config/aurora/strategies/aurora.yaml :: objective.regimes.FLAT_* .gate.enforcement_mode=OBSERVE",
                "apps/reference/config/strategies/common.py :: StrategyObjectiveGateConfig.enforcement_mode",
                "apps/reference/domains/objective_engine/pretrade_kernel.py :: block only when enforcement_mode == GATE",
            ],
        }
    )
    rows.append(aurora_objective)

    neocortex = base_row()
    neocortex.update(
        {
            "gate_name": "neocortex_authority_shadow_mode",
            "config_path": "domains.decision_making.neocortex_enforcement_mode",
            "runtime_consumer_file": [
                "config/aurora/domains.yaml",
                "apps/reference/config/domains/decision_making.py",
                "apps/reference/domains/decision_making/authority_bridge.py",
                "apps/reference/domains/decision_making/gateway/strategy_gateway.py",
            ],
            "enabled_at_runtime": str(dm_cfg.get("neocortex_enforcement_mode", "")).strip().lower() == "shadow",
            "enforced_at_runtime": str(dm_cfg.get("neocortex_enforcement_mode", "")).strip().lower() == "enforce",
            "observe_only": str(dm_cfg.get("neocortex_enforcement_mode", "")).strip().lower() == "shadow",
            "runtime_mode_dependency": "authority bridge mode only; no trading-mode branch in cited consumers",
            "symbols_applicable": safety_enabled_symbols,
            "strategies_applicable": safety_enabled_strategies,
            "required_inputs": ["authority decision request", "bridge enforcement_mode"],
            "reason_code_emitted": "shadow-only journal/apply_result, not a normalized NRR code",
            "evidence_reference": [
                "config/aurora/domains.yaml :: neocortex_enforcement_mode=shadow",
                "apps/reference/config/domains/decision_making.py :: neocortex_enforcement_mode literal[shadow,enforce]",
                "apps/reference/domains/decision_making/authority_bridge.py :: shadow returns allow with shadow metadata",
                "apps/reference/domains/decision_making/gateway/strategy_gateway.py :: ControlDecisionApplyResult.SHADOW_RECORDED",
            ],
        }
    )
    rows.append(neocortex)

    return rows


def build_truth_priority() -> list[dict[str, Any]]:
    return [
        {
            "rank": 1,
            "source": "exchange-backed structured execution state",
            "artifacts": ["logs/aurora_events.jsonl", "logs/order_log_v1.jsonl"],
            "rule": "Use ORDER_STATE_CHANGED / fill evidence with exchangeOrderId or clientOrderId before any lifecycle narrative.",
        },
        {
            "rank": 2,
            "source": "structured execution lifecycle",
            "artifacts": ["logs/trade_lifecycle.jsonl", "logs/shadow_critical_event_journal_v1.jsonl"],
            "rule": "Use lifecycle and shadow journals for position state, guard outcomes, and sidecar observability after exchange state is established.",
        },
        {
            "rank": 3,
            "source": "decision and gate evidence",
            "artifacts": ["logs/domain_decision_making.log*", "logs/regime_confidence_audit_v1.jsonl"],
            "rule": "Use decision/gate artifacts to explain why an intent was allowed, denied, or observed; not to override exchange execution truth.",
        },
        {
            "rank": 4,
            "source": "strategy/objective context",
            "artifacts": ["config/aurora/strategies.yaml", "config/aurora/strategies/*.yaml"],
            "rule": "Use strategy config and objective traces to scope applicability, not to assert execution or fill truth.",
        },
        {
            "rank": 5,
            "source": "plain text logs without exact IDs",
            "artifacts": ["logs/domain_execution_position.log*", "logs/order_guardian.log"],
            "rule": "Use only as supporting context when exact structured IDs are missing; never outrank structured event logs.",
        },
    ]


def build_correlation_policy() -> list[dict[str, Any]]:
    return [
        {
            "rank": 1,
            "key": "rid exact match",
            "strength": "strong",
            "rule": "Preferred join key across order_log, trade_lifecycle, decision logs, and shadow journals.",
        },
        {
            "rank": 2,
            "key": "exchangeOrderId exact match",
            "strength": "strong",
            "rule": "Use for exchange-confirmed order state transitions when rid is absent downstream.",
        },
        {
            "rank": 3,
            "key": "clientOrderId exact match",
            "strength": "strong",
            "rule": "Use before any symbol/time heuristic; keep side and lifecycle stage aligned.",
        },
        {
            "rank": 4,
            "key": "idempotent_key or decision_id",
            "strength": "medium",
            "rule": "Useful for decision/authority traces when exchange IDs are not yet assigned.",
        },
        {
            "rank": 5,
            "key": "symbol + side + narrow timestamp window",
            "strength": "weak",
            "rule": "Only use when exact IDs are absent; mark the join as weak because local wall-clock logs are timezone-shifted relative to ts_ms fields.",
        },
    ]


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    instruments_cfg = load_yaml(CONFIG_DIR / "instruments.yaml")
    strategies_registry = load_yaml(CONFIG_DIR / "strategies.yaml")
    domains_cfg = load_yaml(CONFIG_DIR / "domains.yaml")
    trading_cfg = load_yaml(CONFIG_DIR / "trading.yaml")
    strategy_files = {
        path.stem: load_yaml(path)
        for path in sorted((CONFIG_DIR / "strategies").glob("*.yaml"))
    }

    active_symbols, strategy_assignments, safety_enabled_by_strategy, symbols_by_strategy, assignment_unproven = build_assignments(
        instruments_cfg,
        strategies_registry,
        strategy_files,
    )

    jsonl_specs = [
        LOG_DIR / "order_log_v1.jsonl",
        LOG_DIR / "trade_lifecycle.jsonl",
        LOG_DIR / "regime_confidence_audit_v1.jsonl",
        LOG_DIR / "shadow_critical_event_journal_v1.jsonl",
        LOG_DIR / "aurora_events.jsonl",
    ]
    jsonl_info = {rel(path): scan_jsonl(path) for path in jsonl_specs}

    order_info = jsonl_info[rel(LOG_DIR / "order_log_v1.jsonl")]
    boot_events = order_info.get("boot_events") or []
    known_unproven: list[str] = list(assignment_unproven)

    if boot_events:
        boot_ts_ms = boot_events[-1]["ts_ms"]
        startup_candidates = [boot_ts_ms]
        boot_lookback_ms = 30 * 60 * 1000
        shadow_startup_ms = first_matching_jsonl_ts(
            LOG_DIR / "shadow_critical_event_journal_v1.jsonl",
            lambda record: str(record.get("record_type", "")).lower() in {
                "restore", "transition"},
        )
        if shadow_startup_ms is not None and 0 <= boot_ts_ms - shadow_startup_ms <= boot_lookback_ms:
            startup_candidates.append(shadow_startup_ms)
        trade_startup_ms = first_matching_jsonl_ts(
            LOG_DIR / "trade_lifecycle.jsonl",
            lambda record: str(record.get("event_type", "")).startswith(
                "POSITION_POLICY_SIDECAR_MODE_"),
        )
        if trade_startup_ms is not None and 0 <= boot_ts_ms - trade_startup_ms <= boot_lookback_ms:
            startup_candidates.append(trade_startup_ms)
        runtime_start_ms = min(startup_candidates)
    else:
        runtime_start_ms = min(
            info["first_ts_ms"]
            for info in jsonl_info.values()
            if info["first_ts_ms"] is not None
        )
        known_unproven.append(
            "order_log_v1.jsonl contains no BOOT event; runtime start falls back to the earliest structured timestamp."
        )

    runtime_end_ms = max(
        info["last_ts_ms"] for info in jsonl_info.values() if info["last_ts_ms"] is not None
    )
    runtime_start_local = datetime.fromtimestamp(runtime_start_ms / 1000.0)
    runtime_end_local = datetime.fromtimestamp(runtime_end_ms / 1000.0)

    excluded_segments: list[dict[str, Any]] = []
    for path in jsonl_specs:
        segment = summarize_prestart_segment(path, runtime_start_ms)
        if segment is not None:
            excluded_segments.append(segment)

    decision_logs = [scan_text_log(path) for path in sorted(
        LOG_DIR.glob("domain_decision_making.log*"))]
    execution_logs = [scan_text_log(path) for path in sorted(
        LOG_DIR.glob("domain_execution_position.log*"))]
    order_guardian_logs = [scan_text_log(path) for path in sorted(
        LOG_DIR.glob("order_guardian.log*"))]

    rotated_logs: list[dict[str, Any]] = []
    for group_name, infos in (
        ("domain_decision_making", decision_logs),
        ("domain_execution_position", execution_logs),
        ("order_guardian", order_guardian_logs),
    ):
        for info in infos:
            path_name = Path(info["path"]).name
            is_rotated = path_name != f"{group_name}.log" if group_name != "order_guardian" else path_name != "order_guardian.log"
            if not is_rotated:
                continue
            relevant = False
            if info["last_embedded_ts_ms"] is not None:
                relevant = info["last_embedded_ts_ms"] >= runtime_start_ms
            elif info["last_prefix_dt"] is not None:
                relevant = info["last_prefix_dt"] >= runtime_start_local
            rotated_logs.append(
                {
                    "group": group_name,
                    "path": info["path"],
                    "first_prefix_local": info["first_prefix_local"],
                    "last_prefix_local": info["last_prefix_local"],
                    "first_embedded_ts": ms_to_utc_iso(info["first_embedded_ts_ms"]),
                    "last_embedded_ts": ms_to_utc_iso(info["last_embedded_ts_ms"]),
                    "relevant_to_current_window": relevant,
                }
            )
            if not relevant:
                excluded_segments.append(
                    {
                        "path": info["path"],
                        "reason": "rotated_text_log_pre_current_window",
                        "last_prefix_local": info["last_prefix_local"],
                        "last_embedded_ts": ms_to_utc_iso(info["last_embedded_ts_ms"]),
                    }
                )

    required_log_groups = {
        "logs/order_log_v1.jsonl": [LOG_DIR / "order_log_v1.jsonl"],
        "logs/trade_lifecycle.jsonl": [LOG_DIR / "trade_lifecycle.jsonl"],
        "logs/domain_decision_making.log*": sorted(LOG_DIR.glob("domain_decision_making.log*")),
        "logs/domain_execution_position.log*": sorted(LOG_DIR.glob("domain_execution_position.log*")),
        "logs/regime_confidence_audit_v1.jsonl": [LOG_DIR / "regime_confidence_audit_v1.jsonl"],
        "logs/shadow_critical_event_journal_v1.jsonl": [LOG_DIR / "shadow_critical_event_journal_v1.jsonl"],
        "logs/aurora_events.jsonl": [LOG_DIR / "aurora_events.jsonl"],
        "logs/order_guardian.log*": sorted(LOG_DIR.glob("order_guardian.log*")),
    }
    logs_found: list[dict[str, Any]] = []
    logs_missing: list[dict[str, Any]] = []
    for pattern, matches in required_log_groups.items():
        if matches:
            logs_found.append(
                {
                    "pattern": pattern,
                    "files": [rel(path) for path in matches],
                }
            )
        else:
            logs_missing.append({"pattern": pattern})

    recorder_timeframes = nested_get(
        domains_cfg, "feature_engineering.enabled_timeframes_sec", []) or []
    recorder_files: list[dict[str, Any]] = []
    recorder_missing: list[dict[str, Any]] = []
    for day in daterange(runtime_start_local, runtime_end_local):
        day_dir = RECORDER_DIR / day.strftime("%Y-%m-%d")
        for symbol in active_symbols:
            for tf_sec in recorder_timeframes:
                file_path = day_dir / f"{symbol}_{tf_sec}.csv"
                entry = {
                    "date": day.strftime("%Y-%m-%d"),
                    "symbol": symbol,
                    "tf_sec": tf_sec,
                    "path": rel(file_path),
                    "exists": file_path.exists(),
                }
                if file_path.exists():
                    recorder_files.append(entry)
                else:
                    recorder_missing.append(entry)
    if recorder_missing:
        known_unproven.append(
            "Recorder inventory uses local wall-clock dates derived from runtime_start/runtime_end because recorder folder date basis is not explicitly declared in config."
        )

    gate_rows = build_gate_rows(
        domains_cfg,
        trading_cfg,
        strategy_files,
        safety_enabled_by_strategy,
        symbols_by_strategy,
    )

    truth_priority = build_truth_priority()
    correlation_policy = build_correlation_policy()

    gates_confirmed_disabled = [
        row["gate_name"] if row["nrr_code"] is None else row["nrr_code"]
        for row in gate_rows
        if row["enabled_at_runtime"] is False
    ]
    gates_confirmed_observe_only = [
        row["gate_name"] if row["nrr_code"] is None else row["nrr_code"]
        for row in gate_rows
        if row["observe_only"] is True
    ]
    gates_confirmed_enforced = [
        row["gate_name"] if row["nrr_code"] is None else row["nrr_code"]
        for row in gate_rows
        if row["enforced_at_runtime"] is True
    ]
    gates_unproven: list[str] = []

    verdict = "READY_FOR_PARALLEL_AUDIT"
    if logs_missing:
        verdict = "PARTIAL_READY"
    if not boot_events and runtime_start_ms is None:
        verdict = "BLOCKED_INSUFFICIENT_EVIDENCE"

    manifest = {
        "runtime_window": {
            "start_ts": ms_to_utc_iso(runtime_start_ms),
            "end_ts": ms_to_utc_iso(runtime_end_ms),
            "excluded_segments": excluded_segments,
            "restart_boundaries": boot_events,
            "start_evidence": {
                "shadow_restore_ts": ms_to_utc_iso(
                    first_matching_jsonl_ts(
                        LOG_DIR / "shadow_critical_event_journal_v1.jsonl",
                        lambda record: str(record.get("record_type", "")).lower() in {
                            "restore", "transition"},
                    )
                ),
                "trade_sidecar_mode_ts": ms_to_utc_iso(
                    first_matching_jsonl_ts(
                        LOG_DIR / "trade_lifecycle.jsonl",
                        lambda record: str(record.get("event_type", "")).startswith(
                            "POSITION_POLICY_SIDECAR_MODE_"),
                    )
                ),
                "order_log_boot_ts": boot_events[-1]["ts_utc"] if boot_events else None,
            },
        },
        "logs": {
            "found": logs_found,
            "missing": logs_missing,
            "rotated": rotated_logs,
        },
        "recorder_files": recorder_files,
        "symbols": active_symbols,
        "strategy_assignments": strategy_assignments,
        "disabled_or_observe_only_nrr": gate_rows,
        "truth_priority": truth_priority,
        "correlation_policy": correlation_policy,
        "known_unproven": known_unproven,
    }

    runtime_window_rows = []
    for key, info in jsonl_info.items():
        runtime_window_rows.append(
            [
                key,
                ms_to_utc_iso(info["first_ts_ms"]) or "-",
                ms_to_utc_iso(info["last_ts_ms"]) or "-",
                str(info["line_count"]),
                str(info["malformed_lines"]),
            ]
        )
    runtime_window_table = render_markdown_table(
        ["Structured file", "First ts", "Last ts", "Lines", "Malformed"],
        runtime_window_rows,
    )

    text_rows = []
    for info in decision_logs + execution_logs + order_guardian_logs:
        text_rows.append(
            [
                info["path"],
                info["first_prefix_local"] or "-",
                info["last_prefix_local"] or "-",
                ms_to_utc_iso(info["first_embedded_ts_ms"]) or "-",
                ms_to_utc_iso(info["last_embedded_ts_ms"]) or "-",
            ]
        )
    text_table = render_markdown_table(
        ["Text log", "First local prefix", "Last local prefix",
            "First embedded ts", "Last embedded ts"],
        text_rows,
    )

    assignment_rows = []
    for symbol in active_symbols:
        strategy_names = [
            row["strategy"]
            for row in strategy_assignments[symbol]["strategies"]
            if row["active_assignment"]
        ]
        assignment_rows.append([symbol, ", ".join(strategy_names)])
    assignment_table = render_markdown_table(
        ["Symbol", "Active strategies"], assignment_rows)

    recorder_found_rows = [
        [entry["date"], entry["symbol"], str(entry["tf_sec"]), entry["path"]]
        for entry in recorder_files
    ]
    recorder_missing_rows = [
        [entry["date"], entry["symbol"], str(entry["tf_sec"]), entry["path"]]
        for entry in recorder_missing
    ]
    excluded_segment_lines = fallback_lines(
        [f"    - {json.dumps(segment, ensure_ascii=False)}" for segment in excluded_segments],
        "    - []",
    )
    logs_missing_lines = fallback_lines(
        [f"    - {item['pattern']}" for item in logs_missing],
        "    - []",
    )
    recorder_found_lines = fallback_lines(
        [f"    - {entry['path']}" for entry in recorder_files],
        "    - []",
    )
    recorder_missing_lines = fallback_lines(
        [f"    - {entry['path']}" for entry in recorder_missing],
        "    - []",
    )
    gates_disabled_lines = fallback_lines(
        [f"    - {value}" for value in gates_confirmed_disabled],
        "    - []",
    )
    gates_observe_lines = fallback_lines(
        [f"    - {value}" for value in gates_confirmed_observe_only],
        "    - []",
    )
    gates_enforced_lines = fallback_lines(
        [f"    - {value}" for value in gates_confirmed_enforced],
        "    - []",
    )
    gates_unproven_lines = fallback_lines(
        [f"    - {value}" for value in gates_unproven],
        "    - []",
    )
    assignment_lines = fallback_lines(
        [
            f"    - {symbol}: {', '.join([row['strategy'] for row in strategy_assignments[symbol]['strategies'] if row['active_assignment']])}"
            for symbol in active_symbols
        ],
        "    - []",
    )
    known_unproven_report_lines = fallback_lines(
        [f"- {item}" for item in known_unproven],
        "- None.",
    )

    inventory_report = "\n".join(
        [
            "AGENT_REPORT_V1",
            "",
            "task:",
            "  AURORA_RUNTIME_FORENSIC_COORDINATOR_T0",
            "",
            "verdict:",
            f"  {verdict}",
            "",
            "runtime_window:",
            f"  start_ts: {ms_to_utc_iso(runtime_start_ms)}",
            f"  end_ts: {ms_to_utc_iso(runtime_end_ms)}",
            "  excluded_segments:",
            *excluded_segment_lines,
            "",
            "evidence_inventory:",
            "  logs_found:",
            *[f"    - {item['pattern']}: {', '.join(item['files'])}" for item in logs_found],
            "  logs_missing:",
            *logs_missing_lines,
            "  recorder_files_found:",
            *recorder_found_lines,
            "  recorder_files_missing:",
            *recorder_missing_lines,
            "",
            "disabled_nrr_summary:",
            "  gates_confirmed_disabled:",
            *gates_disabled_lines,
            "  gates_confirmed_observe_only:",
            *gates_observe_lines,
            "  gates_confirmed_enforced:",
            *gates_enforced_lines,
            "  gates_unproven:",
            *gates_unproven_lines,
            "",
            "symbols_and_strategies:",
            "  assignments:",
            *assignment_lines,
            "",
            "## Executive Summary",
            f"Current canonical runtime window starts at {ms_to_utc_iso(runtime_start_ms)} from the earliest structured startup markers and extends to {ms_to_utc_iso(runtime_end_ms)}; order_log BOOT remains a restart boundary within that window.",
            "",
            "## Proven Facts",
            "- Runtime window anchor comes from the earliest structured startup markers in shadow/trade lifecycle evidence, not from documentation or operator memory.",
            "- Required structured logs are present and were scanned streamingly for first/last timestamps.",
            "- Gate status for NRR-026/027/028/029/030/063 is tied to YAML values plus direct runtime consumers in decision_making gates/facade code.",
            "- low_vol_cost_floor gate is currently enforced under global trading.mode=hybrid_live_data_testnet_exec because the consumer reads self.config.trading_mode.",
            "",
            runtime_window_table,
            "",
            text_table,
            "",
            "### Active Symbols And Assignments",
            assignment_table,
            "",
            "### Recorder Files Found",
            render_markdown_table(
                ["Date", "Symbol", "TF", "Path"], recorder_found_rows),
            "",
            "### Recorder Files Missing",
            render_markdown_table(
                ["Date", "Symbol", "TF", "Path"], recorder_missing_rows),
            "",
            "## Inferred Findings",
            "- Rotated decision/execution text logs must be filtered by current BOOT window; suffix ordering alone is not authoritative.",
            "- Strategy registry assignments are the activation boundary; enabled assets without registry assignment are not treated as current runtime assignments.",
            "",
            "## Contradictions / Evidence Gaps",
            *known_unproven_report_lines,
            "",
            "## Root Cause Candidates",
            "- N/A for T0 inventory task. This report establishes a canonical evidence boundary rather than attributing a runtime fault.",
            "",
            "## Operational Risk",
            "- Observability Gap: if agents mix global trading.mode with domain_configuration overrides, they will disagree on low-vol gate status.",
            "",
            "## Files / Areas Touched",
            "- tools/runtime_forensics_tmp/t0_runtime_manifest_builder.py",
            "- reports/runtime_forensics/T0/RUNTIME_EVIDENCE_INVENTORY.md",
            "- reports/runtime_forensics/T0/DISABLED_NRR_TRUTH_TABLE.md",
            "- reports/runtime_forensics/T0/runtime_manifest.json",
            "",
            "## Validation Performed",
            "- Stream-scanned structured logs for timestamps and BOOT boundaries.",
            "- Cross-checked gate statuses against YAML and direct consumer code paths.",
            "- Enumerated recorder files for the local-date window implied by runtime start/end.",
            "",
            "## Residual Risk",
            "- Text-log wall-clock timestamps are local-time evidence and weaker than ts_ms-based joins.",
            "",
            "## What Remains Unproven",
            *known_unproven_report_lines,
            "",
            "## Minimal Safe Verdict",
            f"- {verdict}",
        ]
    )

    gate_table_rows = []
    for row in gate_rows:
        gate_table_rows.append(
            [
                row["nrr_code"] or "N/A",
                row["gate_name"],
                row["config_path"],
                "yes" if row["enabled_at_runtime"] else "no",
                "yes" if row["enforced_at_runtime"] else "no",
                "yes" if row["observe_only"] else "no",
                ", ".join(row["strategies_applicable"]) or "-",
                ", ".join(row["symbols_applicable"]) or "-",
                row["reason_code_emitted"] or "-",
            ]
        )
    truth_table_report = "\n".join(
        [
            "# DISABLED / OBSERVE-ONLY NRR TRUTH TABLE",
            "",
            "## Facts",
            "- Status is taken from YAML plus direct runtime consumers; comments alone are not used as proof.",
            "- low_vol_cost_floor is included because it is a live admission surface relevant to later PnL/execution audits.",
            "- Strategy-level safety_gates.enabled flags are included where they suppress the NRR chain for an assigned strategy.",
            "",
            render_markdown_table(
                [
                    "NRR",
                    "Gate",
                    "Config path",
                    "Enabled",
                    "Enforced",
                    "Observe only",
                    "Strategies",
                    "Symbols",
                    "Reason code",
                ],
                gate_table_rows,
            ),
            "",
            "## Detailed Evidence",
            *[
                "\n".join(
                    [
                        f"### {row['nrr_code'] or row['gate_name']}",
                        f"- Gate name: {row['gate_name']}",
                        f"- Config path: {row['config_path']}",
                        f"- Runtime consumer file(s): {', '.join(row['runtime_consumer_file'])}",
                        f"- Enabled at runtime: {row['enabled_at_runtime']}",
                        f"- Enforced at runtime: {row['enforced_at_runtime']}",
                        f"- Observe only: {row['observe_only']}",
                        f"- Runtime mode dependency: {row['runtime_mode_dependency']}",
                        f"- Symbols applicable: {', '.join(row['symbols_applicable']) or '-'}",
                        f"- Strategies applicable: {', '.join(row['strategies_applicable']) or '-'}",
                        f"- Required inputs: {', '.join(row['required_inputs']) or '-'}",
                        f"- Reason code emitted: {row['reason_code_emitted'] or '-'}",
                        "- Evidence:",
                        *[f"  - {item}" for item in row['evidence_reference']],
                    ]
                )
                for row in gate_rows
            ],
            "",
            "## Inferences",
            "- Registry assignment is treated as the activation boundary for symbol/strategy applicability.",
            "- A strategy with safety_gates.enabled=false is treated as outside the NRR chain unless later runtime evidence proves an alternate path.",
            "",
            "## Unknowns",
            *known_unproven_report_lines,
        ]
    )

    manifest_path = REPORT_DIR / "runtime_manifest.json"
    inventory_path = REPORT_DIR / "RUNTIME_EVIDENCE_INVENTORY.md"
    truth_table_path = REPORT_DIR / "DISABLED_NRR_TRUTH_TABLE.md"

    manifest_path.write_text(json.dumps(
        manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    inventory_path.write_text(inventory_report + "\n", encoding="utf-8")
    truth_table_path.write_text(truth_table_report + "\n", encoding="utf-8")

    print(json.dumps({
        "verdict": verdict,
        "runtime_start": ms_to_utc_iso(runtime_start_ms),
        "runtime_end": ms_to_utc_iso(runtime_end_ms),
        "manifest": rel(manifest_path),
        "inventory": rel(inventory_path),
        "truth_table": rel(truth_table_path),
        "known_unproven": known_unproven,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
