#!/usr/bin/env python3
"""
CLI utility to inspect Aggregated OCO state (positions, bracket sets, open orders).

Usage:
    python tools/agg_oco_snapshot.py [--symbol BTCUSDT --symbol SOLUSDT] [--json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx

from apps.reference.adapters.binance_adapter import BinanceAdapter
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.manage_config import (
    AggregatedOcoConfig,
    resolve_execution_manage_config,
)
from apps.reference.services.order_guardian import BracketSetMeta

LOGGER = logging.getLogger("agg_oco_snapshot")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BINANCE_MAINNET_URL = "https://fapi.binance.com"
BINANCE_TESTNET_URL = "https://testnet.binancefuture.com"


def boolish(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def canonical_symbol(value: Optional[str]) -> str:
    return str(value or "").upper()


def canonical_side(value: Optional[str], fallback_qty: Optional[float] = None) -> Optional[str]:
    if value:
        normalized = str(value).upper()
        if normalized in {"LONG", "SHORT"}:
            return normalized
    if fallback_qty is not None:
        if fallback_qty > 0:
            return "LONG"
        if fallback_qty < 0:
            return "SHORT"
    return None


@dataclass
class NormalizedPosition:
    symbol: str
    side: str
    qty: float
    avg_entry_price: Optional[float]


@dataclass
class TrackedOrder:
    raw: Any
    normalized: Dict[str, Any]
    order_id: str
    client_order_id: Optional[str]
    symbol: str
    side: Optional[str]
    is_reduce_only: bool
    is_sl: bool
    is_tp: bool
    base_id: Optional[str]
    timestamp: float


@dataclass
class SnapshotResult:
    symbol: str
    side: str
    position_qty: float
    avg_entry_price: Optional[float]
    bracket_set: Optional[BracketSetMeta]
    sl_orders: List[str]
    tp_orders: List[str]
    orphan_reduce_only: List[str]
    invariants: Dict[str, bool]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if self.bracket_set is not None:
            payload["bracket_set"] = {
                "bracket_set_id": self.bracket_set.bracket_set_id,
                "symbol": self.bracket_set.symbol,
                "side": self.bracket_set.side,
                "sl_order_id": self.bracket_set.sl_order_id,
                "tp_order_id": self.bracket_set.tp_order_id,
                "created_ts": self.bracket_set.created_ts,
                "version": self.bracket_set.version,
            }
        return payload


def normalize_position(raw: Any) -> Optional[NormalizedPosition]:
    data: Dict[str, Any]
    if isinstance(raw, dict):
        data = dict(raw)
    elif hasattr(raw, "to_dict"):
        try:
            maybe_dict = raw.to_dict()
            data = dict(maybe_dict)
        except Exception:
            data = dict(getattr(raw, "__dict__", {}))
    else:
        data = dict(getattr(raw, "__dict__", {}))

    symbol = canonical_symbol(data.get("symbol"))
    if not symbol:
        return None

    qty_raw = (
        data.get("positionAmt")
        or data.get("position_amount")
        or data.get("positionAmount")
        or data.get("qty")
        or data.get("quantity")
        or 0
    )
    try:
        qty = float(qty_raw)
    except (TypeError, ValueError):
        qty = 0.0

    side = canonical_side(data.get("positionSide"), qty)
    if qty == 0:
        return None
    if not side:
        return None

    avg_price_raw = (
        data.get("entryPrice")
        or data.get("avgEntryPrice")
        or data.get("avg_price")
        or data.get("avgPrice")
    )
    try:
        avg_price = float(avg_price_raw) if avg_price_raw not in (None, "") else None
    except (TypeError, ValueError):
        avg_price = None

    return NormalizedPosition(
        symbol=symbol,
        side=side,
        qty=abs(qty),
        avg_entry_price=avg_price,
    )


def normalize_order_payload(raw_order: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw_order, dict):
        normalized: Dict[str, Any] = dict(raw_order)
    else:
        normalized = {}
        if hasattr(raw_order, "to_dict"):
            try:
                maybe_dict = raw_order.to_dict()
                if isinstance(maybe_dict, dict):
                    normalized = dict(maybe_dict)
            except Exception:
                normalized = {}
        if not normalized and hasattr(raw_order, "__dict__"):
            normalized = dict(vars(raw_order))
        if not normalized:
            return None

    if "orderId" not in normalized and "order_id" in normalized:
        normalized["orderId"] = normalized.get("order_id")
    if "clientOrderId" not in normalized and "client_order_id" in normalized:
        normalized["clientOrderId"] = normalized.get("client_order_id")
    if "symbol" not in normalized and normalized.get("symbol_id"):
        normalized["symbol"] = normalized.get("symbol_id")
    if "type" not in normalized and "order_type" in normalized:
        normalized["type"] = normalized.get("order_type")
    if "status" not in normalized and "state" in normalized:
        normalized["status"] = normalized.get("state")
    if "time" not in normalized and "timestamp_ms" in normalized:
        normalized["time"] = normalized.get("timestamp_ms")
    if "origQty" not in normalized and "quantity" in normalized:
        normalized["origQty"] = normalized.get("quantity")
    if "executedQty" not in normalized and "filled_qty" in normalized:
        normalized["executedQty"] = normalized.get("filled_qty")
    if "reduceOnly" not in normalized and "reduce_only" in normalized:
        normalized["reduceOnly"] = normalized.get("reduce_only")
    if "closePosition" not in normalized and "close_position" in normalized:
        normalized["closePosition"] = normalized.get("close_position")
    return normalized


def infer_order_side(normalized: Dict[str, Any]) -> Optional[str]:
    side = normalized.get("positionSide") or normalized.get("position_side")
    result = canonical_side(side)
    if result:
        return result
    order_side = (normalized.get("side") or "").upper()
    if order_side == "SELL":
        return "LONG"
    if order_side == "BUY":
        return "SHORT"
    return None


def extract_bracket_base(client_order_id: Optional[str]) -> Optional[str]:
    if not client_order_id:
        return None
    lowered = client_order_id.lower()
    if lowered.endswith("_sl") or lowered.endswith("_tp"):
        return client_order_id[:-3]
    return None


def extract_order_timestamp(normalized: Dict[str, Any]) -> float:
    for key in ("updateTime", "time", "timestamp", "ts"):
        value = normalized.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            try:
                return float(str(value))
            except (TypeError, ValueError):
                continue
    return 0.0


def is_sl_order(normalized: Dict[str, Any]) -> bool:
    kind = str(normalized.get("kind") or "").upper()
    order_type = str(normalized.get("type") or "").upper()
    if kind in {"SL", "STOP", "STOP_MARKET", "STOP_LOSS"}:
        return True
    if "STOP" in order_type:
        return True
    client_id = (normalized.get("clientOrderId") or "").lower()
    return client_id.endswith("_sl")


def is_tp_order(normalized: Dict[str, Any]) -> bool:
    kind = str(normalized.get("kind") or "").upper()
    order_type = str(normalized.get("type") or "").upper()
    if kind in {"TP", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"}:
        return True
    if "TAKE_PROFIT" in order_type or "PROFIT" in order_type:
        return True
    client_id = (normalized.get("clientOrderId") or "").lower()
    return client_id.endswith("_tp")


def classify_tracked_order(raw_order: Any) -> Optional[TrackedOrder]:
    normalized = normalize_order_payload(raw_order)
    if not normalized:
        return None
    order_id = normalized.get("orderId")
    if order_id is None:
        return None
    symbol = canonical_symbol(normalized.get("symbol"))
    if not symbol:
        return None
    is_reduce_only = boolish(
        normalized.get("reduceOnly")) or boolish(normalized.get("closePosition"))
    if not is_reduce_only:
        return None
    side = infer_order_side(normalized)
    client_order_id = normalized.get("clientOrderId")
    base_id = extract_bracket_base(client_order_id)
    return TrackedOrder(
        raw=raw_order,
        normalized=normalized,
        order_id=str(order_id),
        client_order_id=client_order_id,
        symbol=symbol,
        side=side,
        is_reduce_only=True,
        is_sl=is_sl_order(normalized),
        is_tp=is_tp_order(normalized),
        base_id=base_id,
        timestamp=extract_order_timestamp(normalized),
    )


def build_bracket_meta(symbol: str, side: str, orders: Sequence[TrackedOrder]) -> Tuple[Optional[BracketSetMeta], int]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for order in orders:
        if not order.base_id:
            continue
        entry = grouped.setdefault(
            order.base_id,
            {"base_id": order.base_id, "sl": None, "tp": None, "ts": 0.0},
        )
        if order.is_sl:
            entry["sl"] = order.order_id
        elif order.is_tp:
            entry["tp"] = order.order_id
        entry["ts"] = max(entry["ts"], order.timestamp)

    if not grouped:
        return None, 0

    valid_groups = [g for g in grouped.values() if g.get("sl") or g.get("tp")]
    if not valid_groups:
        return None, len(grouped)

    best = max(valid_groups, key=lambda g: g.get("ts", 0.0))
    meta = BracketSetMeta(
        bracket_set_id=str(best.get("base_id")),
        symbol=symbol,
        side=side,
        sl_order_id=best.get("sl"),
        tp_order_id=best.get("tp"),
        created_ts=best.get("ts") or 0.0,
        version=0,
    )
    return meta, len(grouped)


def build_snapshot(
    symbol: str,
    side: str,
    position_qty: float,
    avg_entry_price: Optional[float],
    bracket_meta: Optional[BracketSetMeta],
    tracked_orders: Sequence[TrackedOrder],
    aggregated_enabled: bool,
    extra_group_count: int,
) -> SnapshotResult:
    reduce_only_orders = list(tracked_orders)
    sl_orders = [order.order_id for order in reduce_only_orders if order.is_sl]
    tp_orders = [order.order_id for order in reduce_only_orders if order.is_tp]

    group_ids = {
        order.base_id or order.order_id for order in reduce_only_orders if order.base_id or order.order_id
    }
    if bracket_meta:
        group_ids.add(bracket_meta.bracket_set_id)
    if extra_group_count > len(group_ids):
        group_ids.add(f"__group_count__{extra_group_count}")
    invariant_single = len(group_ids) <= 1

    invariant_protected = True
    if position_qty > 0:
        invariant_protected = bool(sl_orders)

    invariant_flat_clean = True
    if position_qty == 0 and reduce_only_orders:
        invariant_flat_clean = False

    meta_ids = set()
    if bracket_meta:
        if bracket_meta.sl_order_id:
            meta_ids.add(str(bracket_meta.sl_order_id))
        if bracket_meta.tp_order_id:
            meta_ids.add(str(bracket_meta.tp_order_id))

    orphan_reduce_only = []
    for order in reduce_only_orders:
        if position_qty == 0 or (order.order_id not in meta_ids):
            orphan_reduce_only.append(order.order_id)

    invariants = {
        "INVARIANT_SINGLE_SET": invariant_single,
        "INVARIANT_PROTECTED_IF_OPEN": invariant_protected,
        "INVARIANT_NO_REDUCE_ONLY_IF_FLAT": invariant_flat_clean,
        "HAS_ORPHANS": bool(orphan_reduce_only),
        "AGGREGATED_OCO_ENABLED": aggregated_enabled,
    }

    return SnapshotResult(
        symbol=symbol,
        side=side,
        position_qty=position_qty,
        avg_entry_price=avg_entry_price,
        bracket_set=bracket_meta,
        sl_orders=sl_orders,
        tp_orders=tp_orders,
        orphan_reduce_only=orphan_reduce_only,
        invariants=invariants,
    )


def format_snapshot(snapshot: SnapshotResult) -> str:
    meta = snapshot.bracket_set
    bracket_set_id = meta.bracket_set_id if meta else None
    sl_id = meta.sl_order_id if meta else None
    tp_id = meta.tp_order_id if meta else None

    lines = [
        f"SYMBOL: {snapshot.symbol:<10} SIDE: {snapshot.side}",
        f"  position_qty:            {snapshot.position_qty:.6f}",
        f"  avg_entry_price:         {snapshot.avg_entry_price if snapshot.avg_entry_price is not None else 'n/a'}",
        f"  bracket_set_id:          {bracket_set_id or 'n/a'}",
        f"  sl_order_id:             {sl_id or 'n/a'}",
        f"  tp_order_id:             {tp_id or 'n/a'}",
        f"  sl_orders:               {snapshot.sl_orders or []}",
        f"  tp_orders:               {snapshot.tp_orders or []}",
        f"  orphan_reduce_only:      {snapshot.orphan_reduce_only or []}",
    ]
    for key, value in snapshot.invariants.items():
        if key == "AGGREGATED_OCO_ENABLED":
            continue
        status = "OK" if value else "FAIL"
        lines.append(f"  {key}: {status}")
    lines.append(
        f"  HAS_ORPHANS:             {'YES' if snapshot.invariants.get('HAS_ORPHANS') else 'NO'}"
    )
    return "\n".join(lines)


async def fetch_positions_and_orders(
    adapter: BinanceAdapter,
    symbols_filter: Optional[Sequence[str]],
) -> Tuple[List[NormalizedPosition], List[TrackedOrder]]:
    symbols_filter_set = {canonical_symbol(sym)
                          for sym in symbols_filter or [] if sym}
    positions_raw = await adapter.get_open_positions()
    normalized_positions: List[NormalizedPosition] = []
    for raw in positions_raw:
        normalized = normalize_position(raw)
        if not normalized:
            continue
        if symbols_filter_set and normalized.symbol not in symbols_filter_set:
            continue
        normalized_positions.append(normalized)

    open_orders_raw = await adapter.get_open_orders()
    tracked_orders: List[TrackedOrder] = []
    for raw_order in open_orders_raw:
        tracked = classify_tracked_order(raw_order)
        if not tracked:
            continue
        if symbols_filter_set and tracked.symbol not in symbols_filter_set:
            continue
        tracked_orders.append(tracked)

    return normalized_positions, tracked_orders


def determine_symbol_sides(
    symbols_filter: Optional[Sequence[str]],
    positions: Sequence[NormalizedPosition],
    orders: Sequence[TrackedOrder],
) -> Dict[str, set[str]]:
    symbol_sides: Dict[str, set[str]] = {}
    for pos in positions:
        symbol_sides.setdefault(pos.symbol, set()).add(pos.side)
    for order in orders:
        if not order.side:
            continue
        symbol_sides.setdefault(order.symbol, set()).add(order.side)

    if symbols_filter:
        for sym in symbols_filter:
            csym = canonical_symbol(sym)
            symbol_sides.setdefault(csym, set())

    return symbol_sides


def compute_snapshots(
    positions: Sequence[NormalizedPosition],
    orders: Sequence[TrackedOrder],
    symbol_sides: Dict[str, set[str]],
    aggregated_cfg: AggregatedOcoConfig,
) -> List[SnapshotResult]:
    positions_map: Dict[Tuple[str, str], NormalizedPosition] = {
        (pos.symbol, pos.side): pos for pos in positions
    }
    orders_map: Dict[Tuple[str, str], List[TrackedOrder]] = {}
    for order in orders:
        if not order.side:
            continue
        orders_map.setdefault((order.symbol, order.side), []).append(order)

    aggregated_enabled = bool(getattr(aggregated_cfg, "enabled", False))
    snapshots: List[SnapshotResult] = []
    for symbol in sorted(symbol_sides):
        sides = symbol_sides[symbol] or {"LONG", "SHORT"}
        for side in sorted(sides):
            key = (symbol, side)
            pos = positions_map.get(key)
            position_qty = pos.qty if pos else 0.0
            avg_price = pos.avg_entry_price if pos else None
            tracked_orders = orders_map.get(key, [])
            bracket_meta = None
            group_count = 0
            if tracked_orders:
                bracket_meta, group_count = build_bracket_meta(
                    symbol, side, tracked_orders)
            snapshot = build_snapshot(
                symbol=symbol,
                side=side,
                position_qty=position_qty,
                avg_entry_price=avg_price,
                bracket_meta=bracket_meta,
                tracked_orders=tracked_orders,
                aggregated_enabled=aggregated_enabled,
                extra_group_count=group_count,
            )

            if not tracked_orders and position_qty == 0:
                # Skip empty pairs unless explicitly requested
                continue
            snapshots.append(snapshot)
    return snapshots


def determine_base_url(config) -> str:
    override = os.environ.get("BINANCE_FUTURES_BASE_URL")
    if override:
        return override
    try:
        use_testnet = bool(getattr(config, "use_testnet") or False)
    except Exception:
        use_testnet = True
    return BINANCE_TESTNET_URL if use_testnet else BINANCE_MAINNET_URL


async def run_cli(args: argparse.Namespace) -> int:
    config_dir = args.config_dir or (PROJECT_ROOT / "config" / "aurora")
    config_loader = ConfigLoader(config_dir=config_dir)
    config = config_loader.load_config()

    manage_cfg = resolve_execution_manage_config(config)
    aggregated_cfg = getattr(manage_cfg.brackets, "aggregated_oco",
                             AggregatedOcoConfig())
    if not getattr(aggregated_cfg, "enabled", False):
        LOGGER.warning(
            "Aggregated OCO appears disabled in config. Invariants will still be computed best-effort.")

    api_key = getattr(config, "binance_api_key", None)
    api_secret = getattr(config, "binance_api_secret", None)
    base_url = determine_base_url(config)

    adapter = BinanceAdapter(
        api_key=api_key or "",
        api_secret=api_secret or "",
        base_url=base_url,
        config=config,
        session=httpx.AsyncClient(
            base_url=base_url,
            timeout=10.0,
            headers={"X-MBX-APIKEY": api_key or ""},
        ),
    )

    try:
        positions, tracked_orders = await fetch_positions_and_orders(
            adapter, args.symbol)
    except Exception as exc:  # pragma: no cover - network path
        LOGGER.error("Failed to fetch data from adapter: %s", exc)
        await adapter.aclose()
        return 1
    finally:
        await adapter.aclose()

    symbol_sides = determine_symbol_sides(
        args.symbol, positions, tracked_orders)
    snapshots = compute_snapshots(
        positions, tracked_orders, symbol_sides, aggregated_cfg)

    if args.json:
        print(json.dumps([snap.to_dict() for snap in snapshots], indent=2))
    else:
        if not snapshots:
            print("No aggregated OCO data for requested symbols.")
        for snapshot in snapshots:
            print(format_snapshot(snapshot))
            print("-" * 60)

    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregated OCO snapshot inspector")
    parser.add_argument(
        "--symbol",
        action="append",
        help="Symbol to inspect (can be specified multiple times).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable output.",
    )
    parser.add_argument(
        "--config-dir",
        default=str(PROJECT_ROOT / "config" / "aurora"),
        help="Path to config directory (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=os.environ.get(
        "LOG_LEVEL", "INFO"), format="%(message)s")
    args = parse_args(argv)
    try:
        return asyncio.run(run_cli(args))
    except KeyboardInterrupt:  # pragma: no cover - CLI path
        return 130


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
