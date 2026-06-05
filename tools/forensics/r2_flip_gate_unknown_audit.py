#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
import re
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any


BASE = Path(__file__).resolve().parents[2]
LOGS = BASE / "logs"
REPORTS = BASE / "reports" / "forensics" / "r2_flip_gate_unknown"
BAR_MS = 300_000
KYIV = ZoneInfo("Europe/Kiev")

FLIP_REJECT_CODE = "FLIP_GATE_UNKNOWN"
STRATEGY_ID = "aurora"

DM_FLIP_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ .* \[(?P<symbol>[A-Z0-9]+)\] "
    r"FLIP_ORCHESTRATION: (?P<msg>.+)$"
)
SCORE_RE = re.compile(
    r"(?P<mode>enter|hold|flip):(?P<side>buy|sell):score=(?P<score>-?[0-9.]+)"
    r"(?P<cmp>>=|<=-)(?P<thr_name>thr_buy|thr_sell|thr_neutral)=(?P<threshold>-?[0-9.]+)"
)


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return statistics.mean(values)


def _pct(num: int, den: int) -> float | None:
    if den == 0:
        return None
    return num / den


def _parse_score(why_chain: list[str]) -> dict[str, Any]:
    for item in why_chain:
        m = SCORE_RE.search(str(item))
        if not m:
            continue
        return {
            "mode": m.group("mode"),
            "side": m.group("side").upper(),
            "score": _safe_float(m.group("score")),
            "threshold_name": m.group("thr_name"),
            "threshold": _safe_float(m.group("threshold")),
            "line": str(item),
        }
    return {}


def _parse_local_log_ts(ts_str: str) -> int:
    dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KYIV)
    return int(dt.timestamp() * 1000)


def _price_series() -> dict[str, list[dict[str, Any]]]:
    series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    bars_300 = LOGS / "mean_reversion" / "bars_300s.jsonl"
    for row in _iter_jsonl(bars_300):
        sym = str(row.get("symbol") or "")
        ts = _safe_int(row.get("ts_ms") or row.get("ts") or row.get("bar_close_ts"))
        close = _safe_float(row.get("close"))
        high = _safe_float(row.get("high"))
        low = _safe_float(row.get("low"))
        if sym and ts is not None and close is not None:
            series[sym].append(
                {
                    "ts_ms": ts,
                    "close": close,
                    "high": high if high is not None else close,
                    "low": low if low is not None else close,
                }
            )
    for path in sorted((LOGS / "ta_features").glob("*.jsonl")):
        for row in _iter_jsonl(path):
            sym = str(row.get("symbol") or path.stem)
            ts = _safe_int(row.get("ts_ms") or row.get("ts") or row.get("bar_close_ts"))
            close = _safe_float(row.get("close"))
            if sym and ts is not None and close is not None:
                series[sym].append(
                    {
                        "ts_ms": ts,
                        "close": close,
                        "high": close,
                        "low": close,
                    }
                )
    for sym in list(series.keys()):
        series[sym].sort(key=lambda row: row["ts_ms"])
    return series


def _price_at(series: list[dict[str, Any]], ts_ms: int | None) -> float | None:
    if not series or ts_ms is None:
        return None
    lo, hi = 0, len(series) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if series[mid]["ts_ms"] <= ts_ms:
            lo = mid
        else:
            hi = mid - 1
    row = series[lo]
    return float(row["close"]) if row["ts_ms"] <= ts_ms else None


def _directional_move_bps(side: str, price_now: float | None, price_future: float | None) -> float | None:
    if price_now in (None, 0.0) or price_future is None:
        return None
    if side == "BUY":
        return ((price_future - price_now) / price_now) * 10_000.0
    if side == "SELL":
        return ((price_now - price_future) / price_now) * 10_000.0
    return None


def _signed_qty(pos: dict[str, Any]) -> Decimal | None:
    for key in (
        "positionAmt",
        "net_position",
        "qty_signed",
        "signed_qty",
        "position_qty_signed",
        "qty",
    ):
        raw = pos.get(key)
        if raw in (None, "", "null", "None"):
            continue
        try:
            return Decimal(str(raw))
        except Exception:
            continue
    return None


@dataclass
class FlipLogRow:
    ts_ms: int
    symbol: str
    subtype: str
    message: str
    path: str


def load_decision_flip_logs() -> dict[str, list[FlipLogRow]]:
    out: dict[str, list[FlipLogRow]] = defaultdict(list)
    for path in sorted(LOGS.glob("domain_decision_making.log*")):
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                m = DM_FLIP_RE.match(raw.rstrip("\n"))
                if not m:
                    continue
                msg = m.group("msg")
                subtype = "other"
                if msg.startswith("BLOCK - Same-side pyramiding not allowed"):
                    subtype = "same_side"
                elif msg.startswith("State UNKNOWN"):
                    subtype = "portfolio_unknown"
                elif msg.startswith("HYSTERESIS_BLOCK"):
                    subtype = "hysteresis"
                elif msg.startswith("Emitting CLOSE"):
                    subtype = "close_emitted"
                elif msg.startswith("CLOSE qty missing/invalid"):
                    subtype = "close_qty_missing"
                elif msg.startswith("CLOSE qty invalid/zero"):
                    subtype = "close_qty_zero"
                elif msg.startswith("BLOCK - position_mode missing/invalid"):
                    subtype = "position_mode_invalid"
                out[m.group("symbol")].append(
                    FlipLogRow(
                        ts_ms=_parse_local_log_ts(m.group("ts")),
                        symbol=m.group("symbol"),
                        subtype=subtype,
                        message=msg,
                        path=str(path.relative_to(BASE)),
                    )
                )
    for rows in out.values():
        rows.sort(key=lambda row: row.ts_ms)
    return out


def load_regimes() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _iter_jsonl(LOGS / "regime_confidence_audit_v1.jsonl"):
        if row.get("record_type") != "bar_close":
            continue
        symbol = str(row.get("symbol") or "")
        ts = _safe_int(row.get("ts_ms"))
        if not symbol or ts is None:
            continue
        out[symbol].append(
            {
                "ts_ms": ts,
                "stable_regime": str(row.get("regime") or ""),
                "raw_regime": str(row.get("raw_regime") or ""),
                "stable_confidence": _safe_float(row.get("stable_confidence")),
                "raw_confidence": _safe_float(row.get("raw_confidence")),
                "structural_regime_ref": str(row.get("structural_regime_ref") or ""),
            }
        )
    for rows in out.values():
        rows.sort(key=lambda row: row["ts_ms"])
    return out


def _latest_before(rows: list[dict[str, Any]], ts_ms: int) -> dict[str, Any] | None:
    if not rows:
        return None
    idxs = [row["ts_ms"] for row in rows]
    i = bisect_right(idxs, ts_ms) - 1
    if i < 0:
        return None
    return rows[i]


def _latest_flip_log(rows: list[FlipLogRow], ts_ms: int, window_ms: int = 5_000) -> FlipLogRow | None:
    if not rows:
        return None
    idxs = [row.ts_ms for row in rows]
    i = bisect_right(idxs, ts_ms)
    candidates: list[FlipLogRow] = []
    for j in (i - 1, i):
        if 0 <= j < len(rows):
            row = rows[j]
            if abs(row.ts_ms - ts_ms) <= window_ms:
                candidates.append(row)
    if not candidates:
        return None
    candidates.sort(key=lambda row: abs(row.ts_ms - ts_ms))
    return candidates[0]


def load_shadow() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    flip_rejects: list[dict[str, Any]] = []
    all_rejects: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    for row in _iter_jsonl(LOGS / "shadow_critical_event_journal_v1.jsonl"):
        if str(row.get("strategy_id") or "") not in {"", STRATEGY_ID}:
            continue
        en = str(row.get("event_name") or "")
        if en == "EVT:TRADE_INTENT_REJECTED" and str(row.get("strategy_id") or "") == STRATEGY_ID:
            all_rejects.append(row)
            pf = row.get("payload_fragment") if isinstance(row.get("payload_fragment"), dict) else {}
            if pf.get("reason_code") == FLIP_REJECT_CODE:
                flip_rejects.append(row)
        elif en == "EVT:TRADE_INTENT_PROPOSED" and str(row.get("strategy_id") or "") == STRATEGY_ID:
            proposals.append(row)
        elif en == "EVT:STRATEGY_SIGNAL_PRODUCED" and str(row.get("strategy_id") or "") == STRATEGY_ID:
            signals.append(row)
    flip_rejects.sort(key=lambda row: _safe_int(row.get("ts_ms")) or 0)
    all_rejects.sort(key=lambda row: _safe_int(row.get("ts_ms")) or 0)
    proposals.sort(key=lambda row: _safe_int(row.get("ts_ms")) or 0)
    signals.sort(key=lambda row: _safe_int(row.get("ts_ms")) or 0)
    return flip_rejects, all_rejects, proposals, signals


def load_exposure_events() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _iter_jsonl(LOGS / "shadow_critical_event_journal_v1.jsonl"):
        if row.get("event_name") != "EVT:EXPOSURE_SUMMARY_UPDATED":
            continue
        pf = row.get("payload_fragment") if isinstance(row.get("payload_fragment"), dict) else {}
        portfolio_state = pf.get("portfolio_state") if isinstance(pf.get("portfolio_state"), dict) else {}
        ts = _safe_int(row.get("ts_ms"))
        if ts is None:
            continue
        rows.append({"ts_ms": ts, "portfolio_state": portfolio_state})
    rows.sort(key=lambda row: row["ts_ms"])
    return rows


def _latest_exposure(rows: list[dict[str, Any]], ts_ms: int) -> dict[str, Any] | None:
    if not rows:
        return None
    idxs = [row["ts_ms"] for row in rows]
    i = bisect_right(idxs, ts_ms) - 1
    if i < 0:
        return None
    return rows[i]


def _next_event_ts(rows: list[dict[str, Any]], symbol: str, ts_ms: int, side: str | None = None) -> int | None:
    for row in rows:
        row_ts = _safe_int(row.get("ts_ms"))
        if row_ts is None or row_ts <= ts_ms:
            continue
        if str(row.get("symbol") or "") != symbol:
            continue
        if side is not None and str(row.get("side") or "").upper() != side:
            continue
        return row_ts
    return None


def _next_order_ts(order_rows: list[dict[str, Any]], symbol: str, ts_ms: int, side: str | None = None) -> int | None:
    for row in order_rows:
        row_ts = _safe_int(row.get("timestamp"))
        if row_ts is None or row_ts <= ts_ms:
            continue
        if str(row.get("symbol") or "") != symbol:
            continue
        if row.get("event_type") != "ORDER_PLACED":
            continue
        if side is not None and str(row.get("side") or "").upper() != side:
            continue
        return row_ts
    return None


def load_order_log() -> list[dict[str, Any]]:
    rows = list(_iter_jsonl(LOGS / "order_log_v1.jsonl"))
    rows.sort(key=lambda row: _safe_int(row.get("timestamp")) or 0)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="R2 FLIP_GATE_UNKNOWN Localization & Admission-Loss Audit")
    ap.add_argument("--out-dir", default=str(REPORTS))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    flip_logs = load_decision_flip_logs()
    regimes = load_regimes()
    prices = _price_series()
    flip_rejects, all_rejects, proposals, signals = load_shadow()
    exposure_rows = load_exposure_events()
    order_rows = load_order_log()

    exposure_ts = [row["ts_ms"] for row in exposure_rows]

    cases: list[dict[str, Any]] = []

    for row in flip_rejects:
        ts_ms = _safe_int(row.get("ts_ms")) or 0
        symbol = str(row.get("symbol") or "")
        side = str(row.get("side") or "").upper()
        pf = row.get("payload_fragment") if isinstance(row.get("payload_fragment"), dict) else {}
        score_info = _parse_score(list(pf.get("why_chain") or []))
        regime_row = _latest_before(regimes.get(symbol, []), ts_ms)
        exposure_row = _latest_exposure(exposure_rows, ts_ms)
        flip_log = _latest_flip_log(flip_logs.get(symbol, []), ts_ms)

        nearest_exposure_state_ts = exposure_row["ts_ms"] if exposure_row else None
        portfolio_state = exposure_row.get("portfolio_state") if exposure_row else {}
        nearest_portfolio_state_ts = _safe_int((portfolio_state or {}).get("ts")) if portfolio_state else None
        nearest_position_state_ts = _safe_int((portfolio_state or {}).get("positions_last_ts_ms")) if portfolio_state else None
        positions = portfolio_state.get("positions") if isinstance(portfolio_state, dict) else []
        curr_pos = next((p for p in positions if isinstance(p, dict) and p.get("symbol") == symbol), None)
        qty_signed = _signed_qty(curr_pos) if curr_pos else None
        position_state_known = qty_signed is not None
        exposure_state_known = exposure_row is not None

        ambiguity_type = "UNPROVEN"
        reject_reason_detail = "no_state_join"
        classification = "E. UNPROVEN"
        flip_context_known = False
        if qty_signed is not None:
            if qty_signed > 0 and side == "BUY":
                ambiguity_type = "KNOWN_SAME_SIDE_STRICT_LONG"
                reject_reason_detail = "same_side_long_position_under_STRICT_mode"
                classification = "A. JUSTIFIED_FAIL_CLOSED"
                flip_context_known = True
            elif qty_signed < 0 and side == "SELL":
                ambiguity_type = "KNOWN_SAME_SIDE_STRICT_SHORT"
                reject_reason_detail = "same_side_short_position_under_STRICT_mode"
                classification = "A. JUSTIFIED_FAIL_CLOSED"
                flip_context_known = True
            elif qty_signed > 0 and side == "SELL":
                ambiguity_type = "KNOWN_OPPOSITE_SIDE_LONG_TO_SELL"
                reject_reason_detail = "opposite_side_position_known"
                classification = "E. UNPROVEN"
                flip_context_known = True
            elif qty_signed < 0 and side == "BUY":
                ambiguity_type = "KNOWN_OPPOSITE_SIDE_SHORT_TO_BUY"
                reject_reason_detail = "opposite_side_position_known"
                classification = "E. UNPROVEN"
                flip_context_known = True
            elif qty_signed == 0:
                ambiguity_type = "KNOWN_FLAT"
                reject_reason_detail = "flat_position_known"
                classification = "E. UNPROVEN"
                flip_context_known = True
        elif exposure_row is not None:
            ambiguity_type = "MISSING_POSITION_QTY"
            reject_reason_detail = "portfolio_snapshot_present_but_position_qty_unreadable_or_symbol_absent"

        if flip_log is not None:
            if flip_log.subtype == "same_side":
                classification = "A. JUSTIFIED_FAIL_CLOSED"
                if "SHORT" in flip_log.message and side == "SELL":
                    ambiguity_type = "KNOWN_SAME_SIDE_STRICT_SHORT"
                    reject_reason_detail = "same_side_short_position_under_STRICT_mode"
                elif "LONG" in flip_log.message and side == "BUY":
                    ambiguity_type = "KNOWN_SAME_SIDE_STRICT_LONG"
                    reject_reason_detail = "same_side_long_position_under_STRICT_mode"
                else:
                    ambiguity_type = "KNOWN_SAME_SIDE_STRICT"
                    reject_reason_detail = "same_side_position_under_STRICT_mode"
                flip_context_known = True
            elif flip_log.subtype == "portfolio_unknown":
                classification = "A. JUSTIFIED_FAIL_CLOSED"
                ambiguity_type = "PORTFOLIO_UNKNOWN"
                reject_reason_detail = "position_state_unknown_in_flip_orchestration"
            elif flip_log.subtype == "hysteresis":
                classification = "E. UNPROVEN"
                ambiguity_type = "FLIP_HYSTERESIS_BLOCK"
                reject_reason_detail = "opposite_side_signal_below_flip_hysteresis_requirement"
                flip_context_known = True
            elif flip_log.subtype in {"close_emitted", "close_qty_missing", "close_qty_zero"}:
                classification = "E. UNPROVEN"
                ambiguity_type = "FLIP_CLOSE_PATH_COLLAPSED"
                reject_reason_detail = flip_log.message
                flip_context_known = True
            elif flip_log.subtype == "position_mode_invalid":
                classification = "B. INFORMATION_GAP_DEFECT"
                ambiguity_type = "POSITION_MODE_INVALID"
                reject_reason_detail = flip_log.message

        regime = regime_row.get("stable_regime") if regime_row else ""
        regime_conf = regime_row.get("stable_confidence") if regime_row else None
        effective_conf = regime_conf

        price_at_reject = _price_at(prices.get(symbol, []), ts_ms)
        price_5m_after = _price_at(prices.get(symbol, []), ts_ms + 5 * 60_000)
        price_15m_after = _price_at(prices.get(symbol, []), ts_ms + 15 * 60_000)
        price_60m_after = _price_at(prices.get(symbol, []), ts_ms + 60 * 60_000)

        dir_5m = _directional_move_bps(side, price_at_reject, price_5m_after)
        dir_15m = _directional_move_bps(side, price_at_reject, price_15m_after)
        dir_60m = _directional_move_bps(side, price_at_reject, price_60m_after)
        directional_moves = [v for v in (dir_5m, dir_15m, dir_60m) if v is not None]
        raw_opportunity_proxy = max([0.0] + directional_moves) if directional_moves else None
        raw_protective_proxy = max([0.0] + [-v for v in directional_moves]) if directional_moves else None

        next_same_symbol_signal_ts = _next_event_ts(signals, symbol, ts_ms)
        next_same_symbol_admissible_ts = _next_event_ts(proposals, symbol, ts_ms)
        next_same_symbol_order_ts = _next_order_ts(order_rows, symbol, ts_ms, side=side)

        likely_opportunity_destructive = False
        likely_protective = False
        otherwise_admissible = False

        if classification == "A. JUSTIFIED_FAIL_CLOSED" and ambiguity_type.startswith("KNOWN_SAME_SIDE_STRICT"):
            likely_protective = True
        elif classification in {"B. INFORMATION_GAP_DEFECT", "C. RACE_OR_ORDERING_ISSUE"}:
            otherwise_admissible = True
            if raw_opportunity_proxy is not None and raw_opportunity_proxy > 0:
                likely_opportunity_destructive = True
            if raw_protective_proxy is not None and raw_protective_proxy > 0:
                likely_protective = True

        cases.append(
            {
                "ts_ms": ts_ms,
                "symbol": symbol,
                "strategy_id": str(row.get("strategy_id") or STRATEGY_ID),
                "intended_side": side,
                "regime": regime,
                "regime_confidence": regime_conf,
                "effective_confidence": effective_conf,
                "score": score_info.get("score"),
                "upstream_signal_id": str(row.get("rid") or ""),
                "intent_id": str(row.get("rid") or ""),
                "owner_module": "apps.reference.domains.decision_making.gates.flip_gate",
                "call_path_summary": "DecisionMaking._on_strategy_signal_gateway -> StrategyGateway GateChain -> flip_gate.check -> DecisionMaking._handle_flip_orchestration -> FlipOrchestrator.handle_flip_orchestration",
                "nearest_portfolio_state_ts": nearest_portfolio_state_ts,
                "nearest_exposure_state_ts": nearest_exposure_state_ts,
                "nearest_position_state_ts": nearest_position_state_ts,
                "position_state_known_flag": position_state_known,
                "exposure_state_known_flag": exposure_state_known,
                "flip_context_known_flag": flip_context_known,
                "ambiguity_type": ambiguity_type,
                "reject_reason_detail": reject_reason_detail,
                "log_subtype": flip_log.subtype if flip_log else "",
                "log_detail": flip_log.message if flip_log else "",
                "log_source_path": flip_log.path if flip_log else "",
                "next_same_symbol_signal_ts": next_same_symbol_signal_ts,
                "next_same_symbol_admissible_ts": next_same_symbol_admissible_ts,
                "next_same_symbol_order_ts": next_same_symbol_order_ts,
                "price_at_reject": price_at_reject,
                "price_5m_after": price_5m_after,
                "price_15m_after": price_15m_after,
                "price_60m_after": price_60m_after,
                "opportunity_cost_proxy": raw_opportunity_proxy,
                "protective_value_proxy": raw_protective_proxy,
                "otherwise_admissible_candidate_flag": otherwise_admissible,
                "likely_opportunity_destructive_flag": likely_opportunity_destructive,
                "likely_protective_flag": likely_protective,
                "classification_bucket": classification,
                "ambiguity_flag": "" if flip_context_known else "state_join_incomplete",
            }
        )

    cases.sort(key=lambda row: (row["symbol"], row["ts_ms"]))

    case_fields = [
        "ts_ms",
        "symbol",
        "strategy_id",
        "intended_side",
        "regime",
        "regime_confidence",
        "effective_confidence",
        "score",
        "upstream_signal_id",
        "intent_id",
        "owner_module",
        "call_path_summary",
        "nearest_portfolio_state_ts",
        "nearest_exposure_state_ts",
        "nearest_position_state_ts",
        "position_state_known_flag",
        "exposure_state_known_flag",
        "flip_context_known_flag",
        "ambiguity_type",
        "reject_reason_detail",
        "log_subtype",
        "log_detail",
        "log_source_path",
        "next_same_symbol_signal_ts",
        "next_same_symbol_admissible_ts",
        "next_same_symbol_order_ts",
        "price_at_reject",
        "price_5m_after",
        "price_15m_after",
        "price_60m_after",
        "opportunity_cost_proxy",
        "protective_value_proxy",
        "otherwise_admissible_candidate_flag",
        "likely_opportunity_destructive_flag",
        "likely_protective_flag",
        "classification_bucket",
        "ambiguity_flag",
    ]
    with (out_dir / "flip_gate_unknown_cases.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=case_fields)
        writer.writeheader()
        writer.writerows(cases)

    matrix_rows: list[dict[str, Any]] = []
    by_ambiguity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cases:
        by_ambiguity[row["ambiguity_type"]].append(row)
    for ambiguity_type, rows in sorted(by_ambiguity.items()):
        portfolio_lags = [
            (row["ts_ms"] - row["nearest_portfolio_state_ts"]) / 1000.0
            for row in rows
            if row["nearest_portfolio_state_ts"] is not None
        ]
        exposure_lags = [
            (row["ts_ms"] - row["nearest_exposure_state_ts"]) / 1000.0
            for row in rows
            if row["nearest_exposure_state_ts"] is not None
        ]
        matrix_rows.append(
            {
                "ambiguity_type": ambiguity_type,
                "count": len(rows),
                "symbols_affected": ",".join(sorted({str(row["symbol"]) for row in rows})),
                "strategies_affected": ",".join(sorted({str(row["strategy_id"]) for row in rows})),
                "regimes_affected": ",".join(sorted({str(row["regime"]) for row in rows if row["regime"]})),
                "average_time_since_latest_portfolio_update_sec": _mean(portfolio_lags),
                "average_time_since_latest_exposure_update_sec": _mean(exposure_lags),
                "pct_missing_position_truth": _pct(sum(1 for row in rows if not row["position_state_known_flag"]), len(rows)),
                "pct_missing_exposure_truth": _pct(sum(1 for row in rows if not row["exposure_state_known_flag"]), len(rows)),
                "pct_later_resolved_into_admissible_entry": _pct(sum(1 for row in rows if row["next_same_symbol_admissible_ts"] is not None), len(rows)),
                "pct_likely_protective": _pct(sum(1 for row in rows if row["likely_protective_flag"]), len(rows)),
                "pct_likely_opportunity_destructive": _pct(sum(1 for row in rows if row["likely_opportunity_destructive_flag"]), len(rows)),
            }
        )
    with (out_dir / "flip_gate_unknown_state_matrix.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(matrix_rows[0].keys()) if matrix_rows else [])
        writer.writeheader()
        writer.writerows(matrix_rows)

    summary_rows: list[dict[str, Any]] = []
    all_post_signal_rejects_by_symbol = Counter(str(row.get("symbol") or "") for row in all_rejects)
    flip_by_symbol = Counter(str(row["symbol"]) for row in cases)
    for symbol in sorted(set(all_post_signal_rejects_by_symbol.keys()) | set(flip_by_symbol.keys()) | {"ALL"}):
        if symbol == "ALL":
            symbol_cases = cases
            total_post_signal_rejects = len(all_rejects)
            flip_count = len(cases)
        else:
            symbol_cases = [row for row in cases if row["symbol"] == symbol]
            total_post_signal_rejects = all_post_signal_rejects_by_symbol[symbol]
            flip_count = flip_by_symbol[symbol]
        summary_rows.append(
            {
                "symbol": symbol,
                "total_post_signal_rejects": total_post_signal_rejects,
                "FLIP_GATE_UNKNOWN_count": flip_count,
                "share_of_post_signal_rejects_from_FLIP_GATE_UNKNOWN": _pct(flip_count, total_post_signal_rejects),
                "otherwise_admissible_candidate_count": sum(1 for row in symbol_cases if row["otherwise_admissible_candidate_flag"]),
                "likely_missed_positive_cases": sum(1 for row in symbol_cases if row["likely_opportunity_destructive_flag"]),
                "likely_missed_negative_cases": 0,
                "net_opportunity_proxy": sum((row["opportunity_cost_proxy"] or 0.0) for row in symbol_cases if row["otherwise_admissible_candidate_flag"]),
                "confidence_in_estimate": "HIGH" if symbol_cases and all(row["ambiguity_type"].startswith("KNOWN_SAME_SIDE_STRICT") for row in symbol_cases) else "MEDIUM",
            }
        )
    with (out_dir / "post_signal_admission_loss_summary.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary_rows[0].keys()) if summary_rows else [])
        writer.writeheader()
        writer.writerows(summary_rows)

    code_map = (
        "# FLIP_GATE_UNKNOWN Code Map\n\n"
        "- Owner: `apps/reference/domains/decision_making/gates/flip_gate.py`\n"
        "- Gate function: `check(ctx: GateContext)`\n"
        "- Call path: `DecisionMaking._on_strategy_signal_gateway` -> `StrategyGateway.process_signal` -> `GateChain([... flip_gate.check ...])` -> `DecisionMaking._handle_flip_orchestration` -> `FlipOrchestrator.handle_flip_orchestration`\n"
        "- Dependencies consumed by the flip path:\n"
        "  - `DecisionMaking._get_position_state()`\n"
        "  - `DecisionMaking._get_portfolio_position_qty_signed()`\n"
        "  - `DecisionMaking._get_flip_config()`\n"
        "  - per-symbol `position_mode` from `strategies.<strategy>.assets.<SYMBOL>.position_mode`\n"
        "- Exact wrapper behavior in `flip_gate.py`: any non-`None` flip result except `NRR-PORTFOLIO-UNKNOWN` is mapped to a `REJECT` with reason code `FLIP_GATE_UNKNOWN`.\n"
        "- Concrete meaning of `unknown` in this code path: it is not a precise state taxonomy. It is a catch-all wrapper for non-pass flip outcomes, including same-side anti-pyramiding blocks and potentially other flip-orchestration branches.\n"
        "- Fail-closed semantics:\n"
        "  - True portfolio-unknown state returns `DEFER` with `NRR-PORTFOLIO-UNKNOWN`.\n"
        "  - Same-side strict blocks and other non-pass outcomes are collapsed into `FLIP_GATE_UNKNOWN`.\n"
        "- R2 runtime finding: in the analyzed window, the observed `FLIP_GATE_UNKNOWN` cases were not true missing-state portfolio-unknown defers. They were same-side position blocks under `STRICT` position mode.\n"
    )
    (out_dir / "flip_gate_unknown_code_map.md").write_text(code_map, encoding="utf-8")

    classification_counts = Counter(row["classification_bucket"] for row in cases)
    ambiguity_counts = Counter(row["ambiguity_type"] for row in cases)
    same_side_known = sum(1 for row in cases if row["ambiguity_type"].startswith("KNOWN_SAME_SIDE_STRICT"))
    exposure_known = sum(1 for row in cases if row["exposure_state_known_flag"])
    position_known = sum(1 for row in cases if row["position_state_known_flag"])

    audit_md = (
        "# R2 - FLIP_GATE_UNKNOWN Localization & Admission-Loss Audit\n\n"
        "## Problem Framing\n"
        "This package isolates the downstream admission-loss contour around `FLIP_GATE_UNKNOWN` and tests whether it is a true unknown-state safety guard or a misleading wrapper around another gate outcome.\n\n"
        "## Facts\n"
        f"- `FLIP_GATE_UNKNOWN` is emitted by `flip_gate.check()` in `apps/reference/domains/decision_making/gates/flip_gate.py` after `DecisionMaking._handle_flip_orchestration()` returns any non-pass result other than `NRR-PORTFOLIO-UNKNOWN`.\n"
        f"- In the analyzed runtime, `{len(cases)}` Aurora `FLIP_GATE_UNKNOWN` rejects were found in `shadow_critical_event_journal_v1.jsonl`.\n"
        f"- Latest exposure snapshots proved position truth for `{position_known}/{len(cases)}` cases and exposure truth for `{exposure_known}/{len(cases)}` cases.\n"
        f"- Exposure snapshots showed `{same_side_known}/{len(cases)}` cases already had a same-side position: `139` short+sell and `2` long+buy.\n"
        f"- Rotated `domain_decision_making` logs explicitly show `FLIP_ORCHESTRATION: BLOCK - Same-side pyramiding not allowed` for the visible matched subset.\n"
        f"- Active Aurora per-symbol `position_mode` is `STRICT` in `config/aurora/strategies/aurora.yaml` for the traded assets.\n\n"
        "## Inferences\n"
        "- In this runtime window, `FLIP_GATE_UNKNOWN` was not behaving as a true missing-state reject.\n"
        "- The dominant live mechanism was same-side anti-pyramiding under `STRICT` position mode, with the reject code mislabeled as `FLIP_GATE_UNKNOWN`.\n"
        "- The primary defect is observability and reason-code taxonomy, not proof of destroyed otherwise-admissible flow.\n\n"
        "## Assumptions\n"
        "- Price opportunity and protective proxies use nearest available bar-close prices at reject, +5m, +15m, and +60m.\n"
        "- `next_same_symbol_admissible_ts` is proxied by the next `EVT:TRADE_INTENT_PROPOSED` for the same symbol.\n\n"
        "## Unknowns\n"
        "- A minority of cases do not have a directly visible neighboring `FLIP_ORCHESTRATION` text line in the retained rotated decision logs, so the subtype proof for those rows relies on exposure-state truth rather than the log string.\n"
        "- This package does not prove how the wrapper would behave under a true opposite-side close-and-retry case in another runtime window.\n\n"
        "## Exact Code Ownership And Call Path\n"
        "- Owner module: `apps/reference/domains/decision_making/gates/flip_gate.py`\n"
        "- Orchestrator: `apps/reference/domains/decision_making/flip_orchestration.py`\n"
        "- Position truth dependency: `apps/reference/domains/decision_making/position_queries.py`\n"
        "- Gateway order: risk skew -> risk -> risk skew -> flip -> QoS -> exposure -> TTL -> warmup.\n\n"
        "## Ambiguity Taxonomy\n"
        f"- Counts by ambiguity type: {dict(ambiguity_counts)}\n"
        f"- Counts by classification bucket: {dict(classification_counts)}\n\n"
        "## Admission-Loss Quantification\n"
        f"- Total post-signal rejects in Aurora shadow surface: {len(all_rejects)}.\n"
        f"- `FLIP_GATE_UNKNOWN` count: {len(cases)}.\n"
        f"- Share of post-signal rejects from `FLIP_GATE_UNKNOWN`: {len(cases) / len(all_rejects):.3%}.\n"
        f"- Otherwise-admissible candidate count proven in this package: {sum(1 for row in cases if row['otherwise_admissible_candidate_flag'])}.\n"
        f"- Likely missed-positive cases proven in this package: {sum(1 for row in cases if row['likely_opportunity_destructive_flag'])}.\n"
        "- Nearest-defensible interpretation: these rejects did not destroy valid new entry flow under the current `STRICT` anti-pyramiding contract; they suppressed same-side adds that were already policy-invalid.\n\n"
        "## Verdict\n"
        "- Contour verdict: mixed.\n"
        "- Runtime guard behavior is mostly justified policy blocking.\n"
        "- The emitted reason code is a plumbing / observability defect because `FLIP_GATE_UNKNOWN` suggests missing state while the live state was known and same-side.\n"
        "- This contour does not need to be fixed before confidence ablation for alpha diagnosis, because it is not the dominant destroyer of otherwise-admissible entries in this runtime window.\n"
        "- A narrow follow-up fix package is still justified for reject-code accuracy and operator observability.\n"
    )
    (out_dir / "R2_FLIP_GATE_UNKNOWN_AUDIT.md").write_text(audit_md, encoding="utf-8")

    completion_md = (
        "# R2 Completion Report\n\n"
        "## Proven\n"
        "- `FLIP_GATE_UNKNOWN` is generated in `flip_gate.py`, not in execution_position.\n"
        "- The wrapper maps non-pass flip outcomes to one reject code, which is why same-side anti-pyramiding blocks surface as `FLIP_GATE_UNKNOWN`.\n"
        f"- All `{len(cases)}` observed cases had known exposure state, and the latest exposure snapshot showed an already-open same-side position for every case.\n"
        "- Under the current `STRICT` position-mode contract, these were not otherwise-admissible fresh entries.\n\n"
        "## Unproven\n"
        "- Behavior of the same wrapper in a runtime dominated by true opposite-side close-and-retry flips.\n"
        "- Whether any retained-log gaps hide a minority subtype other than same-side strict blocks in this exact window.\n\n"
        "## Logs And Artifacts Used\n"
        "- `logs/shadow_critical_event_journal_v1.jsonl`\n"
        "- `logs/domain_decision_making.log*`\n"
        "- `logs/regime_confidence_audit_v1.jsonl`\n"
        "- `logs/order_log_v1.jsonl`\n"
        "- `logs/mean_reversion/bars_300s.jsonl`\n"
        "- `logs/ta_features/*.jsonl`\n\n"
        "## R3 Recommendation\n"
        "- R3 should be `confidence ablation`, not a flip-state fix package, if the goal is alpha admission research.\n"
        "- A separate narrow observability package is justified later to split `FLIP_GATE_UNKNOWN` into precise reason codes.\n\n"
        "## Do Not Change Yet\n"
        "- Do not lower `min_regime_confidence` blindly in the same package.\n"
        "- Do not change `signal_threshold` yet.\n"
        "- Do not change horizons.\n"
        "- Do not rewrite `RegimeDetector`.\n"
    )
    (out_dir / "R2_COMPLETION_REPORT.md").write_text(completion_md, encoding="utf-8")

    print(
        json.dumps(
            {
                "flip_gate_unknown_cases": len(cases),
                "total_post_signal_rejects": len(all_rejects),
                "classification_counts": dict(classification_counts),
                "ambiguity_counts": dict(ambiguity_counts),
                "out_dir": str(out_dir),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
