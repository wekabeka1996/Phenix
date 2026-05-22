#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EPISODES_CSV = ROOT / "reports" / \
    "binance_testnet_window_audit_last7d_utc" / "normalized" / "episodes.csv"
DEFAULT_WAL_DIR = ROOT / "ops" / "wal" / "old"
DEFAULT_OUT_DIR = ROOT / "reports" / "testnet_old_wal_join"

FILL_VERBS = {"TRADE_EXECUTED", "ORDER_FILLED", "FILL_RECEIVED"}
OPEN_SHARED_VERBS = {"TRADE_INTENT_PROPOSED", "OPEN"}
CLOSE_SHARED_VERBS = {"CANCEL_ORDER", "POSITION_CLOSED"}
INTERESTING_VERBS = {
    "TRADE_INTENT_PROPOSED",
    "OPEN",
    "ORDER_PLACED",
    "PENDING_BRACKETS_STORED",
    "PENDING_BRACKETS_CLEARED",
    "TRADE_EXECUTED",
    "ORDER_FILLED",
    "FILL_RECEIVED",
    "CLOSE",
    "CLOSE_ORDER",
    "CANCEL_ORDER",
    "POSITION_CLOSED",
    "ORDER_REJECTED",
    "ORDER_CANCELLED",
    "ORDER_TIMEOUT",
}
UUIDISH_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


@dataclass
class AnchorTrade:
    symbol: str
    direction: str
    entry_order_id: str
    entry_client_order_id: str
    exit_order_id: str
    exit_client_order_id: str
    entry_time_ms: int = 0
    exit_time_ms: int = 0
    entry_time_utc: str = ""
    exit_time_utc: str = ""
    entry_price: float | None = None
    exit_price: float | None = None
    close_reason_proven: str = ""
    close_reason_inferred: str = ""
    raw_episode_rows: int = 0
    episode_qty_sum: float = 0.0
    gross_realized_pnl_sum: float = 0.0
    entry_commission_sum: float = 0.0
    exit_commission_sum: float = 0.0
    net_pnl_after_trade_fees_sum: float = 0.0
    holding_ms_max: int = 0
    entry_local_dates: set[str] = field(default_factory=set)
    exit_local_dates: set[str] = field(default_factory=set)
    open_rid: str | None = None
    close_rid: str | None = None
    matched_anchor_verbs: set[str] = field(default_factory=set)
    evidence_events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def key(self) -> str:
        return "|".join(
            [
                self.symbol,
                self.direction,
                self.entry_order_id,
                self.entry_client_order_id,
                self.exit_order_id,
                self.exit_client_order_id,
            ]
        )


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _fmt_utc(ts_ms: int | None) -> str:
    if not ts_ms:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()


def _norm_token(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(value, "f").rstrip("0").rstrip(".")
    return str(value).strip()


def _norm_verb(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    if ":" in value and value.split(":", 1)[0] in {"EVT", "DEC", "CMD", "UPD"}:
        return value.split(":", 1)[1]
    return value


def _extract_symbol(obj: dict[str, Any]) -> str:
    pld = obj.get("pld") if isinstance(obj.get("pld"), dict) else {}
    for key in ("symbol", "instrument"):
        value = pld.get(key)
        if isinstance(value, str) and value:
            return value
    top_level = obj.get("symbol")
    if isinstance(top_level, str) and top_level:
        return top_level
    return ""


def _extract_tokens(obj: dict[str, Any]) -> set[str]:
    pld = obj.get("pld") if isinstance(obj.get("pld"), dict) else {}
    out: set[str] = set()
    fields = (
        "order_id",
        "exchange_order_id",
        "orderId",
        "exchangeOrderId",
        "client_order_id",
        "clientOrderId",
        "entry_order_id",
        "entry_client_order_id",
        "tracked_bracket_order_id",
        "idempotent_key",
    )
    for key in fields:
        token = _norm_token(pld.get(key))
        if token:
            out.add(token)
    token = _norm_token(obj.get("idempotent_key"))
    if token:
        out.add(token)
    return out


def _candidate_rids(obj: dict[str, Any]) -> list[str]:
    pld = obj.get("pld") if isinstance(obj.get("pld"), dict) else {}
    candidates: list[str] = []
    for value in (pld.get("rid"), obj.get("rid")):
        if isinstance(value, str) and value and value not in candidates:
            candidates.append(value)
    return candidates


def _prefer_logical_rid(candidates: list[str], symbol: str) -> str | None:
    for candidate in candidates:
        if symbol and symbol in candidate:
            return candidate
    for candidate in candidates:
        if not UUIDISH_RE.match(candidate):
            return candidate
    return candidates[0] if candidates else None


def _event_ts_ms(obj: dict[str, Any]) -> int:
    pld = obj.get("pld") if isinstance(obj.get("pld"), dict) else {}
    for value in (pld.get("ts_ms"), pld.get("ts"), obj.get("ts"), obj.get("timestamp"), obj.get("event_ts_ms")):
        ts_ms = _safe_int(value)
        if ts_ms:
            return ts_ms
    return 0


def _iter_jsonl(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in paths:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj


def _load_anchor_trades(episodes_csv: Path, symbols_filter: set[str] | None) -> tuple[list[AnchorTrade], int]:
    groups: dict[tuple[str, str, str, str, str, str], AnchorTrade] = {}
    raw_rows = 0
    with episodes_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            raw_rows += 1
            status = (row.get("status") or "").strip().upper()
            if status != "CLOSED":
                continue
            symbol = (row.get("symbol") or "").strip()
            if symbols_filter and symbol not in symbols_filter:
                continue
            key = (
                symbol,
                (row.get("direction") or "").strip(),
                (row.get("entry_order_id") or "").strip(),
                (row.get("entry_client_order_id") or "").strip(),
                (row.get("exit_order_id") or "").strip(),
                (row.get("exit_client_order_id") or "").strip(),
            )
            trade = groups.get(key)
            if trade is None:
                trade = AnchorTrade(
                    symbol=key[0],
                    direction=key[1],
                    entry_order_id=key[2],
                    entry_client_order_id=key[3],
                    exit_order_id=key[4],
                    exit_client_order_id=key[5],
                    close_reason_proven=(
                        row.get("close_reason_proven") or "").strip(),
                    close_reason_inferred=(
                        row.get("close_reason_inferred") or "").strip(),
                )
                groups[key] = trade
            trade.raw_episode_rows += 1
            trade.episode_qty_sum += _safe_float(row.get("qty")) or 0.0
            trade.gross_realized_pnl_sum += _safe_float(
                row.get("gross_realized_pnl")) or 0.0
            trade.entry_commission_sum += _safe_float(
                row.get("entry_commission")) or 0.0
            trade.exit_commission_sum += _safe_float(
                row.get("exit_commission")) or 0.0
            trade.net_pnl_after_trade_fees_sum += _safe_float(
                row.get("net_pnl_after_trade_fees")) or 0.0
            trade.holding_ms_max = max(
                trade.holding_ms_max, _safe_int(row.get("holding_ms")) or 0)
            entry_time_ms = _safe_int(row.get("entry_time_ms")) or 0
            exit_time_ms = _safe_int(row.get("exit_time_ms")) or 0
            if entry_time_ms and (trade.entry_time_ms == 0 or entry_time_ms < trade.entry_time_ms):
                trade.entry_time_ms = entry_time_ms
                trade.entry_time_utc = (
                    row.get("entry_time_utc") or "").strip() or _fmt_utc(entry_time_ms)
            if exit_time_ms and exit_time_ms > trade.exit_time_ms:
                trade.exit_time_ms = exit_time_ms
                trade.exit_time_utc = (
                    row.get("exit_time_utc") or "").strip() or _fmt_utc(exit_time_ms)
            entry_price = _safe_float(row.get("entry_price"))
            if trade.entry_price is None and entry_price is not None:
                trade.entry_price = entry_price
            exit_price = _safe_float(row.get("exit_price"))
            if trade.exit_price is None and exit_price is not None:
                trade.exit_price = exit_price
            entry_local_date = (row.get("entry_local_date") or "").strip()
            if entry_local_date:
                trade.entry_local_dates.add(entry_local_date)
            exit_local_date = (row.get("exit_local_date") or "").strip()
            if exit_local_date:
                trade.exit_local_dates.add(exit_local_date)
            if not trade.close_reason_proven:
                trade.close_reason_proven = (
                    row.get("close_reason_proven") or "").strip()
            if not trade.close_reason_inferred:
                trade.close_reason_inferred = (
                    row.get("close_reason_inferred") or "").strip()
    return sorted(groups.values(), key=lambda trade: (trade.entry_time_ms, trade.symbol, trade.exit_time_ms)), raw_rows


def _date_strings_between(start_ts_ms: int, end_ts_ms: int) -> set[str]:
    if not start_ts_ms and not end_ts_ms:
        return set()
    start_dt = datetime.fromtimestamp(
        (start_ts_ms or end_ts_ms) / 1000.0, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(
        (end_ts_ms or start_ts_ms) / 1000.0, tz=timezone.utc)
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt
    current = start_dt.date()
    end_date = end_dt.date()
    out: set[str] = set()
    while current <= end_date:
        out.add(current.isoformat())
        current += timedelta(days=1)
    return out


def _wal_paths_for_trades(wal_dir: Path, trades: list[AnchorTrade]) -> list[Path]:
    wanted_dates: set[str] = set()
    for trade in trades:
        wanted_dates.update(_date_strings_between(
            trade.entry_time_ms, trade.exit_time_ms))
    paths = [wal_dir / f"{day}.jsonl" for day in sorted(wanted_dates)]
    return [path for path in paths if path.exists()]


def _pick(source: dict[str, Any], *keys: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            out[key] = value
    return out


def _listify_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if value in (None, ""):
        return []
    return [str(value)]


def _compact_event(obj: dict[str, Any]) -> dict[str, Any]:
    pld = obj.get("pld") if isinstance(obj.get("pld"), dict) else {}
    verb = _norm_verb(obj.get("verb"))
    ts_ms = _event_ts_ms(obj)
    reduced: dict[str, Any] = {
        "verb": verb,
        "ts_ms": ts_ms,
        "ts_utc": _fmt_utc(ts_ms),
        "top_rid": obj.get("rid"),
        "logical_rid": pld.get("rid") if isinstance(pld.get("rid"), str) else None,
        "why": obj.get("why"),
        "data_ref": _listify_strings(obj.get("data_ref")),
        "anchor_tokens": sorted(_extract_tokens(obj)),
    }
    if verb == "TRADE_INTENT_PROPOSED":
        trace = pld.get("trace") if isinstance(pld.get("trace"), dict) else {}
        anti_peak = trace.get("anti_peak_observability") if isinstance(
            trace.get("anti_peak_observability"), dict) else {}
        reduced["pld"] = {
            **_pick(
                pld,
                "instrument",
                "symbol",
                "side",
                "strategy",
                "regime",
                "regime_confidence",
                "regime_epoch_ref",
                "stop_price",
                "target_price",
                "idempotent_key",
                "authority_context",
            ),
            "order": pld.get("order"),
            "why": _listify_strings(pld.get("why")),
            "regime_reason_summary": (((pld.get("regime_provenance") or {}).get("detector_event") or {}).get("reason_summary")),
            "trace": {
                **_pick(
                    trace,
                    "signal_score",
                    "decision_score",
                    "final_score",
                    "final_score_raw",
                    "active_threshold",
                    "spread_bps",
                    "liquidity_kappa",
                    "absorption",
                    "aurora_threshold_factor",
                    "aurora_pillar_confidence_candidate",
                    "aurora_raw_score_to_threshold_ratio",
                    "features_ts_ms",
                ),
                "motion": ((anti_peak.get("motion") or {}) if isinstance(anti_peak.get("motion"), dict) else {}),
                "score_path": ((anti_peak.get("score_path") or {}) if isinstance(anti_peak.get("score_path"), dict) else {}),
            },
        }
    elif verb == "OPEN":
        reduced["pld"] = {
            **_pick(
                pld,
                "symbol",
                "side",
                "qty",
                "order_type",
                "tif",
                "price",
                "valid_for_ms",
                "stop_price",
                "target_price",
                "regime",
                "regime_confidence",
                "regime_epoch_ref",
                "idempotent_key",
            ),
            "regime_reason_summary": (((pld.get("regime_provenance") or {}).get("detector_event") or {}).get("reason_summary")),
        }
    elif verb == "ORDER_PLACED":
        reduced["pld"] = _pick(
            pld,
            "symbol",
            "side",
            "qty",
            "order_type",
            "client_order_id",
            "exchange_order_id",
            "order_id",
            "ts_ms",
            "corr_id",
            "regime",
            "regime_confidence",
        )
    elif verb == "PENDING_BRACKETS_STORED":
        reduced["pld"] = _pick(
            pld,
            "entry_order_id",
            "entry_client_order_id",
            "symbol",
            "side",
            "sl",
            "tp",
            "qty",
            "rid",
            "idem_key",
            "corr_id",
            "oco_group_id",
            "strategy_id",
            "placement_path",
        )
    elif verb in FILL_VERBS:
        reduced["pld"] = _pick(
            pld,
            "symbol",
            "side",
            "quantity",
            "qty",
            "price",
            "ts_ms",
            "fees",
            "commission",
            "commissionAsset",
            "venue",
            "rid",
            "idempotent_key",
            "cumulative_qty",
            "clientOrderId",
            "client_order_id",
            "order_type",
            "status",
            "trade_id",
            "tradeId",
            "fill_trade_id",
            "exchangeOrderId",
            "exchange_order_id",
            "orderId",
            "order_id",
            "realizedPnl",
            "close_reason",
            "bracket_role",
            "tracked_bracket_order_id",
        )
    elif verb in {"CANCEL_ORDER", "POSITION_CLOSED", "PENDING_BRACKETS_CLEARED", "ORDER_REJECTED", "ORDER_CANCELLED", "ORDER_TIMEOUT", "CLOSE", "CLOSE_ORDER"}:
        reduced["pld"] = pld
    else:
        reduced["pld"] = pld
    return reduced


def _event_pld(event: dict[str, Any]) -> dict[str, Any]:
    pld = event.get("pld")
    return pld if isinstance(pld, dict) else {}


def _event_tokens(event: dict[str, Any]) -> set[str]:
    return set(event.get("anchor_tokens") or [])


def _event_matches_anchor(event: dict[str, Any], *tokens: str) -> bool:
    event_tokens = _event_tokens(event)
    return any(token and token in event_tokens for token in tokens)


def _fill_identity(event: dict[str, Any]) -> tuple[Any, ...] | None:
    pld = _event_pld(event)
    trade_id = _norm_token(pld.get("trade_id") or pld.get(
        "tradeId") or pld.get("fill_trade_id"))
    if trade_id:
        return (trade_id,)
    if not any(key in pld for key in ("fees", "commission", "realizedPnl", "commissionAsset")):
        return None
    return (
        _norm_token(pld.get("order_id") or pld.get("orderId") or pld.get(
            "exchange_order_id") or pld.get("exchangeOrderId")),
        _norm_token(pld.get("client_order_id") or pld.get("clientOrderId")),
        _norm_token(pld.get("side")),
        _norm_token(pld.get("price")),
        _norm_token(pld.get("quantity") or pld.get("qty")),
        event.get("ts_ms"),
    )


def _dedupe_fill_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for event in sorted(events, key=lambda item: (item.get("ts_ms") or 0, json.dumps(item.get("pld") or {}, sort_keys=True))):
        identity = _fill_identity(event)
        if identity is None or identity in seen:
            continue
        seen.add(identity)
        out.append(event)
    return out


def _price(event: dict[str, Any]) -> float | None:
    return _safe_float(_event_pld(event).get("price"))


def _quantity(event: dict[str, Any]) -> float | None:
    pld = _event_pld(event)
    return _safe_float(pld.get("quantity") if pld.get("quantity") is not None else pld.get("qty"))


def _vwap(events: list[dict[str, Any]]) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for event in events:
        price = _price(event)
        quantity = _quantity(event)
        if price is None or quantity is None:
            continue
        numerator += price * quantity
        denominator += quantity
    if denominator <= 0:
        return None
    return numerator / denominator


def _sum_numeric(events: list[dict[str, Any]], *keys: str) -> float | None:
    total = 0.0
    seen_any = False
    for event in events:
        pld = _event_pld(event)
        value = None
        for key in keys:
            if key in pld:
                value = _safe_float(pld.get(key))
                if value is not None:
                    break
        if value is None:
            continue
        total += value
        seen_any = True
    return total if seen_any else None


def _first_non_empty(events: list[dict[str, Any]], *paths: tuple[str, ...]) -> Any:
    for event in events:
        for path in paths:
            current: Any = event
            found = True
            for key in path:
                if not isinstance(current, dict) or key not in current:
                    found = False
                    break
                current = current[key]
            if found and current not in (None, "", [], {}):
                return current
    return None


def _flatten_list(value: Any) -> str:
    if isinstance(value, list):
        return " | ".join(str(item) for item in value if item not in (None, ""))
    if value in (None, ""):
        return ""
    return str(value)


def _compact_close_decision(event: dict[str, Any]) -> str:
    verb = event.get("verb") or ""
    why = event.get("why") or ""
    data_ref = _flatten_list(event.get("data_ref"))
    parts = [str(verb)]
    if why:
        parts.append(str(why))
    if data_ref:
        parts.append(data_ref)
    return " :: ".join(part for part in parts if part)


def _build_trade_summary(trade: AnchorTrade) -> dict[str, Any]:
    events = sorted(trade.evidence_events, key=lambda event: (
        event.get("ts_ms") or 0, str(event.get("verb") or "")))
    trade_intents = [event for event in events if event.get(
        "verb") == "TRADE_INTENT_PROPOSED"]
    opens = [event for event in events if event.get("verb") == "OPEN"]
    order_placed = [event for event in events if event.get("verb") == "ORDER_PLACED" and _event_matches_anchor(
        event, trade.entry_order_id, trade.entry_client_order_id)]
    bracket_events = [event for event in events if event.get("verb") == "PENDING_BRACKETS_STORED" and _event_matches_anchor(
        event, trade.entry_order_id, trade.entry_client_order_id)]
    clear_events = [event for event in events if event.get(
        "verb") == "PENDING_BRACKETS_CLEARED" and _event_matches_anchor(event, trade.entry_order_id)]
    fill_events = [event for event in events if event.get(
        "verb") in FILL_VERBS]
    entry_fills = _dedupe_fill_events([event for event in fill_events if _event_matches_anchor(
        event, trade.entry_order_id, trade.entry_client_order_id)])
    close_fills = _dedupe_fill_events([event for event in fill_events if _event_matches_anchor(
        event, trade.exit_order_id, trade.exit_client_order_id)])
    close_decisions = [
        event
        for event in events
        if event.get("verb") in {"CLOSE", "CLOSE_ORDER", "CANCEL_ORDER", "POSITION_CLOSED"}
        and (
            _event_matches_anchor(event, trade.exit_order_id,
                                  trade.exit_client_order_id)
            or (trade.close_rid and ((_norm_token(event.get("logical_rid")) == trade.close_rid) or (_norm_token(event.get("top_rid")) == trade.close_rid)))
        )
    ]

    trade_intent = trade_intents[0] if trade_intents else None
    open_event = opens[0] if opens else None
    order_placed_event = order_placed[0] if order_placed else None
    bracket_event = bracket_events[0] if bracket_events else None
    open_side_matched = bool(
        trade_intent or open_event or order_placed_event or bracket_event or entry_fills)
    close_side_matched = bool(close_fills or close_decisions)

    trace = (((_event_pld(trade_intent or {}).get("trace") or {})
             if trade_intent else {}) if trade_intent else {})
    motion = (((trace.get("motion") or {}) if isinstance(
        trace.get("motion"), dict) else {}) if trace else {})
    score_path = (((trace.get("score_path") or {}) if isinstance(
        trace.get("score_path"), dict) else {}) if trace else {})
    regime_reason_summary = _first_non_empty(
        [trade_intent] if trade_intent else [],
        ("pld", "regime_reason_summary"),
    ) or _first_non_empty([open_event] if open_event else [], ("pld", "regime_reason_summary"))

    entry_fill_qty_sum = _sum_numeric(entry_fills, "quantity", "qty")
    close_fill_qty_sum = _sum_numeric(close_fills, "quantity", "qty")
    entry_fill_vwap = _vwap(entry_fills)
    close_fill_vwap = _vwap(close_fills)
    close_realized_pnl_sum = _sum_numeric(close_fills, "realizedPnl")
    close_reason_from_wal = _first_non_empty(
        close_fills, ("pld", "close_reason"), ("pld", "bracket_role"))
    close_order_type = _first_non_empty(close_fills, ("pld", "order_type"))
    close_decision_text = " | ".join(
        _compact_close_decision(event) for event in close_decisions)
    notes: list[str] = []
    if not trade_intent:
        notes.append("No TRADE_INTENT_PROPOSED event matched by open rid.")
    if not open_event:
        notes.append("No OPEN decision event matched by open rid.")
    if not order_placed_event:
        notes.append("No ORDER_PLACED event matched entry anchors.")
    if not close_fills:
        notes.append("No close-side fill event matched exit anchors.")
    if close_fills and trade.exit_client_order_id.startswith("CLOSE-") and not close_decisions:
        notes.append(
            "Close market fill matched exit anchors, but no explicit CLOSE/CLOSE_ORDER decision event was found in archived WAL.")
    if bracket_event and str(close_reason_from_wal) in {"TP", "SL"}:
        notes.append(
            "Close authority is precommitted by PENDING_BRACKETS_STORED and realized by bracket terminal fill.")
    if entry_fill_qty_sum is not None and abs(entry_fill_qty_sum - trade.episode_qty_sum) > 1e-9:
        notes.append(
            "Entry fill quantity exceeds exit-sliced audit quantity; this anchor shares an opening lifecycle with one or more other exit groups.")

    if close_fills and bracket_event and str(close_reason_from_wal) in {"TP", "SL"}:
        close_authority_class = f"PRECOMMITTED_BRACKET_{close_reason_from_wal}"
    elif close_fills and trade.exit_client_order_id.startswith("CLOSE-"):
        close_authority_class = "CLOSE_MARKET_WITH_DECISION_EVENT" if close_decisions else "CLOSE_MARKET_FILL_ONLY"
    elif close_decisions:
        close_authority_class = "CLOSE_DECISION_EVENT_PRESENT"
    elif close_fills:
        close_authority_class = "CLOSE_FILL_ONLY_UNCLASSIFIED"
    elif open_side_matched:
        close_authority_class = "NO_CLOSE_EVIDENCE"
    else:
        close_authority_class = "UNMATCHED"

    return {
        "trade_key": trade.key,
        "symbol": trade.symbol,
        "direction": trade.direction,
        "entry_order_id": trade.entry_order_id,
        "entry_client_order_id": trade.entry_client_order_id,
        "exit_order_id": trade.exit_order_id,
        "exit_client_order_id": trade.exit_client_order_id,
        "entry_time_utc": trade.entry_time_utc or _fmt_utc(trade.entry_time_ms),
        "exit_time_utc": trade.exit_time_utc or _fmt_utc(trade.exit_time_ms),
        "raw_episode_rows": trade.raw_episode_rows,
        "episode_qty_sum": round(trade.episode_qty_sum, 8),
        "gross_realized_pnl_sum": round(trade.gross_realized_pnl_sum, 8),
        "entry_commission_sum": round(trade.entry_commission_sum, 8),
        "exit_commission_sum": round(trade.exit_commission_sum, 8),
        "net_pnl_after_trade_fees_sum": round(trade.net_pnl_after_trade_fees_sum, 8),
        "close_reason_proven_audit": trade.close_reason_proven,
        "close_reason_inferred_audit": trade.close_reason_inferred,
        "open_rid": trade.open_rid or "",
        "close_rid": trade.close_rid or "",
        "matched": bool(events),
        "open_side_matched": open_side_matched,
        "close_side_matched": close_side_matched,
        "matched_event_count": len(events),
        "matched_anchor_verbs": sorted(trade.matched_anchor_verbs),
        "open_regime": _first_non_empty([trade_intent] if trade_intent else [], ("pld", "regime")) or _first_non_empty([open_event] if open_event else [], ("pld", "regime")) or "",
        "open_regime_confidence": _first_non_empty([trade_intent] if trade_intent else [], ("pld", "regime_confidence")) or _first_non_empty([open_event] if open_event else [], ("pld", "regime_confidence")) or "",
        "open_regime_reason_summary": regime_reason_summary or "",
        "open_decision_why": _flatten_list(_first_non_empty([trade_intent] if trade_intent else [], ("pld", "why")) or _first_non_empty([open_event] if open_event else [], ("data_ref",)) or _first_non_empty([open_event] if open_event else [], ("why",))),
        "signal_score": _first_non_empty([trade_intent] if trade_intent else [], ("pld", "trace", "signal_score")) or "",
        "signal_threshold": _first_non_empty([trade_intent] if trade_intent else [], ("pld", "trace", "active_threshold")) or _first_non_empty([trade_intent] if trade_intent else [], ("pld", "trace", "score_path", "signal_threshold")) or "",
        "spread_bps": _first_non_empty([trade_intent] if trade_intent else [], ("pld", "trace", "spread_bps")) or "",
        "liquidity_kappa": _first_non_empty([trade_intent] if trade_intent else [], ("pld", "trace", "liquidity_kappa")) or "",
        "absorption": _first_non_empty([trade_intent] if trade_intent else [], ("pld", "trace", "absorption")) or "",
        "motion_norm_sigma": motion.get("motion_norm_sigma", "") if isinstance(motion, dict) else "",
        "anti_flat_triggered": motion.get("anti_flat_triggered", "") if isinstance(motion, dict) else "",
        "anti_fomo_triggered": motion.get("anti_fomo_triggered", "") if isinstance(motion, dict) else "",
        "authority_mode": _first_non_empty([trade_intent] if trade_intent else [], ("pld", "authority_context", "authority_mode")) or "",
        "authority_apply_result": _first_non_empty([trade_intent] if trade_intent else [], ("pld", "authority_context", "apply_result")) or "",
        "entry_order_placed_utc": order_placed_event.get("ts_utc", "") if order_placed_event else "",
        "entry_order_corr_id": _first_non_empty([order_placed_event] if order_placed_event else [], ("pld", "corr_id")) or "",
        "bracket_sl": _first_non_empty([bracket_event] if bracket_event else [], ("pld", "sl")) or "",
        "bracket_tp": _first_non_empty([bracket_event] if bracket_event else [], ("pld", "tp")) or "",
        "bracket_placement_path": _first_non_empty([bracket_event] if bracket_event else [], ("pld", "placement_path")) or "",
        "entry_fill_count": len(entry_fills),
        "entry_fill_qty_sum": round(entry_fill_qty_sum, 8) if entry_fill_qty_sum is not None else "",
        "entry_fill_vwap": round(entry_fill_vwap, 8) if entry_fill_vwap is not None else "",
        "entry_fill_first_utc": entry_fills[0].get("ts_utc", "") if entry_fills else "",
        "entry_fill_last_utc": entry_fills[-1].get("ts_utc", "") if entry_fills else "",
        "close_fill_count": len(close_fills),
        "close_fill_qty_sum": round(close_fill_qty_sum, 8) if close_fill_qty_sum is not None else "",
        "close_fill_vwap": round(close_fill_vwap, 8) if close_fill_vwap is not None else "",
        "close_fill_first_utc": close_fills[0].get("ts_utc", "") if close_fills else "",
        "close_fill_last_utc": close_fills[-1].get("ts_utc", "") if close_fills else "",
        "close_realized_pnl_sum_wal": round(close_realized_pnl_sum, 8) if close_realized_pnl_sum is not None else "",
        "close_reason_from_wal": close_reason_from_wal or "",
        "close_order_type": close_order_type or "",
        "close_authority_class": close_authority_class,
        "close_decision_event_count": len(close_decisions),
        "close_decision_events": [event.get("verb") for event in close_decisions],
        "close_decision_why": close_decision_text,
        "clear_events": [event.get("why") for event in clear_events],
        "notes": notes,
        "evidence": {
            "trade_intent_proposed": trade_intent,
            "open": open_event,
            "order_placed": order_placed_event,
            "pending_brackets_stored": bracket_event,
            "entry_fills": entry_fills,
            "close_decisions": close_decisions,
            "close_fills": close_fills,
            "pending_brackets_cleared": clear_events,
        },
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    flat_rows: list[dict[str, Any]] = []
    for row in rows:
        flat_row = {key: value for key, value in row.items() if key !=
                    "evidence"}
        flat_row["matched_anchor_verbs"] = " | ".join(
            flat_row.get("matched_anchor_verbs") or [])
        flat_row["close_decision_events"] = " | ".join(
            flat_row.get("close_decision_events") or [])
        flat_row["clear_events"] = " | ".join(
            flat_row.get("clear_events") or [])
        flat_row["notes"] = " | ".join(flat_row.get("notes") or [])
        flat_rows.append(flat_row)
    fieldnames: list[str] = []
    for row in flat_rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in flat_rows:
            writer.writerow(row)


def _build_markdown(
    rows: list[dict[str, Any]],
    *,
    raw_episode_rows: int,
    wal_paths: list[Path],
    episodes_csv: Path,
    wal_dir: Path,
) -> str:
    matched = sum(1 for row in rows if row.get("matched"))
    unmatched = len(rows) - matched
    by_symbol = Counter(row.get("symbol") for row in rows)
    lines: list[str] = []
    lines.append("# Testnet Audit Episodes Joined To Archived WAL")
    lines.append("")
    lines.append("## Scope")
    lines.append(f"- Audit source: {episodes_csv}")
    lines.append(f"- Archived WAL source: {wal_dir}")
    lines.append(f"- Raw CLOSED episode rows: {raw_episode_rows}")
    lines.append(f"- Unique entry/exit anchor groups: {len(rows)}")
    lines.append(f"- Matched groups: {matched}")
    lines.append(f"- Unmatched groups: {unmatched}")
    lines.append(f"- WAL files scanned: {len(wal_paths)}")
    lines.append("")
    lines.append("## Symbol Counts")
    for symbol, count in sorted(by_symbol.items()):
        lines.append(f"- {symbol}: {count}")
    lines.append("")
    lines.append("## Match Table")
    lines.append("")
    lines.append(
        "| Symbol | Entry Order | Exit Order | Open Regime | Score / Threshold | Close Authority | Close Reason | Net PnL | Match |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | ---: | --- |")
    for row in rows:
        score = row.get("signal_score")
        threshold = row.get("signal_threshold")
        score_text = ""
        if score not in (None, "") or threshold not in (None, ""):
            score_text = f"{score} / {threshold}"
        lines.append(
            "| {symbol} | {entry_order_id} | {exit_order_id} | {open_regime} | {score_text} | {close_authority_class} | {close_reason} | {net_pnl} | {matched} |".format(
                symbol=row.get("symbol", ""),
                entry_order_id=row.get("entry_order_id", ""),
                exit_order_id=row.get("exit_order_id", ""),
                open_regime=row.get("open_regime", ""),
                score_text=score_text,
                close_authority_class=row.get("close_authority_class", ""),
                close_reason=row.get("close_reason_from_wal") or row.get(
                    "close_reason_proven_audit") or "",
                net_pnl=row.get("net_pnl_after_trade_fees_sum", ""),
                matched="YES" if row.get("matched") else "NO",
            )
        )
    if unmatched:
        lines.append("")
        lines.append("## Unmatched Groups")
        for row in rows:
            if row.get("matched"):
                continue
            lines.append(
                "- {symbol} entry={entry_order_id} exit={exit_order_id} entry_client={entry_client_order_id} exit_client={exit_client_order_id}".format(
                    symbol=row.get("symbol", ""),
                    entry_order_id=row.get("entry_order_id", ""),
                    exit_order_id=row.get("exit_order_id", ""),
                    entry_client_order_id=row.get("entry_client_order_id", ""),
                    exit_client_order_id=row.get("exit_client_order_id", ""),
                )
            )
    lines.append("")
    lines.append("## Notes")
    lines.append(
        "- Entry-side decision evidence is shared when multiple exit groups map back to the same opening lifecycle.")
    lines.append("- Exit-side evidence is matched by exit order/client IDs first; this avoids leaking one close fill into sibling exit groups that share the same open RID.")
    lines.append("- `CLOSE_MARKET_FILL_ONLY` means the archived WAL preserved the terminal fill but did not expose a separate close decision event in the scanned slice.")
    lines.append("- Full event excerpts live in the JSON output.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Join testnet audit episode anchors to archived WAL evidence")
    parser.add_argument("--episodes-csv", type=Path,
                        default=DEFAULT_EPISODES_CSV)
    parser.add_argument("--wal-dir", type=Path, default=DEFAULT_WAL_DIR)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--max-groups", type=int, default=None)
    parser.add_argument("--out-json", type=Path,
                        default=DEFAULT_OUT_DIR / "anchor_trade_join.json")
    parser.add_argument("--out-csv", type=Path,
                        default=DEFAULT_OUT_DIR / "anchor_trade_join.csv")
    parser.add_argument("--out-md", type=Path,
                        default=DEFAULT_OUT_DIR / "anchor_trade_join.md")
    args = parser.parse_args()

    if not args.episodes_csv.exists():
        raise SystemExit(f"Episodes CSV not found: {args.episodes_csv}")
    if not args.wal_dir.exists():
        raise SystemExit(f"Archived WAL directory not found: {args.wal_dir}")

    symbols_filter = set(args.symbols or []) if args.symbols else None
    trades, raw_episode_rows = _load_anchor_trades(
        args.episodes_csv, symbols_filter)
    if args.max_groups is not None:
        trades = trades[: args.max_groups]
    if not trades:
        raise SystemExit(
            "No CLOSED episode anchors found for the requested filter.")

    wal_paths = _wal_paths_for_trades(args.wal_dir, trades)
    if not wal_paths:
        raise SystemExit(
            "No archived WAL files found for the requested episode window.")

    trades_by_key = {trade.key: trade for trade in trades}
    anchor_lookup: dict[str, dict[str, list[str]]
                        ] = defaultdict(lambda: defaultdict(list))
    open_rid_lookup: dict[str, dict[str, list[str]]
                          ] = defaultdict(lambda: defaultdict(list))
    close_rid_lookup: dict[str, dict[str, list[str]]
                           ] = defaultdict(lambda: defaultdict(list))
    known_symbols = {trade.symbol for trade in trades}

    for trade in trades:
        for token in (trade.entry_order_id, trade.entry_client_order_id, trade.exit_order_id, trade.exit_client_order_id):
            if token:
                anchor_lookup[trade.symbol][token].append(trade.key)

    for obj in _iter_jsonl(wal_paths):
        symbol = _extract_symbol(obj)
        if symbol not in known_symbols:
            continue
        tokens = _extract_tokens(obj)
        if not tokens:
            continue
        verb = _norm_verb(obj.get("verb"))
        logical_rid = _prefer_logical_rid(_candidate_rids(obj), symbol)
        matched_keys: set[str] = set()
        for token in tokens:
            matched_keys.update(anchor_lookup[symbol].get(token, []))
        for key in matched_keys:
            trade = trades_by_key[key]
            trade.matched_anchor_verbs.add(verb)
            if trade.entry_order_id in tokens or trade.entry_client_order_id in tokens:
                if logical_rid and (trade.open_rid is None or (symbol in logical_rid and symbol not in (trade.open_rid or ""))):
                    trade.open_rid = logical_rid
            if trade.exit_order_id in tokens or trade.exit_client_order_id in tokens:
                if logical_rid and trade.close_rid is None:
                    trade.close_rid = logical_rid
                if logical_rid and trade.open_rid and logical_rid.startswith(trade.open_rid + ":"):
                    trade.close_rid = logical_rid

    for trade in trades:
        if trade.open_rid:
            open_rid_lookup[trade.symbol][trade.open_rid].append(trade.key)
        if trade.close_rid:
            close_rid_lookup[trade.symbol][trade.close_rid].append(trade.key)

    for obj in _iter_jsonl(wal_paths):
        symbol = _extract_symbol(obj)
        if symbol not in known_symbols:
            continue
        verb = _norm_verb(obj.get("verb"))
        if verb not in INTERESTING_VERBS:
            continue
        matched_keys: set[str] = set()
        tokens = _extract_tokens(obj)
        for token in tokens:
            matched_keys.update(anchor_lookup[symbol].get(token, []))

        logical_rid = _prefer_logical_rid(_candidate_rids(obj), symbol)
        if logical_rid and verb in OPEN_SHARED_VERBS:
            matched_keys.update(open_rid_lookup[symbol].get(logical_rid, []))
        if logical_rid and verb in CLOSE_SHARED_VERBS:
            matched_keys.update(close_rid_lookup[symbol].get(logical_rid, []))

        if not matched_keys:
            continue

        compact = _compact_event(obj)
        for key in matched_keys:
            trades_by_key[key].evidence_events.append(compact)

    rows = [_build_trade_summary(trade) for trade in trades]
    open_rid_counts = Counter(row.get("open_rid")
                              for row in rows if row.get("open_rid"))
    for row in rows:
        row["shared_open_group_count"] = open_rid_counts.get(
            row.get("open_rid"), 0) if row.get("open_rid") else 0

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "episodes_csv": str(args.episodes_csv),
        "wal_dir": str(args.wal_dir),
        "raw_closed_episode_rows": raw_episode_rows,
        "anchor_groups": len(rows),
        "matched_groups": sum(1 for row in rows if row.get("matched")),
        "unmatched_groups": sum(1 for row in rows if not row.get("matched")),
        "wal_files_scanned": [str(path) for path in wal_paths],
        "rows": rows,
    }
    with args.out_json.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    _write_csv(args.out_csv, rows)
    args.out_md.write_text(
        _build_markdown(
            rows,
            raw_episode_rows=raw_episode_rows,
            wal_paths=wal_paths,
            episodes_csv=args.episodes_csv,
            wal_dir=args.wal_dir,
        ),
        encoding="utf-8",
    )

    print(f"raw_closed_episode_rows={raw_episode_rows}")
    print(f"anchor_groups={len(rows)}")
    print(f"matched_groups={sum(1 for row in rows if row.get('matched'))}")
    print(
        f"unmatched_groups={sum(1 for row in rows if not row.get('matched'))}")
    print(f"out_json={args.out_json}")
    print(f"out_csv={args.out_csv}")
    print(f"out_md={args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
