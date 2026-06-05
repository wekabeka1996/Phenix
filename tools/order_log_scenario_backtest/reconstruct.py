from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.analysis.order_reconstruction_tp_sl_common import (
    AuthorityRow,
    build_entries_with_regimes,
    iso_utc,
    payload_get,
    reconstruct_entries,
    stringify,
    to_float,
    to_int,
    try_parse_timestamp_ms,
    load_strategy_context,
    write_csv,
)

from .models import CanonicalEntry

RETAINED_EVENT_TYPES = {
    "ORDER_INTENT",
    "ORDER_PLACED",
    "ORDER_FILLED",
    "ORDER_TIMEOUT",
    "ORDER_CANCELLED",
    "POSITION_CLOSED",
}

CORE_REGIME_TPSL_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}).*?\[(?P<symbol>[A-Z0-9_]+)\] REGIME_TPSL: regime=(?P<regime>[A-Z_]+) stop=(?P<stop>-?\d+(?:\.\d+)?) target=(?P<target>-?\d+(?:\.\d+)?)"
)


def _first_value(payload: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value = payload_get(payload, path)
        if value is not None:
            return value
    return None


def _price_motion_value(payload: dict[str, Any], field_name: str) -> float | None:
    value = _first_value(
        payload,
        field_name,
        f"price_motion_context.{field_name}",
        f"metadata.price_motion_context.{field_name}",
        f"metadata.low_vol_cost_floor.price_motion_context.{field_name}",
        f"low_vol_cost_floor.price_motion_context.{field_name}",
    )
    return to_float(value)


def _pick_timestamp(payload: dict[str, Any]) -> tuple[int | None, str]:
    candidates = (
        ("timestamp", "timestamp"),
        ("ts_ms", "ts_ms"),
        ("event_ts_ms", "event_ts_ms"),
        ("request_ts_ms", "request_ts_ms"),
        ("adapter_response.updateTime", "adapter_response.updateTime"),
        ("adapter_response.time", "adapter_response.time"),
        ("metadata.close_ts_ms", "metadata.close_ts_ms"),
    )
    for path, source in candidates:
        ts_ms = try_parse_timestamp_ms(payload_get(payload, path))
        if ts_ms is not None:
            return ts_ms, source
    return None, "missing"


def _iter_authority_rows(order_log_path: Path) -> list[AuthorityRow]:
    rows: list[AuthorityRow] = []
    with order_log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            event_type = stringify(payload.get("event_type")) or ""
            if event_type not in RETAINED_EVENT_TYPES:
                continue
            timestamp_ms, timestamp_source = _pick_timestamp(payload)
            rows.append(
                AuthorityRow(
                    source_file=str(order_log_path),
                    source_line=line_no,
                    payload=payload,
                    timestamp_ms=timestamp_ms,
                    timestamp_iso=iso_utc(timestamp_ms),
                    timestamp_quality="direct_order_log" if timestamp_ms is not None else "missing",
                    timestamp_source=timestamp_source,
                    timestamp_support="order_log_field",
                    sequence_token=f"0001:{line_no:08d}",
                )
            )
    return rows


def _iter_core_regime_tpsl_rows(runtime_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for log_path in sorted(runtime_root.glob("aurora_core.log*")):
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, start=1):
                match = CORE_REGIME_TPSL_PATTERN.match(line.strip())
                if match is None:
                    continue
                local_dt = datetime.strptime(
                    match.group("timestamp"), "%Y-%m-%d %H:%M:%S,%f"
                )
                local_ts_ms = int(
                    local_dt.replace(tzinfo=timezone.utc).timestamp() * 1000
                )
                rows.append(
                    {
                        "source_file": str(log_path),
                        "source_line": line_no,
                        "local_ts_ms": local_ts_ms,
                        "symbol": match.group("symbol"),
                        "regime": match.group("regime"),
                        "stop_price": to_float(match.group("stop")),
                        "target_price": to_float(match.group("target")),
                    }
                )
    return rows


def _pick_decision_row(group: Any) -> Any | None:
    decision_rows = [
        row
        for row in group.intent_rows
        if stringify(row.payload.get("source_fsm")) == "DecisionMaking"
    ]
    if not decision_rows and group.placed_rows:
        decision_rows = group.placed_rows
    if not decision_rows:
        return None
    return sorted(
        decision_rows,
        key=lambda item: ((item.timestamp_ms or 0), item.source_line),
    )[0]


def _price_matches(left: float | None, right: float | None, tolerance: float = 1e-6) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) <= tolerance


def _infer_core_log_offset_ms(groups: dict[str, Any], core_rows: list[dict[str, Any]]) -> int | None:
    if not core_rows:
        return None

    rounded_offsets: list[int] = []
    for group in groups.values():
        decision_row = _pick_decision_row(group)
        if decision_row is None or decision_row.timestamp_ms is None:
            continue
        surface = _decision_surface_from_group(group)
        target_price = to_float(surface.get("historical_target_price"))
        stop_price = to_float(surface.get("historical_stop_price"))
        if target_price is None or stop_price is None:
            continue
        symbol = stringify(decision_row.payload.get("symbol")) or ""
        regime = stringify(decision_row.payload.get("regime")) or ""
        if not symbol or not regime:
            continue

        matches = [
            row
            for row in core_rows
            if row["symbol"] == symbol
            and row["regime"] == regime
            and _price_matches(row["target_price"], target_price)
            and _price_matches(row["stop_price"], stop_price)
        ]
        if not matches:
            continue

        matched_row = min(
            matches,
            key=lambda row: abs(row["local_ts_ms"] -
                                decision_row.timestamp_ms),
        )
        offset_ms = matched_row["local_ts_ms"] - decision_row.timestamp_ms
        rounded_offsets.append(int(round(offset_ms / 60000.0) * 60000))

    if not rounded_offsets:
        return None
    return Counter(rounded_offsets).most_common(1)[0][0]


def _fallback_geometry_from_core_log(
    group: Any,
    core_rows: list[dict[str, Any]],
    core_log_offset_ms: int | None,
) -> dict[str, Any]:
    if not core_rows or core_log_offset_ms is None:
        return {}

    decision_row = _pick_decision_row(group)
    if decision_row is None or decision_row.timestamp_ms is None:
        return {}

    symbol = stringify(decision_row.payload.get("symbol")) or ""
    regime = stringify(decision_row.payload.get("regime")) or ""
    if not symbol or not regime:
        return {}

    decision_ts_ms = decision_row.timestamp_ms
    candidates: list[tuple[int, dict[str, Any]]] = []
    for row in core_rows:
        if row["symbol"] != symbol or row["regime"] != regime:
            continue
        adjusted_ts_ms = row["local_ts_ms"] - core_log_offset_ms
        delta_ms = abs(adjusted_ts_ms - decision_ts_ms)
        if delta_ms > 15 * 60 * 1000:
            continue
        candidates.append((delta_ms, row))

    if not candidates:
        return {}

    _, candidate = min(
        candidates,
        key=lambda item: (item[0], item[1]["source_file"],
                          item[1]["source_line"]),
    )
    return {
        "historical_target_price": candidate["target_price"],
        "historical_stop_price": candidate["stop_price"],
        "historical_geometry_source": "aurora_core_regime_tpsl",
    }


def _extract_surface(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "trend_dir": stringify(_first_value(payload, "trend_dir", "metadata.trend_dir")) or None,
        "trend_confidence": to_float(_first_value(payload, "trend_confidence", "metadata.trend_confidence")),
        "trend_run_length": to_int(_first_value(payload, "trend_run_length", "metadata.trend_run_length")),
        "pm_norm_10s": _price_motion_value(payload, "pm_norm_10s"),
        "pm_norm_60s": _price_motion_value(payload, "pm_norm_60s"),
        "pm_norm_300s": _price_motion_value(payload, "pm_norm_300s"),
        "resolved_min_regime_confidence": to_float(
            payload_get(payload, "metadata.resolved_min_regime_confidence")
        ),
        "resolved_min_regime_confidence_source": stringify(
            payload_get(
                payload, "metadata.resolved_min_regime_confidence_source")
        )
        or None,
        "resolved_max_regime_confidence": to_float(
            payload_get(payload, "metadata.resolved_max_regime_confidence")
        ),
        "resolved_max_regime_confidence_source": stringify(
            payload_get(
                payload, "metadata.resolved_max_regime_confidence_source")
        )
        or None,
    }


def _extract_historical_geometry(payload: dict[str, Any]) -> dict[str, Any]:
    target_price = None
    stop_price = None
    source_parts: list[str] = []

    top_level_target = to_float(_first_value(
        payload, "target_price", "metadata.target_price"))
    top_level_stop = to_float(_first_value(
        payload, "stop_price", "metadata.stop_price"))
    if top_level_target is not None or top_level_stop is not None:
        source_parts.append("order_log_intent")
        target_price = top_level_target
        stop_price = top_level_stop

    economics_target = to_float(
        _first_value(
            payload,
            "economics_context.target_price",
            "metadata.economics_context.target_price",
        )
    )
    economics_stop = to_float(
        _first_value(
            payload,
            "economics_context.stop_price",
            "metadata.economics_context.stop_price",
        )
    )
    if economics_target is not None or economics_stop is not None:
        if target_price is None:
            target_price = economics_target
        if stop_price is None:
            stop_price = economics_stop
        if not source_parts or target_price != top_level_target or stop_price != top_level_stop:
            source_parts.append("economics_context")

    low_vol_target = to_float(
        _first_value(
            payload,
            "low_vol_cost_floor.target_price",
            "metadata.low_vol_cost_floor.target_price",
        )
    )
    low_vol_stop = to_float(
        _first_value(
            payload,
            "low_vol_cost_floor.stop_price",
            "metadata.low_vol_cost_floor.stop_price",
        )
    )
    if low_vol_target is not None or low_vol_stop is not None:
        if target_price is None:
            target_price = low_vol_target
        if stop_price is None:
            stop_price = low_vol_stop
        if "low_vol_cost_floor" not in source_parts:
            source_parts.append("low_vol_cost_floor")

    low_vol_econ_target = to_float(
        _first_value(
            payload,
            "low_vol_cost_floor.economics_context.target_price",
            "metadata.low_vol_cost_floor.economics_context.target_price",
        )
    )
    low_vol_econ_stop = to_float(
        _first_value(
            payload,
            "low_vol_cost_floor.economics_context.stop_price",
            "metadata.low_vol_cost_floor.economics_context.stop_price",
        )
    )
    if low_vol_econ_target is not None or low_vol_econ_stop is not None:
        if target_price is None:
            target_price = low_vol_econ_target
        if stop_price is None:
            stop_price = low_vol_econ_stop
        if "low_vol_cost_floor.economics_context" not in source_parts:
            source_parts.append("low_vol_cost_floor.economics_context")

    return {
        "historical_target_price": target_price,
        "historical_stop_price": stop_price,
        "historical_actual_tp_bps": to_float(
            _first_value(
                payload,
                "actual_tp_bps",
                "economics_context.actual_tp_bps",
                "metadata.economics_context.actual_tp_bps",
                "low_vol_cost_floor.actual_tp_bps",
                "metadata.low_vol_cost_floor.actual_tp_bps",
                "low_vol_cost_floor.economics_context.actual_tp_bps",
                "metadata.low_vol_cost_floor.economics_context.actual_tp_bps",
            )
        ),
        "historical_actual_sl_bps": to_float(
            _first_value(
                payload,
                "actual_sl_bps",
                "economics_context.actual_sl_bps",
                "metadata.economics_context.actual_sl_bps",
                "low_vol_cost_floor.actual_sl_bps",
                "metadata.low_vol_cost_floor.actual_sl_bps",
                "low_vol_cost_floor.economics_context.actual_sl_bps",
                "metadata.low_vol_cost_floor.economics_context.actual_sl_bps",
            )
        ),
        "historical_round_trip_fee_bps": to_float(
            _first_value(
                payload,
                "round_trip_fee_bps",
                "economics_context.round_trip_fee_bps",
                "metadata.economics_context.round_trip_fee_bps",
                "low_vol_cost_floor.round_trip_fee_bps",
                "metadata.low_vol_cost_floor.round_trip_fee_bps",
                "low_vol_cost_floor.economics_context.round_trip_fee_bps",
                "metadata.low_vol_cost_floor.economics_context.round_trip_fee_bps",
            )
        ),
        "historical_expected_net_if_tp_bps": to_float(
            _first_value(
                payload,
                "expected_net_if_tp_bps",
                "economics_context.expected_net_if_tp_bps",
                "metadata.economics_context.expected_net_if_tp_bps",
                "low_vol_cost_floor.expected_net_if_tp_bps",
                "metadata.low_vol_cost_floor.expected_net_if_tp_bps",
                "low_vol_cost_floor.economics_context.expected_net_if_tp_bps",
                "metadata.low_vol_cost_floor.economics_context.expected_net_if_tp_bps",
            )
        ),
        "historical_expected_net_if_sl_bps": to_float(
            _first_value(
                payload,
                "expected_net_if_sl_bps",
                "economics_context.expected_net_if_sl_bps",
                "metadata.economics_context.expected_net_if_sl_bps",
                "low_vol_cost_floor.expected_net_if_sl_bps",
                "metadata.low_vol_cost_floor.expected_net_if_sl_bps",
                "low_vol_cost_floor.economics_context.expected_net_if_sl_bps",
                "metadata.low_vol_cost_floor.economics_context.expected_net_if_sl_bps",
            )
        ),
        "historical_rr_ratio": to_float(
            _first_value(
                payload,
                "rr_ratio",
                "economics_context.rr_ratio",
                "metadata.economics_context.rr_ratio",
                "low_vol_cost_floor.rr_ratio",
                "metadata.low_vol_cost_floor.rr_ratio",
                "low_vol_cost_floor.economics_context.rr_ratio",
                "metadata.low_vol_cost_floor.economics_context.rr_ratio",
            )
        ),
        "historical_geometry_source": "+".join(source_parts) or None,
    }


def _payload_has_historical_geometry(payload: dict[str, Any]) -> bool:
    geometry = _extract_historical_geometry(payload)
    return (
        geometry["historical_target_price"] is not None
        or geometry["historical_stop_price"] is not None
    )


def _decision_surface_from_group(
    group: Any,
    *,
    core_rows: list[dict[str, Any]] | None = None,
    core_log_offset_ms: int | None = None,
) -> dict[str, Any]:
    decision_row = _pick_decision_row(group)
    if decision_row is None:
        surface: dict[str, Any] = {}
    else:
        surface = _extract_surface(decision_row.payload)
        surface["raw_payload"] = decision_row.payload

    geometry_rows = [
        row
        for row in group.intent_rows
        if _payload_has_historical_geometry(row.payload)
    ]
    if geometry_rows:
        geometry_row = sorted(
            geometry_rows,
            key=lambda item: ((item.timestamp_ms or 0), item.source_line),
        )[0]
        surface.update(_extract_historical_geometry(geometry_row.payload))
    elif surface.get("raw_payload"):
        surface.update(_extract_historical_geometry(surface["raw_payload"]))

    if (
        surface.get("historical_target_price") is None
        or surface.get("historical_stop_price") is None
    ):
        fallback_geometry = _fallback_geometry_from_core_log(
            group,
            core_rows or [],
            core_log_offset_ms,
        )
        filled_any = False
        for field_name in ("historical_target_price", "historical_stop_price"):
            if surface.get(field_name) is None and fallback_geometry.get(field_name) is not None:
                surface[field_name] = fallback_geometry[field_name]
                filled_any = True
        if filled_any:
            existing_source = stringify(surface.get(
                "historical_geometry_source")) or ""
            fallback_source = stringify(fallback_geometry.get(
                "historical_geometry_source")) or ""
            if existing_source and fallback_source:
                source_parts = [
                    part for part in existing_source.split("+") if part]
                if fallback_source not in source_parts:
                    source_parts.append(fallback_source)
                surface["historical_geometry_source"] = "+".join(source_parts)
            else:
                surface["historical_geometry_source"] = fallback_source or existing_source or None
    return surface


def reconstruct_canonical_entries(
    workspace_root: Path,
    runtime_root: Path,
    report_root: Path,
) -> tuple[list[CanonicalEntry], list[dict[str, Any]], dict[str, Any]]:
    order_log_path = runtime_root / "order_log_v1.jsonl"
    strategy_context = load_strategy_context(workspace_root)
    substrate_root = report_root / "_substrate"
    substrate_root.mkdir(parents=True, exist_ok=True)

    rows = _iter_authority_rows(order_log_path)
    core_regime_rows = _iter_core_regime_tpsl_rows(runtime_root)
    reconstructed_rows, unresolved_rows, groups = reconstruct_entries(
        rows,
        strategy_context,
        substrate_root,
    )
    entries_with_regimes = build_entries_with_regimes(
        reconstructed_rows,
        groups,
        strategy_context,
        workspace_root,
        substrate_root,
    )
    core_log_offset_ms = _infer_core_log_offset_ms(groups, core_regime_rows)

    canonical_entries: list[CanonicalEntry] = []
    for row in entries_with_regimes:
        entry_id = stringify(row.get("entry_id")) or ""
        group = groups.get(entry_id)
        surface = (
            _decision_surface_from_group(
                group,
                core_rows=core_regime_rows,
                core_log_offset_ms=core_log_offset_ms,
            )
            if group is not None
            else {}
        )
        notes = tuple(
            part.strip()
            for part in str(row.get("notes") or "").split("|")
            if part.strip()
        )
        canonical_entries.append(
            CanonicalEntry(
                entry_id=entry_id,
                lifecycle_id=stringify(row.get("lifecycle_id")) or entry_id,
                rid=stringify(row.get("rid")) or entry_id,
                trade_id=stringify(row.get("trade_id")) or "",
                symbol=stringify(row.get("symbol")) or "",
                side=stringify(row.get("side")) or "",
                strategy_id=stringify(row.get("strategy_id")) or "",
                entry_ts_ms=to_int(row.get("entry_ts_ms")) or 0,
                entry_time_iso=stringify(row.get("entry_time_iso")) or "",
                entry_price=to_float(row.get("entry_price")) or 0.0,
                qty=to_float(row.get("qty")) or 0.0,
                leverage=to_float(row.get("leverage")) or 0.0,
                timestamp_quality=stringify(
                    row.get("timestamp_quality")) or "",
                reconstruction_confidence=stringify(
                    row.get("reconstruction_confidence")) or "",
                regime_at_entry=stringify(
                    row.get("regime_at_entry")) or "UNKNOWN",
                regime_confidence_at_entry=to_float(
                    row.get("regime_confidence_at_entry")),
                regime_source=stringify(row.get("regime_source")) or "missing",
                historical_target_price=surface.get("historical_target_price"),
                historical_stop_price=surface.get("historical_stop_price"),
                historical_actual_tp_bps=surface.get(
                    "historical_actual_tp_bps"),
                historical_actual_sl_bps=surface.get(
                    "historical_actual_sl_bps"),
                historical_round_trip_fee_bps=surface.get(
                    "historical_round_trip_fee_bps"),
                historical_expected_net_if_tp_bps=surface.get(
                    "historical_expected_net_if_tp_bps"),
                historical_expected_net_if_sl_bps=surface.get(
                    "historical_expected_net_if_sl_bps"),
                historical_rr_ratio=surface.get("historical_rr_ratio"),
                historical_geometry_source=surface.get(
                    "historical_geometry_source"),
                actual_close_ts_ms=to_int(row.get("close_ts_ms")),
                actual_close_price=to_float(row.get("close_price")),
                actual_outcome_status=stringify(
                    row.get("actual_outcome_status")) or "",
                notes=notes,
                trend_dir=surface.get("trend_dir"),
                trend_confidence=surface.get("trend_confidence"),
                trend_run_length=surface.get("trend_run_length"),
                pm_norm_10s=surface.get("pm_norm_10s"),
                pm_norm_60s=surface.get("pm_norm_60s"),
                pm_norm_300s=surface.get("pm_norm_300s"),
                resolved_min_regime_confidence=surface.get(
                    "resolved_min_regime_confidence"),
                resolved_min_regime_confidence_source=surface.get(
                    "resolved_min_regime_confidence_source"
                ),
                resolved_max_regime_confidence=surface.get(
                    "resolved_max_regime_confidence"),
                resolved_max_regime_confidence_source=surface.get(
                    "resolved_max_regime_confidence_source"
                ),
                raw_surface=surface.get("raw_payload") or {},
            )
        )

    report_root.mkdir(parents=True, exist_ok=True)
    rows_for_csv = [entry.to_row() for entry in canonical_entries]
    headers = list(rows_for_csv[0].keys()) if rows_for_csv else [
        "entry_id",
        "lifecycle_id",
        "rid",
        "trade_id",
        "symbol",
        "side",
        "strategy_id",
        "entry_ts_ms",
        "entry_time_iso",
        "entry_price",
        "qty",
        "leverage",
        "timestamp_quality",
        "reconstruction_confidence",
        "regime_at_entry",
        "regime_confidence_at_entry",
        "regime_source",
        "historical_target_price",
        "historical_stop_price",
        "historical_actual_tp_bps",
        "historical_actual_sl_bps",
        "historical_round_trip_fee_bps",
        "historical_expected_net_if_tp_bps",
        "historical_expected_net_if_sl_bps",
        "historical_rr_ratio",
        "historical_geometry_source",
        "entry_origin",
        "actual_close_ts_ms",
        "actual_close_price",
        "actual_outcome_status",
        "notes",
        "trend_dir",
        "trend_confidence",
        "trend_run_length",
        "pm_norm_10s",
        "pm_norm_60s",
        "pm_norm_300s",
        "resolved_min_regime_confidence",
        "resolved_min_regime_confidence_source",
        "resolved_max_regime_confidence",
        "resolved_max_regime_confidence_source",
    ]
    write_csv(report_root / "canonical_entries.csv", headers, rows_for_csv)
    (report_root / "canonical_entries.json").write_text(
        json.dumps(rows_for_csv, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "order_log_path": str(order_log_path),
        "retained_rows": len(rows),
        "core_regime_rows": len(core_regime_rows),
        "core_log_offset_ms": core_log_offset_ms,
        "canonical_entries": len(canonical_entries),
        "unresolved_rows": len(unresolved_rows),
    }
    return canonical_entries, unresolved_rows, manifest
