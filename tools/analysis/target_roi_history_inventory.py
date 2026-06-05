from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from tools.analysis.order_reconstruction_tp_sl_common import (
    iso_utc,
    stringify,
    to_float,
    to_int,
    try_parse_timestamp_ms,
)
from tools.order_log_scenario_backtest.models import CanonicalEntry

WAL_OPEN_VERBS = {
    "TRADE_INTENT_PROPOSED",
    "OPEN",
    "ORDER_PLACED",
    "PENDING_BRACKETS_STORED",
    "TRADE_EXECUTED",
}
WAL_MIN_REALISTIC_TS_MS = 1_500_000_000_000
STRATEGY_PRICES_PATTERN = re.compile(
    r"strategy_prices:sl=(?P<sl>-?\d+(?:\.\d+)?),tp=(?P<tp>-?\d+(?:\.\d+)?)"
)


def _normalized_path_key(path: Path) -> str:
    return str(path.resolve(strict=False)).lower()


def _source_kind(root: Path, workspace_root: Path) -> str:
    default_logs_root = (workspace_root / "logs").resolve(strict=False)
    if root.resolve(strict=False) == default_logs_root:
        return "current_logs"
    return "explicit_runtime_root"


def _base_rid(raw_rid: str) -> str:
    return raw_rid.split(":", 1)[0]


def discover_runtime_root_candidates(
    workspace_root: Path,
    *,
    runtime_root: Path | None,
    extra_runtime_roots: Iterable[Path | str] | None = None,
    include_frozen: bool,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def register(root: Path, source_kind: str, source_label: str) -> None:
        normalized_root = root.resolve(strict=False)
        key = _normalized_path_key(normalized_root)
        order_log_path = normalized_root / "order_log_v1.jsonl"
        if key in seen or not order_log_path.exists():
            return

        has_aurora_core = any(normalized_root.glob("aurora_core.log*"))
        has_trade_lifecycle = (
            normalized_root / "trade_lifecycle.jsonl").exists()
        has_execution_lifecycle_stats = (
            normalized_root / "execution_lifecycle_stats_v1.jsonl"
        ).exists()
        has_regime_confidence_audit = (
            normalized_root / "regime_confidence_audit_v1.jsonl"
        ).exists()
        support_score = (
            (2 if has_aurora_core else 0)
            + (1 if has_trade_lifecycle else 0)
            + (1 if has_execution_lifecycle_stats else 0)
            + (1 if has_regime_confidence_audit else 0)
        )
        candidates.append(
            {
                "runtime_root": str(normalized_root),
                "runtime_root_path": normalized_root,
                "order_log_path": str(order_log_path),
                "source_kind": source_kind,
                "source_label": source_label,
                "report_dir_name": f"{len(candidates):02d}_{source_label}",
                "has_aurora_core": has_aurora_core,
                "has_trade_lifecycle": has_trade_lifecycle,
                "has_execution_lifecycle_stats": has_execution_lifecycle_stats,
                "has_regime_confidence_audit": has_regime_confidence_audit,
                "support_score": support_score,
                "discovery_index": len(candidates),
            }
        )
        seen.add(key)

    base_runtime_root = runtime_root or (workspace_root / "logs")
    register(
        base_runtime_root,
        _source_kind(base_runtime_root, workspace_root),
        base_runtime_root.name or "logs",
    )

    for extra_root in extra_runtime_roots or ():
        extra_path = Path(extra_root)
        if not extra_path.is_absolute():
            extra_path = (workspace_root / extra_path).resolve(strict=False)
        else:
            extra_path = extra_path.resolve(strict=False)
        register(extra_path, "explicit_runtime_root",
                 extra_path.name or "runtime_root")

    if include_frozen:
        for order_log_path in sorted((workspace_root / "frozen").glob("*/logs/order_log_v1.jsonl")):
            runtime_logs_root = order_log_path.parent
            source_label = runtime_logs_root.parent.name
            register(runtime_logs_root, "frozen", source_label)

    return candidates


def canonical_entry_identity(entry: CanonicalEntry) -> str:
    for field_name in ("lifecycle_id", "rid", "trade_id"):
        value = stringify(getattr(entry, field_name, None))
        if value:
            return f"{field_name}:{value}"
    return (
        "fallback:"
        f"{entry.symbol}:{entry.side}:{entry.entry_ts_ms}:{entry.entry_price:.10f}:{entry.qty:.10f}"
    )


def _source_priority(source_kind: str) -> int:
    return {
        "current_logs": 300,
        "explicit_runtime_root": 250,
        "frozen": 200,
    }.get(source_kind, 100)


def _entry_rank(entry: CanonicalEntry, source: dict[str, Any]) -> tuple[int, ...]:
    return (
        1 if entry.historical_target_price is not None and entry.historical_stop_price is not None else 0,
        1 if entry.historical_target_price is not None or entry.historical_stop_price is not None else 0,
        1 if entry.actual_close_ts_ms is not None and entry.actual_close_price is not None else 0,
        1 if bool(entry.raw_surface) else 0,
        1 if stringify(entry.regime_at_entry) not in {"", "UNKNOWN"} else 0,
        1 if entry.historical_round_trip_fee_bps is not None else 0,
        int(source.get("has_aurora_core") or False),
        int(source.get("support_score") or 0),
        _source_priority(stringify(source.get("source_kind")) or ""),
        -int(source.get("discovery_index") or 0),
    )


def dedupe_canonical_entries(
    candidate_entries: Iterable[tuple[CanonicalEntry, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry, source in candidate_entries:
        identity_key = canonical_entry_identity(entry)
        grouped[identity_key].append(
            {
                "identity_key": identity_key,
                "entry": entry,
                "source": source,
            }
        )

    selected: list[dict[str, Any]] = []
    inventory_rows: list[dict[str, Any]] = []

    def sort_key(item: tuple[str, list[dict[str, Any]]]) -> tuple[int, str]:
        entries = item[1]
        first_entry = min(
            entries, key=lambda candidate: candidate["entry"].entry_ts_ms or 0)["entry"]
        return first_entry.entry_ts_ms or 0, item[0]

    for identity_key, items in sorted(grouped.items(), key=sort_key):
        chosen = max(items, key=lambda candidate: _entry_rank(
            candidate["entry"], candidate["source"]))
        chosen["candidate_count"] = len(items)
        chosen["duplicate_count"] = len(items) - 1
        chosen["candidate_runtime_roots"] = [
            str(candidate["source"].get("runtime_root") or "") for candidate in items
        ]
        selected.append(chosen)

        chosen_entry = chosen["entry"]
        chosen_source = chosen["source"]
        inventory_rows.append(
            {
                "identity_key": identity_key,
                "symbol": chosen_entry.symbol,
                "side": chosen_entry.side,
                "entry_ts_ms": chosen_entry.entry_ts_ms,
                "selected_runtime_root": chosen_source.get("runtime_root") or "",
                "selected_source_kind": chosen_source.get("source_kind") or "",
                "selected_source_label": chosen_source.get("source_label") or "",
                "candidate_count": len(items),
                "duplicate_count": len(items) - 1,
                "candidate_runtime_roots": "|".join(chosen["candidate_runtime_roots"]),
                "historical_geometry_complete": "true"
                if chosen_entry.historical_target_price is not None and chosen_entry.historical_stop_price is not None
                else "false",
                "historical_geometry_source": chosen_entry.historical_geometry_source or "",
            }
        )

    return selected, inventory_rows


def discover_wal_files(
    workspace_root: Path,
    wal_paths: Iterable[Path | str] | None = None,
) -> list[Path]:
    candidates = list(wal_paths or [workspace_root / "ops" / "wal"])
    resolved: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        normalized = path.resolve(strict=False)
        key = _normalized_path_key(normalized)
        if key in seen or not normalized.exists() or normalized.suffix.lower() != ".jsonl":
            return
        resolved.append(normalized)
        seen.add(key)

    for candidate in candidates:
        path = Path(candidate)
        if not path.is_absolute():
            path = (workspace_root / path).resolve(strict=False)
        else:
            path = path.resolve(strict=False)
        if path.is_dir():
            for wal_file in sorted(path.rglob("*.jsonl")):
                add(wal_file)
        else:
            add(path)
    return resolved


def _load_wal_groups(wal_files: Iterable[Path]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for wal_file in wal_files:
        with wal_file.open("r", encoding="utf-8", errors="replace") as handle:
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
                ts_ms = _wal_timestamp_ms(payload)
                if ts_ms is None or ts_ms < WAL_MIN_REALISTIC_TS_MS:
                    continue
                pld = payload.get("pld") or {}
                if not isinstance(pld, dict):
                    pld = {}
                raw_rid = stringify(pld.get("rid")) or stringify(payload.get("rid")) or ""
                if not raw_rid.startswith("aurora_"):
                    continue
                base_rid = _base_rid(raw_rid)
                grouped[base_rid].append(
                    {
                        "verb": stringify(payload.get("verb")) or "",
                        "payload": payload,
                        "pld": pld,
                        "ts_ms": ts_ms,
                        "source_file": str(wal_file),
                        "source_line": line_no,
                        "raw_rid": raw_rid,
                        "base_rid": base_rid,
                        "is_bracket": raw_rid.endswith(":TP")
                        or raw_rid.endswith(":SL")
                        or stringify(pld.get("bracket_role")) in {"TP", "SL"}
                        or stringify(pld.get("order_type")) in {"take_profit_market", "stop_market"},
                    }
                )
    for rows in grouped.values():
        rows.sort(key=lambda row: (to_int(row.get("ts_ms")) or 0, row.get("source_file") or "", row.get("source_line") or 0))
    return grouped


def _wal_open_rid(payload: dict[str, Any]) -> str:
    pld = payload.get("pld") or {}
    rid = stringify(pld.get("rid")) or stringify(payload.get("rid")) or ""
    if not rid.startswith("aurora_"):
        return ""
    if rid.endswith(":TP") or rid.endswith(":SL"):
        return ""
    return rid


def _wal_timestamp_ms(payload: dict[str, Any]) -> int | None:
    pld = payload.get("pld") or {}
    for candidate in (
        pld.get("ts_ms"),
        pld.get("ts"),
        payload.get("event_ts_ms"),
        payload.get("ts"),
        payload.get("timestamp"),
    ):
        parsed = try_parse_timestamp_ms(candidate)
        if parsed is not None:
            return parsed
    return None


def _is_bracket_execution(payload: dict[str, Any]) -> bool:
    pld = payload.get("pld") or {}
    bracket_role = stringify(pld.get("bracket_role")) or ""
    if bracket_role in {"TP", "SL"}:
        return True
    order_type = stringify(pld.get("order_type")) or ""
    return order_type in {"take_profit_market", "stop_market"}


def scan_wal_open_inventory(wal_files: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    grouped = _load_wal_groups(wal_files)
    for rid, group_rows in sorted(grouped.items(), key=lambda item: (to_int(item[1][0].get("ts_ms")) or 0, item[0])):
        open_verbs = {row["verb"] for row in group_rows if row["verb"] in WAL_OPEN_VERBS}
        symbol = ""
        side = ""
        first_ts_ms = to_int(group_rows[0].get("ts_ms")) or 0
        last_ts_ms = first_ts_ms
        file_set: set[str] = set()
        entry_order_id = ""
        entry_client_order_id = ""
        has_trade_executed = False
        for row in group_rows:
            pld = row["pld"]
            file_set.add(str(row["source_file"]))
            last_ts_ms = max(last_ts_ms, to_int(row.get("ts_ms")) or last_ts_ms)
            if not symbol:
                symbol = stringify(pld.get("symbol")) or stringify(pld.get("instrument")) or ""
            if not side and not row["is_bracket"]:
                side = stringify(pld.get("side")) or ""
            if not entry_order_id:
                entry_order_id = (
                    stringify(pld.get("entry_order_id"))
                    or stringify(pld.get("orderId"))
                    or stringify(pld.get("order_id"))
                    or stringify(pld.get("exchangeOrderId"))
                    or ""
                )
            if not entry_client_order_id:
                entry_client_order_id = (
                    stringify(pld.get("entry_client_order_id"))
                    or stringify(pld.get("client_order_id"))
                    or stringify(pld.get("clientOrderId"))
                    or ""
                )
            if row["verb"] == "TRADE_EXECUTED" and not row["is_bracket"]:
                status = stringify(pld.get("status")) or ""
                if status in {"FILLED", "PARTIALLY_FILLED"}:
                    has_trade_executed = True
        if not has_trade_executed:
            continue
        rows.append(
            {
                "rid": rid,
                "symbol": symbol,
                "side": side,
                "first_ts_ms": first_ts_ms or "",
                "last_ts_ms": last_ts_ms or "",
                "verbs": "|".join(sorted(open_verbs)),
                "file_count": len(file_set),
                "line_count": len(group_rows),
                "has_trade_executed": "true",
                "entry_order_id": entry_order_id,
                "entry_client_order_id": entry_client_order_id,
            }
        )
    return rows


def _strategy_prices_from_rows(rows: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    for row in rows:
        data_ref = row["pld"].get("data_ref") or row["payload"].get("data_ref") or []
        if not isinstance(data_ref, list):
            continue
        for item in data_ref:
            match = STRATEGY_PRICES_PATTERN.search(str(item))
            if match is not None:
                return to_float(match.group("sl")), to_float(match.group("tp"))
    return None, None


def _compute_bps(entry_price: float | None, reference_price: float | None) -> float | None:
    if entry_price is None or reference_price is None or entry_price <= 0:
        return None
    return abs(reference_price - entry_price) / entry_price * 10_000.0


def reconstruct_wal_only_canonical_entries(
    wal_files: Iterable[Path],
    *,
    candidate_rids: set[str] | None,
    instrument_context: dict[str, dict[str, Any]] | None,
) -> list[CanonicalEntry]:
    grouped = _load_wal_groups(wal_files)
    entries: list[CanonicalEntry] = []

    for rid, group_rows in sorted(grouped.items(), key=lambda item: (to_int(item[1][0].get("ts_ms")) or 0, item[0])):
        if candidate_rids is not None and rid not in candidate_rids:
            continue

        open_anchor = None
        for preferred_verb in ("ORDER_PLACED", "OPEN", "TRADE_INTENT_PROPOSED"):
            matches = [row for row in group_rows if row["verb"] == preferred_verb and not row["is_bracket"]]
            if matches:
                open_anchor = matches[0]
                break
        if open_anchor is None:
            continue

        anchor_pld = open_anchor["pld"]
        symbol = stringify(anchor_pld.get("symbol")) or stringify(anchor_pld.get("instrument")) or ""
        side = (stringify(anchor_pld.get("side")) or "").upper()
        if not symbol or side not in {"BUY", "SELL"}:
            continue

        entry_fills = [
            row
            for row in group_rows
            if row["verb"] == "TRADE_EXECUTED"
            and not row["is_bracket"]
            and (stringify(row["pld"].get("side")) or "").upper() == side
            and (stringify(row["pld"].get("status")) or "") in {"FILLED", "PARTIALLY_FILLED"}
        ]
        if not entry_fills:
            continue

        weighted_notional = 0.0
        total_qty = 0.0
        total_fee = 0.0
        cumulative_qty = 0.0
        entry_ts_ms = 0
        entry_order_id = ""
        entry_client_order_id = ""
        for fill in entry_fills:
            fill_pld = fill["pld"]
            qty = to_float(fill_pld.get("qty")) or to_float(fill_pld.get("quantity")) or to_float(fill_pld.get("last_fill_qty")) or 0.0
            price = to_float(fill_pld.get("price"))
            if qty > 0 and price is not None:
                total_qty += qty
                weighted_notional += qty * price
            cumulative_qty = max(cumulative_qty, to_float(fill_pld.get("cumulative_qty")) or 0.0)
            if cumulative_qty <= 0 and total_qty > 0:
                cumulative_qty = total_qty
            if (to_int(fill.get("ts_ms")) or 0) >= entry_ts_ms:
                entry_ts_ms = to_int(fill.get("ts_ms")) or entry_ts_ms
            commission_asset = (stringify(fill_pld.get("commissionAsset")) or "USDT").upper()
            fee_value = to_float(fill_pld.get("commission"))
            if fee_value is None:
                fee_value = to_float(fill_pld.get("fees"))
            if fee_value is not None and commission_asset == "USDT":
                total_fee += fee_value
            if not entry_order_id:
                entry_order_id = stringify(fill_pld.get("orderId")) or stringify(fill_pld.get("order_id")) or stringify(fill_pld.get("exchangeOrderId")) or ""
            if not entry_client_order_id:
                entry_client_order_id = stringify(fill_pld.get("clientOrderId")) or stringify(fill_pld.get("client_order_id")) or ""

        qty = cumulative_qty if cumulative_qty > 0 else total_qty
        entry_price = weighted_notional / total_qty if total_qty > 0 else None
        if entry_price is None or qty <= 0 or entry_ts_ms <= 0:
            continue

        pending_rows = [row for row in group_rows if row["verb"] == "PENDING_BRACKETS_STORED"]
        historical_stop_price = None
        historical_target_price = None
        historical_geometry_source = None
        if pending_rows:
            pending_pld = pending_rows[0]["pld"]
            historical_stop_price = to_float(pending_pld.get("sl"))
            historical_target_price = to_float(pending_pld.get("tp"))
            historical_geometry_source = "wal_pending_brackets"
            if not entry_order_id:
                entry_order_id = stringify(pending_pld.get("entry_order_id")) or entry_order_id
            if not entry_client_order_id:
                entry_client_order_id = stringify(pending_pld.get("entry_client_order_id")) or entry_client_order_id
        if historical_stop_price is None or historical_target_price is None:
            strategy_stop, strategy_target = _strategy_prices_from_rows(group_rows)
            if historical_stop_price is None:
                historical_stop_price = strategy_stop
            if historical_target_price is None:
                historical_target_price = strategy_target
            if historical_stop_price is not None or historical_target_price is not None:
                historical_geometry_source = historical_geometry_source or "wal_strategy_prices"

        leverage = 0.0
        if instrument_context:
            leverage = to_float((instrument_context.get(symbol) or {}).get("target_leverage")) or 0.0

        round_trip_fee_bps = None
        if weighted_notional > 0 and total_fee > 0:
            round_trip_fee_bps = total_fee / weighted_notional * 10_000.0 * 2.0

        actual_close_ts_ms = None
        actual_close_price = None
        actual_outcome_status = ""
        close_candidates = [
            row
            for row in group_rows
            if row["verb"] == "TRADE_EXECUTED"
            and (
                row["is_bracket"]
                or ((stringify(row["pld"].get("side")) or "").upper() not in {"", side})
            )
            and (to_int(row.get("ts_ms")) or 0) >= entry_ts_ms
        ]
        if close_candidates:
            close_row = close_candidates[0]
            close_pld = close_row["pld"]
            actual_close_ts_ms = to_int(close_row.get("ts_ms"))
            actual_close_price = to_float(close_pld.get("price"))
            if close_row["is_bracket"]:
                actual_outcome_status = (stringify(close_pld.get("bracket_role")) or close_row["raw_rid"].split(":", 1)[-1]).lower()
            else:
                actual_outcome_status = "closed_from_wal"

        confidence_score = int(open_anchor is not None) + int(bool(pending_rows)) + int(bool(entry_fills))
        reconstruction_confidence = "high" if confidence_score >= 3 else "medium"
        regime_at_entry = stringify(anchor_pld.get("regime")) or "UNKNOWN"
        regime_confidence_at_entry = to_float(anchor_pld.get("regime_confidence"))
        strategy_id = stringify(anchor_pld.get("strategy")) or stringify(anchor_pld.get("strategy_id")) or "aurora"

        notes = ["wal_only_reconstruction", f"wal_entry_fill_count={len(entry_fills)}"]
        if actual_outcome_status:
            notes.append(f"wal_actual_close={actual_outcome_status}")

        stop_bps = _compute_bps(entry_price, historical_stop_price)
        target_bps = _compute_bps(entry_price, historical_target_price)
        rr_ratio = None
        if stop_bps and target_bps:
            rr_ratio = target_bps / stop_bps

        entries.append(
            CanonicalEntry(
                entry_id=rid,
                lifecycle_id=rid,
                rid=rid,
                trade_id=entry_order_id or entry_client_order_id or rid,
                symbol=symbol,
                side=side,
                strategy_id=strategy_id,
                entry_ts_ms=entry_ts_ms,
                entry_time_iso=iso_utc(entry_ts_ms),
                entry_price=entry_price,
                qty=qty,
                leverage=leverage,
                timestamp_quality="wal_trade_executed",
                reconstruction_confidence=reconstruction_confidence,
                regime_at_entry=regime_at_entry,
                regime_confidence_at_entry=regime_confidence_at_entry,
                regime_source=f"wal_{open_anchor['verb'].lower()}",
                historical_target_price=historical_target_price,
                historical_stop_price=historical_stop_price,
                historical_actual_tp_bps=target_bps,
                historical_actual_sl_bps=stop_bps,
                historical_round_trip_fee_bps=round_trip_fee_bps,
                historical_rr_ratio=rr_ratio,
                historical_geometry_source=historical_geometry_source,
                entry_origin="wal_trade_executed",
                actual_close_ts_ms=actual_close_ts_ms,
                actual_close_price=actual_close_price,
                actual_outcome_status=actual_outcome_status,
                notes=tuple(notes),
                raw_surface=open_anchor["payload"],
            )
        )
    return entries
