from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = PROJECT_ROOT / "reports" / "def005"
ENTRIES_PATH = (
    PROJECT_ROOT
    / "reports"
    / "order_reconstruction_tp_sl"
    / "reconstructed_opened_entries_from_synced_order_log.csv"
)
NORMALIZED_ORDERS_PATH = (
    PROJECT_ROOT
    / "reports"
    / "order_reconstruction_tp_sl"
    / "normalized_exchange_orders.csv"
)
PENDING_BRACKETS_WAL_PATH = (
    PROJECT_ROOT / "ops" / "wal" / "execution_position_pending_brackets_v1.jsonl"
)
STARTUP_TRUTH_PATH = (
    PROJECT_ROOT / "ops" / "restore" / "execution_position_startup_truth_v1.jsonl"
)
RESTORE_ENVELOPE_PATH = (
    PROJECT_ROOT / "ops" / "restore" / "execution_position_restore_envelope_v1.json"
)
ORDER_GUARDIAN_LOG_PATH = PROJECT_ROOT / "logs" / "order_guardian.log"

INVENTORY_PATH = REPORTS_DIR / "def005_position_closed_detected_inventory.csv"
SUMMARY_PATH = REPORTS_DIR / "def005_position_closed_detected_summary.json"

CONTRACT_BREACH_PATTERN = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?"
    r"close-bearing terminal update (?P<client>[^/]+)/(?P<order>[^\s]+) for "
    r"(?P<symbol>[A-Z0-9]+) has no canonical OrderIndex record",
)


@dataclass(frozen=True)
class PendingBracketStored:
    rid: str
    symbol: str
    ts_ms: int
    entry_order_id: Optional[str]
    entry_client_order_id: Optional[str]
    side: Optional[str]
    sl_price: Optional[float]
    tp_price: Optional[float]


@dataclass(frozen=True)
class PendingBracketCleared:
    entry_order_id: str
    symbol: str
    ts_ms: int
    reason: str


@dataclass(frozen=True)
class ContractBreach:
    ts_ms: int
    symbol: str
    client_order_id: str
    exchange_order_id: str
    source_path: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def as_int(value: Any) -> Optional[int]:
    try:
        if value in (None, "", "None"):
            return None
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> Optional[float]:
    try:
        if value in (None, "", "None"):
            return None
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def format_float(value: Optional[float], digits: int = 8) -> str:
    if value is None or math.isnan(value) or math.isinf(value):
        return ""
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def parse_log_ts_ms(raw_ts: str) -> Optional[int]:
    try:
        parsed = datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        return None
    return int(parsed.replace(tzinfo=timezone.utc).timestamp() * 1000)


def compute_net_roi_pct(
    *,
    realized_pnl_net: Optional[float],
    entry_price: Optional[float],
    qty: Optional[float],
    leverage: Optional[float],
) -> Optional[float]:
    if realized_pnl_net is None or entry_price is None or qty is None or leverage in (None, 0):
        return None
    margin_used = (entry_price * qty) / leverage
    if not margin_used:
        return None
    return (realized_pnl_net / margin_used) * 100.0


def load_pending_brackets() -> tuple[
    dict[str, PendingBracketStored],
    dict[str, list[PendingBracketCleared]],
]:
    stored_by_rid: dict[str, PendingBracketStored] = {}
    cleared_by_entry_order: dict[str,
                                 list[PendingBracketCleared]] = defaultdict(list)
    for row in iter_jsonl(PENDING_BRACKETS_WAL_PATH):
        verb = as_str(row.get("verb")).upper()
        payload = row.get("pld") if isinstance(row.get("pld"), dict) else {}
        if verb == "PENDING_BRACKETS_STORED":
            rid = as_str(row.get("rid"))
            if not rid:
                continue
            stored_by_rid[rid] = PendingBracketStored(
                rid=rid,
                symbol=as_str(payload.get("symbol")).upper(),
                ts_ms=as_int(payload.get("ts_ms")) or 0,
                entry_order_id=as_str(payload.get("entry_order_id")) or None,
                entry_client_order_id=as_str(
                    payload.get("entry_client_order_id")) or None,
                side=as_str(payload.get("side")).upper() or None,
                sl_price=as_float(payload.get("sl")),
                tp_price=as_float(payload.get("tp")),
            )
        elif verb == "PENDING_BRACKETS_CLEARED":
            entry_order_id = as_str(payload.get("entry_order_id"))
            if not entry_order_id:
                continue
            cleared_by_entry_order[entry_order_id].append(
                PendingBracketCleared(
                    entry_order_id=entry_order_id,
                    symbol=as_str(payload.get("symbol")).upper(),
                    ts_ms=as_int(payload.get("ts_ms")) or 0,
                    reason=as_str(payload.get("reason")).lower(),
                )
            )
    return stored_by_rid, cleared_by_entry_order


def load_normalized_orders() -> tuple[
    dict[str, list[dict[str, str]]],
    dict[str, list[dict[str, str]]],
    dict[str, list[dict[str, str]]],
]:
    by_rid: dict[str, list[dict[str, str]]] = defaultdict(list)
    close_by_symbol: dict[str, list[dict[str, str]]] = defaultdict(list)
    protective_by_symbol: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv_rows(NORMALIZED_ORDERS_PATH):
        rid = as_str(row.get("rid"))
        symbol = as_str(row.get("symbol")).upper()
        if rid:
            by_rid[rid].append(row)
        role = as_str(row.get("order_role")).lower()
        if symbol and role == "close":
            close_by_symbol[symbol].append(row)
        if symbol and role == "protective":
            protective_by_symbol[symbol].append(row)
    for rows in close_by_symbol.values():
        rows.sort(key=lambda item: as_int(item.get("timestamp_ms")) or 0)
    for rows in protective_by_symbol.values():
        rows.sort(key=lambda item: as_int(item.get("timestamp_ms")) or 0)
    return by_rid, close_by_symbol, protective_by_symbol


def load_contract_breaches() -> dict[str, list[ContractBreach]]:
    breaches_by_symbol: dict[str, list[ContractBreach]] = defaultdict(list)
    for log_path in PROJECT_ROOT.rglob("aurora_core.log*"):
        if log_path.is_dir():
            continue
        try:
            with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    match = CONTRACT_BREACH_PATTERN.search(line)
                    if not match:
                        continue
                    ts_ms = parse_log_ts_ms(match.group("ts"))
                    if ts_ms is None:
                        continue
                    symbol = match.group("symbol").upper()
                    breaches_by_symbol[symbol].append(
                        ContractBreach(
                            ts_ms=ts_ms,
                            symbol=symbol,
                            client_order_id=match.group("client"),
                            exchange_order_id=match.group("order"),
                            source_path=str(
                                log_path.relative_to(PROJECT_ROOT)),
                        )
                    )
        except OSError:
            continue
    for rows in breaches_by_symbol.values():
        rows.sort(key=lambda item: item.ts_ms)
    return breaches_by_symbol


def load_order_guardian_text() -> str:
    if not ORDER_GUARDIAN_LOG_PATH.exists():
        return ""
    try:
        return ORDER_GUARDIAN_LOG_PATH.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def load_startup_truth() -> list[dict[str, Any]]:
    rows = list(iter_jsonl(STARTUP_TRUTH_PATH))
    rows.sort(key=lambda item: as_int(item.get("ts_ms")) or 0)
    return rows


def load_restore_envelope() -> dict[str, Any]:
    if not RESTORE_ENVELOPE_PATH.exists():
        return {}
    try:
        return json.loads(RESTORE_ENVELOPE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def pick_entry_order_id(entry_rows: list[dict[str, str]]) -> str:
    candidate = ""
    for row in entry_rows:
        if as_str(row.get("order_role")).lower() != "entry":
            continue
        exchange_order_id = as_str(row.get("exchange_order_id"))
        if exchange_order_id:
            return exchange_order_id
        if not candidate:
            candidate = as_str(row.get("client_order_id"))
    return candidate


def pick_close_order(
    symbol_close_rows: list[dict[str, str]],
    *,
    close_ts_ms: Optional[int],
) -> Optional[dict[str, str]]:
    if close_ts_ms is None:
        return None
    best_row: Optional[dict[str, str]] = None
    best_delta: Optional[int] = None
    for row in symbol_close_rows:
        row_ts = as_int(row.get("timestamp_ms"))
        if row_ts is None:
            continue
        delta = abs(row_ts - close_ts_ms)
        if delta > 15 * 60 * 1000:
            continue
        if best_delta is None or delta < best_delta:
            best_row = row
            best_delta = delta
    return best_row


def find_contract_breach(
    symbol_breaches: list[ContractBreach],
    *,
    close_ts_ms: Optional[int],
) -> Optional[ContractBreach]:
    if close_ts_ms is None:
        return None
    best: Optional[ContractBreach] = None
    best_delta: Optional[int] = None
    for breach in symbol_breaches:
        delta = abs(breach.ts_ms - close_ts_ms)
        if delta > 30 * 60 * 1000:
            continue
        if best_delta is None or delta < best_delta:
            best = breach
            best_delta = delta
    return best


def find_restore_presence(
    *,
    symbol: str,
    entry_order_id: str,
    startup_truth_rows: list[dict[str, Any]],
    restore_envelope: dict[str, Any],
) -> str:
    active = restore_envelope.get("active_lifecycles")
    if isinstance(active, list):
        for record in active:
            if not isinstance(record, dict):
                continue
            if as_str(record.get("symbol")).upper() != symbol:
                continue
            linked_ref = record.get("linked_bracket_ref")
            if not isinstance(linked_ref, dict):
                continue
            if as_str(linked_ref.get("entry_order_id")) == entry_order_id:
                return "true"
    for row in reversed(startup_truth_rows):
        restore_authoritative = row.get("restore_authoritative")
        if not isinstance(restore_authoritative, dict):
            continue
        for symbol_status in restore_authoritative.get("symbol_statuses") or []:
            if not isinstance(symbol_status, dict):
                continue
            if as_str(symbol_status.get("symbol")).upper() != symbol:
                continue
            if as_str(symbol_status.get("deferred_entry_order_id")) == entry_order_id:
                return "true"
    return "unknown"


def find_guardian_presence(guardian_log_text: str, candidates: Iterable[str]) -> str:
    non_empty = [candidate for candidate in candidates if candidate]
    if not non_empty:
        return "unknown"
    for candidate in non_empty:
        if candidate in guardian_log_text:
            return "true"
    return "unknown"


def classify_entry(
    *,
    pending_stored: Optional[PendingBracketStored],
    clear_events: list[PendingBracketCleared],
    close_row: Optional[dict[str, str]],
    breach: Optional[ContractBreach],
) -> str:
    clear_reasons = {event.reason for event in clear_events}
    if breach is not None and pending_stored is not None:
        return "confirmed_missing_orderindex_mapping"
    if close_row is not None:
        close_reason = as_str(close_row.get("reason")).lower()
        client_order_id = as_str(close_row.get("client_order_id")).lower()
        if (
            close_reason in {"manual_close",
                             "close_submit_returned_without_exception"}
            or client_order_id.startswith("ppsreq:pps:")
            or client_order_id.startswith("close-")
        ):
            return "sidecar_close_legitimate"
    if "cancelled" in clear_reasons and pending_stored is not None:
        return "bracket_cancelled_legitimately"
    if pending_stored is None and breach is None:
        return "insufficient_data"
    return "insufficient_data"


def build_inventory() -> tuple[list[dict[str, str]], dict[str, Any]]:
    entries = read_csv_rows(ENTRIES_PATH)
    stored_by_rid, cleared_by_entry_order = load_pending_brackets()
    normalized_by_rid, close_by_symbol, _ = load_normalized_orders()
    breaches_by_symbol = load_contract_breaches()
    guardian_log_text = load_order_guardian_text()
    startup_truth_rows = load_startup_truth()
    restore_envelope = load_restore_envelope()

    inventory_rows: list[dict[str, str]] = []
    classification_counts: Counter[str] = Counter()
    close_source_counts: Counter[str] = Counter()
    pending_link_count = 0
    breach_count = 0

    for entry in entries:
        actual_outcome_status = as_str(
            entry.get("actual_outcome_status")).upper()
        if actual_outcome_status != "POSITION_CLOSED_DETECTED":
            continue

        entry_id = as_str(entry.get("entry_id"))
        symbol = as_str(entry.get("symbol")).upper()
        close_ts_ms = as_int(entry.get("close_ts_ms"))
        entry_ts_ms = as_int(entry.get("entry_ts_ms"))
        entry_price = as_float(entry.get("entry_price"))
        close_price = as_float(entry.get("close_price"))
        qty = as_float(entry.get("qty"))
        leverage = as_float(entry.get("leverage"))
        realized_pnl_net = as_float(entry.get("realized_pnl_net"))

        pending_stored = stored_by_rid.get(entry_id)
        entry_rows = normalized_by_rid.get(entry_id, [])
        entry_order_id = pick_entry_order_id(entry_rows)
        if not entry_order_id and pending_stored is not None and pending_stored.entry_order_id:
            entry_order_id = pending_stored.entry_order_id

        clear_events = cleared_by_entry_order.get(
            entry_order_id, []) if entry_order_id else []
        close_row = pick_close_order(close_by_symbol.get(
            symbol, []), close_ts_ms=close_ts_ms)
        breach = find_contract_breach(breaches_by_symbol.get(
            symbol, []), close_ts_ms=close_ts_ms)

        close_event_source = "unknown"
        close_order_id = ""
        if breach is not None:
            close_event_source = "binance_ws_contract_breach_no_orderindex"
            close_order_id = breach.exchange_order_id
            breach_count += 1
        elif close_row is not None:
            close_reason = as_str(close_row.get("reason")).lower() or "unknown"
            close_event_source = "order_log_close_order:" + close_reason
            close_order_id = as_str(close_row.get("exchange_order_id"))
        elif clear_events:
            close_event_source = "pending_brackets_wal:" + \
                clear_events[-1].reason
        close_source_counts[close_event_source] += 1

        bracket_link_before_restart = "true" if pending_stored is not None else "unknown"
        if pending_stored is not None:
            pending_link_count += 1
        bracket_link_after_restart = find_restore_presence(
            symbol=symbol,
            entry_order_id=entry_order_id,
            startup_truth_rows=startup_truth_rows,
            restore_envelope=restore_envelope,
        ) if entry_order_id else "unknown"

        guardian_presence = find_guardian_presence(
            guardian_log_text,
            [entry_id, entry_order_id, close_order_id],
        )
        order_index_presence = "false" if breach is not None else "unknown"
        classification = classify_entry(
            pending_stored=pending_stored,
            clear_events=clear_events,
            close_row=close_row,
            breach=breach,
        )
        classification_counts[classification] += 1

        inventory_rows.append(
            {
                "entry_id": entry_id,
                "symbol": symbol,
                "side": as_str(entry.get("side")).upper(),
                "entry_ts_ms": str(entry_ts_ms or ""),
                "close_ts_ms": str(close_ts_ms or ""),
                "entry_price": format_float(entry_price, digits=8),
                "close_price": format_float(close_price, digits=8),
                "net_roi": format_float(
                    compute_net_roi_pct(
                        realized_pnl_net=realized_pnl_net,
                        entry_price=entry_price,
                        qty=qty,
                        leverage=leverage,
                    ),
                    digits=6,
                ),
                "lifecycle_id": as_str(entry.get("lifecycle_id")),
                "trade_id": as_str(entry.get("trade_id")),
                "entry_order_id": entry_order_id,
                "tp_order_id": "",
                "sl_order_id": "",
                "close_order_id": close_order_id,
                "actual_outcome_status": actual_outcome_status,
                "close_event_source": close_event_source,
                "bracket_link_present_before_restart": bracket_link_before_restart,
                "bracket_link_present_after_restart": bracket_link_after_restart,
                "order_guardian_record_found": guardian_presence,
                "order_index_record_found": order_index_presence,
                "classification": classification,
            }
        )

    summary = {
        "total_position_closed_detected": len(inventory_rows),
        "pending_bracket_link_evidence_rows": pending_link_count,
        "contract_breach_rows": breach_count,
        "classification_counts": dict(classification_counts),
        "close_event_source_counts": dict(close_source_counts),
        "inventory_path": str(INVENTORY_PATH.relative_to(PROJECT_ROOT)),
    }
    return inventory_rows, summary


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "entry_id",
        "symbol",
        "side",
        "entry_ts_ms",
        "close_ts_ms",
        "entry_price",
        "close_price",
        "net_roi",
        "lifecycle_id",
        "trade_id",
        "entry_order_id",
        "tp_order_id",
        "sl_order_id",
        "close_order_id",
        "actual_outcome_status",
        "close_event_source",
        "bracket_link_present_before_restart",
        "bracket_link_present_after_restart",
        "order_guardian_record_found",
        "order_index_record_found",
        "classification",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    inventory_rows, summary = build_inventory()
    write_csv(INVENTORY_PATH, inventory_rows)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
