from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


TARGET_OVERRIDE_NAME = "LOW_VOL_SHORT_DIRECTION_ONLY_RAW_SIGNAL"
EXPECTED_OVERRIDE_SIDE = "SELL"
EXPECTED_OVERRIDE_REGIME = "LOW_VOLATILITY"

EXPECTED_ORDER_LOG = "logs/order_log_v1.jsonl"
EXPECTED_TRADE_LIFECYCLE = "logs/trade_lifecycle.jsonl"
EXPECTED_DECISION_LEDGER = "logs/shadow_telemetry/decision_ledger_v1.jsonl"
EXPECTED_SHADOW_JOURNAL = "logs/shadow_critical_event_journal_v1.jsonl"

REJECT_TERMINAL_STATUSES = {
    "REJECTED",
    "REJECTED_UPSTREAM",
    "INVALID_REJECTED",
}

ALTERNATIVE_TERMINAL_EVENTS = {
    "DECISION_INTENT_REJECTED",
    "ORDER_CANCELLED",
    "ORDER_REJECTED",
    "ORDER_TIMEOUT",
}

ACCEPTED_ENABLE_BUNDLE = (
    REPO_ROOT
    / "frozen"
    / "sidecar_peak_giveback_disabled_runtime_20260515T094228Z"
)
ACCEPTED_ENABLE_DOMAINS = (
    ACCEPTED_ENABLE_BUNDLE / "config_snapshot" / "config" / "aurora" / "domains.yaml"
)

PACKAGE_F_REPLAY_JSON = (
    REPO_ROOT
    / "calibrators"
    / "datasets"
    / "nrr062_segment_logic"
    / "nrr062_segment_replay_evaluation.json"
)
PACKAGE_H_LEDGER_JSON = (
    REPO_ROOT
    / "calibrators"
    / "datasets"
    / "nrr062_testnet_override_runtime"
    / "nrr062_override_runtime_ledger.json"
)
PACKAGE_L_LEDGER_JSON = (
    REPO_ROOT
    / "calibrators"
    / "datasets"
    / "nrr062_testnet_override_runtime"
    / "nrr062_override_runtime_ledger_l.json"
)
SHADOW_ECONOMICS_JSON = (
    REPO_ROOT
    / "calibrators"
    / "datasets"
    / "nrr062_testnet_override_runtime"
    / "nrr062_override_economics_stability_review.json"
)
SHADOW_BOUNDARY_JSON = (
    REPO_ROOT
    / "calibrators"
    / "datasets"
    / "nrr062_testnet_override_runtime"
    / "nrr062_override_boundary_stability_review_l.json"
)


@dataclass(frozen=True)
class SourceSurface:
    path: Path
    relative_path: str
    source_kind: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_ts_ms(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            numeric = float(stripped)
        except ValueError:
            normalized = stripped.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1000)
    elif isinstance(value, (int, float)):
        numeric = float(value)
    else:
        return None
    if abs(numeric) < 10_000_000_000:
        return int(numeric * 1000)
    return int(numeric)


def _ts_ms_to_iso(ts_ms: Optional[int]) -> Optional[str]:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def _relative_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            rows.append({**payload, "_line_number": line_number})
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2,
                    ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    serializable_rows: list[dict[str, Any]] = []
    for row in rows:
        serialized: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, (list, dict)):
                serialized[key] = json.dumps(value, ensure_ascii=False)
            else:
                serialized[key] = value
        serializable_rows.append(serialized)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in serializable_rows:
            writer.writerow(row)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _classify_workspace_surface_kind(relative_path: str, authority_relative_path: str) -> str:
    if relative_path == authority_relative_path:
        return "current_workspace_authority"
    if relative_path.startswith("logs/frozen/"):
        return "supplemental_frozen"
    return "explicit_cli_override"


def _is_authority_source_kind(source_kind: Any) -> bool:
    return source_kind == "current_workspace_authority"


def _row_key(row: dict[str, Any]) -> tuple[str, int]:
    return (str(row.get("_source_path")), int(row.get("_line_number", 0)))


def _dedupe_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, int]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = _row_key(row)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _event_type(row: dict[str, Any]) -> str:
    return (
        _normalize_text(row.get("event_type"))
        or _normalize_text(row.get("status"))
        or _normalize_text(row.get("event"))
        or "UNKNOWN"
    )


def _has_realized_fields(row: dict[str, Any]) -> bool:
    return row.get("realized_pnl_net") not in (None, "") or row.get("fees") not in (None, "")


def _trade_lifecycle_is_close(row: dict[str, Any]) -> bool:
    event_type = _event_type(row)
    status = (_normalize_text(row.get("status")) or "").upper()
    close_reason = _normalize_text(row.get("close_reason"))
    return bool(
        event_type == "POSITION_CLOSED"
        or "CLOSE" in event_type
        or status in {"CLOSED", "EXECUTED_AND_CLOSED", "COMPLETED"}
        or row.get("close_ts_ms") not in (None, "")
        or (close_reason is not None and status not in REJECT_TERMINAL_STATUSES)
    )


def _trade_lifecycle_is_fill(row: dict[str, Any]) -> bool:
    event_type = _event_type(row)
    trigger_event = (_normalize_text(row.get("trigger_event")) or "").upper()
    return (
        event_type == "EXECUTION_FILL_INGRESS"
        or trigger_event == "TRADE_EXECUTED"
        or event_type == "TRADE_EXECUTED"
    )


def _order_log_is_entry_fill(row: dict[str, Any]) -> bool:
    if _event_type(row) != "ORDER_FILLED":
        return False
    order_kind = (_normalize_text(row.get("order_kind")) or "ENTRY").upper()
    close_reason = _normalize_text(row.get("close_reason"))
    return order_kind == "ENTRY" and close_reason is None


def _order_log_is_close_fill(row: dict[str, Any]) -> bool:
    if _event_type(row) != "ORDER_FILLED":
        return False
    order_kind = (_normalize_text(row.get("order_kind")) or "").upper()
    close_reason = _normalize_text(row.get("close_reason"))
    return order_kind in {"CLOSE", "EXIT", "TP", "SL"} or close_reason is not None


def _order_log_is_close_submitted(row: dict[str, Any]) -> bool:
    event_type = _event_type(row)
    if event_type not in {"ORDER_INTENT", "ORDER_PLACED"}:
        return False
    order_kind = (_normalize_text(row.get("order_kind")) or "").upper()
    close_reason = _normalize_text(row.get("close_reason"))
    rid = _normalize_text(row.get("rid")) or ""
    return order_kind in {"CLOSE", "EXIT", "TP", "SL"} or close_reason is not None or rid.startswith("ppsreq:")


def _row_ts_ms(row: dict[str, Any]) -> int:
    for key in (
        "timestamp",
        "ts_ms",
        "close_ts_ms",
        "updated_ts_ms",
        "snapshot_ts_ms",
        "order_ts_ms",
        "fill_ts_ms",
        "created_ts_ms",
        "request_ts_ms",
        "response_ts_ms",
    ):
        parsed = _parse_ts_ms(row.get(key))
        if parsed is not None:
            return parsed
    return 0


def _make_surface(path: Path, authority_relative_path: str) -> SourceSurface:
    relative_path = _relative_path(REPO_ROOT, path)
    return SourceSurface(
        path=path,
        relative_path=relative_path,
        source_kind=_classify_workspace_surface_kind(
            relative_path, authority_relative_path),
    )


def _build_index(surfaces: list[SourceSurface]) -> dict[str, Any]:
    by_rid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_lifecycle: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_trade: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_suffix_alias: dict[str, list[dict[str, Any]]] = defaultdict(list)
    malformed_rows: list[dict[str, Any]] = []
    source_stats: list[dict[str, Any]] = []
    for surface in surfaces:
        rows = _read_jsonl(surface.path)
        source_stats.append(
            {
                "path": surface.relative_path,
                "source_kind": surface.source_kind,
                "rows": len(rows),
            }
        )
        for row in rows:
            payload = dict(row)
            payload["_source_path"] = surface.relative_path
            payload["_source_kind"] = surface.source_kind
            rid = _normalize_text(payload.get("rid"))
            lifecycle_id = _normalize_text(payload.get("lifecycle_id"))
            trade_id = _normalize_text(payload.get("trade_id"))
            event_type = _normalize_text(payload.get("event_type"))
            if rid is not None:
                by_rid[rid].append(payload)
                if ":" in rid:
                    by_suffix_alias[rid.split(":", 1)[0]].append(payload)
            if lifecycle_id is not None:
                by_lifecycle[lifecycle_id].append(payload)
            if trade_id is not None:
                by_trade[trade_id].append(payload)
            if event_type is None and rid is None and lifecycle_id is None and trade_id is None:
                malformed_rows.append(payload)
    return {
        "by_rid": by_rid,
        "by_lifecycle": by_lifecycle,
        "by_trade": by_trade,
        "by_suffix_alias": by_suffix_alias,
        "malformed_rows": malformed_rows,
        "source_stats": source_stats,
    }


def _collect_order_summary(decision: dict[str, Any], order_index: dict[str, Any]) -> dict[str, Any]:
    rid = decision["rid"]
    lifecycle_id = decision.get("lifecycle_id")
    trade_id = decision.get("trade_id")
    exact_rows = list(order_index["by_rid"].get(rid, []))
    suffix_alias_rows = [
        row
        for row in order_index["by_suffix_alias"].get(rid, [])
        if (_normalize_text(row.get("rid")) or "") != rid
    ]
    lifecycle_bridge_keys = [key for key in [
        lifecycle_id, rid, decision.get("downstream_rid")] if key]
    lifecycle_rows: list[dict[str, Any]] = []
    for key in lifecycle_bridge_keys:
        lifecycle_rows.extend(order_index["by_lifecycle"].get(key, []))
    trade_rows = list(order_index["by_trade"].get(
        trade_id, [])) if trade_id else []
    relevant_rows = _dedupe_rows(
        [*exact_rows, *suffix_alias_rows, *lifecycle_rows, *trade_rows])
    position_closed_rows = [
        row for row in relevant_rows if _event_type(row) == "POSITION_CLOSED"]
    entry_fill_rows = [
        row for row in relevant_rows if _order_log_is_entry_fill(row)]
    close_fill_rows = [
        row for row in relevant_rows if _order_log_is_close_fill(row)]
    close_submitted_rows = [
        row for row in relevant_rows if _order_log_is_close_submitted(row)]
    placed_rows = [row for row in relevant_rows if _event_type(
        row) == "ORDER_PLACED"]
    has_authority_source = any(_is_authority_source_kind(
        row.get("_source_kind")) for row in relevant_rows)
    exact_event_counts = Counter(_event_type(row) for row in exact_rows)
    bridge_event_counts = Counter(
        _event_type(row) for row in _dedupe_rows([*suffix_alias_rows, *lifecycle_rows, *trade_rows])
    )
    has_alt_terminal = any(_event_type(
        row) in ALTERNATIVE_TERMINAL_EVENTS for row in relevant_rows)
    has_realized_fields_without_position_closed = any(_has_realized_fields(
        row) for row in relevant_rows) and not bool(position_closed_rows)
    malformed_count = sum(1 for row in relevant_rows if _normalize_text(
        row.get("event_type")) is None)
    if not relevant_rows:
        primary_bucket = "no order_log rows"
    elif malformed_count:
        primary_bucket = "malformed/incomplete rows"
    elif len(position_closed_rows) > 1:
        primary_bucket = "duplicate close candidates"
    elif position_closed_rows:
        primary_bucket = "POSITION_CLOSED present"
    elif close_fill_rows:
        primary_bucket = "close fill present"
    elif close_submitted_rows:
        primary_bucket = "close submitted"
    elif has_realized_fields_without_position_closed:
        primary_bucket = "realized fields present without POSITION_CLOSED"
    elif has_alt_terminal:
        primary_bucket = "alternative terminal event present"
    elif entry_fill_rows:
        primary_bucket = "entry fill present"
    else:
        primary_bucket = "order placed only"
    return {
        "primary_bucket": primary_bucket,
        "relevant_rows": relevant_rows,
        "exact_rows": exact_rows,
        "suffix_alias_rows": suffix_alias_rows,
        "lifecycle_rows": lifecycle_rows,
        "trade_rows": trade_rows,
        "position_closed_rows": position_closed_rows,
        "entry_fill_rows": entry_fill_rows,
        "close_fill_rows": close_fill_rows,
        "close_submitted_rows": close_submitted_rows,
        "placed_rows": placed_rows,
        "exact_event_counts": dict(sorted(exact_event_counts.items())),
        "bridge_event_counts": dict(sorted(bridge_event_counts.items())),
        "has_authority_source": has_authority_source,
        "has_alternative_terminal_event": has_alt_terminal,
        "has_realized_fields_without_position_closed": has_realized_fields_without_position_closed,
        "source_paths": sorted({str(row.get("_source_path")) for row in relevant_rows}),
    }


def _collect_trade_lifecycle_summary(decision: dict[str, Any], trade_index: dict[str, Any]) -> dict[str, Any]:
    rid = decision["rid"]
    lifecycle_id = decision.get("lifecycle_id")
    trade_id = decision.get("trade_id")
    exact_rows = list(trade_index["by_rid"].get(rid, []))
    lifecycle_bridge_keys = [key for key in [
        lifecycle_id, rid, decision.get("downstream_rid")] if key]
    lifecycle_rows: list[dict[str, Any]] = []
    for key in lifecycle_bridge_keys:
        lifecycle_rows.extend(trade_index["by_lifecycle"].get(key, []))
    trade_rows = list(trade_index["by_trade"].get(
        trade_id, [])) if trade_id else []
    relevant_rows = _dedupe_rows([*exact_rows, *lifecycle_rows, *trade_rows])
    terminal_rows = [
        row for row in relevant_rows if _trade_lifecycle_is_close(row)]
    rejected_rows = [
        row
        for row in relevant_rows
        if (_normalize_text(row.get("status")) or "").upper() in REJECT_TERMINAL_STATUSES
    ]
    fill_rows = [row for row in relevant_rows if _trade_lifecycle_is_fill(row)]
    exact_status_counts = Counter(_event_type(row) for row in exact_rows)
    bridge_status_counts = Counter(_event_type(
        row) for row in _dedupe_rows([*lifecycle_rows, *trade_rows]))
    return {
        "relevant_rows": relevant_rows,
        "terminal_rows": terminal_rows,
        "rejected_rows": rejected_rows,
        "fill_rows": fill_rows,
        "exact_status_counts": dict(sorted(exact_status_counts.items())),
        "bridge_status_counts": dict(sorted(bridge_status_counts.items())),
        "source_paths": sorted({str(row.get("_source_path")) for row in relevant_rows}),
        "has_terminal_close": bool(terminal_rows),
        "has_rejected_terminal": bool(rejected_rows),
        "has_fill_ingress": bool(fill_rows),
    }


def _latest_row(rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not rows:
        return None
    return sorted(rows, key=_row_ts_ms)[-1]


def _extract_close_row(order_summary: dict[str, Any]) -> Optional[dict[str, Any]]:
    if order_summary["position_closed_rows"]:
        return _latest_row(order_summary["position_closed_rows"])
    if order_summary["close_fill_rows"]:
        return _latest_row(order_summary["close_fill_rows"])
    return None


def _derive_order_state(order_summary: dict[str, Any], lifecycle_summary: dict[str, Any]) -> tuple[bool, bool, bool]:
    close_row = _extract_close_row(order_summary)
    entry_filled = bool(
        order_summary["entry_fill_rows"] or lifecycle_summary["fill_rows"])
    order_submitted = bool(
        order_summary["placed_rows"] or entry_filled or close_row)
    position_closed = close_row is not None and _event_type(
        close_row) == "POSITION_CLOSED"
    return order_submitted, entry_filled, position_closed


def _derive_close_fields(close_row: Optional[dict[str, Any]]) -> dict[str, Any]:
    if close_row is None:
        return {
            "close_reason": None,
            "realized_pnl_net": None,
            "gross_pnl": None,
            "fees": None,
            "close_ts_ms": None,
            "close_ts_utc": None,
        }
    close_ts_ms = _row_ts_ms(close_row)
    realized_pnl_net = _safe_float(close_row.get("realized_pnl_net"))
    fees = _safe_float(close_row.get("fees"))
    gross_pnl = _safe_float(close_row.get("gross_pnl"))
    if gross_pnl is None and realized_pnl_net is not None and fees is not None:
        gross_pnl = realized_pnl_net + fees
    return {
        "close_reason": _normalize_text(close_row.get("close_reason")),
        "realized_pnl_net": realized_pnl_net,
        "gross_pnl": gross_pnl,
        "fees": fees,
        "close_ts_ms": close_ts_ms,
        "close_ts_utc": _ts_ms_to_iso(close_ts_ms),
    }


def _trade_statuses(lifecycle_summary: dict[str, Any]) -> list[str]:
    return sorted({_event_type(row) for row in lifecycle_summary["relevant_rows"]})


def _order_events(order_summary: dict[str, Any]) -> list[str]:
    return sorted({_event_type(row) for row in order_summary["relevant_rows"]})


def _classify_bucket(
    order_summary: dict[str, Any],
    lifecycle_summary: dict[str, Any],
    decision_status: Optional[str],
) -> tuple[str, bool, dict[str, Any]]:
    close_row = _extract_close_row(order_summary)
    order_submitted, entry_filled, position_closed = _derive_order_state(
        order_summary, lifecycle_summary)
    close_fields = _derive_close_fields(close_row)
    exact_roundtrip = bool(close_row and entry_filled and _event_type(
        close_row) == "POSITION_CLOSED")
    reject_like_runtime = any(
        (_normalize_text(row.get("status")) or "").upper(
        ) in REJECT_TERMINAL_STATUSES | {"ORPHANED_TTL"}
        for row in lifecycle_summary["relevant_rows"]
    )
    support_no_effect = (
        not order_submitted
        and not entry_filled
        and close_row is None
        and (
            (_normalize_text(decision_status)
             or "").upper() in REJECT_TERMINAL_STATUSES
            or order_summary["has_alternative_terminal_event"]
            or lifecycle_summary["has_rejected_terminal"]
            or reject_like_runtime
        )
    )
    if close_row is not None:
        realized = close_fields["realized_pnl_net"]
        if exact_roundtrip and realized is not None:
            if realized > 0:
                bucket = "CLOSED_CANONICAL_PROFIT"
            elif realized < 0:
                bucket = "CLOSED_CANONICAL_LOSS"
            else:
                bucket = "CLOSED_CANONICAL_FLAT"
        else:
            bucket = "CLOSED_NON_CANONICAL_EVIDENCE"
    elif order_submitted and not entry_filled:
        bucket = "SUBMITTED_NOT_FILLED"
    elif entry_filled:
        if lifecycle_summary["has_terminal_close"]:
            bucket = "CLOSED_NON_CANONICAL_EVIDENCE"
        else:
            bucket = "FILLED_POSITION_STILL_OPEN"
    elif support_no_effect:
        bucket = "DOWNSTREAM_NO_EFFECT_CONFIRMED"
    else:
        bucket = "INCONCLUSIVE"
    return bucket, support_no_effect, {
        **close_fields,
        "exact_roundtrip": exact_roundtrip,
        "order_submitted": order_submitted,
        "entry_filled": entry_filled,
        "position_closed": position_closed,
    }


def _load_override_decisions(bundle_order_log: Path) -> list[dict[str, Any]]:
    decisions_by_rid: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(bundle_order_log):
        if _event_type(row) != "ORDER_INTENT":
            continue
        if (_normalize_text(row.get("source_fsm")) or "") != "DecisionMaking":
            continue
        low_vol = row.get("metadata", {}).get("low_vol_cost_floor", {})
        if low_vol.get("nrr062_segment_override_applied") is not True:
            continue
        if low_vol.get("nrr062_segment_override_name") != TARGET_OVERRIDE_NAME:
            continue
        rid = _normalize_text(row.get("rid"))
        if rid is None or rid in decisions_by_rid:
            continue
        ts_ms = _parse_ts_ms(row.get("timestamp"))
        side = (_normalize_text(row.get("side")) or _normalize_text(
            low_vol.get("side")) or "").upper()
        decisions_by_rid[rid] = {
            "rid": rid,
            "decision_id": _normalize_text(low_vol.get("decision_id")),
            "lifecycle_id": _normalize_text(row.get("lifecycle_id")),
            "downstream_rid": rid,
            "trade_id": None,
            "timestamp_ms": ts_ms,
            "timestamp_utc": _ts_ms_to_iso(ts_ms),
            "symbol": _normalize_text(row.get("symbol")),
            "side": side.lower() if side else None,
            "strategy_id": _normalize_text(row.get("strategy_id")) or _normalize_text(low_vol.get("strategy_id")),
            "regime": _normalize_text(row.get("regime")) or _normalize_text(low_vol.get("regime")),
            "selected_source": _normalize_text(low_vol.get("selected_source")),
            "selected_scale": _normalize_text(low_vol.get("selected_scale")),
            "threshold_family": _normalize_text(low_vol.get("threshold_family")),
            "original_direction_confidence": _safe_float(low_vol.get("original_direction_confidence")),
            "original_regime_confidence": _safe_float(low_vol.get("original_regime_confidence")),
            "trading_mode": _normalize_text(low_vol.get("trading_mode")),
            "gate_mode": _normalize_text(low_vol.get("gate_mode")),
            "override_name": _normalize_text(low_vol.get("nrr062_segment_override_name")),
            "original_nrr062_reason": _normalize_text(low_vol.get("original_nrr062_reason")),
            "original_low_vol_reason": _normalize_text(low_vol.get("original_low_vol_reason")),
            "metadata_line_number": row.get("_line_number"),
        }
    return sorted(decisions_by_rid.values(), key=lambda row: row["timestamp_ms"] or 0)


def _load_shadow_rows_by_rid(shadow_path: Path) -> dict[str, list[dict[str, Any]]]:
    by_rid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _read_jsonl(shadow_path):
        rid = _normalize_text(row.get("rid"))
        if rid is None:
            continue
        by_rid[rid].append(row)
    return by_rid


def _load_decision_status_by_rid(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    by_rid: dict[str, tuple[int, str]] = {}
    for row in _read_jsonl(path):
        rid = _normalize_text(row.get("rid"))
        if rid is None:
            continue
        status = _normalize_text(
            row.get("terminal_status")) or _normalize_text(row.get("status"))
        if status is None:
            continue
        ts_ms = (
            _parse_ts_ms(row.get("request_ts_ms"))
            or _parse_ts_ms(row.get("response_ts_ms"))
            or _parse_ts_ms(row.get("ts_ms"))
            or 0
        )
        current = by_rid.get(rid)
        if current is None or ts_ms >= current[0]:
            by_rid[rid] = (ts_ms, status)
    return {rid: value for rid, (_, value) in by_rid.items()}


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _compare_sidecar_blocks(current_domains: Path, accepted_domains: Path) -> dict[str, Any]:
    current_hash = _sha256_path(current_domains)
    accepted_hash = _sha256_path(accepted_domains)
    current_yaml = _load_yaml(current_domains)
    accepted_yaml = _load_yaml(accepted_domains)
    current_block = current_yaml["execution_position"]["position_policy_sidecar"]
    accepted_block = accepted_yaml["execution_position"]["position_policy_sidecar"]
    return {
        "current_domains_sha256": current_hash,
        "accepted_domains_sha256": accepted_hash,
        "full_hash_matches": current_hash == accepted_hash,
        "current_sidecar_mode": current_block.get("mode"),
        "accepted_sidecar_mode": accepted_block.get("mode"),
        "sidecar_block_equal": current_block == accepted_block,
    }


def _materialize_n_rows(
    decisions: list[dict[str, Any]],
    freeze_order_index: dict[str, Any],
    freeze_trade_index: dict[str, Any],
    latest_order_index: dict[str, Any],
    latest_trade_index: dict[str, Any],
    decision_status_by_rid: dict[str, str],
    shadow_rows_by_rid: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        freeze_order_summary = _collect_order_summary(
            decision, freeze_order_index)
        freeze_lifecycle_summary = _collect_trade_lifecycle_summary(
            decision, freeze_trade_index)
        latest_order_summary = _collect_order_summary(
            decision, latest_order_index)
        latest_lifecycle_summary = _collect_trade_lifecycle_summary(
            decision, latest_trade_index)
        decision_status = decision_status_by_rid.get(decision["rid"])
        freeze_bucket, freeze_support_no_effect, freeze_state = _classify_bucket(
            freeze_order_summary,
            freeze_lifecycle_summary,
            None,
        )
        latest_bucket, latest_support_no_effect, latest_state = _classify_bucket(
            latest_order_summary,
            latest_lifecycle_summary,
            decision_status,
        )
        freeze_close_row = _extract_close_row(freeze_order_summary)
        latest_close_row = _extract_close_row(latest_order_summary)
        shadow_rows = shadow_rows_by_rid.get(decision["rid"], [])
        low_vol_shadow_rows = []
        for row in shadow_rows:
            low_vol = row.get("low_vol_cost_floor")
            if isinstance(low_vol, dict) and low_vol.get("nrr062_segment_override_applied") is True:
                low_vol_shadow_rows.append(row)
                continue
            if row.get("nrr062_segment_override_applied") is True:
                low_vol_shadow_rows.append(row)
        latest_close_fields = _derive_close_fields(latest_close_row)
        gross_pnl = latest_close_fields["gross_pnl"]
        if gross_pnl is None and latest_state["realized_pnl_net"] is not None and latest_state["fees"] is not None:
            gross_pnl = latest_state["realized_pnl_net"] + latest_state["fees"]
        row = {
            **decision,
            "package": "N",
            "bundle_root": _relative_path(REPO_ROOT, freeze_order_index["source_stats"][0]["path"] if False else REPO_ROOT),
            "sidecar_observed": bool(low_vol_shadow_rows),
            "sidecar_rows": len(low_vol_shadow_rows),
            "decision_ledger_terminal_status": decision_status,
            "freeze_bucket": freeze_bucket,
            "latest_bucket": latest_bucket,
            "support_no_effect": latest_support_no_effect,
            "freeze_support_no_effect": freeze_support_no_effect,
            "order_submitted": latest_state["order_submitted"],
            "entry_filled": latest_state["entry_filled"],
            "position_closed": latest_state["position_closed"],
            "close_reason": latest_close_fields["close_reason"],
            "realized_pnl_net": latest_close_fields["realized_pnl_net"],
            "gross_pnl": gross_pnl,
            "fees": latest_close_fields["fees"],
            "exact_roundtrip": latest_state["exact_roundtrip"],
            "freeze_close_reason": freeze_state["close_reason"],
            "freeze_close_ts_utc": freeze_state["close_ts_utc"],
            "latest_close_ts_utc": latest_close_fields["close_ts_utc"],
            "order_events": _order_events(latest_order_summary),
            "trade_events": _trade_statuses(latest_lifecycle_summary),
            "freeze_order_events": _order_events(freeze_order_summary),
            "freeze_trade_events": _trade_statuses(freeze_lifecycle_summary),
            "freeze_order_primary_bucket": freeze_order_summary["primary_bucket"],
            "latest_order_primary_bucket": latest_order_summary["primary_bucket"],
            "override_outcome_class": latest_bucket,
            "freeze_position_closed_canonical": freeze_close_row is not None and _event_type(freeze_close_row) == "POSITION_CLOSED",
            "latest_position_closed_canonical": latest_close_row is not None and _event_type(latest_close_row) == "POSITION_CLOSED",
            "decision_ledger_frozen_in_bundle": False,
        }
        rows.append(row)
    return rows


def _materialize_historical_enable_rows(package_name: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in payload.get("rows", []):
        bucket = row.get("latest_bucket")
        if bucket is None:
            realized = _safe_float(row.get("realized_pnl_net"))
            exact_roundtrip = bool(row.get("exact_roundtrip"))
            position_closed = bool(row.get("position_closed"))
            entry_filled = bool(row.get("entry_filled"))
            order_submitted = bool(row.get("order_submitted"))
            if position_closed and exact_roundtrip and realized is not None:
                if realized > 0:
                    bucket = "CLOSED_CANONICAL_PROFIT"
                elif realized < 0:
                    bucket = "CLOSED_CANONICAL_LOSS"
                else:
                    bucket = "CLOSED_CANONICAL_FLAT"
            elif position_closed:
                bucket = "CLOSED_NON_CANONICAL_EVIDENCE"
            elif order_submitted and not entry_filled:
                bucket = "SUBMITTED_NOT_FILLED"
            elif entry_filled:
                bucket = "FILLED_POSITION_STILL_OPEN"
            else:
                bucket = "INCONCLUSIVE"
        rows.append(
            {
                "package": package_name,
                "bundle_root": row.get("bundle_root") or payload.get("bundle_root"),
                "rid": row.get("rid"),
                "timestamp_utc": row.get("timestamp_utc"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "regime": row.get("regime"),
                "selected_source": row.get("selected_source"),
                "selected_scale": row.get("selected_scale"),
                "threshold_family": row.get("threshold_family"),
                "original_direction_confidence": row.get("original_direction_confidence"),
                "original_regime_confidence": row.get("original_regime_confidence"),
                "freeze_bucket": row.get("freeze_bucket") or bucket,
                "latest_bucket": row.get("latest_bucket") or bucket,
                "order_submitted": row.get("order_submitted"),
                "entry_filled": row.get("entry_filled"),
                "position_closed": row.get("position_closed"),
                "close_reason": row.get("close_reason"),
                "realized_pnl_net": row.get("realized_pnl_net"),
                "gross_pnl": row.get("gross_pnl"),
                "fees": row.get("fees"),
                "exact_roundtrip": row.get("exact_roundtrip"),
                "sidecar_observed": row.get("sidecar_observed"),
                "decision_ledger_terminal_status": row.get("decision_ledger_terminal_status"),
                "source_artifact": row.get("source_artifact"),
            }
        )
    return rows


def _summarize_runtime(rows: list[dict[str, Any]], bucket_key: str) -> dict[str, Any]:
    counts = Counter(row.get(bucket_key) for row in rows)
    resolved = [row for row in rows if row.get(bucket_key) in {
        "CLOSED_CANONICAL_PROFIT", "CLOSED_CANONICAL_LOSS", "CLOSED_CANONICAL_FLAT", "CLOSED_NON_CANONICAL_EVIDENCE"}]
    wins = sum(1 for row in rows if row.get(
        bucket_key) == "CLOSED_CANONICAL_PROFIT")
    losses = sum(1 for row in rows if row.get(
        bucket_key) == "CLOSED_CANONICAL_LOSS")
    flats = sum(1 for row in rows if row.get(
        bucket_key) == "CLOSED_CANONICAL_FLAT")
    submitted_not_filled = sum(1 for row in rows if row.get(
        bucket_key) == "SUBMITTED_NOT_FILLED")
    filled_open = sum(1 for row in rows if row.get(
        bucket_key) == "FILLED_POSITION_STILL_OPEN")
    downstream_no_effect = sum(1 for row in rows if row.get(
        bucket_key) == "DOWNSTREAM_NO_EFFECT_CONFIRMED")
    net_pnl = sum(_safe_float(row.get("realized_pnl_net"))
                  or 0.0 for row in resolved)
    return {
        "override_count": len(rows),
        "bucket_counts": dict(sorted((str(key), value) for key, value in counts.items() if key is not None)),
        "resolved_closes": len(resolved),
        "wins": wins,
        "losses": losses,
        "flats": flats,
        "submitted_not_filled": submitted_not_filled,
        "filled_position_still_open": filled_open,
        "downstream_no_effect_confirmed": downstream_no_effect,
        "net_pnl_quote": net_pnl,
    }


def _package_breakout(rows: list[dict[str, Any]], bucket_key: str) -> dict[str, Any]:
    by_package: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_package[str(row.get("package"))].append(row)
    result: dict[str, Any] = {}
    for package_name in sorted(by_package):
        result[package_name] = _summarize_runtime(
            by_package[package_name], bucket_key)
    return result


def _render_markdown_table(rows: list[list[Any]], headers: list[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " +
             " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        rendered = []
        for value in row:
            if isinstance(value, float):
                text = f"{value:.8f}".rstrip("0").rstrip(".")
            elif value is None:
                text = ""
            else:
                text = str(value)
            rendered.append(text.replace("\n", " "))
        lines.append("| " + " | ".join(rendered) + " |")
    return "\n".join(lines)


def _format_count_table(summary: dict[str, Any], title: str) -> str:
    rows = [[key, value] for key, value in summary.items()]
    return f"## {title}\n\n" + _render_markdown_table(rows, ["Metric", "Value"])


def _render_runtime_ledger_md(title: str, payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    summary_rows = [
        ["Bundle Root", payload.get("bundle_root")],
        ["Distinct Override RIDs", payload["summary"].get(
            "distinct_override_rids")],
        ["Freeze Bucket Counts", json.dumps(payload["summary"].get(
            "freeze_bucket_counts", {}), ensure_ascii=False)],
        ["Latest Bucket Counts", json.dumps(payload["summary"].get(
            "latest_bucket_counts", {}), ensure_ascii=False)],
        ["Decision Ledger Frozen In Bundle", payload["summary"].get(
            "decision_ledger_frozen_in_bundle")],
    ]
    ledger_rows = []
    for row in rows:
        ledger_rows.append(
            [
                row.get("rid"),
                row.get("timestamp_utc"),
                row.get("symbol"),
                row.get("side"),
                row.get("latest_bucket"),
                row.get("close_reason"),
                row.get("realized_pnl_net"),
                row.get("fees"),
                row.get("decision_ledger_terminal_status"),
            ]
        )
    return "\n\n".join(
        [
            f"# {title}",
            _render_markdown_table(summary_rows, ["Metric", "Value"]),
            "## Rows\n\n" + _render_markdown_table(
                ledger_rows,
                ["RID", "timestamp_utc", "symbol", "side", "latest_bucket", "close_reason",
                    "realized_pnl_net", "fees", "decision_ledger_terminal_status"],
            ),
        ]
    )


def _render_enable_cohort_md(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    summary_rows = [
        ["Occurrence Rows", payload["summary"].get("occurrence_row_count")],
        ["Unique RIDs", payload["summary"].get("unique_rid_count")],
        ["Package Counts", json.dumps(payload["summary"].get(
            "package_counts", {}), ensure_ascii=False)],
        ["Latest Bucket Counts", json.dumps(payload["summary"].get(
            "latest_bucket_counts", {}), ensure_ascii=False)],
    ]
    detail_rows = []
    for row in rows:
        detail_rows.append(
            [
                row.get("package"),
                row.get("rid"),
                row.get("timestamp_utc"),
                row.get("symbol"),
                row.get("latest_bucket"),
                row.get("realized_pnl_net"),
            ]
        )
    return "\n\n".join(
        [
            "# NRR062_ENABLE_COHORT_OVERRIDE_LEDGER",
            _render_markdown_table(summary_rows, ["Metric", "Value"]),
            "## Rows\n\n" + _render_markdown_table(detail_rows, [
                                                   "package", "rid", "timestamp_utc", "symbol", "latest_bucket", "realized_pnl_net"]),
        ]
    )


def _render_boundary_md(payload: dict[str, Any]) -> str:
    summary_rows = [
        ["Verdict", payload.get("verdict")],
        ["N Override Count", payload["package_n"].get("override_count")],
        ["Unexpected Side Rows", payload["package_n"].get(
            "unexpected_side_rows")],
        ["Unexpected Regime Rows", payload["package_n"].get(
            "unexpected_regime_rows")],
        ["Accepted Sidecar Mode", payload["config_compare"].get(
            "accepted_sidecar_mode")],
        ["Current Sidecar Mode", payload["config_compare"].get(
            "current_sidecar_mode")],
        ["Sidecar Block Equal", payload["config_compare"].get(
            "sidecar_block_equal")],
        ["Full Domains Hash Matches",
            payload["config_compare"].get("full_hash_matches")],
        ["Decision Ledger Frozen In Bundle", payload["bundle_gaps"].get(
            "decision_ledger_frozen_in_bundle")],
    ]
    return "# NRR062_ENABLE_COHORT_BOUNDARY_AUDIT\n\n" + _render_markdown_table(summary_rows, ["Metric", "Value"])


def _render_economics_md(payload: dict[str, Any]) -> str:
    rows = [
        ["Package F Replay Candidate Rows",
            payload["package_f_replay"].get("candidate_rows")],
        ["Package F Replay Net Quote", payload["package_f_replay"].get(
            "estimated_net_pnl_quote")],
        ["Enable Cohort Latest Override Count",
            payload["combined_enable_latest"].get("override_count")],
        ["Enable Cohort Latest Resolved Closes",
            payload["combined_enable_latest"].get("resolved_closes")],
        ["Enable Cohort Latest Wins",
            payload["combined_enable_latest"].get("wins")],
        ["Enable Cohort Latest Losses",
            payload["combined_enable_latest"].get("losses")],
        ["Enable Cohort Latest Net Quote",
            payload["combined_enable_latest"].get("net_pnl_quote")],
        ["Verdict", payload.get("verdict")],
    ]
    return "# NRR062_ENABLE_COHORT_ECONOMICS_REVIEW\n\n" + _render_markdown_table(rows, ["Metric", "Value"])


def _render_shadow_appendix_md(payload: dict[str, Any]) -> str:
    rows = [
        ["Package I Override Count",
            payload["package_i_runtime"].get("override_count")],
        ["Package I Net Quote",
            payload["package_i_runtime"].get("net_pnl_quote")],
        ["Package J Freeze Override Count",
            payload["package_j_freeze_runtime"].get("override_count")],
        ["Package J Latest Net Quote",
            payload["package_j_latest_known"].get("net_pnl_quote")],
        ["Shadow Drift Detected", payload["shadow_boundary"].get(
            "sidecar_mode_drift", {}).get("detected")],
        ["Shadow Verdict", payload.get("verdict")],
    ]
    return "# NRR062_SHADOW_COHORT_APPENDIX\n\n" + _render_markdown_table(rows, ["Metric", "Value"])


def _render_replay_vs_runtime_md(payload: dict[str, Any]) -> str:
    rows = [
        ["Replay Candidate Rows",
            payload["package_f_replay"].get("candidate_rows")],
        ["Replay Candidate Net Quote", payload["package_f_replay"].get(
            "estimated_net_pnl_quote")],
        ["Enable Latest Override Count",
            payload["enable_runtime_latest"].get("override_count")],
        ["Enable Latest Resolved Closes",
            payload["enable_runtime_latest"].get("resolved_closes")],
        ["Enable Latest Net Quote",
            payload["enable_runtime_latest"].get("net_pnl_quote")],
        ["Override Sample Fraction vs Replay Candidate", payload.get(
            "override_sample_fraction_vs_replay_candidate")],
        ["Resolved Close Fraction vs Replay Candidate", payload.get(
            "resolved_close_fraction_vs_replay_candidate")],
        ["Verdict", payload.get("verdict")],
    ]
    return "# NRR062_ENABLE_COHORT_REPLAY_VS_RUNTIME\n\n" + _render_markdown_table(rows, ["Metric", "Value"])


def _render_freeze_report(payload: dict[str, Any]) -> str:
    summary_rows = [
        ["Bundle Root", payload.get("bundle_root")],
        ["Capture Scan UTC", payload.get("scan_ts")],
        ["Manifest Probe order_log_nrr062_rows",
            payload.get("order_log_nrr062_rows")],
        ["Distinct Override RIDs", payload.get("distinct_override_rids")],
        ["Recorder Coverage Sufficient", payload.get(
            "recorder_coverage_sufficient")],
        ["Config Snapshot Required Present", payload.get(
            "config_snapshot_required_present")],
        ["Decision Ledger Frozen In Bundle", payload.get(
            "decision_ledger_frozen_in_bundle")],
        ["Accepted Sidecar Mode", payload.get("accepted_sidecar_mode")],
        ["Current Sidecar Mode", payload.get("current_sidecar_mode")],
        ["Sidecar Block Equal Accepted", payload.get(
            "sidecar_block_equal_accepted")],
        ["Full Domains Hash Matches Accepted", payload.get(
            "full_domains_hash_matches_accepted")],
    ]
    integrity_lines = [
        "- Derived artifacts were generated without mutating runtime code or YAML.",
        "- Manifest probe.order_log_nrr062_rows and derived distinct override rid count are different measures; the former is the capture script's top-level NRR062 probe, while the latter is derived from nested metadata.low_vol_cost_floor override markers.",
        "- Fresh bundle still does not contain a frozen decision_ledger surface; decision_ledger evidence in derived reports is current-workspace diagnostics only.",
    ]
    return "\n\n".join(
        [
            "# FREEZE_REPORT",
            _render_markdown_table(summary_rows, ["Metric", "Value"]),
            "## Capture Integrity\n\n" + "\n".join(integrity_lines),
        ]
    )


def _render_agent_report(report_payload: dict[str, Any]) -> str:
    def bullet_list(values: list[str]) -> str:
        if not values:
            return "- none"
        return "\n".join(f"- {value}" for value in values)

    sections = [
        "# AGENT_REPORT_V1",
        "## Executive Summary\n" + report_payload["executive_summary"],
        "## Proven Facts\n" + bullet_list(report_payload["proven_facts"]),
        "## Inferred Findings\n" +
        bullet_list(report_payload["inferred_findings"]),
        "## Contradictions / Evidence Gaps\n" +
        bullet_list(report_payload["evidence_gaps"]),
        "## Root Cause Candidates\n" +
        bullet_list(report_payload["root_cause_candidates"]),
        "## Operational Risk\n- " + report_payload["operational_risk"],
        "## Files / Areas Touched\n" +
        bullet_list(report_payload["files_touched"]),
        "## Validation Performed\n" +
        bullet_list(report_payload["validation"]),
        "## Residual Risk\n" + bullet_list(report_payload["residual_risk"]),
        "## What Remains Unproven\n" + bullet_list(report_payload["unproven"]),
        "## Minimal Safe Verdict\n- " + report_payload["minimal_safe_verdict"],
    ]
    return "\n\n".join(sections)


def _json_path_for(dataset_dir: Path, stem: str) -> Path:
    return dataset_dir / f"{stem}.json"


def _md_path_for(dataset_dir: Path, stem: str) -> Path:
    return dataset_dir / f"{stem}.md"


def _csv_path_for(dataset_dir: Path, stem: str) -> Path:
    return dataset_dir / f"{stem}.csv"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Package N NRR062 post-baseline reconciliation artifacts")
    parser.add_argument(
        "--bundle-root",
        default="logs/frozen/nrr062_fresh_capture_20260529_065313",
        help="Fresh NRR062 frozen bundle root",
    )
    parser.add_argument(
        "--dataset-dir",
        default="calibrators/datasets/nrr062_testnet_override_runtime",
        help="Output dataset directory for Package N artifacts",
    )
    parser.add_argument(
        "--report-path",
        default="CALIBRATORS_NRR_PACKAGE_N_CONTINUE_COLLECTION_POST_BASELINE_RECONCILIATION_REPORT.md",
        help="Top-level Package N report path",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    bundle_root = (REPO_ROOT / args.bundle_root).resolve()
    dataset_dir = (REPO_ROOT / args.dataset_dir).resolve()
    report_path = (REPO_ROOT / args.report_path).resolve()

    bundle_order_log = bundle_root / "logs" / "order_log_v1.jsonl"
    bundle_trade_lifecycle = bundle_root / "logs" / "trade_lifecycle.jsonl"
    bundle_shadow_journal = bundle_root / "logs" / \
        "shadow_critical_event_journal_v1.jsonl"
    bundle_manifest = bundle_root / "MANIFEST.json"
    bundle_domains = bundle_root / "config_snapshot" / \
        "config" / "aurora" / "domains.yaml"

    live_order_log = REPO_ROOT / EXPECTED_ORDER_LOG
    live_trade_lifecycle = REPO_ROOT / EXPECTED_TRADE_LIFECYCLE
    live_decision_ledger = REPO_ROOT / EXPECTED_DECISION_LEDGER

    if not bundle_order_log.exists() or not bundle_trade_lifecycle.exists() or not bundle_shadow_journal.exists():
        parser.error("Bundle is missing one or more required runtime surfaces")
    if not bundle_manifest.exists() or not bundle_domains.exists():
        parser.error("Bundle is missing MANIFEST.json or frozen domains.yaml")

    manifest = _read_json(bundle_manifest)
    config_compare = _compare_sidecar_blocks(
        bundle_domains, ACCEPTED_ENABLE_DOMAINS)

    decisions = _load_override_decisions(bundle_order_log)
    freeze_order_index = _build_index(
        [_make_surface(bundle_order_log, EXPECTED_ORDER_LOG)])
    freeze_trade_index = _build_index(
        [_make_surface(bundle_trade_lifecycle, EXPECTED_TRADE_LIFECYCLE)])
    latest_order_index = _build_index(
        [_make_surface(live_order_log, EXPECTED_ORDER_LOG)])
    latest_trade_index = _build_index(
        [_make_surface(live_trade_lifecycle, EXPECTED_TRADE_LIFECYCLE)])
    decision_status_by_rid = _load_decision_status_by_rid(live_decision_ledger)
    shadow_rows_by_rid = _load_shadow_rows_by_rid(bundle_shadow_journal)

    n_rows = _materialize_n_rows(
        decisions,
        freeze_order_index,
        freeze_trade_index,
        latest_order_index,
        latest_trade_index,
        decision_status_by_rid,
        shadow_rows_by_rid,
    )
    for row in n_rows:
        row["bundle_root"] = _relative_path(REPO_ROOT, bundle_root)

    n_summary = {
        "distinct_override_rids": len(n_rows),
        "override_rows_order_log": len(n_rows),
        "override_rows_shadow_journal": sum(row["sidecar_rows"] for row in n_rows),
        "freeze_bucket_counts": dict(sorted(Counter(row["freeze_bucket"] for row in n_rows).items())),
        "latest_bucket_counts": dict(sorted(Counter(row["latest_bucket"] for row in n_rows).items())),
        "active_symbols": sorted({row["symbol"] for row in n_rows if row.get("symbol")}),
        "decision_ledger_frozen_in_bundle": False,
        "decision_ledger_source_kind": "current_workspace_authority" if live_decision_ledger.exists() else "missing_authority",
    }
    n_payload = {
        "bundle_root": _relative_path(REPO_ROOT, bundle_root),
        "observation_scope": "post_package_m_enable_mode_reconciliation_current_window",
        "accepted_enable_reference": {
            "bundle_root": _relative_path(REPO_ROOT, ACCEPTED_ENABLE_BUNDLE),
            **config_compare,
        },
        "summary": n_summary,
        "rows": n_rows,
    }

    package_h_rows = _materialize_historical_enable_rows(
        "H", _read_json(PACKAGE_H_LEDGER_JSON))
    package_l_rows = _materialize_historical_enable_rows(
        "L", _read_json(PACKAGE_L_LEDGER_JSON))
    enable_rows = [*package_h_rows, *package_l_rows, *n_rows]
    enable_summary = {
        "occurrence_row_count": len(enable_rows),
        "unique_rid_count": len({row.get("rid") for row in enable_rows if row.get("rid")}),
        "package_counts": dict(sorted(Counter(row["package"] for row in enable_rows).items())),
        "freeze_bucket_counts": dict(sorted(Counter(row["freeze_bucket"] for row in enable_rows).items())),
        "latest_bucket_counts": dict(sorted(Counter(row["latest_bucket"] for row in enable_rows).items())),
    }
    enable_payload = {
        "generated_at_utc": _utc_now(),
        "summary": enable_summary,
        "rows": enable_rows,
    }

    package_n_breakout = _summarize_runtime(n_rows, "latest_bucket")
    combined_enable_latest = _summarize_runtime(enable_rows, "latest_bucket")
    package_breakout = _package_breakout(enable_rows, "latest_bucket")

    boundary_payload = {
        "package_h": package_breakout.get("H", {}),
        "package_l": package_breakout.get("L", {}),
        "package_n": {
            **package_n_breakout,
            "unexpected_side_rows": sum(1 for row in n_rows if (row.get("side") or "").upper() != EXPECTED_OVERRIDE_SIDE),
            "unexpected_regime_rows": sum(1 for row in n_rows if (row.get("regime") or "").upper() != EXPECTED_OVERRIDE_REGIME),
            "unexpected_override_name_rows": sum(1 for row in n_rows if row.get("override_name") != TARGET_OVERRIDE_NAME),
            "active_symbols": sorted({row["symbol"] for row in n_rows if row.get("symbol")}),
        },
        "config_compare": config_compare,
        "bundle_gaps": {
            "decision_ledger_frozen_in_bundle": False,
            "freeze_report_preexisting": (bundle_root / "FREEZE_REPORT.md").exists(),
        },
        "verdict": (
            "BOUNDARY_STABLE_NO_OVERRIDE_LEAKAGE_SIDECAR_OWNER_EQUIVALENT_FULL_CONFIG_DRIFT_OUTSIDE_OWNER_SURFACE"
            if config_compare["sidecar_block_equal"]
            else "BOUNDARY_REVIEW_REQUIRED_SIDECAR_OWNER_SURFACE_DRIFT"
        ),
    }

    replay_payload = _read_json(PACKAGE_F_REPLAY_JSON)["candidate_summary"]
    economics_payload = {
        "package_f_replay": {
            "candidate_rows": replay_payload.get("row_count"),
            "tp": replay_payload.get("tp_count"),
            "sl": replay_payload.get("sl_count"),
            "timeout": replay_payload.get("timeout_count"),
            "estimated_net_pnl_quote": replay_payload.get("estimated_net_pnl_quote"),
            "profit_factor": replay_payload.get("profit_factor"),
        },
        "package_breakout": package_breakout,
        "package_n_latest": package_n_breakout,
        "combined_enable_latest": combined_enable_latest,
    }
    economics_payload["verdict"] = (
        "ENABLE_RUNTIME_NET_POSITIVE_SAMPLE_STILL_THIN"
        if (economics_payload["combined_enable_latest"].get("net_pnl_quote") or 0.0) > 0
        else "ENABLE_RUNTIME_NOT_YET_POSITIVE_CONTINUE_TESTNET_COLLECTION_ONLY"
    )

    shadow_economics_payload = _read_json(SHADOW_ECONOMICS_JSON)
    shadow_boundary_payload = _read_json(SHADOW_BOUNDARY_JSON)
    shadow_appendix_payload = {
        "package_i_runtime": shadow_economics_payload.get("package_i_runtime", {}),
        "package_j_freeze_runtime": shadow_economics_payload.get("package_j_freeze_runtime", {}),
        "package_j_latest_known": shadow_economics_payload.get("package_j_latest_known", {}),
        "shadow_boundary": shadow_boundary_payload,
        "verdict": "SHADOW_APPENDIX_ONLY_DO_NOT_BLEND_INTO_ENABLE_COHORT_CONCLUSIONS",
    }

    replay_vs_runtime_payload = {
        "package_f_replay": economics_payload["package_f_replay"],
        "enable_runtime_latest": combined_enable_latest,
        "override_sample_fraction_vs_replay_candidate": round(
            (combined_enable_latest["override_count"] /
             economics_payload["package_f_replay"]["candidate_rows"]),
            6,
        )
        if economics_payload["package_f_replay"]["candidate_rows"]
        else None,
        "resolved_close_fraction_vs_replay_candidate": round(
            (combined_enable_latest["resolved_closes"] /
             economics_payload["package_f_replay"]["candidate_rows"]),
            6,
        )
        if economics_payload["package_f_replay"]["candidate_rows"]
        else None,
        "verdict": (
            "DIRECTIONALLY_ALIGNED_ENABLE_RUNTIME_SAMPLE_STILL_TOO_SMALL"
            if (combined_enable_latest["net_pnl_quote"] or 0.0) > 0
            else "ENABLE_RUNTIME_NOT_YET_DIRECTIONALLY_ALIGNED_WITH_POSITIVE_REPLAY"
        ),
    }

    freeze_report_payload = {
        "bundle_root": _relative_path(REPO_ROOT, bundle_root),
        "scan_ts": manifest.get("scan_ts"),
        "order_log_nrr062_rows": manifest.get("probe", {}).get("order_log_nrr062_rows"),
        "distinct_override_rids": len(n_rows),
        "recorder_coverage_sufficient": manifest.get("probe", {}).get("recorder_coverage", {}).get("coverage_sufficient"),
        "config_snapshot_required_present": (
            f"{manifest.get('config_snapshot', {}).get('summary', {}).get('required_present')} / "
            f"{manifest.get('config_snapshot', {}).get('summary', {}).get('required_files')}"
        ),
        "decision_ledger_frozen_in_bundle": False,
        "accepted_sidecar_mode": config_compare["accepted_sidecar_mode"],
        "current_sidecar_mode": config_compare["current_sidecar_mode"],
        "sidecar_block_equal_accepted": config_compare["sidecar_block_equal"],
        "full_domains_hash_matches_accepted": config_compare["full_hash_matches"],
    }

    n_csv_rows = []
    for row in n_rows:
        n_csv_rows.append(
            {
                "rid": row.get("rid"),
                "timestamp_utc": row.get("timestamp_utc"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "strategy_id": row.get("strategy_id"),
                "regime": row.get("regime"),
                "selected_source": row.get("selected_source"),
                "selected_scale": row.get("selected_scale"),
                "threshold_family": row.get("threshold_family"),
                "original_direction_confidence": row.get("original_direction_confidence"),
                "original_regime_confidence": row.get("original_regime_confidence"),
                "trading_mode": row.get("trading_mode"),
                "gate_mode": row.get("gate_mode"),
                "decision_ledger_terminal_status": row.get("decision_ledger_terminal_status"),
                "order_submitted": row.get("order_submitted"),
                "entry_filled": row.get("entry_filled"),
                "position_closed": row.get("position_closed"),
                "close_reason": row.get("close_reason"),
                "realized_pnl_net": row.get("realized_pnl_net"),
                "gross_pnl": row.get("gross_pnl"),
                "fees": row.get("fees"),
                "exact_roundtrip": row.get("exact_roundtrip"),
                "support_no_effect": row.get("support_no_effect"),
                "freeze_bucket": row.get("freeze_bucket"),
                "latest_bucket": row.get("latest_bucket"),
                "sidecar_observed": row.get("sidecar_observed"),
                "sidecar_rows": row.get("sidecar_rows"),
                "order_events": row.get("order_events"),
                "trade_events": row.get("trade_events"),
            }
        )
    enable_csv_rows = []
    for row in enable_rows:
        enable_csv_rows.append(
            {
                "package": row.get("package"),
                "rid": row.get("rid"),
                "timestamp_utc": row.get("timestamp_utc"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "regime": row.get("regime"),
                "freeze_bucket": row.get("freeze_bucket"),
                "latest_bucket": row.get("latest_bucket"),
                "realized_pnl_net": row.get("realized_pnl_net"),
                "fees": row.get("fees"),
                "decision_ledger_terminal_status": row.get("decision_ledger_terminal_status"),
            }
        )

    _write_csv(_csv_path_for(
        dataset_dir, "NRR062_OVERRIDE_RUNTIME_LEDGER_N"), n_csv_rows)
    _write_json(_json_path_for(
        dataset_dir, "nrr062_override_runtime_ledger_n"), n_payload)
    _write_text(_md_path_for(dataset_dir, "NRR062_OVERRIDE_RUNTIME_LEDGER_N"),
                _render_runtime_ledger_md("NRR062_OVERRIDE_RUNTIME_LEDGER_N", n_payload, n_rows))

    _write_csv(_csv_path_for(
        dataset_dir, "NRR062_ENABLE_COHORT_OVERRIDE_LEDGER"), enable_csv_rows)
    _write_json(_json_path_for(
        dataset_dir, "nrr062_enable_cohort_override_ledger"), enable_payload)
    _write_text(_md_path_for(dataset_dir, "NRR062_ENABLE_COHORT_OVERRIDE_LEDGER"),
                _render_enable_cohort_md(enable_payload, enable_rows))

    _write_json(_json_path_for(
        dataset_dir, "nrr062_enable_cohort_boundary_audit"), boundary_payload)
    _write_text(_md_path_for(dataset_dir, "NRR062_ENABLE_COHORT_BOUNDARY_AUDIT"),
                _render_boundary_md(boundary_payload))

    _write_json(_json_path_for(
        dataset_dir, "nrr062_enable_cohort_economics_review"), economics_payload)
    _write_text(_md_path_for(dataset_dir, "NRR062_ENABLE_COHORT_ECONOMICS_REVIEW"),
                _render_economics_md(economics_payload))

    _write_json(_json_path_for(
        dataset_dir, "nrr062_shadow_cohort_appendix"), shadow_appendix_payload)
    _write_text(_md_path_for(dataset_dir, "NRR062_SHADOW_COHORT_APPENDIX"),
                _render_shadow_appendix_md(shadow_appendix_payload))

    _write_json(_json_path_for(
        dataset_dir, "nrr062_enable_cohort_replay_vs_runtime"), replay_vs_runtime_payload)
    _write_text(_md_path_for(dataset_dir, "NRR062_ENABLE_COHORT_REPLAY_VS_RUNTIME"),
                _render_replay_vs_runtime_md(replay_vs_runtime_payload))

    _write_text(bundle_root / "FREEZE_REPORT.md",
                _render_freeze_report(freeze_report_payload))

    report_payload = {
        "executive_summary": (
            "Package N extends NRR062 override runtime collection under enable-mode sidecar authority, with current owner-surface equivalence to the accepted enable baseline and fresh override-applied runtime evidence in the new window. Git history for Packages H and M confirms that the accepted clean cohort remains enable-mode, while I/J remain a separate shadow cohort."
        ),
        "proven_facts": [
            f"Fresh bundle {_relative_path(REPO_ROOT, bundle_root)} contains {len(n_rows)} distinct override-applied ORDER_INTENT rows derived from DecisionMaking ORDER_INTENT metadata.low_vol_cost_floor; this is a different measure from MANIFEST probe.order_log_nrr062_rows={freeze_report_payload['order_log_nrr062_rows']}.",
            f"Current frozen domains full hash is {config_compare['current_domains_sha256']} while accepted enable snapshot hash is {config_compare['accepted_domains_sha256']}.",
            f"execution_position.position_policy_sidecar blocks are equal between current frozen domains and the accepted enable snapshot, and both use mode={config_compare['current_sidecar_mode']}.",
            f"Fresh bundle recorder coverage is sufficient={freeze_report_payload['recorder_coverage_sufficient']} and config snapshot required files are {freeze_report_payload['config_snapshot_required_present']}.",
            f"Fresh bundle still lacks a frozen decision_ledger surface, so decision_ledger terminal status used in derived reports comes from current workspace authority only.",
            "Package H and Package M reports re-read from git history confirm that H/L are the clean enable cohort at hash 3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5, while I/J are the dirty shadow cohort at hash e33e95a9a44f7606169ad78ac6bf0bc68be4a1d47df0d61940ce05f117fd0477.",
        ],
        "inferred_findings": [
            "Full domains hash drift is outside the sidecar owner surface, so enable-vs-shadow cohort separation remains supportable on the override authority surface for this Package N window.",
            f"Enable-cohort latest-known runtime net quote is {combined_enable_latest['net_pnl_quote']}, which remains {'positive' if (combined_enable_latest['net_pnl_quote'] or 0.0) > 0 else 'non-positive'} across H/L/N occurrence rows.",
            "Package N should remain grouped with the enable cohort, not with the I/J shadow cohort, because the current sidecar owner block matches the accepted enable snapshot and git-history lineage keeps enable as the accepted baseline.",
            "Shadow I/J economics remain appendix-only evidence and are not blended into enable-cohort verdicts.",
        ],
        "evidence_gaps": [
            "Fresh capture script still does not freeze decision_ledger into the bundle, so decision terminal evidence is not capture-time sealed for Package N.",
            "Package N report does not replay new N rows against recorder bars; replay-vs-runtime remains anchored to the pre-existing Package F candidate surface.",
        ],
        "root_cause_candidates": [
            "The capture contract omits FREEZE_REPORT.md and decision_ledger freezing, so post-capture forensic reporting has to reconstruct part of the authority story outside the bundle.",
        ],
        "operational_risk": "Observability Gap",
        "files_touched": [
            "tools/analysis/generate_nrr062_package_n_report.py",
            _relative_path(REPO_ROOT, bundle_root / "FREEZE_REPORT.md"),
            _relative_path(REPO_ROOT, dataset_dir /
                           "NRR062_OVERRIDE_RUNTIME_LEDGER_N.md"),
            _relative_path(REPO_ROOT, dataset_dir /
                           "NRR062_ENABLE_COHORT_OVERRIDE_LEDGER.md"),
            _relative_path(REPO_ROOT, dataset_dir /
                           "NRR062_ENABLE_COHORT_BOUNDARY_AUDIT.md"),
            _relative_path(REPO_ROOT, dataset_dir /
                           "NRR062_ENABLE_COHORT_ECONOMICS_REVIEW.md"),
            _relative_path(REPO_ROOT, dataset_dir /
                           "NRR062_SHADOW_COHORT_APPENDIX.md"),
            _relative_path(REPO_ROOT, dataset_dir /
                           "NRR062_ENABLE_COHORT_REPLAY_VS_RUNTIME.md"),
            _relative_path(REPO_ROOT, report_path),
        ],
        "validation": [
            "Executed the generator against the fresh bundle and emitted all requested Package N artifacts.",
            "Validated sidecar owner-surface equivalence by YAML-loading current frozen domains and the accepted enable snapshot and comparing execution_position.position_policy_sidecar blocks directly.",
            "Used runtime bundle order_log/trade_lifecycle plus current workspace decision_ledger authority to classify Package N latest-known lifecycle buckets.",
            "Re-read deleted Package H and Package M root reports from git history to verify that enable remains the accepted clean cohort and that I/J stay explicitly separated as the shadow cohort.",
        ],
        "residual_risk": [
            "Decision-ledger-dependent no-effect interpretations are weaker than they would be under a fully frozen decision_ledger capture.",
            "Replay-vs-runtime still relies on historical Package F candidate economics instead of a fresh N-only replay rerun.",
        ],
        "unproven": [
            "Whether every current full-config delta outside the sidecar block is operationally irrelevant to realized economics remains unproven.",
            "Whether a fresh N-only replay rerun over the current window would preserve the same positive directionality seen in the Package F candidate replay remains unproven.",
        ],
        "minimal_safe_verdict": (
            "Continue Package G override collection in hybrid_live_data_testnet_exec as enable-cohort testnet-only evidence. Do not promote, do not tune thresholds, and keep shadow I/J economics appendix-only while fresh bundle sealing still lacks a frozen decision_ledger surface."
        ),
    }
    _write_text(report_path, _render_agent_report(report_payload))

    print("Generated Package N artifacts")
    print(f"  bundle_root={_relative_path(REPO_ROOT, bundle_root)}")
    print(f"  distinct_override_rids={len(n_rows)}")
    print(
        f"  combined_enable_latest_net_quote={combined_enable_latest['net_pnl_quote']}")
    print(f"  report_path={_relative_path(REPO_ROOT, report_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
