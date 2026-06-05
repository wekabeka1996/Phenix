from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


T0_DIR = ROOT / "reports" / "runtime_forensics" / "T0"
OUT_DIR = ROOT / "reports" / "runtime_forensics" / "T3_decision_nrr_rebuild"

REQUIRED_INPUTS = {
    "runtime_manifest": T0_DIR / "runtime_manifest.json",
    "evidence_inventory": T0_DIR / "RUNTIME_EVIDENCE_INVENTORY.md",
    "disabled_truth_table": T0_DIR / "DISABLED_NRR_TRUTH_TABLE.md",
}

LOG_PATHS = {
    "order_log": ROOT / "logs" / "order_log_v1.jsonl",
    "trade_lifecycle": ROOT / "logs" / "trade_lifecycle.jsonl",
    "regime_confidence": ROOT / "logs" / "regime_confidence_audit_v1.jsonl",
    "shadow_journal": ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl",
}

CONFIG_PATHS = {
    "domains": ROOT / "config" / "aurora" / "domains.yaml",
    "trading": ROOT / "config" / "aurora" / "trading.yaml",
    "aurora_strategy": ROOT / "config" / "aurora" / "strategies" / "aurora.yaml",
}

DISABLED_REPLAY_GATES = ["NRR-026", "NRR-027", "NRR-028", "NRR-029", "NRR-030"]
ENFORCED_BASELINE_GATES = ["NRR-063", "low_vol_cost_floor_gate"]

NORMALIZED_COLUMNS = [
    "event_ts",
    "event_name",
    "source_file",
    "symbol",
    "strategy_id",
    "side",
    "tf_sec",
    "intent_id",
    "rid",
    "signal_id",
    "candidate_id",
    "status",
    "nrr_code",
    "reject_reason",
    "why_chain",
    "regime",
    "regime_confidence",
    "score",
    "signal_score",
    "final_score",
    "direction_confidence",
    "trend_dir",
    "trend_confidence",
    "trend_run_length",
    "pm_norm_60s",
    "pm_norm_300s",
    "entry_price",
    "stop_price",
    "target_price",
    "qty",
    "notional",
    "raw_payload_hash",
    "correlation_confidence",
]

REPLAY_COLUMNS = [
    "intent_id",
    "event_ts",
    "symbol",
    "strategy_id",
    "side",
    "nrr_code",
    "counterfactual_result",
    "result_reason",
    "missing_inputs",
    "required_inputs",
    "replay_method",
    "confidence",
    "evidence_source",
]

REJECT_COLUMNS = [
    "event_ts",
    "intent_id",
    "rid",
    "symbol",
    "strategy_id",
    "side",
    "nrr_code",
    "reject_reason",
    "why_chain",
    "status",
    "source_file",
    "raw_payload_hash",
    "evidence_source",
]

STRATEGY_SIGNAL_EVENT = "EVT:STRATEGY_SIGNAL_PRODUCED"
QUADRATIC_TRACE_EVENT = "EVT:QUADRATIC_DECISION_TRACE"
TRADE_INTENT_PROPOSED_EVENT = "EVT:TRADE_INTENT_PROPOSED"
TRADE_INTENT_REJECTED_EVENT = "EVT:TRADE_INTENT_REJECTED"


def nested_get(obj: Any, *path: str) -> Any:
    current = obj
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
        if current is None:
            return None
    return current


def iso_z(ts_ms: int | None) -> str:
    if ts_ms is None:
        return ""
    return __import__("datetime").datetime.fromtimestamp(
        ts_ms / 1000, tz=__import__("datetime").timezone.utc
    ).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_payload(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def dump_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def parse_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def decimal_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.15g}"
    return str(value)


def normalize_side(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    if text == "LONG":
        return "BUY"
    if text == "SHORT":
        return "SELL"
    return text


def join_why_chain(value: Any) -> str:
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=True)
    if value is None:
        return ""
    return str(value)


def parse_strategy_prices(why_items: list[str]) -> tuple[str, str]:
    stop_price = ""
    target_price = ""
    for item in why_items:
        match = re.search(
            r"strategy_prices:sl=([^,]+),tp=([^,\s]+)", str(item))
        if match:
            stop_price = match.group(1)
            target_price = match.group(2)
            break
    return stop_price, target_price


def parse_signal_why(why_items: list[str]) -> dict[str, str]:
    parsed = {
        "signal_score": "",
        "direction_confidence": "",
    }
    for item in why_items:
        text = str(item)
        score_match = re.search(r"score=([-+]?\d+(?:\.\d+)?)", text)
        if score_match and not parsed["signal_score"]:
            parsed["signal_score"] = score_match.group(1)
    return parsed


def check_directional_gate_replica(
    *,
    strategy_id: str,
    apply_safety_gates: bool,
    ds_enabled: bool,
    reduce_only: bool,
    intent_side: str,
    trend_dir: str,
    trend_run_length: int,
    trend_confidence: float,
    regime_confidence: float | None,
    min_conf: float,
    hard_veto_consecutive_bars: int,
    nrr026_enabled: bool,
    nrr027_enabled: bool,
) -> tuple[str, str | None, str]:
    effective_conf = max(float(regime_confidence or 0.0),
                         float(trend_confidence or 0.0))
    if reduce_only:
        return "ALLOW", None, "reduce_only"
    if not apply_safety_gates:
        return "ALLOW", None, f"safety_gates_skipped:strategy={strategy_id}"
    if not ds_enabled:
        return "ALLOW", None, "directional_sanity_disabled"
    if nrr026_enabled:
        if trend_dir not in {"UP", "DOWN"}:
            return "DENY", "NRR-026", "insufficient trend confirmation"
        if effective_conf < float(min_conf):
            return "DENY", "NRR-026", "insufficient confidence"
    if trend_dir == "DOWN" and intent_side == "LONG":
        if trend_run_length < int(hard_veto_consecutive_bars):
            return "ALLOW", None, f"countertrend long soft: run={trend_run_length} < veto_bars={hard_veto_consecutive_bars}"
        if nrr027_enabled:
            return "DENY", "NRR-027", "downtrend blocks long"
    if trend_dir == "UP" and intent_side == "SHORT":
        if trend_run_length < int(hard_veto_consecutive_bars):
            return "ALLOW", None, f"countertrend short soft: run={trend_run_length} < veto_bars={hard_veto_consecutive_bars}"
        if nrr027_enabled:
            return "DENY", "NRR-027", "uptrend blocks short"
    return "ALLOW", None, "ok"


def check_price_motion_gate_replica(
    *,
    price_motion_cfg: Any,
    trading_mode: str,
    intent_side: str,
    reduce_only: bool,
    apply_safety_gates: bool,
    pm_norm_10s: float | None,
    pm_norm_60s: float | None,
    pm_norm_300s: float | None,
) -> tuple[str, str | None, str]:
    pm_enabled = bool(getattr(price_motion_cfg, "enabled", False))
    is_backtest = str(trading_mode).strip().lower() == "backtest"
    if (not apply_safety_gates) or reduce_only or (not pm_enabled) or is_backtest:
        return "ALLOW", None, "ok"

    def select_pm(window_sec: int) -> float | None:
        if window_sec == 10:
            return pm_norm_10s
        if window_sec == 60:
            return pm_norm_60s
        if window_sec == 300:
            return pm_norm_300s
        raise ValueError(f"Unsupported price_motion window_sec={window_sec}")

    flash_window = int(getattr(price_motion_cfg, "flash_window_sec", 60))
    bleed_window = int(getattr(price_motion_cfg, "bleed_window_sec", 300))
    t_flash = float(getattr(price_motion_cfg, "flash_threshold_norm", 0.0))
    t_bleed = float(getattr(price_motion_cfg, "bleed_threshold_norm", 0.0))
    require_bleed_ready = bool(
        getattr(price_motion_cfg, "require_bleed_ready", False))

    pm_flash = select_pm(flash_window)
    pm_bleed = select_pm(bleed_window)
    if pm_flash is None:
        return "DENY", "NRR-028", "price_motion flash insufficient"
    if require_bleed_ready and pm_bleed is None:
        return "DENY", "NRR-028", "price_motion bleed insufficient"
    if intent_side == "LONG" and pm_flash <= -t_flash:
        return "DENY", "NRR-029", "flash down blocks long"
    if intent_side == "SHORT" and pm_flash >= t_flash:
        return "DENY", "NRR-029", "flash up blocks short"
    if pm_bleed is not None:
        if intent_side == "LONG" and pm_bleed <= -t_bleed:
            return "DENY", "NRR-030", "bleed down blocks long"
        if intent_side == "SHORT" and pm_bleed >= t_bleed:
            return "DENY", "NRR-030", "bleed up blocks short"
    return "ALLOW", None, "ok"


@dataclass
class ProposedIntent:
    rid: str
    intent_id: str
    symbol: str
    strategy_id: str
    side: str
    event_ts_ms: int
    tf_sec: int | None
    regime: str
    regime_confidence: float | None
    score: float | None
    signal_score: float | None
    final_score: float | None
    direction_confidence: float | None
    entry_price: str
    stop_price: str
    target_price: str
    qty: str
    notional: str
    raw_payload_hash: str
    why_chain: list[str]
    detector_bar_close_ts_ms: int | None
    candidate_id: str
    signal_id: str
    threshold_reason: str
    threshold_verdict: str
    min_regime_confidence: float | None
    max_regime_confidence: float | None


@dataclass
class RejectRecord:
    rid: str
    intent_id: str
    event_ts_ms: int
    symbol: str
    strategy_id: str
    side: str
    nrr_code: str
    reject_reason: str
    why_chain: str
    source_file: str
    raw_payload_hash: str


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def build_price_motion_runtime_config(domains_cfg: dict[str, Any], trading_cfg: dict[str, Any]) -> Any:
    pm_cfg = nested_get(domains_cfg, "decision_making",
                        "price_motion_sanity") or {}
    trading_mode = nested_get(trading_cfg, "trading", "mode") or ""
    return SimpleNamespace(
        trading_mode=str(trading_mode),
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                price_motion_sanity=SimpleNamespace(
                    enabled=bool(pm_cfg.get("enabled", False)),
                    flash_window_sec=int(pm_cfg.get("flash_window_sec", 60)),
                    bleed_window_sec=int(pm_cfg.get("bleed_window_sec", 300)),
                    flash_threshold_norm=float(
                        pm_cfg.get("flash_threshold_norm", 0.0)),
                    bleed_threshold_norm=float(
                        pm_cfg.get("bleed_threshold_norm", 0.0)),
                    require_bleed_ready=bool(
                        pm_cfg.get("require_bleed_ready", False)),
                )
            )
        ),
    )


def parse_disabled_gate_codes(truth_table_path: Path) -> list[str]:
    rows: list[str] = []
    for line in truth_table_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| NRR-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        nrr_code, _, _, enabled, enforced = cells[:5]
        if enabled.lower() == "no" and enforced.lower() == "no":
            rows.append(nrr_code)
    return rows


def window_filter(record: dict[str, Any], start_ms: int, end_ms: int) -> bool:
    ts = record.get("ts_ms")
    if ts is None:
        ts = record.get("timestamp")
    if ts is None:
        ts = record.get("ts")
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return False
    return start_ms <= ts <= end_ms


def coerce_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def coerce_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_replay_inputs_from_low_vol(metadata: dict[str, Any]) -> dict[str, Any]:
    low_vol = metadata.get("low_vol_cost_floor") if isinstance(
        metadata, dict) else None
    if not isinstance(low_vol, dict):
        return {}
    out = {}
    out["pm_norm_60s"] = coerce_float(nested_get(
        low_vol, "price_motion_context", "pm_norm_60s"))
    out["pm_norm_300s"] = coerce_float(nested_get(
        low_vol, "price_motion_context", "pm_norm_300s"))
    out["direction_confidence"] = coerce_float(
        low_vol.get("direction_confidence"))
    out["entry_price"] = decimal_text(low_vol.get("entry_price"))
    out["stop_price"] = decimal_text(low_vol.get("stop_price"))
    out["target_price"] = decimal_text(low_vol.get("target_price"))
    return out


def required_inputs_for_gate(nrr_code: str) -> list[str]:
    if nrr_code == "NRR-026":
        return ["trend_dir", "trend_confidence", "regime_confidence", "min_confidence"]
    if nrr_code == "NRR-027":
        return ["trend_dir", "trend_run_length", "intent_side", "hard_veto_consecutive_bars"]
    if nrr_code in {"NRR-028", "NRR-029", "NRR-030"}:
        return ["pm_norm_60s", "pm_norm_300s", "intent_side"]
    raise ValueError(f"unsupported gate {nrr_code}")


def replay_disabled_gate(
    *,
    nrr_code: str,
    row: ProposedIntent,
    directional_cfg: dict[str, Any],
    price_motion_runtime_cfg: Any,
    extra_inputs: dict[str, Any],
) -> dict[str, str]:
    gate_inputs = {
        "intent_side": "LONG" if row.side == "BUY" else "SHORT",
        "regime_confidence": row.regime_confidence,
        "min_confidence": coerce_float(directional_cfg.get("min_confidence")),
        "hard_veto_consecutive_bars": coerce_int(directional_cfg.get("hard_veto_consecutive_bars") or directional_cfg.get("consecutive_bars")),
        "trend_dir": extra_inputs.get("trend_dir"),
        "trend_confidence": extra_inputs.get("trend_confidence"),
        "trend_run_length": extra_inputs.get("trend_run_length"),
        "pm_norm_60s": extra_inputs.get("pm_norm_60s"),
        "pm_norm_300s": extra_inputs.get("pm_norm_300s"),
    }

    required_inputs = required_inputs_for_gate(nrr_code)
    missing_inputs = [
        name for name in required_inputs if gate_inputs.get(name) in (None, "")]
    if missing_inputs:
        return {
            "counterfactual_result": "UNPROVEN_INPUT_MISSING",
            "result_reason": f"missing_required_inputs:{','.join(missing_inputs)}",
            "missing_inputs": ",".join(missing_inputs),
            "required_inputs": ",".join(required_inputs),
            "replay_method": "runtime_gate_function_inputs_incomplete",
            "confidence": "0.0",
        }

    if nrr_code in {"NRR-026", "NRR-027"}:
        outcome, deny_reason, why_short = check_directional_gate_replica(
            strategy_id=row.strategy_id,
            apply_safety_gates=True,
            ds_enabled=True,
            reduce_only=False,
            intent_side=gate_inputs["intent_side"],
            trend_dir=str(gate_inputs["trend_dir"]),
            trend_run_length=int(gate_inputs["trend_run_length"]),
            trend_confidence=float(gate_inputs["trend_confidence"]),
            regime_confidence=float(gate_inputs["regime_confidence"]),
            min_conf=float(gate_inputs["min_confidence"]),
            hard_veto_consecutive_bars=int(
                gate_inputs["hard_veto_consecutive_bars"]),
            nrr026_enabled=bool(directional_cfg.get("nrr026_enabled", False)),
            nrr027_enabled=bool(directional_cfg.get("nrr027_enabled", False)),
        )
        blocked = outcome == "DENY" and deny_reason == nrr_code
        return {
            "counterfactual_result": "BLOCK" if blocked else "PASS",
            "result_reason": deny_reason or why_short or "allow",
            "missing_inputs": "",
            "required_inputs": ",".join(required_inputs),
            "replay_method": "audit_replica:check_directional_gate",
            "confidence": "1.0",
        }

    outcome, deny_reason, why_short = check_price_motion_gate_replica(
        price_motion_cfg=price_motion_runtime_cfg.domains.decision_making.price_motion_sanity,
        trading_mode=price_motion_runtime_cfg.trading_mode,
        intent_side=gate_inputs["intent_side"],
        reduce_only=False,
        apply_safety_gates=True,
        pm_norm_10s=None,
        pm_norm_60s=float(gate_inputs["pm_norm_60s"]),
        pm_norm_300s=float(gate_inputs["pm_norm_300s"]),
    )
    blocked = outcome == "DENY" and deny_reason == nrr_code
    return {
        "counterfactual_result": "BLOCK" if blocked else "PASS",
        "result_reason": deny_reason or why_short or "allow",
        "missing_inputs": "",
        "required_inputs": ",".join(required_inputs),
        "replay_method": "audit_replica:check_price_motion_gate",
        "confidence": "1.0",
    }


def load_runtime_inputs() -> tuple[dict[str, Any], list[str]]:
    missing = [str(path)
               for path in REQUIRED_INPUTS.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("BLOCKED: missing " + ", ".join(missing))
    runtime_manifest = json.loads(
        REQUIRED_INPUTS["runtime_manifest"].read_text(encoding="utf-8"))
    return runtime_manifest, parse_disabled_gate_codes(REQUIRED_INPUTS["disabled_truth_table"])


def build_indices(start_ms: int, end_ms: int) -> dict[str, Any]:
    shadow_signal_events: dict[str, dict[str, Any]] = {}
    shadow_trace_events: dict[str, dict[str, Any]] = {}
    shadow_proposed_events: dict[str, dict[str, Any]] = {}
    shadow_rejected_events: dict[str, dict[str, Any]] = {}
    regime_audit_by_rid: dict[str, dict[str, Any]] = {}
    order_intent_rows: dict[str, dict[str, Any]] = {}
    order_placed_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    decision_reject_rows: dict[str, dict[str, Any]] = {}
    exchange_reject_rows: list[dict[str, Any]] = []

    for row in parse_jsonl(LOG_PATHS["shadow_journal"]):
        if not window_filter(row, start_ms, end_ms):
            continue
        rid = str(row.get("rid") or "")
        if not rid:
            continue
        event_name = str(row.get("event_name") or "")
        if event_name == STRATEGY_SIGNAL_EVENT:
            shadow_signal_events[rid] = row
        elif event_name == QUADRATIC_TRACE_EVENT:
            shadow_trace_events[rid] = row
        elif event_name == TRADE_INTENT_PROPOSED_EVENT:
            shadow_proposed_events[rid] = row
        elif event_name == TRADE_INTENT_REJECTED_EVENT:
            shadow_rejected_events[rid] = row

    for row in parse_jsonl(LOG_PATHS["regime_confidence"]):
        if not window_filter(row, start_ms, end_ms):
            continue
        if str(row.get("record_type") or "") != "decision":
            continue
        rid = str(row.get("rid") or "")
        if rid:
            regime_audit_by_rid[rid] = row

    for row in parse_jsonl(LOG_PATHS["order_log"]):
        if not window_filter(row, start_ms, end_ms):
            continue
        event_type = str(row.get("event_type") or "")
        rid = str(row.get("rid") or "")
        if event_type == "ORDER_INTENT" and rid and row.get("source_fsm") == "DecisionMaking":
            order_intent_rows[rid] = row
        elif event_type == "ORDER_PLACED" and rid:
            order_placed_rows[rid].append(row)
        elif event_type == "DECISION_INTENT_REJECTED" and rid:
            decision_reject_rows[rid] = row
        elif event_type == "ORDER_REJECTED":
            exchange_reject_rows.append(row)

    return {
        "shadow_signal_events": shadow_signal_events,
        "shadow_trace_events": shadow_trace_events,
        "shadow_proposed_events": shadow_proposed_events,
        "shadow_rejected_events": shadow_rejected_events,
        "regime_audit_by_rid": regime_audit_by_rid,
        "order_intent_rows": order_intent_rows,
        "order_placed_rows": order_placed_rows,
        "decision_reject_rows": decision_reject_rows,
        "exchange_reject_rows": exchange_reject_rows,
    }


def build_proposed_intents(indices: dict[str, Any]) -> dict[str, ProposedIntent]:
    proposed: dict[str, ProposedIntent] = {}
    for rid, shadow_row in indices["shadow_proposed_events"].items():
        payload = shadow_row.get("payload_fragment") if isinstance(
            shadow_row.get("payload_fragment"), dict) else {}
        trace = payload.get("trace") if isinstance(
            payload.get("trace"), dict) else {}
        why_items = [str(item) for item in payload.get("why") or []]
        parsed_signal = parse_signal_why(why_items)
        stop_price, target_price = parse_strategy_prices(why_items)
        order_intent_row = indices["order_intent_rows"].get(rid, {})
        order_meta = order_intent_row.get("metadata") if isinstance(
            order_intent_row.get("metadata"), dict) else {}
        regime_audit = indices["regime_audit_by_rid"].get(rid, {})
        qty_value = payload.get("qty")
        entry_price = decimal_text(payload.get("price"))
        notional = ""
        try:
            if qty_value not in (None, "") and entry_price:
                notional = decimal_text(float(qty_value) * float(entry_price))
        except (TypeError, ValueError):
            notional = ""
        proposed[rid] = ProposedIntent(
            rid=rid,
            intent_id=str(payload.get("idempotent_key")
                          or order_meta.get("idempotent_key") or rid),
            symbol=str(payload.get("instrument") or shadow_row.get(
                "symbol") or order_intent_row.get("symbol") or ""),
            strategy_id=str(payload.get("strategy") or shadow_row.get(
                "strategy_id") or order_intent_row.get("strategy_id") or ""),
            side=normalize_side(payload.get("side") or shadow_row.get(
                "side") or order_intent_row.get("side")),
            event_ts_ms=coerce_int(shadow_row.get("ts_ms")) or 0,
            tf_sec=coerce_int(regime_audit.get("basis_tf_sec")),
            regime=str(payload.get("regime") or order_intent_row.get(
                "regime") or regime_audit.get("regime_used") or ""),
            regime_confidence=coerce_float(payload.get("regime_confidence") or order_intent_row.get(
                "regime_confidence") or regime_audit.get("regime_confidence_used")),
            score=coerce_float(trace.get("final_score_raw")),
            signal_score=coerce_float(
                trace.get("signal_score") or parsed_signal.get("signal_score")),
            final_score=coerce_float(trace.get("final_score_raw")),
            direction_confidence=coerce_float(trace.get(
                "strategy_confidence") or trace.get("strategy_confidence_candidate")),
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            qty=decimal_text(qty_value),
            notional=notional,
            raw_payload_hash=sha256_payload(shadow_row),
            why_chain=why_items,
            detector_bar_close_ts_ms=coerce_int(nested_get(trace, "detector_event", "bar_close_ts_ms") or nested_get(
                payload, "regime_provenance", "detector_event", "bar_close_ts_ms")),
            candidate_id=str(trace.get("decision_id")
                             or trace.get("cycle_key") or ""),
            signal_id=rid,
            threshold_reason=str(order_meta.get("threshold_reason") or ""),
            threshold_verdict=str(order_meta.get("threshold_verdict") or ""),
            min_regime_confidence=coerce_float(
                order_meta.get("resolved_min_regime_confidence")),
            max_regime_confidence=coerce_float(
                order_meta.get("resolved_max_regime_confidence")),
        )
    return proposed


def build_normalized_rows(indices: dict[str, Any], proposed_by_rid: dict[str, ProposedIntent]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for rid, shadow_row in indices["shadow_signal_events"].items():
        payload = shadow_row.get("payload_fragment") if isinstance(
            shadow_row.get("payload_fragment"), dict) else {}
        proposal = proposed_by_rid.get(rid)
        rows.append(
            {
                "event_ts": iso_z(coerce_int(shadow_row.get("ts_ms"))),
                "event_name": shadow_row.get("event_name"),
                "source_file": str(LOG_PATHS["shadow_journal"].relative_to(ROOT)).replace("\\", "/"),
                "symbol": shadow_row.get("symbol"),
                "strategy_id": shadow_row.get("strategy_id"),
                "side": normalize_side(shadow_row.get("side") or payload.get("side")),
                "tf_sec": proposal.tf_sec if proposal else "",
                "intent_id": proposal.intent_id if proposal else rid,
                "rid": rid,
                "signal_id": rid,
                "candidate_id": proposal.candidate_id if proposal else "",
                "status": "signal_produced",
                "nrr_code": "",
                "reject_reason": "",
                "why_chain": join_why_chain(payload.get("why_chain")),
                "regime": proposal.regime if proposal else "",
                "regime_confidence": proposal.regime_confidence if proposal and proposal.regime_confidence is not None else "",
                "score": proposal.score if proposal and proposal.score is not None else "",
                "signal_score": proposal.signal_score if proposal and proposal.signal_score is not None else "",
                "final_score": proposal.final_score if proposal and proposal.final_score is not None else "",
                "direction_confidence": proposal.direction_confidence if proposal and proposal.direction_confidence is not None else "",
                "trend_dir": "",
                "trend_confidence": "",
                "trend_run_length": "",
                "pm_norm_60s": "",
                "pm_norm_300s": "",
                "entry_price": proposal.entry_price if proposal else "",
                "stop_price": proposal.stop_price if proposal else "",
                "target_price": proposal.target_price if proposal else "",
                "qty": proposal.qty if proposal else "",
                "notional": proposal.notional if proposal else "",
                "raw_payload_hash": sha256_payload(shadow_row),
                "correlation_confidence": "1.0" if proposal else "0.7",
            }
        )

    for rid, shadow_row in indices["shadow_trace_events"].items():
        proposal = proposed_by_rid.get(rid)
        payload = shadow_row.get("payload_fragment") if isinstance(
            shadow_row.get("payload_fragment"), dict) else {}
        rows.append(
            {
                "event_ts": iso_z(coerce_int(shadow_row.get("ts_ms"))),
                "event_name": shadow_row.get("event_name"),
                "source_file": str(LOG_PATHS["shadow_journal"].relative_to(ROOT)).replace("\\", "/"),
                "symbol": shadow_row.get("symbol"),
                "strategy_id": shadow_row.get("strategy_id"),
                "side": normalize_side(payload.get("side") or shadow_row.get("side")),
                "tf_sec": proposal.tf_sec if proposal else "",
                "intent_id": proposal.intent_id if proposal else rid,
                "rid": rid,
                "signal_id": rid,
                "candidate_id": proposal.candidate_id if proposal else "",
                "status": "decision_trace",
                "nrr_code": "",
                "reject_reason": "",
                "why_chain": "",
                "regime": payload.get("regime") or (proposal.regime if proposal else ""),
                "regime_confidence": payload.get("regime_confidence") if payload.get("regime_confidence") is not None else (proposal.regime_confidence if proposal else ""),
                "score": proposal.score if proposal and proposal.score is not None else "",
                "signal_score": proposal.signal_score if proposal and proposal.signal_score is not None else "",
                "final_score": proposal.final_score if proposal and proposal.final_score is not None else "",
                "direction_confidence": proposal.direction_confidence if proposal and proposal.direction_confidence is not None else "",
                "trend_dir": "",
                "trend_confidence": "",
                "trend_run_length": "",
                "pm_norm_60s": "",
                "pm_norm_300s": "",
                "entry_price": proposal.entry_price if proposal else "",
                "stop_price": proposal.stop_price if proposal else "",
                "target_price": proposal.target_price if proposal else "",
                "qty": proposal.qty if proposal else "",
                "notional": proposal.notional if proposal else "",
                "raw_payload_hash": sha256_payload(shadow_row),
                "correlation_confidence": "1.0" if proposal else "0.7",
            }
        )

    for rid, proposal in proposed_by_rid.items():
        rows.append(
            {
                "event_ts": iso_z(proposal.event_ts_ms),
                "event_name": TRADE_INTENT_PROPOSED_EVENT,
                "source_file": str(LOG_PATHS["shadow_journal"].relative_to(ROOT)).replace("\\", "/"),
                "symbol": proposal.symbol,
                "strategy_id": proposal.strategy_id,
                "side": proposal.side,
                "tf_sec": proposal.tf_sec or "",
                "intent_id": proposal.intent_id,
                "rid": rid,
                "signal_id": proposal.signal_id,
                "candidate_id": proposal.candidate_id,
                "status": "proposed",
                "nrr_code": "",
                "reject_reason": proposal.threshold_reason,
                "why_chain": join_why_chain(proposal.why_chain),
                "regime": proposal.regime,
                "regime_confidence": proposal.regime_confidence if proposal.regime_confidence is not None else "",
                "score": proposal.score if proposal.score is not None else "",
                "signal_score": proposal.signal_score if proposal.signal_score is not None else "",
                "final_score": proposal.final_score if proposal.final_score is not None else "",
                "direction_confidence": proposal.direction_confidence if proposal.direction_confidence is not None else "",
                "trend_dir": "",
                "trend_confidence": "",
                "trend_run_length": "",
                "pm_norm_60s": "",
                "pm_norm_300s": "",
                "entry_price": proposal.entry_price,
                "stop_price": proposal.stop_price,
                "target_price": proposal.target_price,
                "qty": proposal.qty,
                "notional": proposal.notional,
                "raw_payload_hash": proposal.raw_payload_hash,
                "correlation_confidence": "1.0",
            }
        )

    accepted_rids = sorted(set(proposed_by_rid).intersection(
        indices["order_placed_rows"].keys()))
    for rid in accepted_rids:
        proposal = proposed_by_rid[rid]
        accepted_rows = sorted(indices["order_placed_rows"][rid], key=lambda row: int(
            row.get("timestamp") or 0))
        accepted = accepted_rows[0]
        rows.append(
            {
                "event_ts": iso_z(coerce_int(accepted.get("timestamp"))),
                "event_name": accepted.get("event_type"),
                "source_file": str(LOG_PATHS["order_log"].relative_to(ROOT)).replace("\\", "/"),
                "symbol": accepted.get("symbol"),
                "strategy_id": proposal.strategy_id,
                "side": normalize_side(accepted.get("side") or proposal.side),
                "tf_sec": proposal.tf_sec or "",
                "intent_id": proposal.intent_id,
                "rid": rid,
                "signal_id": proposal.signal_id,
                "candidate_id": proposal.candidate_id,
                "status": "accepted_for_execution",
                "nrr_code": "",
                "reject_reason": "",
                "why_chain": join_why_chain(proposal.why_chain),
                "regime": proposal.regime,
                "regime_confidence": proposal.regime_confidence if proposal.regime_confidence is not None else "",
                "score": proposal.score if proposal.score is not None else "",
                "signal_score": proposal.signal_score if proposal.signal_score is not None else "",
                "final_score": proposal.final_score if proposal.final_score is not None else "",
                "direction_confidence": proposal.direction_confidence if proposal.direction_confidence is not None else "",
                "trend_dir": "",
                "trend_confidence": "",
                "trend_run_length": "",
                "pm_norm_60s": "",
                "pm_norm_300s": "",
                "entry_price": proposal.entry_price,
                "stop_price": proposal.stop_price,
                "target_price": proposal.target_price,
                "qty": decimal_text(accepted.get("quantity") or proposal.qty),
                "notional": proposal.notional,
                "raw_payload_hash": sha256_payload(accepted),
                "correlation_confidence": "1.0",
            }
        )

    for rid, order_row in indices["decision_reject_rows"].items():
        metadata = order_row.get("metadata") if isinstance(
            order_row.get("metadata"), dict) else {}
        low_vol_inputs = extract_replay_inputs_from_low_vol(metadata)
        proposal = proposed_by_rid.get(rid)
        rows.append(
            {
                "event_ts": iso_z(coerce_int(order_row.get("timestamp"))),
                "event_name": order_row.get("event_type"),
                "source_file": str(LOG_PATHS["order_log"].relative_to(ROOT)).replace("\\", "/"),
                "symbol": order_row.get("symbol"),
                "strategy_id": order_row.get("strategy_id") or (proposal.strategy_id if proposal else ""),
                "side": normalize_side(order_row.get("side") or (proposal.side if proposal else "")),
                "tf_sec": proposal.tf_sec if proposal else "",
                "intent_id": proposal.intent_id if proposal else rid,
                "rid": rid,
                "signal_id": proposal.signal_id if proposal else rid,
                "candidate_id": proposal.candidate_id if proposal else "",
                "status": "rejected",
                "nrr_code": order_row.get("nrr_code") or metadata.get("deny_reason") or "",
                "reject_reason": metadata.get("reject_reason") or order_row.get("why") or "",
                "why_chain": join_why_chain(proposal.why_chain if proposal else metadata.get("why_chain") or []),
                "regime": order_row.get("regime") or (proposal.regime if proposal else ""),
                "regime_confidence": order_row.get("regime_confidence") if order_row.get("regime_confidence") is not None else (proposal.regime_confidence if proposal else ""),
                "score": proposal.score if proposal and proposal.score is not None else "",
                "signal_score": proposal.signal_score if proposal and proposal.signal_score is not None else "",
                "final_score": proposal.final_score if proposal and proposal.final_score is not None else "",
                "direction_confidence": low_vol_inputs.get("direction_confidence", proposal.direction_confidence if proposal and proposal.direction_confidence is not None else ""),
                "trend_dir": metadata.get("trend_dir") or "",
                "trend_confidence": metadata.get("trend_confidence") or "",
                "trend_run_length": metadata.get("trend_run_length") or "",
                "pm_norm_60s": low_vol_inputs.get("pm_norm_60s", metadata.get("pm_norm_60s") or ""),
                "pm_norm_300s": low_vol_inputs.get("pm_norm_300s", metadata.get("pm_norm_300s") or ""),
                "entry_price": low_vol_inputs.get("entry_price", proposal.entry_price if proposal else ""),
                "stop_price": low_vol_inputs.get("stop_price", proposal.stop_price if proposal else ""),
                "target_price": low_vol_inputs.get("target_price", proposal.target_price if proposal else ""),
                "qty": proposal.qty if proposal else decimal_text(order_row.get("quantity")),
                "notional": proposal.notional if proposal else "",
                "raw_payload_hash": sha256_payload(order_row),
                "correlation_confidence": "1.0" if proposal else "0.8",
            }
        )

    return sorted(rows, key=lambda row: (row["event_ts"], row["event_name"], row["rid"]))


def build_reject_rows(indices: dict[str, Any], proposed_by_rid: dict[str, ProposedIntent]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rid, order_row in sorted(indices["decision_reject_rows"].items(), key=lambda item: int(item[1].get("timestamp") or 0)):
        proposal = proposed_by_rid.get(rid)
        rows.append(
            {
                "event_ts": iso_z(coerce_int(order_row.get("timestamp"))),
                "intent_id": proposal.intent_id if proposal else rid,
                "rid": rid,
                "symbol": order_row.get("symbol"),
                "strategy_id": order_row.get("strategy_id") or (proposal.strategy_id if proposal else ""),
                "side": normalize_side(order_row.get("side") or (proposal.side if proposal else "")),
                "nrr_code": order_row.get("nrr_code") or "",
                "reject_reason": order_row.get("why") or nested_get(order_row, "metadata", "reject_reason") or "",
                "why_chain": join_why_chain(proposal.why_chain if proposal else []),
                "status": "rejected",
                "source_file": str(LOG_PATHS["order_log"].relative_to(ROOT)).replace("\\", "/"),
                "raw_payload_hash": sha256_payload(order_row),
                "evidence_source": "order_log_v1.jsonl + shadow_critical_event_journal_v1.jsonl",
            }
        )
    return rows


def build_counterfactual_rows(
    indices: dict[str, Any],
    proposed_by_rid: dict[str, ProposedIntent],
    directional_cfg: dict[str, Any],
    price_motion_runtime_cfg: Any,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    accepted_rids = sorted(set(proposed_by_rid).intersection(
        indices["order_placed_rows"].keys()))
    for rid in accepted_rids:
        proposal = proposed_by_rid[rid]
        decision_reject = indices["decision_reject_rows"].get(rid, {})
        low_vol_inputs = extract_replay_inputs_from_low_vol(decision_reject.get(
            "metadata") if isinstance(decision_reject.get("metadata"), dict) else {})
        extra_inputs = {
            "trend_dir": None,
            "trend_confidence": None,
            "trend_run_length": None,
            "pm_norm_60s": low_vol_inputs.get("pm_norm_60s"),
            "pm_norm_300s": low_vol_inputs.get("pm_norm_300s"),
        }
        for nrr_code in DISABLED_REPLAY_GATES:
            result = replay_disabled_gate(
                nrr_code=nrr_code,
                row=proposal,
                directional_cfg=directional_cfg,
                price_motion_runtime_cfg=price_motion_runtime_cfg,
                extra_inputs=extra_inputs,
            )
            rows.append(
                {
                    "intent_id": proposal.intent_id,
                    "event_ts": iso_z(proposal.event_ts_ms),
                    "symbol": proposal.symbol,
                    "strategy_id": proposal.strategy_id,
                    "side": proposal.side,
                    "nrr_code": nrr_code,
                    "counterfactual_result": result["counterfactual_result"],
                    "result_reason": result["result_reason"],
                    "missing_inputs": result["missing_inputs"],
                    "required_inputs": result["required_inputs"],
                    "replay_method": result["replay_method"],
                    "confidence": result["confidence"],
                    "evidence_source": "shadow_critical_event_journal_v1.jsonl + order_log_v1.jsonl + regime_confidence_audit_v1.jsonl",
                }
            )
    return rows


def render_top_counts(counter: Counter[str], limit: int = 8) -> str:
    if not counter:
        return "{}"
    items = [f"{key}:{value}" for key, value in counter.most_common(limit)]
    return "{" + ", ".join(items) + "}"


def build_report(
    *,
    runtime_manifest: dict[str, Any],
    normalized_rows: list[dict[str, Any]],
    replay_rows: list[dict[str, Any]],
    reject_rows: list[dict[str, Any]],
    proposed_by_rid: dict[str, ProposedIntent],
    accepted_count: int,
    disabled_gate_codes: list[str],
    exchange_reject_rows: list[dict[str, Any]],
) -> str:
    signals = {row["rid"]
               for row in normalized_rows if row["event_name"] == STRATEGY_SIGNAL_EVENT}
    proposed = {row["rid"] for row in normalized_rows if row["event_name"]
                == TRADE_INTENT_PROPOSED_EVENT}
    rejected_by_nrr = Counter(row["nrr_code"]
                              for row in reject_rows if row["nrr_code"])
    replay_results = Counter(row["counterfactual_result"]
                             for row in replay_rows)
    gate_summary: dict[str, Counter[str]] = defaultdict(Counter)
    for row in replay_rows:
        gate_summary[row["nrr_code"]][row["counterfactual_result"]] += 1
    unproven_reasons = Counter(
        row["result_reason"] for row in replay_rows if row["counterfactual_result"].startswith("UNPROVEN"))

    baseline_nrr063 = Counter(
        row["nrr_code"]
        for row in reject_rows
        if row["nrr_code"] == "NRR-063"
    )
    low_vol_blocks = sum(
        1 for row in normalized_rows if row["nrr_code"] == "NRR-062")
    verdict = "DECISION_NRR_REPLAY_COMPLETE"
    if replay_results["UNPROVEN_INPUT_MISSING"] > 0:
        verdict = "PARTIAL_INPUT_GAPS"
    if not normalized_rows:
        verdict = "BLOCKED"

    proven = [
        f"T0 inputs found at {T0_DIR.as_posix()} and runtime window respected exactly.",
        f"Canonical decision chain reconstructed from shadow journal for {len(proposed)} proposed intents and {len(signals)} strategy signals.",
        f"Accepted intent replay dataset generated for {accepted_count} accepted intents across {len(DISABLED_REPLAY_GATES)} disabled gates.",
    ]
    unproven = []
    if replay_results["UNPROVEN_INPUT_MISSING"]:
        unproven.append(
            "Directional and price-motion gate inputs are not durably persisted for accepted intents in the allowed evidence surfaces, so disabled-gate replay is mostly input-limited."
        )
    if exchange_reject_rows:
        unproven.append(
            "Exchange/order-layer rejects (for example NRR-015 propagation failures) were observed but are not counted as decision-intent rejects in T3 summary metrics."
        )

    risks = [
        "Accepted-intent replay cannot safely infer PASS from absent decision-time inputs; missing fields remain fail-closed as UNPROVEN_INPUT_MISSING.",
        "Text decision logs expose regime-band audit lines but did not provide a deterministic RID-scoped recovery surface for trend_dir/trend_run_length or price-motion values.",
    ]

    lines = [
        "AGENT_REPORT_V1",
        "",
        "task:",
        "  AURORA_DECISION_NRR_REBUILD_T3A",
        "",
        "verdict:",
        f"  {verdict}",
        "",
        "runtime_window:",
        f"  start_ts: {runtime_manifest['runtime_window']['start_ts']}",
        f"  end_ts: {runtime_manifest['runtime_window']['end_ts']}",
        "",
        "decision_summary:",
        f"  strategy_signals: {len(signals)}",
        f"  trade_intents_proposed: {len(proposed)}",
        f"  trade_intents_rejected: {len(reject_rows)}",
        f"  accepted_for_execution: {accepted_count}",
        f"  rejected_by_nrr_top: {render_top_counts(rejected_by_nrr)}",
        "",
        "counterfactual_summary:",
        f"  disabled_gates_tested: {', '.join(disabled_gate_codes)}",
        f"  accepted_intents_replayed: {accepted_count}",
        f"  total_block: {replay_results['BLOCK']}",
        f"  total_pass: {replay_results['PASS']}",
        f"  total_unproven: {sum(value for key, value in replay_results.items() if key.startswith('UNPROVEN'))}",
        f"  unproven_reasons: {render_top_counts(unproven_reasons)}",
        "",
        "per_gate_summary:",
    ]
    for gate in DISABLED_REPLAY_GATES:
        summary = gate_summary.get(gate, Counter())
        lines.append(
            f"  {gate}: BLOCK={summary['BLOCK']} PASS={summary['PASS']} UNPROVEN={sum(v for k, v in summary.items() if k.startswith('UNPROVEN'))}"
        )
    lines.extend(
        [
            "",
            "enforced_baseline_observed:",
            f"  NRR-063: observed_rejects={baseline_nrr063['NRR-063']}",
            f"  low_vol_cost_floor_gate: observed_blocks={low_vol_blocks}",
            "",
            "proven:",
        ]
    )
    lines.extend([f"  - {item}" for item in proven])
    lines.append("")
    lines.append("unproven:")
    lines.extend([f"  - {item}" for item in unproven] or ["  - none"])
    lines.append("")
    lines.append("risks:")
    lines.extend([f"  - {item}" for item in risks])
    lines.extend(
        [
            "",
            "handoff_to_T4:",
            "  datasets: decision_events_normalized.csv, accepted_intents_counterfactual_nrr_replay.csv, rejected_intents_by_nrr.csv",
            "  caveats: Treat NRR-026..030 replay rows with UNPROVEN_INPUT_MISSING as evidence of observability gaps, not as safe PASS decisions.",
            "",
            "facts:",
            f"  canonical_proposed_rids: {len(proposed_by_rid)}",
            f"  order_log_exchange_reject_rows: {len(exchange_reject_rows)}",
            f"  normalized_rows_total: {len(normalized_rows)}",
            f"  replay_rows_total: {len(replay_rows)}",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    runtime_manifest, disabled_gate_codes = load_runtime_inputs()
    missing_logs = [str(path)
                    for path in LOG_PATHS.values() if not path.exists()]
    if missing_logs:
        raise FileNotFoundError("BLOCKED: missing " + ", ".join(missing_logs))

    start_ts = runtime_manifest["runtime_window"]["start_ts"]
    end_ts = runtime_manifest["runtime_window"]["end_ts"]
    start_ms = int(__import__("datetime").datetime.fromisoformat(
        start_ts.replace("Z", "+00:00")).timestamp() * 1000)
    end_ms = int(__import__("datetime").datetime.fromisoformat(
        end_ts.replace("Z", "+00:00")).timestamp() * 1000)

    domains_cfg = load_yaml(CONFIG_PATHS["domains"])
    trading_cfg = load_yaml(CONFIG_PATHS["trading"])
    price_motion_runtime_cfg = build_price_motion_runtime_config(
        domains_cfg, trading_cfg)
    directional_cfg = nested_get(
        domains_cfg, "decision_making", "directional_sanity") or {}

    indices = build_indices(start_ms, end_ms)
    proposed_by_rid = build_proposed_intents(indices)
    normalized_rows = build_normalized_rows(indices, proposed_by_rid)
    reject_rows = build_reject_rows(indices, proposed_by_rid)
    replay_rows = build_counterfactual_rows(
        indices, proposed_by_rid, directional_cfg, price_motion_runtime_cfg)
    accepted_count = len(set(proposed_by_rid).intersection(
        indices["order_placed_rows"].keys()))

    present_gates = {row["nrr_code"] for row in replay_rows}
    missing_gate_coverage = [
        gate for gate in disabled_gate_codes if gate not in present_gates]
    if missing_gate_coverage:
        raise RuntimeError(
            f"disabled gate coverage missing: {missing_gate_coverage}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dump_csv(OUT_DIR / "decision_events_normalized.csv",
             NORMALIZED_COLUMNS, normalized_rows)
    dump_csv(OUT_DIR / "accepted_intents_counterfactual_nrr_replay.csv",
             REPLAY_COLUMNS, replay_rows)
    dump_csv(OUT_DIR / "rejected_intents_by_nrr.csv",
             REJECT_COLUMNS, reject_rows)

    report_text = build_report(
        runtime_manifest=runtime_manifest,
        normalized_rows=normalized_rows,
        replay_rows=replay_rows,
        reject_rows=reject_rows,
        proposed_by_rid=proposed_by_rid,
        accepted_count=accepted_count,
        disabled_gate_codes=disabled_gate_codes,
        exchange_reject_rows=indices["exchange_reject_rows"],
    )
    (OUT_DIR / "DECISION_NRR_REBUILD_REPORT.md").write_text(report_text, encoding="utf-8")

    print(
        json.dumps(
            {
                "normalized_rows": len(normalized_rows),
                "proposed_intents": len(proposed_by_rid),
                "rejected_intents": len(reject_rows),
                "accepted_intents": accepted_count,
                "replay_rows": len(replay_rows),
                "disabled_gates": disabled_gate_codes,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
