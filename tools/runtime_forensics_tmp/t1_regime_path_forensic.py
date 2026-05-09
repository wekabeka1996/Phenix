from __future__ import annotations

import csv
import json
import math
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "reports" / "runtime_forensics" / "T1_regime_path"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REQ_MANIFEST = ROOT / "reports" / \
    "runtime_forensics" / "T0" / "runtime_manifest.json"
FALLBACK_MANIFEST = ROOT / "reports" / "forensics" / \
    "r7q_long_window_data" / "evidence_freeze" / "R7Q_A_EVIDENCE_MANIFEST.csv"
AGENT2_CSV = ROOT / "reports" / "runtime_forensics" / \
    "T1_execution_pnl" / "trades_reconstructed.csv"


def to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        if isinstance(v, str) and not v.strip():
            return None
        return float(v)
    except Exception:
        return None


def to_int(v: Any) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def iso_utc(ts_ms: int | None) -> str:
    if ts_ms is None:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def side_norm(side: str | None) -> str:
    s = (side or "").upper()
    if s in {"BUY", "LONG"}:
        return "LONG"
    if s in {"SELL", "SHORT"}:
        return "SHORT"
    return "UNKNOWN"


def confidence_bucket(c: float | None) -> str:
    if c is None:
        return "UNKNOWN"
    if c < 0.2:
        return "VERY_LOW"
    if c < 0.35:
        return "LOW"
    if c < 0.6:
        return "MEDIUM"
    if c < 0.8:
        return "HIGH"
    return "VERY_HIGH"


def recursive_pick(d: Any, keys: set[str]) -> float | None:
    if isinstance(d, dict):
        for k, v in d.items():
            kl = str(k).lower()
            if kl in keys:
                f = to_float(v)
                if f is not None:
                    return f
            found = recursive_pick(v, keys)
            if found is not None:
                return found
    elif isinstance(d, list):
        for x in d:
            found = recursive_pick(x, keys)
            if found is not None:
                return found
    return None


@dataclass
class RegimePoint:
    ts_ms: int
    regime: str
    confidence: float | None


def nearest_regime(points: list[RegimePoint], ts_ms: int | None, max_gap_ms: int = 600_000) -> tuple[str, float | None, int | None]:
    if ts_ms is None or not points:
        return "UNKNOWN", None, None
    arr = [p.ts_ms for p in points]
    idx = bisect_left(arr, ts_ms)
    cand: list[RegimePoint] = []
    if idx < len(points):
        cand.append(points[idx])
    if idx > 0:
        cand.append(points[idx - 1])
    if not cand:
        return "UNKNOWN", None, None
    best = min(cand, key=lambda p: abs(p.ts_ms - ts_ms))
    dt = abs(best.ts_ms - ts_ms)
    if dt > max_gap_ms:
        return "UNKNOWN", None, dt
    return best.regime or "UNKNOWN", best.confidence, dt


def load_runtime_inputs() -> tuple[Path, Path, Path, Path, dict[str, Any]]:
    runtime_notes: dict[str, Any] = {
        "required_runtime_manifest_path": str(REQ_MANIFEST),
        "required_runtime_manifest_found": REQ_MANIFEST.exists(),
        "fallback_manifest_path": str(FALLBACK_MANIFEST),
        "fallback_manifest_found": FALLBACK_MANIFEST.exists(),
        "agent2_trades_reconstructed_path": str(AGENT2_CSV),
        "agent2_trades_reconstructed_found": AGENT2_CSV.exists(),
    }
    logs_dir = ROOT / "logs"
    evidence_logs_dir = ROOT / "reports" / "forensics" / \
        "r7q_long_window_data" / "evidence_freeze" / "logs"
    if evidence_logs_dir.exists():
        logs_dir = evidence_logs_dir
        runtime_notes["logs_source"] = "evidence_freeze"
    else:
        runtime_notes["logs_source"] = "live_logs"

    order_log = logs_dir / "order_log_v1.jsonl"
    trade_log = logs_dir / "trade_lifecycle.jsonl"

    regime_log = ROOT / "logs" / "regime_confidence_audit_v1.jsonl"
    if not regime_log.exists():
        regime_log = logs_dir / "regime_confidence_audit_v1.jsonl"

    return order_log, trade_log, regime_log, AGENT2_CSV, runtime_notes


def parse_trade_candidates(order_log: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    trades: dict[str, dict[str, Any]] = {}
    entry_agg: dict[str, dict[str, float]] = defaultdict(
        lambda: {"qty": 0.0, "px_qty": 0.0, "first_ts": math.inf})
    client_to_lifecycle: dict[str, str] = {}

    with order_log.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue

            et = row.get("event_type")
            ts = to_int(row.get("timestamp") or row.get("ts_ms"))

            if et == "ORDER_INTENT" and row.get("source_fsm") == "DecisionMaking":
                rid = row.get("rid") or row.get("lifecycle_id")
                if not rid:
                    continue
                t = trades.setdefault(rid, {})
                t["trade_id"] = rid
                t.setdefault("symbol", row.get("symbol"))
                t.setdefault("strategy_id", row.get("strategy_id"))
                t.setdefault("side", side_norm(row.get("side")))
                t.setdefault("signal_ts", ts)
                t.setdefault("entry_price", to_float(row.get("price")))
                t.setdefault("regime_signal_log",
                             row.get("regime") or "UNKNOWN")
                t.setdefault("regime_signal_conf_log",
                             to_float(row.get("regime_confidence")))

            if et == "ORDER_PLACED":
                cid = row.get("client_order_id")
                lid = row.get("rid") or row.get("lifecycle_id")
                if cid and lid:
                    client_to_lifecycle[str(cid)] = str(lid)

            if et == "ORDER_FILLED" and (row.get("order_kind") or "").upper() == "ENTRY":
                lid = row.get("lifecycle_id")
                if not lid:
                    continue
                t = trades.setdefault(lid, {"trade_id": lid})
                t.setdefault("symbol", row.get("symbol"))
                t.setdefault("side", side_norm(row.get("side")))
                px = to_float(row.get("price"))
                qty = to_float(row.get("quantity"))
                if qty is None:
                    qty = 0.0
                if px is not None and qty > 0:
                    entry_agg[lid]["qty"] += qty
                    entry_agg[lid]["px_qty"] += px * qty
                if ts is not None:
                    entry_agg[lid]["first_ts"] = min(
                        entry_agg[lid]["first_ts"], float(ts))

            if et == "POSITION_CLOSED":
                lid = row.get("lifecycle_id") or row.get("rid")
                if not lid:
                    continue
                t = trades.setdefault(lid, {"trade_id": lid})
                t.setdefault("symbol", row.get("symbol"))
                t.setdefault("side", side_norm(row.get("side")))
                t["exit_ts"] = ts
                t["exit_price"] = to_float(
                    (row.get("metadata") or {}).get("close_price"))

    for lid, agg in entry_agg.items():
        t = trades.setdefault(lid, {"trade_id": lid})
        if agg["qty"] > 0:
            t["entry_price"] = agg["px_qty"] / agg["qty"]
        if agg["first_ts"] != math.inf:
            t["entry_ts"] = int(agg["first_ts"])

    return trades, client_to_lifecycle


def merge_agent2_rows(
        agent2_csv: Path,
        trades: dict[str, dict[str, Any]],
        client_to_lifecycle: dict[str, str],
        runtime_notes: dict[str, Any],
) -> None:
    if not agent2_csv.exists():
        runtime_notes["agent2_rows_read"] = 0
        runtime_notes["agent2_rows_merged"] = 0
        return

    total = 0
    merged = 0
    with agent2_csv.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            trade_id = (row.get("trade_id") or "").strip()
            if not trade_id or not trade_id.startswith("ENTRY-"):
                continue
            lid = client_to_lifecycle.get(trade_id) or trade_id
            t = trades.setdefault(lid, {"trade_id": lid})
            t.setdefault("symbol", row.get("symbol"))
            t.setdefault("strategy_id", row.get("strategy_id_if_known") or "")
            t.setdefault("side", side_norm(row.get("side")))
            t.setdefault("entry_ts", to_int(row.get("entry_fill_ts") or row.get(
                "entry_order_ts") or row.get("entry_intent_ts")))
            t.setdefault("entry_price", to_float(row.get("entry_price")))
            if t.get("exit_ts") is None:
                t["exit_ts"] = to_int(
                    row.get("close_fill_ts") or row.get("close_order_ts"))
            if t.get("exit_price") is None:
                t["exit_price"] = to_float(row.get("close_price"))
            if t.get("stop_price") is None:
                t["stop_price"] = to_float(row.get("initial_stop_price"))
            if t.get("target_price") is None:
                t["target_price"] = to_float(row.get("initial_target_price"))
            t["agent2_row_seen"] = True
            merged += 1

    runtime_notes["agent2_rows_read"] = total
    runtime_notes["agent2_rows_merged"] = merged


def enrich_from_trade_lifecycle(trades: dict[str, dict[str, Any]], trade_log: Path) -> None:
    stop_keys = {"stop_price", "sl_price", "stop_loss_price", "stoploss_price"}
    target_keys = {"target_price", "tp_price",
                   "take_profit_price", "takeprofit_price"}

    with trade_log.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            rid = row.get("rid") or row.get("lifecycle_id")
            if rid not in trades:
                continue
            t = trades[rid]

            if row.get("event_type") == "TRADE_LIFECYCLE_FILLED":
                t.setdefault("strategy_id", row.get("strategy_id"))
                t.setdefault("side", side_norm(row.get("side")))
                t.setdefault("symbol", row.get("symbol"))
                t.setdefault("entry_ts", to_int(row.get("fill_ts_ms")))
                t.setdefault("entry_price", to_float(row.get("fill_price")))

                if t.get("signal_ts") is None:
                    t["signal_ts"] = to_int(row.get("intent_ts_ms"))
                if t.get("regime_signal_log") is None and row.get("regime"):
                    t["regime_signal_log"] = row.get("regime")
                if t.get("regime_signal_conf_log") is None:
                    t["regime_signal_conf_log"] = to_float(
                        row.get("regime_confidence"))

                if t.get("stop_price") is None:
                    t["stop_price"] = recursive_pick(row, stop_keys)
                if t.get("target_price") is None:
                    t["target_price"] = recursive_pick(row, target_keys)


def load_regime_series(regime_log: Path) -> tuple[dict[str, list[RegimePoint]], dict[str, tuple[str, float | None, int | None]]]:
    by_symbol: dict[str, list[RegimePoint]] = defaultdict(list)
    by_rid_decision: dict[str, tuple[str, float | None, int | None]] = {}

    if not regime_log.exists():
        return by_symbol, by_rid_decision

    with regime_log.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            rtype = row.get("record_type")
            if rtype == "bar_close":
                sym = row.get("symbol")
                ts = to_int(row.get("ts_ms") or row.get("bar_close_ts_ms"))
                if not sym or ts is None:
                    continue
                conf = to_float(row.get("emitted_confidence"))
                if conf is None:
                    conf = to_float(row.get("stable_confidence"))
                by_symbol[sym].append(RegimePoint(ts_ms=ts, regime=row.get(
                    "regime") or "UNKNOWN", confidence=conf))
            elif rtype == "decision":
                rid = row.get("rid")
                if rid:
                    by_rid_decision[rid] = (
                        row.get("regime_used") or "UNKNOWN",
                        to_float(row.get("regime_confidence_used")),
                        to_int(row.get("ts_ms")),
                    )

    for sym in by_symbol:
        by_symbol[sym].sort(key=lambda p: p.ts_ms)

    return by_symbol, by_rid_decision


def daterange_utc(start_ts_ms: int, end_ts_ms: int) -> list[str]:
    start = datetime.fromtimestamp(start_ts_ms / 1000, tz=timezone.utc).date()
    end = datetime.fromtimestamp(end_ts_ms / 1000, tz=timezone.utc).date()
    out = []
    cur = start
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def choose_tf(symbol: str, dates: list[str], preferred: tuple[int, ...] = (300, 180, 900)) -> int | None:
    for tf in preferred:
        for d in dates:
            p = ROOT / "data" / "recorder" / d / f"{symbol}_{tf}.csv"
            if p.exists():
                return tf
    return None


def load_recorder_rows(symbol: str, start_ts: int, end_ts: int) -> tuple[int | None, list[dict[str, Any]], str]:
    if end_ts < start_ts:
        return None, [], "bad_time_window"

    dates = daterange_utc(start_ts, end_ts)
    tf = choose_tf(symbol, dates)
    if tf is None:
        return None, [], "recorder_file_not_found"

    rows: list[dict[str, Any]] = []
    for d in dates:
        p = ROOT / "data" / "recorder" / d / f"{symbol}_{tf}.csv"
        if not p.exists():
            continue
        with p.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = to_int(row.get("timestamp"))
                if ts is None:
                    continue
                if start_ts <= ts <= end_ts:
                    high = to_float(row.get("high"))
                    low = to_float(row.get("low"))
                    close = to_float(row.get("close"))
                    if high is None or low is None or close is None:
                        continue
                    rows.append({"ts": ts, "high": high,
                                "low": low, "close": close})
    rows.sort(key=lambda r: r["ts"])
    if not rows:
        return tf, [], "no_rows_in_window"
    return tf, rows, ""


def compute_path_metrics(tr: dict[str, Any]) -> dict[str, Any]:
    side = side_norm(tr.get("side"))
    entry_ts = to_int(tr.get("entry_ts"))
    entry_price = to_float(tr.get("entry_price"))
    exit_ts = to_int(tr.get("exit_ts"))
    exit_price = to_float(tr.get("exit_price"))
    symbol = tr.get("symbol")

    out: dict[str, Any] = {
        "recorder_tf_sec": None,
        "recorder_rows_used": 0,
        "path_available": False,
        "path_missing_reason": "",
        "mfe_price": None,
        "mae_price": None,
        "mfe_roi": None,
        "mae_roi": None,
        "peak_roi": None,
        "final_roi": None,
        "giveback_ratio": None,
        "bars_to_mfe": None,
        "bars_to_mae": None,
        "tp_touched": False,
        "sl_touched": False,
        "tp_touch_ts": None,
        "sl_touch_ts": None,
        "tp_before_sl": None,
        "sl_before_tp": None,
    }

    if not symbol or entry_ts is None or entry_price in (None, 0.0) or side not in {"LONG", "SHORT"}:
        out["path_missing_reason"] = "missing_symbol_or_entry"
        return out

    if exit_ts is None:
        # Candidate without resolved close: bounded provisional horizon.
        exit_ts = entry_ts + 3_600_000

    tf, rows, reason = load_recorder_rows(
        symbol=symbol, start_ts=entry_ts, end_ts=exit_ts)
    out["recorder_tf_sec"] = tf
    out["recorder_rows_used"] = len(rows)
    if not rows:
        out["path_missing_reason"] = reason
        return out

    out["path_available"] = True

    best_roi = -10**9
    worst_roi = 10**9
    best_idx = None
    worst_idx = None
    mfe_price = None
    mae_price = None

    for i, r in enumerate(rows):
        high = r["high"]
        low = r["low"]
        if side == "LONG":
            cand_best = (high - entry_price) / entry_price
            cand_worst = (low - entry_price) / entry_price
            cand_mfe_price = high
            cand_mae_price = low
        else:
            cand_best = (entry_price - low) / entry_price
            cand_worst = (entry_price - high) / entry_price
            cand_mfe_price = low
            cand_mae_price = high

        if cand_best > best_roi:
            best_roi = cand_best
            best_idx = i
            mfe_price = cand_mfe_price
        if cand_worst < worst_roi:
            worst_roi = cand_worst
            worst_idx = i
            mae_price = cand_mae_price

    if exit_price is None:
        close_last = rows[-1]["close"]
        if side == "LONG":
            final_roi = (close_last - entry_price) / entry_price
        else:
            final_roi = (entry_price - close_last) / entry_price
    else:
        if side == "LONG":
            final_roi = (exit_price - entry_price) / entry_price
        else:
            final_roi = (entry_price - exit_price) / entry_price

    giveback = None
    if best_roi is not None and final_roi is not None and best_roi > 0:
        giveback = max(0.0, (best_roi - final_roi) / best_roi)

    out.update(
        {
            "mfe_price": mfe_price,
            "mae_price": mae_price,
            "mfe_roi": best_roi,
            "mae_roi": worst_roi,
            "peak_roi": best_roi,
            "final_roi": final_roi,
            "giveback_ratio": giveback,
            "bars_to_mfe": best_idx,
            "bars_to_mae": worst_idx,
        }
    )

    target = to_float(tr.get("target_price"))
    stop = to_float(tr.get("stop_price"))
    if target is None or stop is None:
        out["path_missing_reason"] = "missing_stop_target_prices"
        return out

    ambiguous = False
    tp_ts = None
    sl_ts = None
    for r in rows:
        high = r["high"]
        low = r["low"]
        ts = r["ts"]
        if side == "LONG":
            hit_tp = high >= target
            hit_sl = low <= stop
        else:
            hit_tp = low <= target
            hit_sl = high >= stop

        if hit_tp and hit_sl:
            ambiguous = True
            tp_ts = ts
            sl_ts = ts
            break
        if hit_tp and tp_ts is None:
            tp_ts = ts
        if hit_sl and sl_ts is None:
            sl_ts = ts

    out["tp_touched"] = tp_ts is not None
    out["sl_touched"] = sl_ts is not None
    out["tp_touch_ts"] = tp_ts
    out["sl_touch_ts"] = sl_ts
    if ambiguous:
        out["tp_before_sl"] = "AMBIGUOUS_SAME_CANDLE"
        out["sl_before_tp"] = "AMBIGUOUS_SAME_CANDLE"
    elif tp_ts is not None and sl_ts is not None:
        out["tp_before_sl"] = tp_ts < sl_ts
        out["sl_before_tp"] = sl_ts < tp_ts
    elif tp_ts is not None:
        out["tp_before_sl"] = True
        out["sl_before_tp"] = False
    elif sl_ts is not None:
        out["tp_before_sl"] = False
        out["sl_before_tp"] = True
    return out


def classify_bucket(row: dict[str, Any]) -> str:
    if not row.get("path_available"):
        return "PATH_UNPROVEN"

    reg_entry = row.get("regime_at_entry")
    reg_exit = row.get("regime_at_exit")
    if reg_entry not in {None, "", "UNKNOWN"} and reg_exit not in {None, "", "UNKNOWN"} and reg_entry != reg_exit:
        return "REGIME_SHIFT_AFTER_ENTRY"

    final_roi = to_float(row.get("final_roi"))
    peak_roi = to_float(row.get("peak_roi"))
    giveback = to_float(row.get("giveback_ratio"))
    bars_to_mae = to_int(row.get("bars_to_mae"))

    if final_roi is not None and abs(final_roi) <= 0.0005:
        return "FEE_ONLY_OR_NEAR_FLAT"
    if peak_roi is None or peak_roi <= 0.0002:
        return "NO_EDGE_NO_PROGRESS"
    if giveback is not None and giveback >= 0.7 and final_roi is not None and final_roi <= peak_roi * 0.3:
        return "EDGE_EARNED_THEN_GAVE_BACK"
    if final_roi is not None and final_roi < 0 and bars_to_mae is not None and bars_to_mae <= 1:
        return "BAD_ENTRY_IMMEDIATE"
    if final_roi is not None and final_roi < peak_roi * 0.4:
        return "GOOD_ENTRY_BAD_EXIT"
    return "UNKNOWN"


def evidence_confidence(row: dict[str, Any]) -> str:
    n_reg = sum(
        1
        for k in ["regime_at_signal", "regime_at_entry", "regime_at_exit"]
        if (row.get(k) or "UNKNOWN") != "UNKNOWN"
    )
    path = bool(row.get("path_available"))
    has_tp_sl = to_float(row.get("target_price")) is not None and to_float(
        row.get("stop_price")) is not None
    if n_reg == 3 and path and has_tp_sl:
        return "HIGH"
    if n_reg >= 2 and path:
        return "MEDIUM"
    if n_reg >= 1 or path:
        return "LOW"
    return "UNPROVEN"


def main() -> None:
    order_log, trade_log, regime_log, agent2_csv, runtime_notes = load_runtime_inputs()

    trades, client_to_lifecycle = parse_trade_candidates(order_log)
    merge_agent2_rows(agent2_csv, trades, client_to_lifecycle, runtime_notes)
    enrich_from_trade_lifecycle(trades, trade_log)
    regime_by_symbol, regime_by_rid = load_regime_series(regime_log)

    rows: list[dict[str, Any]] = []
    unknown_regime_count = 0
    conf_buckets = Counter()
    ambiguous_count = 0

    for trade_id in sorted(trades.keys()):
        t = trades[trade_id]
        symbol = t.get("symbol")
        signal_ts = to_int(t.get("signal_ts"))
        entry_ts = to_int(t.get("entry_ts"))
        exit_ts = to_int(t.get("exit_ts"))

        if trade_id in regime_by_rid:
            reg_s, conf_s, _ = regime_by_rid[trade_id]
            dt_s = 0
        else:
            reg_s, conf_s, dt_s = nearest_regime(
                regime_by_symbol.get(symbol, []), signal_ts)
            if reg_s == "UNKNOWN":
                reg_s = t.get("regime_signal_log") or "UNKNOWN"
                conf_s = to_float(t.get("regime_signal_conf_log"))

        reg_e, conf_e, dt_e = nearest_regime(
            regime_by_symbol.get(symbol, []), entry_ts)
        reg_x, conf_x, dt_x = nearest_regime(
            regime_by_symbol.get(symbol, []), exit_ts)

        if reg_s == "UNKNOWN" or reg_e == "UNKNOWN" or reg_x == "UNKNOWN":
            unknown_regime_count += 1

        conf_buckets[confidence_bucket(conf_s)] += 1
        conf_buckets[confidence_bucket(conf_e)] += 1
        conf_buckets[confidence_bucket(conf_x)] += 1

        reg_score_parts = []
        for dt in [dt_s, dt_e, dt_x]:
            if dt is None:
                continue
            reg_score_parts.append(max(0.0, 1.0 - (dt / 600_000)))
        regime_corr_conf = mean(reg_score_parts) if reg_score_parts else 0.0

        path = compute_path_metrics(t)
        if path.get("tp_before_sl") == "AMBIGUOUS_SAME_CANDLE":
            ambiguous_count += 1

        row = {
            "trade_id": trade_id,
            "symbol": symbol or "",
            "strategy_id": t.get("strategy_id") or "",
            "side": side_norm(t.get("side")),
            "entry_ts": entry_ts,
            "entry_price": to_float(t.get("entry_price")),
            "exit_ts": exit_ts,
            "exit_price": to_float(t.get("exit_price")),
            "stop_price": to_float(t.get("stop_price")),
            "target_price": to_float(t.get("target_price")),
            "regime_at_signal": reg_s,
            "regime_confidence_at_signal": conf_s,
            "regime_at_entry": reg_e,
            "regime_confidence_at_entry": conf_e,
            "regime_at_exit": reg_x,
            "regime_confidence_at_exit": conf_x,
            "regime_correlation_confidence": regime_corr_conf,
            **path,
        }
        row["path_bucket"] = classify_bucket(row)
        row["evidence_confidence"] = evidence_confidence(row)
        rows.append(row)

    cols = [
        "trade_id",
        "symbol",
        "strategy_id",
        "side",
        "entry_ts",
        "entry_price",
        "exit_ts",
        "exit_price",
        "stop_price",
        "target_price",
        "regime_at_signal",
        "regime_confidence_at_signal",
        "regime_at_entry",
        "regime_confidence_at_entry",
        "regime_at_exit",
        "regime_confidence_at_exit",
        "regime_correlation_confidence",
        "recorder_tf_sec",
        "recorder_rows_used",
        "path_available",
        "path_missing_reason",
        "mfe_price",
        "mae_price",
        "mfe_roi",
        "mae_roi",
        "peak_roi",
        "final_roi",
        "giveback_ratio",
        "bars_to_mfe",
        "bars_to_mae",
        "tp_touched",
        "sl_touched",
        "tp_touch_ts",
        "sl_touch_ts",
        "tp_before_sl",
        "sl_before_tp",
        "path_bucket",
        "evidence_confidence",
    ]

    out_main = OUT_DIR / "trade_regime_path_metrics.csv"
    with out_main.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    by_regime = defaultdict(list)
    for r in rows:
        by_regime[r.get("regime_at_entry") or "UNKNOWN"].append(r)
    out_reg = OUT_DIR / "pnl_path_by_regime.csv"
    with out_reg.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["regime_at_entry", "trade_count", "avg_final_roi",
                   "median_final_roi", "avg_peak_roi", "avg_giveback_ratio"])
        for reg, rs in sorted(by_regime.items()):
            finals = [to_float(x.get("final_roi"))
                      for x in rs if to_float(x.get("final_roi")) is not None]
            peaks = [to_float(x.get("peak_roi"))
                     for x in rs if to_float(x.get("peak_roi")) is not None]
            gbs = [to_float(x.get("giveback_ratio")) for x in rs if to_float(
                x.get("giveback_ratio")) is not None]
            w.writerow(
                [
                    reg,
                    len(rs),
                    mean(finals) if finals else "",
                    median(finals) if finals else "",
                    mean(peaks) if peaks else "",
                    mean(gbs) if gbs else "",
                ]
            )

    out_bucket = OUT_DIR / "path_buckets_by_symbol.csv"
    bucket_counter = Counter(
        (r.get("symbol"), r.get("path_bucket")) for r in rows)
    with out_bucket.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "path_bucket", "count"])
        for (sym, bucket), c in sorted(bucket_counter.items()):
            w.writerow([sym, bucket, c])

    giveback_cases = [r for r in rows if to_float(r.get(
        "giveback_ratio")) is not None and to_float(r.get("giveback_ratio")) >= 0.5]
    giveback_cases.sort(key=lambda x: to_float(
        x.get("giveback_ratio")) or 0.0, reverse=True)
    out_give = OUT_DIR / "giveback_cases.csv"
    with out_give.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "trade_id",
                "symbol",
                "regime_at_entry",
                "regime_at_exit",
                "peak_roi",
                "final_roi",
                "giveback_ratio",
                "path_bucket",
            ],
        )
        w.writeheader()
        for r in giveback_cases:
            w.writerow({k: r.get(k) for k in w.fieldnames})

    transition_cases = [
        r
        for r in rows
        if (r.get("regime_at_signal") not in {"", None, "UNKNOWN"} and r.get("regime_at_entry") not in {"", None, "UNKNOWN"} and r.get("regime_at_signal") != r.get("regime_at_entry"))
        or (r.get("regime_at_entry") not in {"", None, "UNKNOWN"} and r.get("regime_at_exit") not in {"", None, "UNKNOWN"} and r.get("regime_at_entry") != r.get("regime_at_exit"))
    ]
    out_trans = OUT_DIR / "regime_transition_cases.csv"
    with out_trans.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "trade_id",
                "symbol",
                "regime_at_signal",
                "regime_at_entry",
                "regime_at_exit",
                "regime_confidence_at_signal",
                "regime_confidence_at_entry",
                "regime_confidence_at_exit",
                "final_roi",
                "path_bucket",
            ],
        )
        w.writeheader()
        for r in transition_cases:
            w.writerow({k: r.get(k) for k in w.fieldnames})

    start_ts = min((to_int(r.get("signal_ts")) or to_int(
        r.get("entry_ts")) or 2**63 - 1) for r in trades.values()) if trades else None
    end_ts = max((to_int(r.get("exit_ts")) or to_int(r.get("entry_ts")) or 0)
                 for r in trades.values()) if trades else None
    if start_ts == 2**63 - 1:
        start_ts = None

    with_path = sum(1 for r in rows if r.get("path_available"))
    verdict = "BLOCKED"
    if rows:
        if with_path == 0:
            verdict = "BLOCKED"
        elif with_path < len(rows):
            verdict = "PARTIAL_PATH_RECONSTRUCTION"
        else:
            verdict = "PATH_RECONSTRUCTED"

    report = OUT_DIR / "REGIME_RECORDER_PATH_REPORT.md"
    edge_giveback = [r for r in rows if r.get(
        "path_bucket") == "EDGE_EARNED_THEN_GAVE_BACK"]
    edge_giveback.sort(key=lambda x: to_float(
        x.get("giveback_ratio")) or 0.0, reverse=True)

    signal_reg_cnt = sum(1 for r in rows if (
        r.get("regime_at_signal") or "UNKNOWN") != "UNKNOWN")
    entry_reg_cnt = sum(1 for r in rows if (
        r.get("regime_at_entry") or "UNKNOWN") != "UNKNOWN")
    exit_reg_cnt = sum(1 for r in rows if (
        r.get("regime_at_exit") or "UNKNOWN") != "UNKNOWN")

    sig_to_entry_shift = sum(
        1
        for r in rows
        if (r.get("regime_at_signal") not in {"", None, "UNKNOWN"} and r.get("regime_at_entry") not in {"", None, "UNKNOWN"} and r.get("regime_at_signal") != r.get("regime_at_entry"))
    )
    entry_to_exit_shift = sum(
        1
        for r in rows
        if (r.get("regime_at_entry") not in {"", None, "UNKNOWN"} and r.get("regime_at_exit") not in {"", None, "UNKNOWN"} and r.get("regime_at_entry") != r.get("regime_at_exit"))
    )

    toxic = [
        r
        for r in transition_cases
        if to_float(r.get("final_roi")) is not None and to_float(r.get("final_roi")) < 0
    ]

    with report.open("w", encoding="utf-8") as f:
        f.write("AGENT_REPORT_V1\n\n")
        f.write("task:\n")
        f.write("  AURORA_REGIME_AND_RECORDER_PATH_FORENSIC_T1\n\n")
        f.write("verdict:\n")
        f.write(f"  {verdict}\n\n")
        f.write("runtime_window:\n")
        f.write(f"  start_ts: {start_ts}\n")
        f.write(f"  end_ts: {end_ts}\n\n")

        f.write("regime_summary:\n")
        f.write(f"  trades_with_signal_regime: {signal_reg_cnt}\n")
        f.write(f"  trades_with_entry_regime: {entry_reg_cnt}\n")
        f.write(f"  trades_with_exit_regime: {exit_reg_cnt}\n")
        f.write(f"  unknown_regime_count: {unknown_regime_count}\n")
        f.write(f"  regime_confidence_buckets: {dict(conf_buckets)}\n\n")

        f.write("path_summary:\n")
        f.write(f"  trades_with_recorder_path: {with_path}\n")
        f.write(f"  trades_without_recorder_path: {len(rows) - with_path}\n")
        f.write(
            f"  mfe_mae_available_count: {sum(1 for r in rows if r.get('mfe_roi') is not None and r.get('mae_roi') is not None)}\n")
        f.write(f"  ambiguous_same_candle_count: {ambiguous_count}\n\n")

        f.write("giveback_summary:\n")
        f.write(f"  edge_earned_then_gave_back_count: {len(edge_giveback)}\n")
        f.write("  largest_giveback_cases:\n")
        for r in edge_giveback[:5]:
            f.write(
                f"  - {r.get('trade_id')} {r.get('symbol')} giveback={r.get('giveback_ratio')} peak={r.get('peak_roi')} final={r.get('final_roi')}\n"
            )
        f.write("  possible_profit_lock_cases:\n")
        for r in giveback_cases[:5]:
            f.write(
                f"  - {r.get('trade_id')} {r.get('symbol')} giveback={r.get('giveback_ratio')}\n")
        f.write("\n")

        f.write("regime_transition_summary:\n")
        f.write(f"  signal_to_entry_shift_count: {sig_to_entry_shift}\n")
        f.write(f"  entry_to_exit_shift_count: {entry_to_exit_shift}\n")
        f.write("  toxic_transition_candidates:\n")
        for r in toxic[:8]:
            f.write(
                f"  - {r.get('trade_id')} {r.get('symbol')} {r.get('regime_at_entry')}->{r.get('regime_at_exit')} final_roi={r.get('final_roi')}\n"
            )
        f.write("\n")

        f.write("proven:\n")
        f.write(f"  - Parsed runtime regime from {regime_log}\n")
        f.write(f"  - Reconstructed trade candidates from {order_log}\n")
        f.write(
            f"  - Generated recorder path metrics for {with_path}/{len(rows)} rows\n\n")

        f.write("unproven:\n")
        if not runtime_notes["required_runtime_manifest_found"]:
            f.write(
                "  - Required T0 runtime_manifest.json missing at specified path; fallback evidence manifest used\n")
        if not runtime_notes["agent2_trades_reconstructed_found"]:
            f.write(
                "  - Agent 2 trades_reconstructed.csv unavailable; trade table is provisional from logs\n")
        f.write(
            "  - TP/SL touch order unproven when stop/target prices absent in runtime logs\n\n")

        f.write("risks:\n")
        f.write(
            "  - Potential trade linkage drift where lifecycle IDs are absent on close events\n")
        f.write(
            "  - Recorder/candle path cannot infer intra-candle TP vs SL sequence\n\n")

        f.write("handoff_to_final_synthesis:\n")
        f.write("  datasets:\n")
        f.write(f"  - {out_main}\n")
        f.write(f"  - {out_reg}\n")
        f.write(f"  - {out_bucket}\n")
        f.write(f"  - {out_give}\n")
        f.write(f"  - {out_trans}\n")
        f.write("  important_caveats:\n")
        f.write(f"  - {json.dumps(runtime_notes, ensure_ascii=False)}\n")

    meta = OUT_DIR / "runtime_notes.json"
    with meta.open("w", encoding="utf-8") as f:
        json.dump(runtime_notes, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
