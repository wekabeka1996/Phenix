from __future__ import annotations

import json
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
            payload_get(payload, "metadata.resolved_min_regime_confidence_source")
        )
        or None,
        "resolved_max_regime_confidence": to_float(
            payload_get(payload, "metadata.resolved_max_regime_confidence")
        ),
        "resolved_max_regime_confidence_source": stringify(
            payload_get(payload, "metadata.resolved_max_regime_confidence_source")
        )
        or None,
    }


def _decision_surface_from_group(group: Any) -> dict[str, Any]:
    decision_rows = [
        row
        for row in group.intent_rows
        if stringify(row.payload.get("source_fsm")) == "DecisionMaking"
    ]
    if not decision_rows and group.placed_rows:
        decision_rows = group.placed_rows
    if not decision_rows:
        return {}
    row = sorted(
        decision_rows,
        key=lambda item: ((item.timestamp_ms or 0), item.source_line),
    )[0]
    surface = _extract_surface(row.payload)
    surface["raw_payload"] = row.payload
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

    canonical_entries: list[CanonicalEntry] = []
    for row in entries_with_regimes:
        entry_id = stringify(row.get("entry_id")) or ""
        group = groups.get(entry_id)
        surface = _decision_surface_from_group(group) if group is not None else {}
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
                timestamp_quality=stringify(row.get("timestamp_quality")) or "",
                reconstruction_confidence=stringify(row.get("reconstruction_confidence")) or "",
                regime_at_entry=stringify(row.get("regime_at_entry")) or "UNKNOWN",
                regime_confidence_at_entry=to_float(row.get("regime_confidence_at_entry")),
                regime_source=stringify(row.get("regime_source")) or "missing",
                actual_close_ts_ms=to_int(row.get("close_ts_ms")),
                actual_close_price=to_float(row.get("close_price")),
                actual_outcome_status=stringify(row.get("actual_outcome_status")) or "",
                notes=notes,
                trend_dir=surface.get("trend_dir"),
                trend_confidence=surface.get("trend_confidence"),
                trend_run_length=surface.get("trend_run_length"),
                pm_norm_10s=surface.get("pm_norm_10s"),
                pm_norm_60s=surface.get("pm_norm_60s"),
                pm_norm_300s=surface.get("pm_norm_300s"),
                resolved_min_regime_confidence=surface.get("resolved_min_regime_confidence"),
                resolved_min_regime_confidence_source=surface.get(
                    "resolved_min_regime_confidence_source"
                ),
                resolved_max_regime_confidence=surface.get("resolved_max_regime_confidence"),
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
        "canonical_entries": len(canonical_entries),
        "unresolved_rows": len(unresolved_rows),
    }
    return canonical_entries, unresolved_rows, manifest
