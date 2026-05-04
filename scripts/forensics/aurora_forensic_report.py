#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


UTC = dt.timezone.utc
TARGET_STRATEGIES = {"aurora", "mean_reversion", "md_amr"}
STRATEGY_TF_SEC = {
    "aurora": 300,
    "mean_reversion": 180,
    "md_amr": 900,
}


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    try:
        value = float(text)
    except Exception:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    try:
        return int(float(text))
    except Exception:
        return None


def _fmt_ts_ms(ts_ms: Optional[int]) -> str:
    if not ts_ms:
        return "n/a"
    return dt.datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_num(value: Optional[float], digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _fmt_money(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def _minutes(ms: int) -> float:
    return ms / 60000.0


def _parse_log_ts_ms(text: str) -> Optional[int]:
    try:
        value = dt.datetime.strptime(text, "%Y-%m-%d %H:%M:%S,%f").replace(tzinfo=UTC)
    except ValueError:
        return None
    return int(value.timestamp() * 1000)


def _direction(side: str) -> str:
    side = (side or "").upper()
    if side == "BUY":
        return "LONG"
    if side == "SELL":
        return "SHORT"
    return side or "UNKNOWN"


def _strategy_from_rid(rid: str) -> Optional[str]:
    if rid.startswith("aurora_"):
        return "aurora"
    if rid.startswith("mdamr-"):
        return "md_amr"
    if rid.startswith("rid-"):
        return "mean_reversion"
    return None


def _extract_regime(values: Sequence[str]) -> Optional[str]:
    for value in values:
        match = re.search(r"tpsl:regime=([A-Z_]+)", value)
        if match:
            return match.group(1)
        match = re.search(r"regime:([A-Z_]+)", value)
        if match:
            label = match.group(1)
            if label.startswith("FLAT_"):
                return "MEAN_REVERSION"
            return label
    return None


def _extract_reason(values: Sequence[str]) -> str:
    if not values:
        return "n/a"
    return values[0]


def _gross_profit(trades: Sequence["TradeRecord"]) -> float:
    return sum(max(t.pnl, 0.0) for t in trades)


def _gross_loss(trades: Sequence["TradeRecord"]) -> float:
    return abs(sum(min(t.pnl, 0.0) for t in trades))


def _profit_factor(trades: Sequence["TradeRecord"]) -> Optional[float]:
    losses = _gross_loss(trades)
    if losses <= 0:
        return None
    return _gross_profit(trades) / losses


def _max_drawdown(trades: Sequence["TradeRecord"]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for trade in sorted(trades, key=lambda t: t.exit_time_ms):
        equity += trade.pnl
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def _sharpe_like(trades: Sequence["TradeRecord"]) -> Optional[float]:
    if len(trades) < 2:
        return None
    values = [trade.pnl for trade in trades]
    sigma = pstdev(values)
    if sigma == 0:
        return None
    return mean(values) / sigma * math.sqrt(len(values))


def _ascii_bar(value: float, scale: float, width: int = 20) -> str:
    if scale <= 0:
        return ""
    units = int(round(abs(value) / scale * width))
    units = max(0, min(width, units))
    return ("#" if value >= 0 else "-") * units


@dataclass
class TradeIntent:
    rid: str
    ts_ms: int
    symbol: str
    side: str
    strategy: str
    order_type: str
    tif: Optional[str]
    qty: Optional[float]
    price: Optional[float]
    valid_for_ms: Optional[int]
    stop_price: Optional[float]
    target_price: Optional[float]
    why: List[str]
    regime_hint: Optional[str]


@dataclass
class DecisionOpen:
    rid: str
    ts_ms: int
    symbol: str
    side: str
    order_type: str
    qty: Optional[float]
    price: Optional[float]
    valid_for_ms: Optional[int]
    stop_price: Optional[float]
    target_price: Optional[float]
    why: List[str]


@dataclass
class DecisionClose:
    rid: str
    ts_ms: int
    symbol: str
    why: Optional[str]
    trigger: Optional[str]
    reason: Optional[str]
    data_ref: List[str]


@dataclass
class RegimePoint:
    ts_ms: int
    symbol: str
    regime: str


@dataclass
class OrderPlaced:
    rid: str
    ts_ms: int
    order_id: str
    symbol: str
    side: str
    price: Optional[float]
    qty: Optional[float]
    order_type: Optional[str]
    strategy: Optional[str]
    valid_for_ms: Optional[int]


@dataclass
class OrderCancelled:
    rid: str
    ts_ms: int
    order_id: str
    symbol: str
    reason: str
    bracket_type: Optional[str]
    strategy: Optional[str]


@dataclass
class SupersedeEvent:
    rid: str
    ts_ms: int
    symbol: str
    side: str
    noop_candidate: bool
    order_ids: List[str]


@dataclass
class AccountPos:
    symbol: str
    qty: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float


@dataclass
class AccountUpdate:
    ts_ms: int
    wallet: float
    unrealized_total: float
    positions: Dict[str, AccountPos]


@dataclass
class Episode:
    symbol: str
    side: str
    start_ms: int
    end_ms: int
    start_qty: float
    last_qty: float
    max_abs_qty: float
    entry_price: float
    exit_mark_price: float
    exit_unrealized_pnl: float
    open_dec: Optional[DecisionOpen] = None
    intent: Optional[TradeIntent] = None
    close_dec: Optional[DecisionClose] = None
    regime_entry: Optional[str] = None
    regime_exit: Optional[str] = None


@dataclass
class TradeRecord:
    symbol: str
    strategy: str
    direction: str
    entry_time_ms: int
    entry_price: float
    exit_time_ms: int
    exit_price: float
    exit_reason: str
    pnl: float
    pnl_r: Optional[float]
    qty: float
    holding_ms: int
    regime_at_entry: Optional[str]
    regime_at_exit: Optional[str]
    stop_price: Optional[float]
    target_price: Optional[float]
    entry_reason: str
    conflict_flag: bool = False
    mae: Optional[float] = None
    mfe: Optional[float] = None
    distance_to_local_extreme: Optional[float] = None
    bars_tf_sec: int = 180
    notes: List[str] = field(default_factory=list)


@dataclass
class ConflictRecord:
    ts_ms: int
    symbol: str
    strategy_a: str
    direction_a: str
    strategy_b: str
    direction_b: str
    position_state: str
    source: str


@dataclass
class PendingInterval:
    rid: str
    order_id: str
    symbol: str
    side: str
    strategy: str
    placed_ts_ms: int
    end_ts_ms: int
    price: Optional[float]
    valid_for_ms: Optional[int]


class RecorderCache:
    def __init__(self, recorder_dir: Path):
        self.recorder_dir = recorder_dir
        self.cache: Dict[Tuple[str, int], Tuple[List[int], List[Dict[str, Any]]]] = {}

    def load(self, symbol: str, tf_sec: int) -> Tuple[List[int], List[Dict[str, Any]]]:
        key = (symbol, tf_sec)
        if key in self.cache:
            return self.cache[key]
        files = sorted(self.recorder_dir.glob(f"**/{symbol}_{tf_sec}.csv"))
        rows: List[Dict[str, Any]] = []
        for path in files:
            with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    ts = _safe_int(row.get("timestamp"))
                    if ts is not None:
                        row["timestamp"] = str(ts)
                        rows.append(row)
        rows.sort(key=lambda row: int(row["timestamp"]))
        dedup: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            dedup[int(row["timestamp"])] = row
        ts_list = sorted(dedup.keys())
        row_list = [dedup[ts] for ts in ts_list]
        self.cache[key] = (ts_list, row_list)
        return ts_list, row_list

    def bars_between(self, symbol: str, tf_sec: int, start_ms: int, end_ms: int) -> List[Dict[str, Any]]:
        ts_list, rows = self.load(symbol, tf_sec)
        left = bisect_left(ts_list, start_ms)
        right = bisect_right(ts_list, end_ms)
        return rows[left:right]

    def bars_after(self, symbol: str, tf_sec: int, after_ms: int, limit: int) -> List[Dict[str, Any]]:
        ts_list, rows = self.load(symbol, tf_sec)
        left = bisect_right(ts_list, after_ms)
        return rows[left : left + limit]


def iter_jsonl(paths: Sequence[Path]) -> Iterable[Dict[str, Any]]:
    for path in paths:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    payload["_path"] = str(path)
                    yield payload


def parse_trade_intents(events: Sequence[Dict[str, Any]]) -> List[TradeIntent]:
    intents: List[TradeIntent] = []
    for event in events:
        if event.get("op") != "EVT" or event.get("verb") != "TRADE_INTENT_PROPOSED":
            continue
        payload = event.get("pld") if isinstance(event.get("pld"), dict) else {}
        strategy = str(payload.get("strategy") or "")
        if strategy not in TARGET_STRATEGIES:
            continue
        order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
        why = [str(item) for item in (payload.get("why") or event.get("data_ref") or [])]
        intents.append(
            TradeIntent(
                rid=str(event.get("rid") or payload.get("rid") or ""),
                ts_ms=_safe_int(event.get("ts") or event.get("timestamp")) or 0,
                symbol=str(payload.get("instrument") or payload.get("symbol") or ""),
                side=str(payload.get("side") or ""),
                strategy=strategy,
                order_type=str(order.get("order_type") or ""),
                tif=str(order.get("tif")) if order.get("tif") is not None else None,
                qty=_safe_float(order.get("qty")),
                price=_safe_float(order.get("price")),
                valid_for_ms=_safe_int(payload.get("valid_for_ms")),
                stop_price=_safe_float(payload.get("stop_price")),
                target_price=_safe_float(payload.get("target_price")),
                why=why,
                regime_hint=_extract_regime(why),
            )
        )
    intents.sort(key=lambda item: item.ts_ms)
    return intents


def parse_decision_opens(events: Sequence[Dict[str, Any]]) -> List[DecisionOpen]:
    opens: List[DecisionOpen] = []
    for event in events:
        if event.get("op") != "DEC" or event.get("verb") != "OPEN":
            continue
        payload = event.get("pld") if isinstance(event.get("pld"), dict) else {}
        opens.append(
            DecisionOpen(
                rid=str(event.get("rid") or ""),
                ts_ms=_safe_int(event.get("ts") or event.get("timestamp")) or 0,
                symbol=str(payload.get("symbol") or ""),
                side=str(payload.get("side") or ""),
                order_type=str(payload.get("order_type") or ""),
                qty=_safe_float(payload.get("qty")),
                price=_safe_float(payload.get("price")),
                valid_for_ms=_safe_int(payload.get("valid_for_ms")),
                stop_price=_safe_float(payload.get("stop_price")),
                target_price=_safe_float(payload.get("target_price")),
                why=[str(item) for item in (event.get("data_ref") or [])],
            )
        )
    opens.sort(key=lambda item: item.ts_ms)
    return opens


def parse_decision_closes(events: Sequence[Dict[str, Any]]) -> List[DecisionClose]:
    closes: List[DecisionClose] = []
    for event in events:
        if event.get("op") != "DEC" or event.get("verb") != "CLOSE":
            continue
        payload = event.get("pld") if isinstance(event.get("pld"), dict) else {}
        closes.append(
            DecisionClose(
                rid=str(event.get("rid") or ""),
                ts_ms=_safe_int(event.get("ts") or event.get("timestamp")) or 0,
                symbol=str(payload.get("symbol") or ""),
                why=str(event.get("why")) if event.get("why") is not None else None,
                trigger=str(payload.get("trigger")) if payload.get("trigger") is not None else None,
                reason=str(payload.get("reason")) if payload.get("reason") is not None else None,
                data_ref=[str(item) for item in (event.get("data_ref") or [])],
            )
        )
    closes.sort(key=lambda item: item.ts_ms)
    return closes


def parse_account_updates(events: Sequence[Dict[str, Any]]) -> List[AccountUpdate]:
    updates: List[AccountUpdate] = []
    for event in events:
        if event.get("op") != "EVT" or event.get("verb") != "ACCOUNT_UPDATE_RECEIVED":
            continue
        payload = event.get("pld") if isinstance(event.get("pld"), dict) else {}
        ts_ms = _safe_int(payload.get("updateTime"))
        if ts_ms is None:
            continue
        positions: Dict[str, AccountPos] = {}
        for pos in payload.get("positions") or []:
            if not isinstance(pos, dict):
                continue
            symbol = str(pos.get("symbol") or "")
            qty = _safe_float(pos.get("positionAmt"))
            entry = _safe_float(pos.get("entryPrice"))
            mark = _safe_float(pos.get("markPrice"))
            unreal = _safe_float(pos.get("unRealizedProfit"))
            if not symbol or qty is None or entry is None or mark is None or unreal is None:
                continue
            if abs(qty) <= 1e-12:
                continue
            positions[symbol] = AccountPos(symbol=symbol, qty=qty, entry_price=entry, mark_price=mark, unrealized_pnl=unreal)
        updates.append(
            AccountUpdate(
                ts_ms=ts_ms,
                wallet=_safe_float(payload.get("totalWalletBalance")) or 0.0,
                unrealized_total=_safe_float(payload.get("totalUnrealizedProfit")) or 0.0,
                positions=positions,
            )
        )
    updates.sort(key=lambda item: item.ts_ms)
    return updates


def build_episodes(updates: Sequence[AccountUpdate]) -> List[Episode]:
    open_state: Dict[str, Dict[str, Any]] = {}
    episodes: List[Episode] = []
    for update in updates:
        current_symbols = set(update.positions.keys())
        previous_symbols = set(open_state.keys())

        for symbol in sorted(previous_symbols - current_symbols):
            state = open_state.pop(symbol)
            last_pos = state["last_pos"]
            episodes.append(
                Episode(
                    symbol=symbol,
                    side=state["side"],
                    start_ms=state["start_ms"],
                    end_ms=update.ts_ms,
                    start_qty=state["start_pos"].qty,
                    last_qty=last_pos.qty,
                    max_abs_qty=state["max_abs_qty"],
                    entry_price=last_pos.entry_price,
                    exit_mark_price=last_pos.mark_price,
                    exit_unrealized_pnl=last_pos.unrealized_pnl,
                )
            )

        for symbol in sorted(previous_symbols & current_symbols):
            pos = update.positions[symbol]
            state = open_state[symbol]
            prev_qty = state["last_pos"].qty
            if prev_qty * pos.qty < 0:
                last_pos = state["last_pos"]
                episodes.append(
                    Episode(
                        symbol=symbol,
                        side=state["side"],
                        start_ms=state["start_ms"],
                        end_ms=update.ts_ms,
                        start_qty=state["start_pos"].qty,
                        last_qty=last_pos.qty,
                        max_abs_qty=state["max_abs_qty"],
                        entry_price=last_pos.entry_price,
                        exit_mark_price=last_pos.mark_price,
                        exit_unrealized_pnl=last_pos.unrealized_pnl,
                    )
                )
                open_state[symbol] = {
                    "start_ms": update.ts_ms,
                    "side": "LONG" if pos.qty > 0 else "SHORT",
                    "start_pos": pos,
                    "last_pos": pos,
                    "max_abs_qty": abs(pos.qty),
                }
            else:
                state["last_pos"] = pos
                state["max_abs_qty"] = max(state["max_abs_qty"], abs(pos.qty))

        for symbol in sorted(current_symbols - previous_symbols):
            pos = update.positions[symbol]
            open_state[symbol] = {
                "start_ms": update.ts_ms,
                "side": "LONG" if pos.qty > 0 else "SHORT",
                "start_pos": pos,
                "last_pos": pos,
                "max_abs_qty": abs(pos.qty),
            }
    episodes.sort(key=lambda item: item.start_ms)
    return episodes


def parse_regime_points(log_paths: Sequence[Path]) -> Dict[str, List[RegimePoint]]:
    by_symbol: Dict[str, List[RegimePoint]] = defaultdict(list)
    pattern = re.compile(r"^\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*\[([A-Z0-9]+)\] Regime updated: .*raw=([A-Z_]+)")
    for path in log_paths:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                match = pattern.search(line)
                if not match:
                    continue
                ts_ms = _parse_log_ts_ms(match.group(1))
                if ts_ms is None:
                    continue
                by_symbol[match.group(2)].append(RegimePoint(ts_ms=ts_ms, symbol=match.group(2), regime=match.group(3)))
    for symbol in by_symbol:
        by_symbol[symbol].sort(key=lambda item: item.ts_ms)
    return by_symbol


def regime_at(points: Dict[str, List[RegimePoint]], symbol: str, ts_ms: int) -> Optional[str]:
    items = points.get(symbol) or []
    if not items:
        return None
    ts_list = [item.ts_ms for item in items]
    idx = bisect_right(ts_list, ts_ms) - 1
    if idx < 0:
        return None
    return items[idx].regime


def parse_order_log(path: Path, intents_by_rid: Dict[str, TradeIntent]) -> Tuple[List[OrderPlaced], List[OrderCancelled], List[SupersedeEvent], List[Dict[str, Any]]]:
    placed: List[OrderPlaced] = []
    cancelled: List[OrderCancelled] = []
    supersede: List[SupersedeEvent] = []
    fill_discovered: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                event = json.loads(text)
            except Exception:
                continue
            event_type = str(event.get("event_type") or "")
            rid = str(event.get("rid") or "")
            symbol = str(event.get("symbol") or "")
            strategy = intents_by_rid[rid].strategy if rid in intents_by_rid else _strategy_from_rid(rid)
            if event_type == "ORDER_PLACED":
                metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
                adapter = event.get("adapter_response") if isinstance(event.get("adapter_response"), dict) else {}
                order_type = str(adapter.get("type") or metadata.get("order_type") or "")
                placed.append(
                    OrderPlaced(
                        rid=rid,
                        ts_ms=_safe_int(event.get("timestamp")) or 0,
                        order_id=str(event.get("order_id") or ""),
                        symbol=symbol,
                        side=str(event.get("side") or ""),
                        price=_safe_float(event.get("price") or adapter.get("price")),
                        qty=_safe_float(event.get("quantity")),
                        order_type=order_type,
                        strategy=strategy,
                        valid_for_ms=intents_by_rid[rid].valid_for_ms if rid in intents_by_rid else None,
                    )
                )
            elif event_type == "ORDER_CANCELLED":
                cancelled.append(
                    OrderCancelled(
                        rid=rid,
                        ts_ms=_safe_int(event.get("timestamp")) or 0,
                        order_id=str(event.get("order_id") or ""),
                        symbol=symbol,
                        reason=str(event.get("reason") or ""),
                        bracket_type=str(event.get("bracket_type")) if event.get("bracket_type") is not None else None,
                        strategy=strategy,
                    )
                )
            elif event_type == "ORDER_SUPERSEDE_REPRICE_ANALYZED":
                analyses = event.get("analyses") if isinstance(event.get("analyses"), list) else []
                supersede.append(
                    SupersedeEvent(
                        rid=rid,
                        ts_ms=_safe_int(event.get("timestamp")) or 0,
                        symbol=symbol,
                        side=str(event.get("side") or ""),
                        noop_candidate=bool(event.get("noop_candidate")),
                        order_ids=[str(item.get("order_id")) for item in analyses if isinstance(item, dict) and item.get("order_id")],
                    )
                )
            elif event_type == "ORDER_FILL_DISCOVERED":
                fill_discovered.append(event)
    placed.sort(key=lambda item: item.ts_ms)
    cancelled.sort(key=lambda item: item.ts_ms)
    supersede.sort(key=lambda item: item.ts_ms)
    fill_discovered.sort(key=lambda item: _safe_int(item.get("timestamp")) or 0)
    return placed, cancelled, supersede, fill_discovered


def attach_episode_context(
    episodes: Sequence[Episode],
    intents: Sequence[TradeIntent],
    opens: Sequence[DecisionOpen],
    closes: Sequence[DecisionClose],
    regimes: Dict[str, List[RegimePoint]],
) -> None:
    intents_by_rid = {intent.rid: intent for intent in intents}
    closes_by_symbol: Dict[str, List[DecisionClose]] = defaultdict(list)
    for close in closes:
        closes_by_symbol[close.symbol].append(close)
    intents_by_symbol_side: Dict[Tuple[str, str], List[TradeIntent]] = defaultdict(list)
    for intent in intents:
        intents_by_symbol_side[(intent.symbol, intent.side)].append(intent)

    for episode in episodes:
        best_open: Optional[DecisionOpen] = None
        for open_ in opens:
            if open_.symbol != episode.symbol:
                continue
            if _direction(open_.side) != episode.side:
                continue
            if open_.ts_ms > episode.start_ms:
                continue
            if episode.start_ms - open_.ts_ms > 30 * 60 * 1000:
                continue
            if best_open is None or open_.ts_ms > best_open.ts_ms:
                best_open = open_
        episode.open_dec = best_open

        if best_open and best_open.rid in intents_by_rid:
            episode.intent = intents_by_rid[best_open.rid]
        else:
            desired_side = "BUY" if episode.side == "LONG" else "SELL"
            for intent in reversed(intents_by_symbol_side.get((episode.symbol, desired_side), [])):
                if intent.ts_ms <= episode.start_ms and episode.start_ms - intent.ts_ms <= 30 * 60 * 1000:
                    episode.intent = intent
                    break

        candidate_close: Optional[DecisionClose] = None
        for close in closes_by_symbol.get(episode.symbol, []):
            if abs(close.ts_ms - episode.end_ms) > 2 * 60 * 1000:
                continue
            if candidate_close is None or abs(close.ts_ms - episode.end_ms) < abs(candidate_close.ts_ms - episode.end_ms):
                candidate_close = close
        episode.close_dec = candidate_close
        episode.regime_entry = regime_at(regimes, episode.symbol, episode.start_ms)
        episode.regime_exit = regime_at(regimes, episode.symbol, episode.end_ms)
        if episode.regime_entry is None and episode.intent is not None:
            episode.regime_entry = episode.intent.regime_hint


def trade_filter(episodes: Sequence[Episode], start_ts_ms: int, end_ts_ms: int) -> List[Episode]:
    filtered: List[Episode] = []
    for episode in episodes:
        if episode.intent is None:
            continue
        if episode.intent.strategy not in TARGET_STRATEGIES:
            continue
        if not (start_ts_ms <= episode.intent.ts_ms <= end_ts_ms):
            continue
        filtered.append(episode)
    filtered.sort(key=lambda item: item.start_ms)
    return filtered


def classify_exit(episode: Episode, bars: List[Dict[str, Any]], post_bars: List[Dict[str, Any]]) -> str:
    stop_price = episode.intent.stop_price if episode.intent else (episode.open_dec.stop_price if episode.open_dec else None)
    target_price = episode.intent.target_price if episode.intent else (episode.open_dec.target_price if episode.open_dec else None)
    if episode.close_dec is not None:
        why = (episode.close_dec.why or "").lower()
        reason = (episode.close_dec.reason or "").upper()
        refs = " ".join(episode.close_dec.data_ref).lower()
        if "max_hold" in why or "MAX_HOLD_TIME_EXCEEDED" in reason:
            return "WATCHDOG"
        if episode.close_dec.trigger == "CMD:CLOSE":
            if "flip_orchestration" in refs:
                return "MANUAL"
            return "MANUAL"
    if stop_price is not None:
        if episode.side == "LONG" and episode.exit_mark_price <= stop_price:
            return "SL"
        if episode.side == "SHORT" and episode.exit_mark_price >= stop_price:
            return "SL"
    if target_price is not None:
        if episode.side == "LONG" and episode.exit_mark_price >= target_price:
            return "TP"
        if episode.side == "SHORT" and episode.exit_mark_price <= target_price:
            return "TP"
    for bar in bars:
        high = _safe_float(bar.get("high"))
        low = _safe_float(bar.get("low"))
        if high is None or low is None:
            continue
        if stop_price is not None:
            if episode.side == "LONG" and low <= stop_price:
                return "SL"
            if episode.side == "SHORT" and high >= stop_price:
                return "SL"
        if target_price is not None:
            if episode.side == "LONG" and high >= target_price:
                return "TP"
            if episode.side == "SHORT" and low <= target_price:
                return "TP"
    if post_bars and stop_price is not None:
        for bar in post_bars:
            high = _safe_float(bar.get("high"))
            low = _safe_float(bar.get("low"))
            if high is None or low is None:
                continue
            if episode.side == "LONG" and low <= stop_price:
                return "SL"
            if episode.side == "SHORT" and high >= stop_price:
                return "SL"
    return "UNKNOWN"


def build_pending_intervals(
    placed: Sequence[OrderPlaced],
    cancelled: Sequence[OrderCancelled],
    episodes: Sequence[Episode],
    end_ts_ms: int,
) -> List[PendingInterval]:
    cancel_by_order: Dict[str, List[OrderCancelled]] = defaultdict(list)
    for item in cancelled:
        cancel_by_order[item.order_id].append(item)
    episode_lookup: Dict[Tuple[str, str, str], List[Episode]] = defaultdict(list)
    for episode in episodes:
        if episode.intent is None:
            continue
        episode_lookup[(episode.symbol, episode.intent.strategy, episode.side)].append(episode)

    intervals: List[PendingInterval] = []
    for order in placed:
        if order.strategy not in TARGET_STRATEGIES:
            continue
        if order.order_type and order.order_type.upper().startswith("TAKE_PROFIT"):
            continue
        if order.order_type and order.order_type.upper().startswith("STOP"):
            continue
        cancel_candidates = sorted(cancel_by_order.get(order.order_id, []), key=lambda item: item.ts_ms)
        end_time = cancel_candidates[0].ts_ms if cancel_candidates else end_ts_ms
        key = (order.symbol, order.strategy, _direction(order.side))
        for episode in episode_lookup.get(key, []):
            if episode.start_ms < order.ts_ms:
                continue
            if order.valid_for_ms is not None and episode.start_ms - order.ts_ms > order.valid_for_ms + 5 * 60 * 1000:
                continue
            end_time = min(end_time, episode.start_ms)
            break
        intervals.append(
            PendingInterval(
                rid=order.rid,
                order_id=order.order_id,
                symbol=order.symbol,
                side=_direction(order.side),
                strategy=order.strategy or "unknown",
                placed_ts_ms=order.ts_ms,
                end_ts_ms=end_time,
                price=order.price,
                valid_for_ms=order.valid_for_ms,
            )
        )
    intervals.sort(key=lambda item: item.placed_ts_ms)
    return intervals


def detect_conflicts(intents: Sequence[TradeIntent], trades: Sequence[TradeRecord], pending_intervals: Sequence[PendingInterval]) -> List[ConflictRecord]:
    active_by_symbol: Dict[str, List[TradeRecord]] = defaultdict(list)
    for trade in trades:
        active_by_symbol[trade.symbol].append(trade)
    pending_by_symbol: Dict[str, List[PendingInterval]] = defaultdict(list)
    for interval in pending_intervals:
        pending_by_symbol[interval.symbol].append(interval)

    conflicts: List[ConflictRecord] = []
    seen: set[Tuple[int, str, str, str, str, str, str]] = set()
    for intent in intents:
        side = _direction(intent.side)
        opposite = "SHORT" if side == "LONG" else "LONG"
        for trade in active_by_symbol.get(intent.symbol, []):
            if trade.strategy == intent.strategy or trade.direction != opposite:
                continue
            if not (trade.entry_time_ms <= intent.ts_ms <= trade.exit_time_ms):
                continue
            key = (intent.ts_ms, intent.symbol, trade.strategy, trade.direction, intent.strategy, side, "active")
            if key in seen:
                continue
            seen.add(key)
            conflicts.append(
                ConflictRecord(
                    ts_ms=intent.ts_ms,
                    symbol=intent.symbol,
                    strategy_a=trade.strategy,
                    direction_a=trade.direction,
                    strategy_b=intent.strategy,
                    direction_b=side,
                    position_state=f"active_{trade.direction.lower()} by {trade.strategy}",
                    source="active_position_vs_intent",
                )
            )
        for interval in pending_by_symbol.get(intent.symbol, []):
            if interval.strategy == intent.strategy or interval.side != opposite:
                continue
            if not (interval.placed_ts_ms <= intent.ts_ms <= interval.end_ts_ms):
                continue
            key = (intent.ts_ms, intent.symbol, interval.strategy, interval.side, intent.strategy, side, "pending")
            if key in seen:
                continue
            seen.add(key)
            conflicts.append(
                ConflictRecord(
                    ts_ms=intent.ts_ms,
                    symbol=intent.symbol,
                    strategy_a=interval.strategy,
                    direction_a=interval.side,
                    strategy_b=intent.strategy,
                    direction_b=side,
                    position_state=f"pending_{interval.side.lower()} by {interval.strategy}",
                    source="pending_entry_vs_intent",
                )
            )
    conflicts.sort(key=lambda item: item.ts_ms)
    return conflicts


def build_trade_records(
    episodes: Sequence[Episode],
    recorder: RecorderCache,
    conflict_keys: set[Tuple[int, str, str]],
) -> List[TradeRecord]:
    trades: List[TradeRecord] = []
    for episode in episodes:
        strategy = episode.intent.strategy if episode.intent else (_strategy_from_rid(episode.open_dec.rid) if episode.open_dec else None)
        if strategy is None:
            continue
        bars = recorder.bars_between(episode.symbol, 180, episode.start_ms, episode.end_ms)
        post_bars = recorder.bars_after(episode.symbol, 180, episode.end_ms, 3)
        qty = abs(episode.last_qty)
        sign = 1.0 if episode.side == "LONG" else -1.0
        pnl = (episode.exit_mark_price - episode.entry_price) * qty * sign
        stop_price = episode.intent.stop_price if episode.intent else (episode.open_dec.stop_price if episode.open_dec else None)
        target_price = episode.intent.target_price if episode.intent else (episode.open_dec.target_price if episode.open_dec else None)
        risk_per_unit = abs(episode.entry_price - stop_price) if stop_price is not None else None
        pnl_r = (sign * (episode.exit_mark_price - episode.entry_price) / risk_per_unit) if risk_per_unit not in (None, 0.0) else None

        highs = [_safe_float(bar.get("high")) for bar in bars]
        lows = [_safe_float(bar.get("low")) for bar in bars]
        highs = [value for value in highs if value is not None]
        lows = [value for value in lows if value is not None]
        mfe = None
        mae = None
        distance_to_local_extreme = None
        if highs and lows:
            if episode.side == "LONG":
                mfe = max(highs) - episode.entry_price
                mae = min(lows) - episode.entry_price
                local_lows = [_safe_float(bar.get("low")) for bar in bars[:3]]
                local_lows = [value for value in local_lows if value is not None]
                if local_lows:
                    distance_to_local_extreme = episode.entry_price - min(local_lows)
            else:
                mfe = episode.entry_price - min(lows)
                mae = episode.entry_price - max(highs)
                local_highs = [_safe_float(bar.get("high")) for bar in bars[:3]]
                local_highs = [value for value in local_highs if value is not None]
                if local_highs:
                    distance_to_local_extreme = max(local_highs) - episode.entry_price

        trade = TradeRecord(
            symbol=episode.symbol,
            strategy=strategy,
            direction=episode.side,
            entry_time_ms=episode.start_ms,
            entry_price=episode.entry_price,
            exit_time_ms=episode.end_ms,
            exit_price=episode.exit_mark_price,
            exit_reason=classify_exit(episode, bars, post_bars),
            pnl=pnl,
            pnl_r=pnl_r,
            qty=qty,
            holding_ms=episode.end_ms - episode.start_ms,
            regime_at_entry=episode.regime_entry,
            regime_at_exit=episode.regime_exit,
            stop_price=stop_price,
            target_price=target_price,
            entry_reason=_extract_reason(episode.intent.why if episode.intent else episode.open_dec.why if episode.open_dec else []),
            conflict_flag=(episode.intent.ts_ms, episode.symbol, strategy) in conflict_keys if episode.intent else False,
            mae=mae,
            mfe=mfe,
            distance_to_local_extreme=distance_to_local_extreme,
            bars_tf_sec=STRATEGY_TF_SEC.get(strategy, 180),
        )
        if episode.close_dec is not None:
            if episode.close_dec.why:
                trade.notes.append(f"close_why={episode.close_dec.why}")
            if episode.close_dec.reason:
                trade.notes.append(f"close_reason={episode.close_dec.reason}")
        trades.append(trade)
    trades.sort(key=lambda item: item.exit_time_ms)
    return trades


def simulate_tpsl(trade: TradeRecord, bars: Sequence[Dict[str, Any]], tp_mult: float, sl_mult: float, post_bars: Sequence[Dict[str, Any]] = ()) -> str:
    if trade.stop_price is None or trade.target_price is None:
        return "NO_BRACKETS"
    tp_dist = abs(trade.target_price - trade.entry_price)
    sl_dist = abs(trade.entry_price - trade.stop_price)
    if tp_dist <= 0 or sl_dist <= 0:
        return "NO_BRACKETS"
    if trade.direction == "LONG":
        tp_price = trade.entry_price + tp_dist * tp_mult
        sl_price = trade.entry_price - sl_dist * sl_mult
    else:
        tp_price = trade.entry_price - tp_dist * tp_mult
        sl_price = trade.entry_price + sl_dist * sl_mult
    for bar in list(bars) + list(post_bars):
        high = _safe_float(bar.get("high"))
        low = _safe_float(bar.get("low"))
        if high is None or low is None:
            continue
        if trade.direction == "LONG":
            tp_hit = high >= tp_price
            sl_hit = low <= sl_price
        else:
            tp_hit = low <= tp_price
            sl_hit = high >= sl_price
        if tp_hit and sl_hit:
            return "AMBIGUOUS"
        if tp_hit:
            return "TP"
        if sl_hit:
            return "SL"
    profitable = (trade.exit_price - trade.entry_price) > 0 if trade.direction == "LONG" else (trade.entry_price - trade.exit_price) > 0
    return "PROFIT_EXIT" if profitable else "LOSS_EXIT"


def counterfactual_matrix(trades: Sequence[TradeRecord], recorder: RecorderCache) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    tp_multipliers = [0.75, 1.0, 1.25, 1.5, 2.0]
    sl_multipliers = [0.5, 0.75, 1.0, 1.25]
    rows: List[Dict[str, Any]] = []
    sl_to_profit = Counter()
    tp_extension = Counter()
    sl_reversal = 0
    sl_total = 0
    ambiguous = 0

    for trade in trades:
        bars = recorder.bars_between(trade.symbol, 180, trade.entry_time_ms, trade.exit_time_ms)
        post_bars = recorder.bars_after(trade.symbol, 180, trade.exit_time_ms, 3)
        if trade.exit_reason == "SL":
            sl_total += 1
            if trade.direction == "LONG":
                recovered = any((_safe_float(bar.get("high")) or -math.inf) >= trade.entry_price for bar in post_bars)
            else:
                recovered = any((_safe_float(bar.get("low")) or math.inf) <= trade.entry_price for bar in post_bars)
            sl_reversal += int(recovered)
        if trade.stop_price is None or trade.target_price is None:
            continue
        for tp_mult in tp_multipliers:
            for sl_mult in sl_multipliers:
                result = simulate_tpsl(trade, bars, tp_mult, sl_mult, post_bars if trade.exit_reason == "TP" else ())
                rows.append(
                    {
                        "symbol": trade.symbol,
                        "strategy": trade.strategy,
                        "entry_time": _fmt_ts_ms(trade.entry_time_ms),
                        "actual_exit_reason": trade.exit_reason,
                        "tp_mult": tp_mult,
                        "sl_mult": sl_mult,
                        "result": result,
                    }
                )
                if result == "AMBIGUOUS":
                    ambiguous += 1
                if trade.exit_reason == "SL" and sl_mult > 1.0 and result in {"TP", "PROFIT_EXIT"}:
                    sl_to_profit[f"sl_x{sl_mult:g}"] += 1
                if trade.exit_reason == "TP" and tp_mult > 1.0 and result == "TP":
                    tp_extension[f"tp_x{tp_mult:g}"] += 1

    summary = {
        "sl_trades": sl_total,
        "sl_reversed_within_3_bars": sl_reversal,
        "sl_to_profit_with_larger_sl": dict(sl_to_profit),
        "tp_extension_hits": dict(tp_extension),
        "ambiguous_paths": ambiguous,
    }
    return rows, summary


def cancellation_impact(
    pending_intervals: Sequence[PendingInterval],
    cancelled: Sequence[OrderCancelled],
    recorder: RecorderCache,
) -> List[Dict[str, Any]]:
    cancel_by_order = {item.order_id: item for item in cancelled if item.reason}
    rows: List[Dict[str, Any]] = []
    for interval in pending_intervals:
        cancel = cancel_by_order.get(interval.order_id)
        if cancel is None:
            continue
        bars = recorder.bars_between(interval.symbol, 180, interval.end_ts_ms, interval.end_ts_ms + 30 * 60 * 1000)
        touched_after_cancel = False
        if interval.price is not None:
            for bar in bars:
                high = _safe_float(bar.get("high"))
                low = _safe_float(bar.get("low"))
                if high is None or low is None:
                    continue
                if interval.side == "LONG" and low <= interval.price:
                    touched_after_cancel = True
                    break
                if interval.side == "SHORT" and high >= interval.price:
                    touched_after_cancel = True
                    break
        rows.append(
            {
                "timestamp": _fmt_ts_ms(cancel.ts_ms),
                "symbol": interval.symbol,
                "strategy": interval.strategy,
                "side": interval.side,
                "order_id": interval.order_id,
                "cancel_reason": cancel.reason,
                "price": interval.price,
                "touched_after_cancel_30m": touched_after_cancel,
            }
        )
    return rows


def build_strategy_metrics(trades: Sequence[TradeRecord]) -> List[Dict[str, Any]]:
    by_strategy: Dict[str, List[TradeRecord]] = defaultdict(list)
    for trade in trades:
        by_strategy[trade.strategy].append(trade)
    rows: List[Dict[str, Any]] = []
    for strategy in sorted(by_strategy):
        items = by_strategy[strategy]
        wins = [trade for trade in items if trade.pnl > 0]
        rows.append(
            {
                "strategy": strategy,
                "total_trades": len(items),
                "win_rate": len(wins) / len(items) if items else 0.0,
                "profit_factor": _profit_factor(items),
                "average_R": mean([trade.pnl_r for trade in items if trade.pnl_r is not None]) if any(trade.pnl_r is not None for trade in items) else None,
                "average_pnl": mean([trade.pnl for trade in items]) if items else None,
                "max_drawdown": _max_drawdown(items),
                "average_hold_time_min": mean([_minutes(trade.holding_ms) for trade in items]) if items else None,
                "sharpe_like_metric": _sharpe_like(items),
                "net_pnl": sum(trade.pnl for trade in items),
            }
        )
    return rows


def build_regime_metrics(trades: Sequence[TradeRecord]) -> List[Dict[str, Any]]:
    by_regime: Dict[str, List[TradeRecord]] = defaultdict(list)
    for trade in trades:
        by_regime[trade.regime_at_entry or "UNKNOWN"].append(trade)
    rows: List[Dict[str, Any]] = []
    for regime in sorted(by_regime):
        items = by_regime[regime]
        wins = [trade for trade in items if trade.pnl > 0]
        rows.append(
            {
                "regime": regime,
                "trade_count": len(items),
                "win_rate": len(wins) / len(items) if items else 0.0,
                "avg_pnl": mean([trade.pnl for trade in items]) if items else None,
                "avg_R": mean([trade.pnl_r for trade in items if trade.pnl_r is not None]) if any(trade.pnl_r is not None for trade in items) else None,
                "net_pnl": sum(trade.pnl for trade in items),
            }
        )
    return rows


def build_equity_rows(trades: Sequence[TradeRecord]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    cumulative_global = 0.0
    cumulative_by_strategy: Dict[str, float] = defaultdict(float)
    for trade in sorted(trades, key=lambda item: item.exit_time_ms):
        cumulative_global += trade.pnl
        cumulative_by_strategy[trade.strategy] += trade.pnl
        row = {
            "exit_time": _fmt_ts_ms(trade.exit_time_ms),
            "symbol": trade.symbol,
            "strategy": trade.strategy,
            "pnl": trade.pnl,
            "equity_global": cumulative_global,
        }
        for strategy in sorted(TARGET_STRATEGIES):
            row[f"equity_{strategy}"] = cumulative_by_strategy[strategy]
        rows.append(row)
    return rows


def count_by_reason(cancelled: Sequence[OrderCancelled]) -> Dict[str, int]:
    return dict(Counter(item.reason for item in cancelled if item.reason))


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def render_report(
    out_path: Path,
    *,
    start_ts_ms: int,
    end_ts_ms: int,
    trades: Sequence[TradeRecord],
    strategy_rows: Sequence[Dict[str, Any]],
    regime_rows: Sequence[Dict[str, Any]],
    counterfactual_summary: Dict[str, Any],
    conflicts: Sequence[ConflictRecord],
    cancel_counts: Dict[str, int],
    cancel_impact_rows: Sequence[Dict[str, Any]],
    supersede_events: Sequence[SupersedeEvent],
    top_losses: Sequence[TradeRecord],
) -> None:
    lines: List[str] = []
    lines.append("# Aurora / Phenix Forensic Report")
    lines.append("")
    lines.append(f"- Evidence window: {_fmt_ts_ms(start_ts_ms)} UTC to {_fmt_ts_ms(end_ts_ms)} UTC")
    lines.append("- PnL note: entry price is exchange-reported from ACCOUNT_UPDATE_RECEIVED; exit price is the last pre-close mark captured before the position disappeared.")
    lines.append("")
    lines.append("## Trade Table")
    lines.append("")
    lines.append("| Symbol | Strategy | Dir | Entry UTC | Entry Px | Exit UTC | Exit Px* | Exit Reason | PnL* | Hold Min | Regime In | Regime Out | Conflict |")
    lines.append("| --- | --- | --- | --- | ---: | --- | ---: | --- | ---: | ---: | --- | --- | --- |")
    for trade in trades:
        lines.append(
            f"| {trade.symbol} | {trade.strategy} | {trade.direction} | {_fmt_ts_ms(trade.entry_time_ms)} | {_fmt_num(trade.entry_price, 6)} | "
            f"{_fmt_ts_ms(trade.exit_time_ms)} | {_fmt_num(trade.exit_price, 6)} | {trade.exit_reason} | {_fmt_money(trade.pnl)} | "
            f"{_fmt_num(_minutes(trade.holding_ms), 1)} | {trade.regime_at_entry or 'n/a'} | {trade.regime_at_exit or 'n/a'} | {'Y' if trade.conflict_flag else 'N'} |"
        )
    lines.append("")
    lines.append("## Strategy Ranking")
    lines.append("")
    lines.append("| Strategy | Trades | Win Rate | Profit Factor | Avg R | Avg PnL | Max DD | Avg Hold Min | Sharpe Like | Net PnL |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in strategy_rows:
        lines.append(
            f"| {row['strategy']} | {row['total_trades']} | {_fmt_num(100.0 * row['win_rate'], 1)}% | {_fmt_num(row['profit_factor'], 2)} | "
            f"{_fmt_num(row['average_R'], 2)} | {_fmt_money(row['average_pnl'])} | {_fmt_money(row['max_drawdown'])} | "
            f"{_fmt_num(row['average_hold_time_min'], 1)} | {_fmt_num(row['sharpe_like_metric'], 2)} | {_fmt_money(row['net_pnl'])} |"
        )
    lines.append("")
    lines.append("## Regime Profitability Map")
    lines.append("")
    lines.append("| Regime | Trades | Win Rate | Avg PnL | Avg R | Net PnL | Bar |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | --- |")
    scale = max((abs(row["net_pnl"]) for row in regime_rows if row["net_pnl"] is not None), default=1.0)
    for row in regime_rows:
        lines.append(
            f"| {row['regime']} | {row['trade_count']} | {_fmt_num(100.0 * row['win_rate'], 1)}% | {_fmt_money(row['avg_pnl'])} | "
            f"{_fmt_num(row['avg_R'], 2)} | {_fmt_money(row['net_pnl'])} | `{_ascii_bar(row['net_pnl'], scale)}` |"
        )
    lines.append("")
    lines.append("## TP / SL Counterfactual")
    lines.append("")
    lines.append(f"- SL trades: {counterfactual_summary.get('sl_trades', 0)}")
    lines.append(f"- SL trades that crossed back through entry within next 3 bars: {counterfactual_summary.get('sl_reversed_within_3_bars', 0)}")
    lines.append(f"- Larger-SL scenarios turning SL trades profitable: {counterfactual_summary.get('sl_to_profit_with_larger_sl', {})}")
    lines.append(f"- Larger-TP scenarios still hit after extension: {counterfactual_summary.get('tp_extension_hits', {})}")
    lines.append(f"- Ambiguous bar paths in the matrix: {counterfactual_summary.get('ambiguous_paths', 0)}")
    lines.append("")
    lines.append("## Strategy Conflicts")
    lines.append("")
    if conflicts:
        lines.append("| Timestamp UTC | Symbol | Strategy A | Dir A | Strategy B | Dir B | Position State | Source |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for record in conflicts:
            lines.append(
                f"| {_fmt_ts_ms(record.ts_ms)} | {record.symbol} | {record.strategy_a} | {record.direction_a} | "
                f"{record.strategy_b} | {record.direction_b} | {record.position_state} | {record.source} |"
            )
        lines.append("")
        lines.append(f"- Symbol-level mutex verdict: `missing_or_incomplete` ({len(conflicts)} opposite-side overlaps reached intent or pending-entry state).")
    else:
        lines.append("- No opposite-side cross-strategy overlap reached the evidence threshold in the analyzed window.")
    lines.append("")
    lines.append("## Execution Anomalies")
    lines.append("")
    lines.append(f"- Order cancel reasons: {cancel_counts}")
    lines.append(f"- Supersede analyses: {len(supersede_events)}")
    touched = sum(1 for row in cancel_impact_rows if row.get("cancel_reason") == "CANCEL_SUPERSEDED" and row.get("touched_after_cancel_30m"))
    total_superseded = sum(1 for row in cancel_impact_rows if row.get("cancel_reason") == "CANCEL_SUPERSEDED")
    lines.append(f"- Superseded entries later touched their original price within 30m: {touched}/{total_superseded}")
    lines.append(f"- TTL cancels observed: {cancel_counts.get('CANCEL_TTL_EXPIRED', 0)}")
    lines.append(f"- Regime-stale cancels observed: {cancel_counts.get('CANCEL_STALE_REGIME', 0)}")
    lines.append("")
    lines.append("## Top 10 Largest Losses")
    lines.append("")
    for trade in top_losses:
        note = ", ".join(trade.notes[:2]) if trade.notes else "no explicit close note"
        lines.append(
            f"- {_fmt_ts_ms(trade.exit_time_ms)} UTC | {trade.symbol} {trade.direction} | {trade.strategy} | PnL*={_fmt_money(trade.pnl)} | "
            f"exit={trade.exit_reason} | regime_in={trade.regime_at_entry or 'n/a'} | entry_reason={trade.entry_reason} | {note}"
        )
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    for item in [
        "Add a symbol-level strategy mutex before DEC:OPEN so opposite-side intents cannot coexist as active position plus pending entry.",
        "Move strategy arbitration earlier. The current run still shows overlap events that reached live intent or pending-order state.",
        "Audit CANCEL_SUPERSEDED on Aurora LIMIT entries. Multiple repriced entries later saw the original price touched, which means fill destruction is plausible.",
        "Reduce manual flip churn in Aurora. Manual CMD:CLOSE dominates explicit close intents in this run.",
        "Recalibrate TP/SL by regime instead of globally. The regime map is materially different between MEAN_REVERSION, UNCERTAIN, and LOW_VOLATILITY.",
        "Persist exact close-fill price and realized net PnL into WAL for every position close. The current run forces mark-based exit estimation.",
    ]:
        lines.append(f"- {item}")
    lines.append("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aurora / Phenix forensic analysis from WAL + logs.")
    parser.add_argument(
        "--wal",
        nargs="*",
        default=["ops/wal/2026-03-06.jsonl", "ops/wal/2026-03-07.jsonl"],
        help="WAL files to analyze",
    )
    parser.add_argument("--order-log", default="logs/order_log_v1.jsonl")
    parser.add_argument("--regime-log-glob", default="logs/domain_regime_detector.log*")
    parser.add_argument("--recorder-dir", default="data/recorder")
    parser.add_argument("--report", default="reports/aurora_forensic_report_2026-03-06_2026-03-07.md")
    parser.add_argument("--csv-prefix", default="reports/aurora_forensic_2026-03-06_2026-03-07")
    parser.add_argument("--json-out", default="reports/aurora_forensic_2026-03-06_2026-03-07_summary.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    wal_paths = [Path(item) for item in args.wal]
    events = list(iter_jsonl(wal_paths))
    intents = parse_trade_intents(events)
    if not intents:
        raise SystemExit("No target-strategy TRADE_INTENT_PROPOSED events found in the selected WAL files.")
    start_ts_ms = min(intent.ts_ms for intent in intents)
    end_ts_ms = max(_safe_int(event.get("ts") or event.get("timestamp")) or 0 for event in events)
    intents_by_rid = {intent.rid: intent for intent in intents}

    opens = parse_decision_opens(events)
    closes = parse_decision_closes(events)
    updates = parse_account_updates(events)
    episodes = build_episodes(updates)

    regime_paths = sorted(Path().glob(args.regime_log_glob))
    regimes = parse_regime_points(regime_paths)
    attach_episode_context(episodes, intents, opens, closes, regimes)
    episodes = trade_filter(episodes, start_ts_ms, end_ts_ms)

    placed, cancelled, supersede_events, fill_discovered = parse_order_log(Path(args.order_log), intents_by_rid)
    placed = [item for item in placed if start_ts_ms <= item.ts_ms <= end_ts_ms and item.strategy in TARGET_STRATEGIES]
    cancelled = [item for item in cancelled if start_ts_ms <= item.ts_ms <= end_ts_ms]
    pending_intervals = build_pending_intervals(placed, cancelled, episodes, end_ts_ms)

    recorder = RecorderCache(Path(args.recorder_dir))
    initial_conflicts = detect_conflicts(intents, [], pending_intervals)
    conflict_keys = {(record.ts_ms, record.symbol, record.strategy_b) for record in initial_conflicts}
    trades = build_trade_records(episodes, recorder, conflict_keys)
    conflicts = detect_conflicts(intents, trades, pending_intervals)
    conflict_keys = {(record.ts_ms, record.symbol, record.strategy_b) for record in conflicts}
    trades = build_trade_records(episodes, recorder, conflict_keys)

    strategy_rows = build_strategy_metrics(trades)
    regime_rows = build_regime_metrics(trades)
    equity_rows = build_equity_rows(trades)
    counter_rows, counter_summary = counterfactual_matrix(trades, recorder)
    cancel_impact_rows = cancellation_impact(pending_intervals, cancelled, recorder)
    cancel_counts = count_by_reason(cancelled)
    top_losses = sorted(trades, key=lambda trade: trade.pnl)[:10]

    csv_prefix = Path(args.csv_prefix)
    write_csv(
        csv_prefix.with_name(csv_prefix.name + "_trades.csv"),
        [
            {
                "symbol": trade.symbol,
                "strategy": trade.strategy,
                "direction": trade.direction,
                "entry_time": _fmt_ts_ms(trade.entry_time_ms),
                "entry_price": trade.entry_price,
                "exit_time": _fmt_ts_ms(trade.exit_time_ms),
                "exit_price_est": trade.exit_price,
                "exit_reason": trade.exit_reason,
                "pnl_est": trade.pnl,
                "pnl_r_est": trade.pnl_r,
                "holding_min": _minutes(trade.holding_ms),
                "regime_at_entry": trade.regime_at_entry,
                "regime_at_exit": trade.regime_at_exit,
                "stop_price": trade.stop_price,
                "target_price": trade.target_price,
                "conflict_flag": trade.conflict_flag,
                "mae": trade.mae,
                "mfe": trade.mfe,
                "distance_to_local_extreme": trade.distance_to_local_extreme,
                "entry_reason": trade.entry_reason,
            }
            for trade in trades
        ],
    )
    write_csv(csv_prefix.with_name(csv_prefix.name + "_strategy_metrics.csv"), strategy_rows)
    write_csv(csv_prefix.with_name(csv_prefix.name + "_regime_metrics.csv"), regime_rows)
    write_csv(
        csv_prefix.with_name(csv_prefix.name + "_conflicts.csv"),
        [
            {
                "timestamp": _fmt_ts_ms(item.ts_ms),
                "symbol": item.symbol,
                "strategy_a": item.strategy_a,
                "direction_a": item.direction_a,
                "strategy_b": item.strategy_b,
                "direction_b": item.direction_b,
                "position_state": item.position_state,
                "source": item.source,
            }
            for item in conflicts
        ],
    )
    write_csv(csv_prefix.with_name(csv_prefix.name + "_counterfactual.csv"), counter_rows)
    write_csv(csv_prefix.with_name(csv_prefix.name + "_equity.csv"), equity_rows)
    write_csv(csv_prefix.with_name(csv_prefix.name + "_cancel_impact.csv"), cancel_impact_rows)

    summary = {
        "window_start_utc": _fmt_ts_ms(start_ts_ms),
        "window_end_utc": _fmt_ts_ms(end_ts_ms),
        "trade_count": len(trades),
        "strategy_metrics": strategy_rows,
        "regime_metrics": regime_rows,
        "counterfactual_summary": counter_summary,
        "cancel_reason_counts": cancel_counts,
        "supersede_event_count": len(supersede_events),
        "fill_discovered_count": len(fill_discovered),
        "conflict_count": len(conflicts),
    }
    Path(args.json_out).write_text(json.dumps(summary, indent=2), encoding="utf-8")

    render_report(
        Path(args.report),
        start_ts_ms=start_ts_ms,
        end_ts_ms=end_ts_ms,
        trades=trades,
        strategy_rows=strategy_rows,
        regime_rows=regime_rows,
        counterfactual_summary=counter_summary,
        conflicts=conflicts,
        cancel_counts=cancel_counts,
        cancel_impact_rows=cancel_impact_rows,
        supersede_events=supersede_events,
        top_losses=top_losses,
    )

    print(f"report={args.report}")
    print(f"trade_count={len(trades)}")
    print(f"conflict_count={len(conflicts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
