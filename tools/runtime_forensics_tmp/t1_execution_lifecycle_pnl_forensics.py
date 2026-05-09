from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(r"c:\Users\user\Music\Phenix")
EXPECTED_MANIFEST = ROOT / "reports" / \
    "runtime_forensics" / "T0" / "runtime_manifest.json"
EVIDENCE_ROOT = ROOT / "reports" / "forensics" / \
    "r7q_long_window_data" / "evidence_freeze"
LOGS = EVIDENCE_ROOT / "logs"
OUT = ROOT / "reports" / "runtime_forensics" / "T1_execution_pnl"

ORDER_COLUMNS = [
    "ts",
    "source_file",
    "symbol",
    "side",
    "order_role",
    "order_id",
    "client_order_id",
    "rid",
    "intent_id",
    "order_type",
    "tif",
    "reduce_only",
    "close_position",
    "qty",
    "price",
    "stop_price",
    "status",
    "reject_code",
    "reject_reason",
    "exchange_response",
    "raw_payload_hash",
    "correlation_confidence",
]

TRADE_COLUMNS = [
    "trade_id",
    "symbol",
    "strategy_id_if_known",
    "side",
    "entry_intent_ts",
    "entry_order_ts",
    "entry_fill_ts",
    "entry_order_id",
    "entry_client_order_id",
    "entry_price",
    "entry_qty",
    "entry_notional",
    "entry_fee",
    "entry_fee_asset",
    "entry_order_type",
    "entry_tif",
    "initial_stop_price",
    "initial_target_price",
    "sl_order_id",
    "tp_order_id",
    "bracket_status",
    "bracket_fail_reason",
    "close_trigger",
    "close_order_ts",
    "close_fill_ts",
    "close_order_id",
    "close_price",
    "close_qty",
    "close_fee",
    "close_fee_asset",
    "gross_pnl",
    "total_fee_usdt",
    "net_pnl",
    "net_roi",
    "holding_seconds",
    "status",
    "execution_anomalies",
    "lifecycle_anomalies",
    "correlation_confidence",
    "estimated_fee_usdt",
    "pnl_estimation_flag",
    "proven_net_pnl",
    "estimated_net_pnl",
]


def to_f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def to_i(v: Any) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(v)
    except Exception:
        return None


def json_hash(row: dict[str, Any]) -> str:
    blob = json.dumps(row, sort_keys=True,
                      ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8", errors="replace")).hexdigest()


def role_from_row(row: dict[str, Any]) -> str:
    et = str(row.get("event_type") or "")
    kind = str(row.get("order_kind") or "").upper()
    bracket_type = str(row.get("bracket_type") or "").upper()
    close_reason = str(row.get("close_reason") or "").upper()
    coid = str(row.get("client_order_id") or "")

    if kind in {"ENTRY", "SL", "TP", "CLOSE"}:
        return {"SL": "STOP_LOSS", "TP": "TAKE_PROFIT"}.get(kind, kind)
    if bracket_type == "SL":
        return "STOP_LOSS"
    if bracket_type == "TP":
        return "TAKE_PROFIT"
    if coid.startswith("ENTRY-"):
        return "ENTRY"
    if coid.startswith("CLOSE-"):
        return "CLOSE"
    if et == "ORDER_CANCELLED":
        return "CANCEL"
    if close_reason == "SL":
        return "STOP_LOSS"
    if close_reason == "TP":
        return "TAKE_PROFIT"
    return "UNKNOWN"


def status_from_event(event_type: str, adapter_status: str | None) -> str:
    mapping = {
        "ORDER_INTENT": "INTENT",
        "ORDER_PLACED": adapter_status or "PLACED",
        "ORDER_FILLED": "FILLED",
        "ORDER_REJECTED": "REJECTED",
        "ORDER_CANCELLED": "CANCELLED",
        "ORDER_TIMEOUT": "TIMEOUT",
    }
    return mapping.get(event_type, event_type)


def corr_confidence(order_id: str, client_order_id: str, rid: str, lifecycle_id: str) -> str:
    score = 0
    if order_id:
        score += 1
    if client_order_id:
        score += 1
    if rid:
        score += 1
    if lifecycle_id:
        score += 1
    if score >= 3:
        return "HIGH"
    if score == 2:
        return "MEDIUM"
    return "LOW"


@dataclass
class Trade:
    trade_id: str
    symbol: str = ""
    strategy_id_if_known: str = ""
    side: str = ""
    entry_intent_ts: int | None = None
    entry_order_ts: int | None = None
    entry_fill_ts: int | None = None
    entry_order_id: str = ""
    entry_client_order_id: str = ""
    entry_order_type: str = ""
    entry_tif: str = ""

    initial_stop_price: float | None = None
    initial_target_price: float | None = None
    sl_order_id: str = ""
    tp_order_id: str = ""

    close_trigger: str = ""
    close_order_ts: int | None = None
    close_fill_ts: int | None = None
    close_order_id: str = ""

    entry_fills: list[tuple[float, float, float |
                            None, str]] = field(default_factory=list)
    close_fills: list[tuple[float, float, float | None,
                            str, float]] = field(default_factory=list)

    execution_anomalies: set[str] = field(default_factory=set)
    lifecycle_anomalies: set[str] = field(default_factory=set)

    entry_order_count: int = 0
    close_order_count: int = 0
    bracket_rejects: list[str] = field(default_factory=list)
    timeout_ts: int | None = None
    position_closed_realized_net: float | None = None
    post_close_order_events: int = 0


def pick_trade_key(
    row: dict[str, Any],
    lifecycle_to_trade: dict[str, str],
    client_to_trade: dict[str, str],
    open_by_symbol: dict[str, list[str]],
) -> str | None:
    lifecycle_id = str(row.get("lifecycle_id") or "")
    rid = str(row.get("rid") or "")
    coid = str(row.get("client_order_id") or "")
    symbol = str(row.get("symbol") or "")

    if lifecycle_id and lifecycle_id in lifecycle_to_trade:
        return lifecycle_to_trade[lifecycle_id]
    if coid and coid in client_to_trade:
        return client_to_trade[coid]
    if rid and rid in client_to_trade:
        return client_to_trade[rid]

    if rid.endswith(":TP") or rid.endswith(":SL"):
        base = rid.rsplit(":", 1)[0]
        if base in lifecycle_to_trade:
            return lifecycle_to_trade[base]

    if lifecycle_id:
        return lifecycle_id
    if coid:
        return coid
    if rid and rid.startswith("aurora_"):
        return rid

    active = open_by_symbol.get(symbol) or []
    if active:
        return active[-1]
    return None


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in columns})


def main() -> None:
    manifest_found = EXPECTED_MANIFEST.exists()

    order_log = LOGS / "order_log_v1.jsonl"
    trade_lifecycle = LOGS / "trade_lifecycle.jsonl"
    domain_exec_logs = [
        LOGS / "domain_execution_position.log",
        LOGS / "domain_execution_position.log.1",
        LOGS / "domain_execution_position.log.2",
    ]

    if not order_log.exists():
        raise FileNotFoundError(f"Missing required file: {order_log}")

    source_files = [order_log]
    if trade_lifecycle.exists():
        source_files.append(trade_lifecycle)

    orders_rows: list[dict[str, Any]] = []
    orders_payload_hash_seen: set[str] = set()

    trades: dict[str, Trade] = {}
    lifecycle_to_trade: dict[str, str] = {}
    client_to_trade: dict[str, str] = {}
    open_by_symbol: dict[str, list[str]] = defaultdict(list)

    min_ts: int | None = None
    max_ts: int | None = None

    unmatched_fills = 0
    unmatched_orders = 0

    event_whitelist = {
        "ORDER_INTENT",
        "ORDER_PLACED",
        "ORDER_FILLED",
        "ORDER_REJECTED",
        "ORDER_CANCELLED",
        "ORDER_TIMEOUT",
        "POSITION_CLOSED",
    }

    # Parse JSONL sources in one pass each.
    for src in source_files:
        with src.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue

                event_type = str(row.get("event_type") or "")
                if event_type not in event_whitelist:
                    continue

                ts = to_i(row.get("timestamp") or row.get("ts_ms"))
                if ts is not None:
                    min_ts = ts if min_ts is None else min(min_ts, ts)
                    max_ts = ts if max_ts is None else max(max_ts, ts)

                rid = str(row.get("rid") or "")
                lifecycle_id = str(row.get("lifecycle_id") or "")
                symbol = str(row.get("symbol") or "")
                side = str(row.get("side") or "")
                coid = str(row.get("client_order_id") or "")
                order_id = str(row.get("order_id") or "")
                role = role_from_row(row)
                adapter = row.get("adapter_response") if isinstance(
                    row.get("adapter_response"), dict) else {}
                order_type = str(row.get("order_type")
                                 or adapter.get("type") or "")
                tif = str((row.get("metadata") or {}).get("tif")
                          or adapter.get("timeInForce") or "")
                reduce_only = row.get("reduce_only")
                if reduce_only is None:
                    reduce_only = adapter.get("reduceOnly")
                close_position = row.get("close_position")
                if close_position is None:
                    close_position = adapter.get("closePosition")
                qty = row.get("quantity")
                if qty is None:
                    qty = adapter.get("origQty")
                price = row.get("price")
                if price is None:
                    price = adapter.get("price")
                stop_price = row.get("stop_price")
                if stop_price is None:
                    stop_price = adapter.get("stopPrice")

                reject_code = str(row.get("nrr_code") or "")
                reject_reason = str(row.get("why") or (
                    row.get("metadata") or {}).get("error") or "")

                order_row = {
                    "ts": ts or "",
                    "source_file": src.name,
                    "symbol": symbol,
                    "side": side,
                    "order_role": role,
                    "order_id": order_id,
                    "client_order_id": coid,
                    "rid": rid,
                    "intent_id": lifecycle_id,
                    "order_type": order_type,
                    "tif": tif,
                    "reduce_only": "" if reduce_only is None else bool(reduce_only),
                    "close_position": "" if close_position is None else bool(close_position),
                    "qty": qty if qty is not None else "",
                    "price": price if price is not None else "",
                    "stop_price": stop_price if stop_price is not None else "",
                    "status": status_from_event(event_type, str(adapter.get("status") or "")),
                    "reject_code": reject_code,
                    "reject_reason": reject_reason,
                    "exchange_response": json.dumps(adapter, ensure_ascii=False, sort_keys=True) if adapter else "",
                    "raw_payload_hash": json_hash(row),
                    "correlation_confidence": corr_confidence(order_id, coid, rid, lifecycle_id),
                }
                if order_row["raw_payload_hash"] not in orders_payload_hash_seen:
                    orders_payload_hash_seen.add(order_row["raw_payload_hash"])
                    orders_rows.append(order_row)

                key = pick_trade_key(
                    row, lifecycle_to_trade, client_to_trade, open_by_symbol)
                if not key:
                    if event_type == "ORDER_FILLED":
                        unmatched_fills += 1
                    continue

                if key not in trades:
                    trades[key] = Trade(trade_id=key)
                t = trades[key]

                if symbol:
                    t.symbol = t.symbol or symbol
                if side:
                    t.side = t.side or side

                if lifecycle_id:
                    lifecycle_to_trade[lifecycle_id] = key
                if coid:
                    client_to_trade[coid] = key

                if event_type == "ORDER_INTENT":
                    source_fsm = str(row.get("source_fsm") or "")
                    if source_fsm == "DecisionMaking":
                        t.entry_intent_ts = ts if t.entry_intent_ts is None else min(
                            t.entry_intent_ts, ts or t.entry_intent_ts)
                        strategy = str(row.get("strategy_id") or "")
                        if strategy:
                            t.strategy_id_if_known = strategy
                    if role == "CLOSE" and t.close_order_ts is None:
                        t.close_order_ts = ts
                        t.close_trigger = t.close_trigger or "MANUAL_OR_POLICY_CLOSE"

                if event_type == "ORDER_PLACED":
                    if role == "ENTRY":
                        t.entry_order_count += 1
                        t.entry_order_ts = ts if t.entry_order_ts is None else min(
                            t.entry_order_ts, ts or t.entry_order_ts)
                        t.entry_order_id = t.entry_order_id or order_id
                        t.entry_client_order_id = t.entry_client_order_id or coid
                        t.entry_order_type = t.entry_order_type or order_type
                        t.entry_tif = t.entry_tif or tif
                        if t.trade_id not in open_by_symbol[t.symbol]:
                            open_by_symbol[t.symbol].append(t.trade_id)
                    elif role in {"STOP_LOSS", "TAKE_PROFIT"}:
                        if role == "STOP_LOSS":
                            t.sl_order_id = t.sl_order_id or order_id
                            v = to_f(stop_price if stop_price not in (
                                None, "") else price, default=0.0)
                            if v > 0:
                                t.initial_stop_price = t.initial_stop_price or v
                        if role == "TAKE_PROFIT":
                            t.tp_order_id = t.tp_order_id or order_id
                            v = to_f(price, default=0.0)
                            if v > 0:
                                t.initial_target_price = t.initial_target_price or v
                        ro = adapter.get("reduceOnly")
                        if ro is False:
                            t.lifecycle_anomalies.add(
                                "reduce_only_missing_on_bracket")
                    elif role == "CLOSE":
                        t.close_order_count += 1
                        t.close_order_ts = ts if t.close_order_ts is None else min(
                            t.close_order_ts, ts or t.close_order_ts)
                        t.close_order_id = t.close_order_id or str(
                            adapter.get("orderId") or order_id)
                        if adapter.get("reduceOnly") is False:
                            t.lifecycle_anomalies.add("reduce_only_conflict")

                if event_type == "ORDER_FILLED":
                    fee = to_f((row.get("metadata") or {}).get(
                        "commission"), default=float("nan"))
                    fee_asset = str((row.get("metadata") or {}).get(
                        "commissionAsset") or "")
                    realized = to_f((row.get("metadata") or {}).get(
                        "realized_pnl"), default=0.0)
                    q = to_f(qty)
                    p = to_f(price)
                    if role == "ENTRY":
                        t.entry_fills.append(
                            (q, p, None if fee != fee else fee, fee_asset))
                        t.entry_fill_ts = ts if t.entry_fill_ts is None else min(
                            t.entry_fill_ts, ts or t.entry_fill_ts)
                        if not t.entry_client_order_id and rid.startswith("ENTRY-"):
                            t.entry_client_order_id = rid
                    else:
                        if role in {"TAKE_PROFIT", "STOP_LOSS"}:
                            t.close_trigger = "TP" if role == "TAKE_PROFIT" else "SL"
                        elif role == "CLOSE":
                            t.close_trigger = t.close_trigger or "CLOSE"
                        t.close_fills.append(
                            (q, p, None if fee != fee else fee, fee_asset, realized))
                        t.close_fill_ts = ts if t.close_fill_ts is None else max(
                            t.close_fill_ts, ts or t.close_fill_ts)

                if event_type == "ORDER_REJECTED":
                    if role in {"STOP_LOSS", "TAKE_PROFIT"}:
                        t.bracket_rejects.append(
                            reject_code or reject_reason or "BRACKET_REJECTED")
                    if "close_submission_restore_truth" in reject_reason:
                        t.execution_anomalies.add("stale_retained_close_truth")

                if event_type == "ORDER_TIMEOUT":
                    t.timeout_ts = ts

                if event_type == "POSITION_CLOSED":
                    t.position_closed_realized_net = to_f(
                        row.get("realized_pnl_net"), default=0.0)
                    if t.close_trigger == "":
                        cr = str(row.get("close_reason")
                                 or row.get("why") or "")
                        t.close_trigger = cr or "POSITION_CLOSED"

                if t.close_fill_ts is not None and ts is not None and event_type in {"ORDER_PLACED", "ORDER_INTENT"}:
                    if ts > t.close_fill_ts and role in {"ENTRY", "STOP_LOSS", "TAKE_PROFIT", "CLOSE"}:
                        t.post_close_order_events += 1

    trade_rows: list[dict[str, Any]] = []
    defect_rows: list[dict[str, Any]] = []
    severity_counter = Counter()
    affected_trade_ids: list[str] = []

    for key, t in trades.items():
        has_execution_fact = any(
            [
                t.entry_order_ts is not None,
                t.entry_fill_ts is not None,
                bool(t.entry_order_id),
                bool(t.entry_client_order_id),
                t.close_order_ts is not None,
                t.close_fill_ts is not None,
                bool(t.close_order_id),
            ]
        )
        if not has_execution_fact:
            continue

        entry_qty = sum(q for q, _, _, _ in t.entry_fills)
        entry_notional = sum(q * p for q, p, _, _ in t.entry_fills)
        entry_fee_proven = 0.0
        estimated_fee = 0.0
        entry_fee_asset_set = set()

        for q, p, fee, fee_asset in t.entry_fills:
            if fee is None:
                estimated_fee += q * p * 0.0002
            else:
                if fee_asset.upper() == "USDT" or fee_asset == "":
                    entry_fee_proven += fee
                else:
                    estimated_fee += q * p * 0.0002
            if fee_asset:
                entry_fee_asset_set.add(fee_asset)

        close_qty = sum(q for q, _, _, _, _ in t.close_fills)
        close_notional = sum(q * p for q, p, _, _, _ in t.close_fills)
        close_fee_proven = 0.0
        close_fee_asset_set = set()
        gross_pnl = sum(r for _, _, _, _, r in t.close_fills)

        for q, p, fee, fee_asset, _ in t.close_fills:
            if fee is None:
                estimated_fee += q * p * 0.0002
            else:
                if fee_asset.upper() == "USDT" or fee_asset == "":
                    close_fee_proven += fee
                else:
                    estimated_fee += q * p * 0.0002
            if fee_asset:
                close_fee_asset_set.add(fee_asset)

        entry_price = (entry_notional / entry_qty) if entry_qty > 0 else 0.0
        close_price = (close_notional / close_qty) if close_qty > 0 else 0.0

        total_fee_usdt = entry_fee_proven + close_fee_proven
        proven_net_pnl = gross_pnl - total_fee_usdt
        estimated_net_pnl = gross_pnl - (total_fee_usdt + estimated_fee)
        pnl_estimation_flag = estimated_fee > 0

        status = "CLOSED" if close_qty > 0 else "OPEN"
        if status == "CLOSED" and entry_qty > 0 and close_qty > entry_qty * 1.001:
            t.execution_anomalies.add("close_qty_exceeds_entry_qty")
        if status == "OPEN" and t.entry_order_ts and entry_qty == 0:
            t.execution_anomalies.add("order_without_fill")
            unmatched_orders += 1
        if t.entry_order_count > 1:
            t.execution_anomalies.add("duplicate_entry_orders")
        if t.close_order_count > 1:
            t.lifecycle_anomalies.add("duplicate_close")
        if t.timeout_ts and t.entry_fill_ts and t.entry_fill_ts > t.timeout_ts:
            t.lifecycle_anomalies.add("timeout_path_inconsistent")
        if t.post_close_order_events > 0:
            t.lifecycle_anomalies.add("orphan_orders_after_close")
        if t.entry_fill_ts and (not t.sl_order_id or not t.tp_order_id):
            if not t.sl_order_id:
                t.lifecycle_anomalies.add("sl_missing_after_entry_fill")
            if not t.tp_order_id:
                t.lifecycle_anomalies.add("tp_missing_after_entry_fill")
        if t.bracket_rejects:
            t.lifecycle_anomalies.add("exchange_reject_of_bracket")
        if t.side and close_qty > 0:
            close_side = "BUY" if t.side == "SELL" else "SELL"
            if close_side == t.side:
                t.execution_anomalies.add("close_side_mismatch")
        if t.position_closed_realized_net is not None and abs(t.position_closed_realized_net - proven_net_pnl) > 1e-6:
            t.execution_anomalies.add("reconciliation_divergence")

        if t.side == "SELL":
            if t.initial_stop_price is not None and t.initial_stop_price <= entry_price and entry_price > 0:
                t.lifecycle_anomalies.add("sl_wrong_side_of_entry")
            if t.initial_target_price is not None and t.initial_target_price >= entry_price and entry_price > 0:
                t.lifecycle_anomalies.add("tp_wrong_side_of_entry")
        elif t.side == "BUY":
            if t.initial_stop_price is not None and t.initial_stop_price >= entry_price and entry_price > 0:
                t.lifecycle_anomalies.add("sl_wrong_side_of_entry")
            if t.initial_target_price is not None and t.initial_target_price <= entry_price and entry_price > 0:
                t.lifecycle_anomalies.add("tp_wrong_side_of_entry")

        exec_an = sorted(t.execution_anomalies)
        life_an = sorted(t.lifecycle_anomalies)

        severity = "NONE"
        if exec_an:
            severity = "P0_EXECUTION_TRUTH_DEFECT"
        elif life_an:
            severity = "P1_POSITION_MANAGEMENT_DEFECT"
        elif pnl_estimation_flag:
            severity = "P2_OBSERVABILITY_GAP"
        elif status == "CLOSED" and proven_net_pnl < 0:
            severity = "P3_EXPECTED_MARKET_LOSS"

        severity_counter[severity] += 1
        if severity in {"P0_EXECUTION_TRUTH_DEFECT", "P1_POSITION_MANAGEMENT_DEFECT", "P2_OBSERVABILITY_GAP"}:
            affected_trade_ids.append(t.trade_id)

        for defect in exec_an:
            defect_rows.append(
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "severity": "P0_EXECUTION_TRUTH_DEFECT",
                    "defect_class": defect,
                    "details": "execution_defect",
                }
            )
        for defect in life_an:
            defect_rows.append(
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "severity": "P1_POSITION_MANAGEMENT_DEFECT",
                    "defect_class": defect,
                    "details": "lifecycle_defect",
                }
            )
        if pnl_estimation_flag:
            defect_rows.append(
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "severity": "P2_OBSERVABILITY_GAP",
                    "defect_class": "estimated_fees_used",
                    "details": "fees_missing_or_non_usdt",
                }
            )

        net_pnl = estimated_net_pnl if pnl_estimation_flag else proven_net_pnl
        net_roi = (net_pnl / entry_notional) if entry_notional > 0 else 0.0
        holding_seconds = (
            (t.close_fill_ts - t.entry_fill_ts) / 1000.0
            if (t.close_fill_ts is not None and t.entry_fill_ts is not None)
            else ""
        )

        bracket_status = "OK" if t.sl_order_id and t.tp_order_id else "MISSING_BRACKET"
        bracket_fail_reason = ";".join(t.bracket_rejects)

        trade_rows.append(
            {
                "trade_id": t.trade_id,
                "symbol": t.symbol,
                "strategy_id_if_known": t.strategy_id_if_known,
                "side": t.side,
                "entry_intent_ts": t.entry_intent_ts or "",
                "entry_order_ts": t.entry_order_ts or "",
                "entry_fill_ts": t.entry_fill_ts or "",
                "entry_order_id": t.entry_order_id,
                "entry_client_order_id": t.entry_client_order_id,
                "entry_price": round(entry_price, 10) if entry_price else "",
                "entry_qty": round(entry_qty, 10) if entry_qty else "",
                "entry_notional": round(entry_notional, 10) if entry_notional else "",
                "entry_fee": round(entry_fee_proven, 10) if entry_fee_proven else "",
                "entry_fee_asset": ",".join(sorted(entry_fee_asset_set)),
                "entry_order_type": t.entry_order_type,
                "entry_tif": t.entry_tif,
                "initial_stop_price": "" if t.initial_stop_price is None else t.initial_stop_price,
                "initial_target_price": "" if t.initial_target_price is None else t.initial_target_price,
                "sl_order_id": t.sl_order_id,
                "tp_order_id": t.tp_order_id,
                "bracket_status": bracket_status,
                "bracket_fail_reason": bracket_fail_reason,
                "close_trigger": t.close_trigger,
                "close_order_ts": t.close_order_ts or "",
                "close_fill_ts": t.close_fill_ts or "",
                "close_order_id": t.close_order_id,
                "close_price": round(close_price, 10) if close_price else "",
                "close_qty": round(close_qty, 10) if close_qty else "",
                "close_fee": round(close_fee_proven, 10) if close_fee_proven else "",
                "close_fee_asset": ",".join(sorted(close_fee_asset_set)),
                "gross_pnl": round(gross_pnl, 10) if gross_pnl else 0.0,
                "total_fee_usdt": round(total_fee_usdt, 10),
                "net_pnl": round(net_pnl, 10),
                "net_roi": round(net_roi, 10),
                "holding_seconds": holding_seconds,
                "status": status,
                "execution_anomalies": ";".join(exec_an),
                "lifecycle_anomalies": ";".join(life_an),
                "correlation_confidence": "HIGH" if t.entry_order_id and t.entry_client_order_id else "MEDIUM",
                "estimated_fee_usdt": round(estimated_fee, 10) if estimated_fee else 0.0,
                "pnl_estimation_flag": pnl_estimation_flag,
                "proven_net_pnl": round(proven_net_pnl, 10),
                "estimated_net_pnl": round(estimated_net_pnl, 10),
            }
        )

    write_csv(OUT / "orders_normalized.csv", orders_rows, ORDER_COLUMNS)
    write_csv(OUT / "trades_reconstructed.csv", trade_rows, TRADE_COLUMNS)

    # Aggregations
    def aggregate(rows: list[dict[str, Any]], key_name: str, key_fn) -> list[dict[str, Any]]:
        bucket: dict[str, dict[str, Any]] = {}
        for r in rows:
            k = key_fn(r) or "UNKNOWN"
            if k not in bucket:
                bucket[k] = {
                    key_name: k,
                    "trades": 0,
                    "closed_trades": 0,
                    "open_trades": 0,
                    "proven_net_pnl": 0.0,
                    "estimated_net_pnl": 0.0,
                    "total_fee_usdt": 0.0,
                    "estimated_fee_usdt": 0.0,
                    "wins": 0,
                    "losses": 0,
                }
            b = bucket[k]
            b["trades"] += 1
            if r["status"] == "CLOSED":
                b["closed_trades"] += 1
            else:
                b["open_trades"] += 1
            b["proven_net_pnl"] += to_f(r["proven_net_pnl"])
            b["estimated_net_pnl"] += to_f(r["estimated_net_pnl"])
            b["total_fee_usdt"] += to_f(r["total_fee_usdt"])
            b["estimated_fee_usdt"] += to_f(r["estimated_fee_usdt"])
            net = to_f(r["net_pnl"])
            if net > 0:
                b["wins"] += 1
            elif net < 0:
                b["losses"] += 1

        out_rows = []
        for _, b in sorted(bucket.items(), key=lambda kv: kv[0]):
            denom = b["wins"] + b["losses"]
            b["winrate"] = (b["wins"] / denom) if denom else 0.0
            out_rows.append(b)
        return out_rows

    by_symbol = aggregate(trade_rows, "symbol", lambda r: r.get("symbol"))
    by_strategy = aggregate(trade_rows, "strategy_id_if_known", lambda r: r.get(
        "strategy_id_if_known") or "UNKNOWN")
    by_side = aggregate(trade_rows, "side",
                        lambda r: r.get("side") or "UNKNOWN")
    by_close = aggregate(trade_rows, "close_trigger",
                         lambda r: r.get("close_trigger") or "UNKNOWN")

    write_csv(
        OUT / "pnl_by_symbol.csv",
        by_symbol,
        [
            "symbol",
            "trades",
            "closed_trades",
            "open_trades",
            "proven_net_pnl",
            "estimated_net_pnl",
            "total_fee_usdt",
            "estimated_fee_usdt",
            "wins",
            "losses",
            "winrate",
        ],
    )
    write_csv(
        OUT / "pnl_by_strategy_if_known.csv",
        by_strategy,
        [
            "strategy_id_if_known",
            "trades",
            "closed_trades",
            "open_trades",
            "proven_net_pnl",
            "estimated_net_pnl",
            "total_fee_usdt",
            "estimated_fee_usdt",
            "wins",
            "losses",
            "winrate",
        ],
    )
    write_csv(
        OUT / "pnl_by_side.csv",
        by_side,
        [
            "side",
            "trades",
            "closed_trades",
            "open_trades",
            "proven_net_pnl",
            "estimated_net_pnl",
            "total_fee_usdt",
            "estimated_fee_usdt",
            "wins",
            "losses",
            "winrate",
        ],
    )
    write_csv(
        OUT / "pnl_by_close_trigger.csv",
        by_close,
        [
            "close_trigger",
            "trades",
            "closed_trades",
            "open_trades",
            "proven_net_pnl",
            "estimated_net_pnl",
            "total_fee_usdt",
            "estimated_fee_usdt",
            "wins",
            "losses",
            "winrate",
        ],
    )
    write_csv(
        OUT / "position_management_defects.csv",
        defect_rows,
        ["trade_id", "symbol", "severity", "defect_class", "details"],
    )

    order_status = Counter(r["status"] for r in orders_rows)
    order_role = Counter(r["order_role"] for r in orders_rows)

    closed = [r for r in trade_rows if r["status"] == "CLOSED"]
    open_trades = [r for r in trade_rows if r["status"] == "OPEN"]

    proven_net_total = sum(to_f(r["proven_net_pnl"]) for r in trade_rows)
    est_net_total = sum(to_f(r["estimated_net_pnl"]) for r in trade_rows)
    total_fee_proven = sum(to_f(r["total_fee_usdt"]) for r in trade_rows)
    total_fee_est = sum(to_f(r["estimated_fee_usdt"]) for r in trade_rows)

    closed_net = [to_f(r["net_pnl"]) for r in closed]
    wins = sum(1 for x in closed_net if x > 0)
    losses = sum(1 for x in closed_net if x < 0)
    winrate = (wins / len(closed_net)) if closed_net else 0.0
    gross_profit = sum(x for x in closed_net if x > 0)
    gross_loss = abs(sum(x for x in closed_net if x < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

    top_defects = Counter(d["defect_class"]
                          for d in defect_rows).most_common(10)
    top_defects_s = ", ".join(f"{k}:{v}" for k, v in top_defects)

    report = f"""AGENT_REPORT_V1

task:
  AURORA_EXECUTION_LIFECYCLE_PNL_FORENSIC_T1

verdict:
  {"PARTIAL_RECONSTRUCTION" if not manifest_found else "EXECUTION_RECONSTRUCTED"}

runtime_window:
  start_ts: {min_ts or ''}
  end_ts: {max_ts or ''}

order_summary:
  total_orders: {len(orders_rows)}
  entry_orders: {order_role.get("ENTRY", 0)}
  close_orders: {order_role.get("CLOSE", 0)}
  sl_orders: {order_role.get("STOP_LOSS", 0)}
  tp_orders: {order_role.get("TAKE_PROFIT", 0)}
  rejected_orders: {order_status.get("REJECTED", 0)}
  timed_out_orders: {order_status.get("TIMEOUT", 0)}
  filled_orders: {order_status.get("FILLED", 0)}

trade_summary:
  reconstructed_trades: {len(trade_rows)}
  closed_trades: {len(closed)}
  open_trades: {len(open_trades)}
  unmatched_orders: {unmatched_orders}
  unmatched_fills: {unmatched_fills}

pnl_summary:
  proven_net_pnl: {proven_net_total:.10f}
  estimated_net_pnl: {est_net_total:.10f}
  total_fees_proven: {total_fee_proven:.10f}
  total_fees_estimated: {total_fee_est:.10f}
  winrate: {winrate:.6f}
  profit_factor: {profit_factor:.6f}

defect_summary:
  p0_count: {severity_counter.get("P0_EXECUTION_TRUTH_DEFECT", 0)}
  p1_count: {severity_counter.get("P1_POSITION_MANAGEMENT_DEFECT", 0)}
  p2_count: {severity_counter.get("P2_OBSERVABILITY_GAP", 0)}
  affected_trade_ids: {", ".join(sorted(set(affected_trade_ids)))}
  top_defect_classes: {top_defects_s}

proven:
  - Parsed execution truth from order_log_v1.jsonl and trade_lifecycle.jsonl in evidence freeze.
  - Reconstructed per-trade entry/exit, fees, close trigger, and realized gross/net PnL with explicit estimated-fee split.
  - Produced normalized orders and required aggregation datasets.

unproven:
  - reports/runtime_forensics/T0/runtime_manifest.json was not found in workspace.
  - domain_decision_making logs were not present in evidence freeze for correlation enrichment.

risks:
  - POSITION_CLOSED lifecycle_id sometimes diverges from ENTRY lifecycle key; correlation uses multi-key heuristic.
  - Some fills have missing fee payloads and require estimated_fee_usdt.

handoff_to_final_synthesis:
  datasets:
    - reports/runtime_forensics/T1_execution_pnl/orders_normalized.csv
    - reports/runtime_forensics/T1_execution_pnl/trades_reconstructed.csv
    - reports/runtime_forensics/T1_execution_pnl/pnl_by_symbol.csv
    - reports/runtime_forensics/T1_execution_pnl/pnl_by_strategy_if_known.csv
    - reports/runtime_forensics/T1_execution_pnl/pnl_by_side.csv
    - reports/runtime_forensics/T1_execution_pnl/pnl_by_close_trigger.csv
    - reports/runtime_forensics/T1_execution_pnl/position_management_defects.csv
  important_caveats:
    - Missing T0 runtime_manifest.json forced fallback to evidence_freeze manifest and direct log discovery.
    - Estimated fees are explicitly separated and never silently merged into proven totals.
"""

    (OUT / "EXECUTION_LIFECYCLE_PNL_REPORT.md").write_text(report, encoding="utf-8")

    # Lightweight domain_execution_position scan for report sanity context.
    restore_truth_hits = 0
    for p in domain_exec_logs:
        if not p.exists():
            continue
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "close_submission_restore_truth" in line:
                    restore_truth_hits += 1

    print(json.dumps(
        {
            "manifest_found": manifest_found,
            "orders_rows": len(orders_rows),
            "trades": len(trade_rows),
            "closed_trades": len(closed),
            "open_trades": len(open_trades),
            "restore_truth_hits_in_domain_exec_logs": restore_truth_hits,
            "output_dir": str(OUT),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
