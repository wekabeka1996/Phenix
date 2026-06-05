import os
import json
import csv
import argparse
import yaml
from typing import Dict, List, Any, Tuple

# Map of gates and their rules
GATES_MAP = {
    "nrr_026": {
        "gate_id": "NRR-026",
        "canonical_name": "INSUFFICIENT_TREND_CONFIRMATION",
        "implementation_file": "apps/reference/domains/decision_making/gates/safety_gates.py",
        "function_class": "_check_directional_gate",
        "config_path": "domains.decision_making.directional_sanity.nrr026_enabled",
        "enabled_status": "runtime_dependent",
        "required_inputs": ["trend_dir", "regime_confidence", "trend_confidence", "min_conf"],
        "output_reason": "insufficient trend confirmation",
        "current_runtime_observability": "partial",
        "replay_confidence": "medium"
    },
    "nrr_027": {
        "gate_id": "NRR-027",
        "canonical_name": "DIRECTIONAL_SANITY_BLOCKED",
        "implementation_file": "apps/reference/domains/decision_making/gates/safety_gates.py",
        "function_class": "_check_directional_gate",
        "config_path": "domains.decision_making.directional_sanity.nrr027_enabled",
        "enabled_status": "runtime_dependent",
        "required_inputs": ["trend_dir", "intent_side", "trend_run_length", "hard_veto_consecutive_bars"],
        "output_reason": "countertrend block",
        "current_runtime_observability": "partial",
        "replay_confidence": "high"
    },
    "nrr_028": {
        "gate_id": "NRR-028",
        "canonical_name": "PRICE_MOTION_INSUFFICIENT",
        "implementation_file": "apps/reference/domains/decision_making/gates/safety_gates.py",
        "function_class": "_check_price_motion_gate",
        "config_path": "domains.decision_making.price_motion_sanity.enabled",
        "enabled_status": "runtime_dependent",
        "required_inputs": ["pm_flash", "pm_bleed", "require_bleed_ready"],
        "output_reason": "price_motion insufficient",
        "current_runtime_observability": "partial",
        "replay_confidence": "high"
    },
    "nrr_029": {
        "gate_id": "NRR-029",
        "canonical_name": "PRICE_MOTION_FLASH_BLOCKED",
        "implementation_file": "apps/reference/domains/decision_making/gates/safety_gates.py",
        "function_class": "_check_price_motion_gate",
        "config_path": "domains.decision_making.price_motion_sanity.flash_threshold_norm",
        "enabled_status": "runtime_dependent",
        "required_inputs": ["pm_flash", "intent_side", "flash_threshold_norm"],
        "output_reason": "flash block",
        "current_runtime_observability": "partial",
        "replay_confidence": "high"
    },
    "nrr_030": {
        "gate_id": "NRR-030",
        "canonical_name": "PRICE_MOTION_BLEED_BLOCKED",
        "implementation_file": "apps/reference/domains/decision_making/gates/safety_gates.py",
        "function_class": "_check_price_motion_gate",
        "config_path": "domains.decision_making.price_motion_sanity.bleed_threshold_norm",
        "enabled_status": "runtime_dependent",
        "required_inputs": ["pm_bleed", "intent_side", "bleed_threshold_norm"],
        "output_reason": "bleed block",
        "current_runtime_observability": "partial",
        "replay_confidence": "high"
    },
    "gate_anti_fomo": {
        "gate_id": "GATE_ANTI_FOMO_SIGMA",
        "canonical_name": "GATE_ANTI_FOMO_SIGMA",
        "implementation_file": "apps/reference/domains/strategies/runtimes/aurora/scoring_helpers.py",
        "function_class": "_apply_vol_adj_gates",
        "config_path": "strategies.aurora.decision.gates.anti_fomo_sigma",
        "enabled_status": "runtime_dependent",
        "required_inputs": ["motion_norm_sigma", "anti_fomo_sigma"],
        "output_reason": "anti fomo block",
        "current_runtime_observability": "high",
        "replay_confidence": "high"
    }
}


def _load_yaml_file(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}

    return loaded if isinstance(loaded, dict) else {}


def load_yaml_config(config_root: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    domains_cfg = _load_yaml_file(os.path.join(config_root, "domains.yaml"))
    strategies_cfg = _load_yaml_file(
        os.path.join(config_root, "strategies/aurora.yaml")
    )

    return domains_cfg, strategies_cfg


def get_config_value(cfg: Dict, path: str, default=None):
    parts = path.split('.')
    cur = cfg
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur


def parse_configs(config_root: str) -> Dict[str, Any]:
    domains_cfg, strategies_cfg = load_yaml_config(config_root)

    ds = get_config_value(
        domains_cfg, "domains.decision_making.directional_sanity", {})
    pm = get_config_value(
        domains_cfg, "domains.decision_making.price_motion_sanity", {})
    aurora_gates = get_config_value(
        strategies_cfg, "strategies.aurora.decision.gates", {})

    return {
        "directional_sanity": ds if isinstance(ds, dict) else {},
        "price_motion_sanity": pm if isinstance(pm, dict) else {},
        "anti_fomo_enabled": bool(aurora_gates.get("enabled", False)) if isinstance(aurora_gates, dict) else False,
        "anti_fomo_sigma": aurora_gates.get("anti_fomo_sigma") if isinstance(aurora_gates, dict) else None,
    }


def _extract_value(trace: Dict[str, Any], *paths: Tuple[str, ...]) -> Any:
    for path in paths:
        current: Any = trace
        for key in path:
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]
        if current is not None:
            return current
    return None


def _extract_price_motion_value(trace: Dict[str, Any], field_name: str) -> Any:
    return _extract_value(
        trace,
        (field_name,),
        ("price_motion_context", field_name),
        ("metadata", "low_vol_cost_floor", "price_motion_context", field_name),
        ("low_vol_cost_floor", "price_motion_context", field_name),
    )


def _trace_timestamp_ms(trace: Dict[str, Any]) -> int:
    for path in (
        ("ts_ms",),
        ("event_ts_ms",),
        ("ts",),
        ("timestamp",),
        ("close_ts_ms",),
        ("updated_ts_ms",),
        ("created_ts_ms",),
        ("metadata", "low_vol_cost_floor", "persistence_context", "trace_ts_ms"),
        ("metadata", "low_vol_cost_floor", "persistence_context", "decision_ts_ms"),
    ):
        value = _extract_value(trace, path)
        if value is None:
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return 0


def _is_replay_trace_candidate(data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict) or not data.get("symbol"):
        return False

    event_type = str(data.get("event_type", "") or "")
    if "DECISION_TRACE" in event_type or event_type == "STRATEGY_SIGNAL_PRODUCED":
        return True
    if data.get("decision_surface") is not None or data.get("gate_chain_result") is not None:
        return True
    if isinstance(_extract_value(data, ("metadata", "low_vol_cost_floor")), dict):
        return True
    return _extract_price_motion_value(data, "pm_norm_300s") is not None


def load_traces(runtime_root: str) -> Dict[str, List[Dict[str, Any]]]:
    traces_by_symbol = {}

    files_to_check = [
        os.path.join(runtime_root, "shadow_critical_event_journal_v1.jsonl"),
        os.path.join(runtime_root, "order_log_v1.jsonl")
    ]

    for fpath in files_to_check:
        if not os.path.exists(fpath):
            continue

        with open(fpath, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    sym = data.get("symbol")
                    if not sym:
                        continue
                    if _is_replay_trace_candidate(data):
                        if sym not in traces_by_symbol:
                            traces_by_symbol[sym] = []
                        traces_by_symbol[sym].append(data)
                except Exception:
                    pass

    # Sort traces by ts_ms
    for sym in traces_by_symbol:
        traces_by_symbol[sym].sort(key=_trace_timestamp_ms)

    return traces_by_symbol


def find_closest_trace(traces: List[Dict[str, Any]], entry: Dict[str, Any], window_ms: int = 60000) -> Tuple[Dict[str, Any], str, str, int]:
    side = str(entry.get("side", "")).upper()
    entry_ts_ms = entry.get("entry_ts_ms", 0)
    rid = entry.get("rid", "")
    lifecycle_id = entry.get("lifecycle_id", "")
    trade_id = entry.get("trade_id", "")

    closest = {}
    min_diff = float('inf')
    join_key_used = "none"
    join_quality = "none"
    join_delta_ms = 0

    for trace in traces:
        t_ts = _trace_timestamp_ms(trace)
        t_side = str(trace.get("side", "")).upper()
        t_rid = trace.get("rid", "")
        t_lifecycle_id = trace.get("lifecycle_id", "")
        t_trade_id = trace.get("trade_id", "")

        diff = abs(t_ts - entry_ts_ms)

        # 1. Exact match by RID
        if rid and t_rid == rid:
            return trace, "rid", "exact", diff

        # 2. Exact match by lifecycle_id
        if lifecycle_id and t_lifecycle_id == lifecycle_id:
            return trace, "lifecycle_id", "exact", diff

        # 3. Exact match by trade_id
        if trade_id and t_trade_id == trade_id:
            return trace, "trade_id", "exact", diff

        # 4. Fallback to time-bounded match
        if diff <= window_ms:
            if t_side and t_side != side:
                continue
            if diff < min_diff:
                min_diff = diff
                closest = trace
                join_key_used = "nearest_timestamp"
                join_quality = "bounded_time"
                join_delta_ms = diff

    if not closest:
        join_key_used = "none"
        join_quality = "weak"

    return closest, join_key_used, join_quality, join_delta_ms


def safe_float(val, default=None):
    if val is None:
        return default
    try:
        return float(val)
    except:
        return default


def _parse_trade_lifecycle_row(
    data: Dict[str, Any],
    *,
    strategy_id: str,
    include_open: bool,
) -> Dict[str, Any] | None:
    symbol = data.get("symbol")
    if not symbol or symbol == "__DOMAIN__":
        return None

    event = str(data.get("event", "") or "").lower()
    state = str(data.get("state", "") or "").upper()
    ts_ms = data.get("ts_ms")
    entry_ts_ms = data.get("entry_ts_ms", data.get("entry_ts", ts_ms))

    if state == "CLOSED" and event == "closed":
        return {
            "lifecycle_id": data.get("lifecycle_id", ""),
            "trade_id": data.get("trade_id", ""),
            "rid": data.get("rid", ""),
            "symbol": symbol,
            "strategy_id": data.get("strategy_id", strategy_id),
            "side": data.get("side", ""),
            "entry_ts_ms": entry_ts_ms,
            "entry_price": data.get("entry_price", 0),
            "close_ts_ms": data.get("close_ts_ms", ts_ms),
            "outcome_status": "closed",
            "realized_pnl_net": safe_float(data.get("realized_pnl_net", 0)),
            "realized_pnl_gross": safe_float(data.get("realized_pnl_gross", 0)),
            "fee_total": safe_float(data.get("fee_total", data.get("fee", 0))),
        }

    if state == "OPEN" and event == "opened" and include_open:
        return {
            "lifecycle_id": data.get("lifecycle_id", ""),
            "trade_id": data.get("trade_id", ""),
            "rid": data.get("rid", ""),
            "symbol": symbol,
            "strategy_id": data.get("strategy_id", strategy_id),
            "side": data.get("side", ""),
            "entry_ts_ms": entry_ts_ms,
            "entry_price": data.get("entry_price", 0),
            "close_ts_ms": None,
            "outcome_status": "unresolved",
            "realized_pnl_net": None,
            "realized_pnl_gross": None,
            "fee_total": None,
        }

    return None


def evaluate_nrr_026(trace: Dict[str, Any], side: str, ds_cfg: Dict[str, Any], missing: List[str]) -> str:
    if not ds_cfg.get("nrr026_enabled", False):
        return "disabled"

    min_conf = safe_float(ds_cfg.get("min_regime_confidence"))
    if min_conf is None:
        missing.append("nrr026_min_regime_confidence_missing")
        return "null"

    trend_dir = trace.get("trend_dir", "UNKNOWN")
    reg_conf = safe_float(
        _extract_value(
            trace,
            ("regime_confidence",),
            ("metadata", "low_vol_cost_floor", "regime_confidence"),
        )
    )
    trend_conf = safe_float(trace.get("trend_confidence"))

    if reg_conf is None and trend_conf is None:
        missing.append("nrr026_confidence_missing")
        return "null"

    if trend_dir == "UNKNOWN":
        return "true"

    eff_conf = max(reg_conf or 0.0, trend_conf or 0.0)
    if eff_conf < min_conf:
        return "true"

    return "false"


def evaluate_nrr_027(trace: Dict[str, Any], side: str, ds_cfg: Dict[str, Any], missing: List[str]) -> str:
    if not ds_cfg.get("nrr027_enabled", False):
        return "disabled"

    trend_dir = trace.get("trend_dir", "UNKNOWN")
    trend_run = safe_float(trace.get("trend_run_length"))
    hard_veto = safe_float(ds_cfg.get("hard_veto_consecutive_bars"))
    if hard_veto is None:
        missing.append("nrr027_hard_veto_consecutive_bars_missing")
        return "null"
    hard_veto = int(hard_veto)

    if trend_run is None:
        missing.append("nrr027_trend_run_length_missing")
        return "null"

    if trend_dir == "DOWN" and side.upper() == "BUY":
        if trend_run >= hard_veto:
            return "true"
    if trend_dir == "UP" and side.upper() == "SELL":
        if trend_run >= hard_veto:
            return "true"

    return "false"


def evaluate_nrr_028(trace: Dict[str, Any], side: str, pm_cfg: Dict[str, Any], missing: List[str]) -> str:
    if not pm_cfg.get("enabled", False):
        return "disabled"
    pm_flash = _extract_price_motion_value(trace, "pm_norm_10s")
    pm_bleed = _extract_price_motion_value(trace, "pm_norm_60s")

    if pm_flash is None:
        missing.append("nrr028_pm_flash_missing")
        return "true"
    if pm_cfg.get("require_bleed_ready", False) and pm_bleed is None:
        missing.append("nrr028_pm_bleed_missing")
        return "true"
    return "false"


def evaluate_nrr_029(trace: Dict[str, Any], side: str, pm_cfg: Dict[str, Any], missing: List[str]) -> str:
    if not pm_cfg.get("enabled", False):
        return "disabled"
    pm_flash = safe_float(_extract_price_motion_value(trace, "pm_norm_10s"))
    t_flash = safe_float(pm_cfg.get("flash_threshold_norm"))
    if pm_flash is None:
        missing.append("nrr029_pm_flash_missing")
        return "null"
    if t_flash is None:
        missing.append("nrr029_flash_threshold_missing")
        return "null"

    if side.upper() == "BUY" and pm_flash <= -t_flash:
        return "true"
    if side.upper() == "SELL" and pm_flash >= t_flash:
        return "true"
    return "false"


def evaluate_nrr_030(trace: Dict[str, Any], side: str, pm_cfg: Dict[str, Any], missing: List[str]) -> str:
    if not pm_cfg.get("enabled", False):
        return "disabled"
    pm_bleed = safe_float(_extract_price_motion_value(trace, "pm_norm_60s"))
    t_bleed = safe_float(pm_cfg.get("bleed_threshold_norm"))
    if pm_bleed is None:
        missing.append("nrr030_pm_bleed_missing")
        return "null"
    if t_bleed is None:
        missing.append("nrr030_bleed_threshold_missing")
        return "null"

    if side.upper() == "BUY" and pm_bleed <= -t_bleed:
        return "true"
    if side.upper() == "SELL" and pm_bleed >= t_bleed:
        return "true"
    return "false"


def evaluate_anti_fomo(
    trace: Dict[str, Any],
    side: str,
    anti_fomo_enabled: bool,
    config_anti_fomo: float | None,
    missing: List[str],
) -> str:
    if not anti_fomo_enabled:
        return "disabled"

    if config_anti_fomo is None:
        missing.append("anti_fomo_sigma_missing")
        return "null"

    pm = safe_float(_extract_price_motion_value(trace, "pm_norm_300s"))
    if pm is None:
        missing.append("pm_norm_300s_missing")
        return "null"

    if abs(pm) > config_anti_fomo:
        return "true"
    return "false"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default="logs")
    parser.add_argument("--recorder-root", default="data/recorder")
    parser.add_argument("--config-root", default="config/aurora")
    parser.add_argument(
        "--out-dir", default="reports/anti_peak_counterfactual")
    parser.add_argument("--start", default="auto")
    parser.add_argument("--end", default="auto")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--strategy", default="aurora")
    parser.add_argument("--include-open", default="false")
    parser.add_argument("--strict", default="true")

    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    configs = parse_configs(args.config_root)
    ds_cfg = configs["directional_sanity"]
    pm_cfg = configs["price_motion_sanity"]
    cfg_anti_fomo_enabled = configs["anti_fomo_enabled"]
    cfg_anti_fomo = configs["anti_fomo_sigma"]

    # Update gate map based on real loaded config
    GATES_MAP["nrr_026"]["enabled_now"] = ds_cfg.get("nrr026_enabled", False)
    GATES_MAP["nrr_027"]["enabled_now"] = ds_cfg.get("nrr027_enabled", False)
    GATES_MAP["nrr_028"]["enabled_now"] = pm_cfg.get("enabled", False)
    GATES_MAP["nrr_029"]["enabled_now"] = pm_cfg.get("enabled", False)
    GATES_MAP["nrr_030"]["enabled_now"] = pm_cfg.get("enabled", False)
    GATES_MAP["gate_anti_fomo"]["enabled_now"] = cfg_anti_fomo_enabled

    traces_by_symbol = load_traces(args.runtime_root)

    positions = []
    tl_path = os.path.join(args.runtime_root, "trade_lifecycle.jsonl")
    raw_lifecycle_rows = 0
    include_open = args.include_open.lower() == "true"

    if os.path.exists(tl_path):
        with open(tl_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    raw_lifecycle_rows += 1
                    position = _parse_trade_lifecycle_row(
                        data,
                        strategy_id=args.strategy,
                        include_open=include_open,
                    )
                    if position is not None:
                        positions.append(position)
                except Exception:
                    pass

    if (
        args.strict.lower() == "true"
        and os.path.exists(tl_path)
        and raw_lifecycle_rows > 0
        and not positions
    ):
        raise SystemExit(
            "No usable trade_lifecycle opened/closed rows found; replay input contract unsupported"
        )

    results = []
    stats = {
        "losing_closed": 0,
        "winning_closed": 0,
        "unresolved": 0,
        "nrr_026_blocked": 0,
        "nrr_027_blocked": 0,
        "nrr_028_blocked": 0,
        "nrr_029_blocked": 0,
        "nrr_030_blocked": 0,
        "anti_fomo_blocked": 0,
        "any_gate_blocked": 0,
        "losing_blocked": 0,
        "winning_blocked": 0,
        "unresolved_blocked": 0,
        "net_loss_avoided": 0.0,
        "gross_loss_avoided": 0.0,
        "profit_missed": 0.0,
    }

    for p in positions:
        sym = p["symbol"]
        side = p["side"]

        trace, join_key_used, join_quality, join_delta_ms = find_closest_trace(
            traces_by_symbol.get(sym, []), p)

        p["join_key_used"] = join_key_used
        p["join_quality"] = join_quality
        p["join_delta_ms"] = join_delta_ms

        pnl = p["realized_pnl_net"]
        if p["outcome_status"] == "closed":
            if pnl and pnl < 0:
                stats["losing_closed"] += 1
            else:
                stats["winning_closed"] += 1
        else:
            stats["unresolved"] += 1

        missing_inputs = []
        nrr_026 = evaluate_nrr_026(trace, side, ds_cfg, missing_inputs)
        nrr_027 = evaluate_nrr_027(trace, side, ds_cfg, missing_inputs)
        nrr_028 = evaluate_nrr_028(trace, side, pm_cfg, missing_inputs)
        nrr_029 = evaluate_nrr_029(trace, side, pm_cfg, missing_inputs)
        nrr_030 = evaluate_nrr_030(trace, side, pm_cfg, missing_inputs)
        anti_fomo = evaluate_anti_fomo(
            trace,
            side,
            cfg_anti_fomo_enabled,
            safe_float(cfg_anti_fomo),
            missing_inputs,
        )

        any_blocked = "true" in [nrr_026, nrr_027,
                                 nrr_028, nrr_029, nrr_030, anti_fomo]

        p["nrr_026_would_block"] = nrr_026
        p["nrr_027_would_block"] = nrr_027
        p["nrr_028_would_block"] = nrr_028
        p["nrr_029_would_block"] = nrr_029
        p["nrr_030_would_block"] = nrr_030
        p["gate_anti_fomo_would_block"] = anti_fomo
        p["any_counterfactual_block"] = any_blocked
        p["data_quality"] = "partial" if trace else "insufficient_data"
        p["regime"] = trace.get("regime", "")
        p["regime_confidence"] = trace.get("regime_confidence", "")
        p["motion_norm_sigma"] = trace.get("pm_norm_300s", "")
        p["anti_fomo_sigma"] = cfg_anti_fomo
        p["missing_inputs"] = ";".join(missing_inputs) if missing_inputs else (
            "" if trace else "trace_missing")

        # Only count decisives if join quality is acceptable
        if any_blocked and join_quality in ["exact", "bounded_time"]:
            stats["any_gate_blocked"] += 1
            if nrr_026 == "true":
                stats["nrr_026_blocked"] += 1
            if nrr_027 == "true":
                stats["nrr_027_blocked"] += 1
            if nrr_028 == "true":
                stats["nrr_028_blocked"] += 1
            if nrr_029 == "true":
                stats["nrr_029_blocked"] += 1
            if nrr_030 == "true":
                stats["nrr_030_blocked"] += 1
            if anti_fomo == "true":
                stats["anti_fomo_blocked"] += 1

            if p["outcome_status"] == "closed":
                if pnl and pnl < 0:
                    stats["losing_blocked"] += 1
                    stats["net_loss_avoided"] += abs(pnl)
                    stats["gross_loss_avoided"] += abs(
                        p["realized_pnl_gross"] or 0)
                else:
                    stats["winning_blocked"] += 1
                    stats["profit_missed"] += (pnl or 0)
            else:
                stats["unresolved_blocked"] += 1

        results.append(p)

    with open(os.path.join(args.out_dir, "opened_positions_nrr_026_030_anti_fomo_counterfactual.csv"), "w", newline="") as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)

    with open(os.path.join(args.out_dir, "nrr_026_030_gate_map.json"), "w") as f:
        json.dump(GATES_MAP, f, indent=2)

    summary = {
        "runtime_start": "auto",
        "runtime_end": "auto",
        "total_opened_positions": len(positions),
        "total_closed_positions": stats["losing_closed"] + stats["winning_closed"],
        "total_losing_positions": stats["losing_closed"],
        "total_winning_positions": stats["winning_closed"],
        "total_unresolved_positions": stats["unresolved"],
        "losing_positions_blocked_by_any_gate": stats["losing_blocked"],
        "winning_positions_blocked_by_any_gate": stats["winning_blocked"],
        "unresolved_positions_blocked_by_any_gate": stats["unresolved_blocked"],
        "net_loss_avoided_if_blocked": stats["net_loss_avoided"],
        "gross_loss_avoided_if_blocked": stats["gross_loss_avoided"],
        "profit_missed_if_blocked": stats["profit_missed"],
        "net_counterfactual_delta": stats["net_loss_avoided"] - stats["profit_missed"],
        "gate_hit_counts": {
            "NRR-026": stats["nrr_026_blocked"],
            "NRR-027": stats["nrr_027_blocked"],
            "NRR-028": stats["nrr_028_blocked"],
            "NRR-029": stats["nrr_029_blocked"],
            "NRR-030": stats["nrr_030_blocked"],
            "GATE_ANTI_FOMO_SIGMA": stats["anti_fomo_blocked"]
        }
    }

    with open(os.path.join(args.out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
