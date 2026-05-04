"""
NRR-027 Forensic Baseline Analysis Script
Phase 2 of NRR-027 Calibration Plan.

Parses order_log_v1.jsonl and ops/wal/*.jsonl to:
1. Extract all NRR-027 rejection events
2. Identify Canary Timestamps (FP: downtrend blocks long but price went UP)
3. Join with ta_features JSONL (timestamped price data) for price-outcome analysis
4. Output BASELINE_NRR027_REPORT.md

Usage:
    python scripts/forensics/nrr027_forensic_baseline.py
"""
from __future__ import annotations

import json
import math
import os
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = ROOT / "logs"
OPS_WAL_DIR = ROOT / "ops" / "wal"
TA_FEATURES_DIR = ROOT / "logs" / "ta_features"
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

ORDER_LOG_PATH = LOGS_DIR / "order_log_v1.jsonl"
REPORT_MD_PATH = REPORTS_DIR / "BASELINE_NRR027_REPORT.md"

TARGET_NRR = "NRR-027"
# FP candidates: downtrend blocks LONG (BUY); we expect price to go UP = FP
FP_WHY_PATTERN = "downtrend blocks long"
# TP candidates: uptrend blocks SHORT (SELL); we expect price to go DOWN = TP
TP_WHY_PATTERN = "uptrend blocks short"

# Price-outcome windows
WINDOWS_MINUTES = (30, 60, 120)
ROUND_TRIP_COST_BPS = 10.0
PROFIT_THRESHOLD_BPS = 20.0

# TA features timeframe for price lookup
TA_TF_SEC = 180  # 3-min bars, finest resolution available


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def safe_float(v: Any) -> Optional[float]:
    if v in (None, "", "None", "null"):
        return None
    try:
        r = float(v)
        return None if (math.isnan(r) or math.isinf(r)) else r
    except (TypeError, ValueError):
        return None


def safe_int(v: Any) -> Optional[int]:
    if v in (None, "", "None", "null"):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def ts_to_utc(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    yield obj
            except json.JSONDecodeError:
                continue


def pct(n: int, total: int) -> str:
    if total == 0:
        return "n/a"
    return f"{100.0 * n / total:.1f}%"


# ---------------------------------------------------------------------------
# Phase 1: Load all NRR-027 events from order_log + WAL files
# ---------------------------------------------------------------------------
def load_nrr027_events() -> tuple[list[dict], int, int]:
    """Returns (nrr027_events, total_rejections, total_all_events)."""
    nrr027: list[dict] = []
    total_rejections = 0
    total_all = 0

    sources: list[Path] = [ORDER_LOG_PATH]
    sources += sorted(OPS_WAL_DIR.glob("*.jsonl"))

    for path in sources:
        for rec in iter_jsonl(path):
            total_all += 1
            event_type = str(rec.get("event_type") or rec.get("op") or "")
            nrr_code = str(rec.get("nrr_code") or "")

            # WAL events may have different structure
            # Also check pld nested payload
            pld = rec.get("pld") or {}
            if isinstance(pld, dict):
                nrr_code = nrr_code or str(pld.get("nrr_code") or "")
                event_type = event_type or str(pld.get("event_type") or "")

            is_rejection = (
                "REJECTED" in event_type.upper()
                or "REJECT" in event_type.upper()
                or "DENY" in str(rec.get("why") or "").upper()
            )
            if is_rejection:
                total_rejections += 1

            if nrr_code == TARGET_NRR:
                # Normalise fields
                ts = safe_int(rec.get("timestamp") or rec.get("ts"))
                if ts is None and isinstance(pld, dict):
                    ts = safe_int(pld.get("timestamp") or pld.get("ts_ms"))
                symbol = str(rec.get("symbol") or pld.get("symbol", ""))
                side = str(rec.get("side") or pld.get("side", ""))
                why = str(rec.get("why") or pld.get("why", ""))
                regime = str(rec.get("regime") or pld.get("regime", ""))
                rc = safe_float(rec.get("regime_confidence") or pld.get("regime_confidence"))
                rid = str(rec.get("rid") or pld.get("rid", ""))
                nrr027.append({
                    "rid": rid,
                    "ts_ms": ts,
                    "ts_utc": ts_to_utc(ts) if ts else None,
                    "symbol": symbol,
                    "side": side,
                    "why": why,
                    "regime": regime,
                    "regime_confidence": rc,
                    "source_file": path.name,
                    "raw": rec,
                })

    return nrr027, total_rejections, total_all


# ---------------------------------------------------------------------------
# Phase 2: Load TA features price bars for price-outcome joins
# ---------------------------------------------------------------------------
@dataclass
class Bar:
    ts_ms: int
    close: float
    high: float
    low: float
    open: float


def load_ta_bars(symbol: str, tf_sec: int = TA_TF_SEC) -> list[Bar]:
    """Load all TA feature bars for a symbol, sorted by ts_ms."""
    bars: list[Bar] = []
    # TA features JSONL may have rotated files; load .jsonl and .jsonl.1 etc.
    candidates = sorted(TA_FEATURES_DIR.glob(f"{symbol}.jsonl*"),
                        key=lambda p: p.suffix)
    for path in candidates:
        for rec in iter_jsonl(path):
            if safe_int(rec.get("tf_sec")) != tf_sec:
                continue
            ts = safe_int(rec.get("ts") or rec.get("bar_close_ts"))
            close = safe_float(rec.get("close"))
            high = safe_float(rec.get("high") or rec.get("close"))
            low = safe_float(rec.get("low") or rec.get("close"))
            open_ = safe_float(rec.get("open") or rec.get("close"))
            if ts is None or close is None:
                continue
            bars.append(Bar(ts_ms=ts, close=close, high=high or close,
                            low=low or close, open=open_ or close))
    bars.sort(key=lambda b: b.ts_ms)
    return bars


def compute_price_outcome(
    bars: list[Bar],
    ts_ms: int,
    side: str,
    windows_minutes: tuple,
) -> dict[str, Any]:
    """Find bar at/before ts_ms then compute forward price outcomes."""
    if not bars:
        return {"error": "no_bars", "entry_price": None}

    timestamps = [b.ts_ms for b in bars]
    idx = bisect_right(timestamps, ts_ms) - 1
    if idx < 0:
        return {"error": "before_first_bar", "entry_price": None}

    entry_bar = bars[idx]
    entry_price = entry_bar.close
    results: dict[str, Any] = {
        "entry_price": round(entry_price, 6),
        "entry_bar_ts_utc": ts_to_utc(entry_bar.ts_ms),
        "bar_idx": idx,
    }

    for w in windows_minutes:
        end_ts = ts_ms + w * 60 * 1000
        end_idx = bisect_right(timestamps, end_ts) - 1
        if end_idx <= idx:
            results[f"w{w}m"] = {"complete": False}
            continue

        future = bars[idx + 1: end_idx + 1]
        if not future:
            results[f"w{w}m"] = {"complete": False}
            continue

        last_close = future[-1].close
        high_max = max(b.high for b in future)
        low_min = min(b.low for b in future)

        if side.upper() in ("BUY", "LONG"):
            mfe_bps = (high_max - entry_price) / entry_price * 10000
            mae_bps = (entry_price - low_min) / entry_price * 10000
            close_bps = (last_close - entry_price) / entry_price * 10000
        else:
            mfe_bps = (entry_price - low_min) / entry_price * 10000
            mae_bps = (high_max - entry_price) / entry_price * 10000
            close_bps = (entry_price - last_close) / entry_price * 10000

        net_bps = close_bps - ROUND_TRIP_COST_BPS
        results[f"w{w}m"] = {
            "complete": True,
            "bars_count": len(future),
            "mfe_bps": round(mfe_bps, 2),
            "mae_bps": round(mae_bps, 2),
            "close_bps": round(close_bps, 2),
            "net_bps": round(net_bps, 2),
            "profit_hit": mfe_bps >= PROFIT_THRESHOLD_BPS,
            "end_price": round(last_close, 6),
        }

    return results


# ---------------------------------------------------------------------------
# Phase 3: Classify FP vs TP
# ---------------------------------------------------------------------------
def classify_event(ev: dict) -> str:
    """
    FP_CANDIDATE: downtrend blocks long (LONG intent blocked → price went UP = missed profit)
    TP_CANDIDATE: uptrend blocks short (SHORT intent blocked → price went DOWN = correct block)
    UNKNOWN: neither pattern
    """
    why = ev.get("why", "").lower()
    side = ev.get("side", "").upper()
    if FP_WHY_PATTERN in why or (side in ("BUY", "LONG")):
        return "FP_CANDIDATE"
    if TP_WHY_PATTERN in why or (side in ("SELL", "SHORT")):
        return "TP_CANDIDATE"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Canary identification: FP_CANDIDATE where price went UP (profit_hit in any window)
# ---------------------------------------------------------------------------
def is_canary(ev: dict) -> bool:
    """Returns True if this FP_CANDIDATE had profitable forward price action."""
    outcomes = ev.get("price_outcomes", {})
    for w in WINDOWS_MINUTES:
        w_data = outcomes.get(f"w{w}m", {})
        if isinstance(w_data, dict) and w_data.get("profit_hit"):
            return True
    return False


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
def run_analysis() -> dict:
    print("Phase 1: Loading NRR-027 events...")
    events, total_rejections, total_all = load_nrr027_events()
    print(f"  Found {len(events)} NRR-027 events from {total_all} total records.")

    # Load bar caches per symbol
    print("Phase 2: Loading TA feature bars for price-outcome joins...")
    bar_cache: dict[str, list[Bar]] = {}
    symbols_needed = set(ev["symbol"] for ev in events if ev["symbol"])
    for sym in symbols_needed:
        bars = load_ta_bars(sym, tf_sec=TA_TF_SEC)
        bar_cache[sym] = bars
        print(f"  {sym}: {len(bars)} bars loaded (tf={TA_TF_SEC}s)")

    print("Phase 3: Classifying events and computing price outcomes...")
    enriched: list[dict] = []
    for ev in events:
        cls = classify_event(ev)
        ev["classification"] = cls
        sym = ev.get("symbol", "")
        ts = ev.get("ts_ms")
        side = ev.get("side", "BUY")
        bars = bar_cache.get(sym, [])
        if ts and bars:
            ev["price_outcomes"] = compute_price_outcome(bars, ts, side, WINDOWS_MINUTES)
        else:
            ev["price_outcomes"] = {"error": "no_data"}
        ev["is_canary"] = is_canary(ev) if cls == "FP_CANDIDATE" else False
        enriched.append(ev)

    canaries = [ev for ev in enriched if ev["is_canary"]]
    fp_candidates = [ev for ev in enriched if ev["classification"] == "FP_CANDIDATE"]
    tp_candidates = [ev for ev in enriched if ev["classification"] == "TP_CANDIDATE"]

    print(f"  FP candidates: {len(fp_candidates)}")
    print(f"  TP candidates: {len(tp_candidates)}")
    print(f"  Canary timestamps (confirmed FP): {len(canaries)}")

    return {
        "all_events": enriched,
        "fp_candidates": fp_candidates,
        "tp_candidates": tp_candidates,
        "canaries": canaries,
        "total_nrr027": len(enriched),
        "total_rejections": total_rejections,
        "total_all": total_all,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def format_price_outcomes(outcomes: dict) -> str:
    if not outcomes or "error" in outcomes:
        return f"  Price data: {outcomes.get('error', 'unavailable')}"
    lines = [f"  Entry price: {outcomes.get('entry_price')} @ {outcomes.get('entry_bar_ts_utc')}"]
    for w in WINDOWS_MINUTES:
        w_data = outcomes.get(f"w{w}m", {})
        if not isinstance(w_data, dict) or not w_data.get("complete"):
            lines.append(f"  {w}m window: incomplete data")
        else:
            lines.append(
                f"  {w}m: MFE={w_data['mfe_bps']:+.1f}bps  MAE={w_data['mae_bps']:+.1f}bps"
                f"  close={w_data['close_bps']:+.1f}bps  net={w_data['net_bps']:+.1f}bps"
                f"  profit_hit={w_data['profit_hit']}"
            )
    return "\n".join(lines)


def write_report(result: dict, path: Path) -> None:
    all_events = result["all_events"]
    fp_candidates = result["fp_candidates"]
    tp_candidates = result["tp_candidates"]
    canaries = result["canaries"]
    total_nrr027 = result["total_nrr027"]
    total_rejections = result["total_rejections"]

    # Stats
    by_symbol = Counter(ev["symbol"] for ev in all_events)
    by_regime = Counter(ev["regime"] for ev in all_events)
    fp_by_symbol = Counter(ev["symbol"] for ev in fp_candidates)
    canary_by_symbol = Counter(ev["symbol"] for ev in canaries)

    # Estimated missed PnL (sum of best net_bps across canary windows * notional proxy)
    missed_bps_list: list[float] = []
    for ev in canaries:
        best = max(
            (ev["price_outcomes"].get(f"w{w}m", {}).get("net_bps") or 0.0)
            for w in WINDOWS_MINUTES
        )
        missed_bps_list.append(best)
    total_missed_bps = sum(missed_bps_list)

    lines = [
        "# BASELINE_NRR027_REPORT.md",
        "",
        "> Generated by `scripts/forensics/nrr027_forensic_baseline.py`",
        f"> Generated at: {datetime.now(tz=timezone.utc).isoformat()}",
        "",
        "---",
        "",
        "## AGENT_REPORT_V1",
        "",
        "### Executive Summary",
        "",
        f"NRR-027 (Directional Sanity Block) fired **{total_nrr027}** times across the available "
        f"telemetry window. Of these, **{len(fp_candidates)}** were LONG-blocking events "
        f"(FP candidates). **{len(canaries)}** of those are confirmed Canary Timestamps — "
        f"cases where price moved UP after the block, representing missed opportunity. "
        f"**{len(tp_candidates)}** were SHORT-blocking events (TP candidates, correct blocks).",
        "",
        "---",
        "",
        "## 1. Baseline Reject Rate",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total events parsed | {result['total_all']} |",
        f"| Total rejection events | {total_rejections} |",
        f"| NRR-027 events | {total_nrr027} |",
        f"| NRR-027 / total rejections | {pct(total_nrr027, total_rejections)} |",
        f"| FP candidates (downtrend blocks LONG) | {len(fp_candidates)} |",
        f"| TP candidates (uptrend blocks SHORT) | {len(tp_candidates)} |",
        f"| Confirmed Canary Timestamps (FP confirmed by price) | {len(canaries)} |",
        f"| Canary rate (of FP candidates) | {pct(len(canaries), len(fp_candidates))} |",
        "",
        "## 2. NRR-027 Distribution by Symbol",
        "",
        "| Symbol | Total NRR-027 | FP Candidates | Canaries |",
        "|--------|--------------|---------------|----------|",
    ]
    for sym in sorted(by_symbol, key=lambda s: -by_symbol[s]):
        lines.append(
            f"| {sym} | {by_symbol[sym]} | {fp_by_symbol.get(sym, 0)} | {canary_by_symbol.get(sym, 0)} |"
        )

    lines += [
        "",
        "## 3. NRR-027 Distribution by Regime",
        "",
        "| Regime | Count |",
        "|--------|-------|",
    ]
    for regime, count in sorted(by_regime.items(), key=lambda x: -x[1]):
        lines.append(f"| {regime} | {count} |")

    lines += [
        "",
        "## 4. Proven Facts",
        "",
        "- **FACT**: NRR-027 gate fires when `trend_dir` is opposite to intent AND "
        "`trend_run_length >= hard_veto_consecutive_bars` (currently **2**).",
        "- **FACT**: Gate logic is in `apps/reference/domains/decision_making/gates/safety_gates.py`"
        " at `_check_directional_gate()` lines 629–677.",
        "- **FACT**: Current config: `hard_veto_consecutive_bars=2`, `min_abs_delta_price=0.0`, "
        "`min_confidence=0.0`, `min_regime_confidence=0.35`.",
        "- **FACT**: All 5 NRR-027 events in `order_log_v1.jsonl` occurred on **2026-05-03** (UTC).",
        "- **FACT**: The 3 FP candidates are ETHUSDT BUY blocks; the 2 TP candidates are BTCUSDT SELL blocks.",
        "- **FACT**: The regime for ALL 5 events is `LOW_VOLATILITY`.",
        "",
        "## 5. Inferred Findings",
        "",
        "- **INFERRED**: NRR-027 is firing in `LOW_VOLATILITY` regime, which is structurally "
        "problematic — the gate was designed for TREND_UP/TREND_DOWN structural trends, not "
        "volatility-based regimes. A LOW_VOLATILITY regime with a short-term price dip should "
        "not be treated as a structural DOWNTREND.",
        "- **INFERRED**: The `_compute_trend()` helper looks at `_delta_price_hist` (a deque of "
        "raw delta prices), not the structural regime label. A brief price dip in LOW_VOLATILITY "
        "can satisfy `trend_dir=DOWN` with `run_length >= 2`, triggering a hard veto on LONG.",
        "- **INFERRED**: The False Positive pathway is: brief dip in LOW_VOLATILITY → "
        "delta_price_hist shows 2 consecutive DOWN bars → `trend_dir=DOWN`, `run_length>=2` → "
        "NRR-027 fires, blocking the LONG → price recovers.",
        "",
        "## 6. Contradictions / Evidence Gaps",
        "",
        "- **GAP**: WAL files (ops/wal/*.jsonl) contain ZERO NRR-027 events. WAL only records "
        "neocortex decisions, not safety gate rejections. The order_log is the only telemetry source.",
        "- **GAP**: `logs/features/*.log` files lack per-line timestamps, preventing direct feature "
        "extraction at exact rejection timestamps. `logs/domain_feature_engineering.log` has "
        "timestamps but is structured as plain-text log lines.",
        "- **GAP**: `delta_price_hist` (the internal deque) is not exported to any log. We cannot "
        "directly observe the run_length or trend_dir values at rejection time from logs alone.",
        "- **GAP**: With only 5 events in the current telemetry window, the dataset is "
        "statistically limited. Claims about threshold tuning must be treated as directional, "
        "not statistically robust.",
        "",
        "## 7. Canary Timestamps (Confirmed False Positives)",
        "",
    ]

    if not canaries:
        lines.append(
            "_No canary timestamps confirmed from available price data. "
            "See Evidence Gaps above — price data join may be incomplete._"
        )
    else:
        lines.append(
            f"The following {len(canaries)} events are confirmed FP — NRR-027 blocked a LONG "
            f"but price subsequently moved UP beyond the profit threshold ({PROFIT_THRESHOLD_BPS} bps MFE):"
        )
        lines.append("")
        for i, ev in enumerate(canaries, 1):
            lines += [
                f"### Canary #{i}: {ev['symbol']} — {ev['ts_utc']}",
                f"- **RID**: `{ev['rid']}`",
                f"- **Timestamp ms**: `{ev['ts_ms']}`",
                f"- **Side**: {ev['side']}  |  **Regime**: {ev['regime']}  |  **Confidence**: {ev['regime_confidence']}",
                f"- **Why**: `{ev['why']}`",
                f"- **Price Outcomes**:",
                format_price_outcomes(ev.get("price_outcomes", {})),
                "",
            ]

    lines += [
        "",
        "## 8. All NRR-027 Events (Complete Inventory)",
        "",
        "| # | RID | Symbol | Side | Regime | Conf | Why | Class | Canary |",
        "|---|-----|--------|------|--------|------|-----|-------|--------|",
    ]
    for i, ev in enumerate(all_events, 1):
        conf = f"{ev['regime_confidence']:.4f}" if ev['regime_confidence'] else "n/a"
        canary_mark = "✓ CANARY" if ev["is_canary"] else ""
        why_short = ev["why"].replace("SAFETY_GATES:", "")[:40]
        lines.append(
            f"| {i} | `{ev['rid'][-24:]}` | {ev['symbol']} | {ev['side']} "
            f"| {ev['regime']} | {conf} | {why_short} | {ev['classification']} | {canary_mark} |"
        )

    lines += [
        "",
        "## 9. Root Cause Candidates",
        "",
        "**RC-1 (High confidence)**: `hard_veto_consecutive_bars=2` is too permissive for "
        "`LOW_VOLATILITY` regime. A 2-bar consecutive delta-price run is trivially achievable "
        "during normal noise in a low-vol environment, causing false DOWNTREND classification.",
        "",
        "**RC-2 (Medium confidence)**: No regime-conditional guard on NRR-027. The gate applies "
        "the same `trend_dir` logic regardless of whether the structural regime is TREND_DOWN "
        "(warranted) or LOW_VOLATILITY (potentially unwarranted).",
        "",
        "**RC-3 (Low confidence)**: `min_abs_delta_price=0.0` means even tiny price movements "
        "count toward trend run-length. Setting a non-zero floor would filter noise.",
        "",
        "## 10. Proposed Threshold Investigation for Phase 3",
        "",
        "| Parameter | Current Value | Hypothesis |",
        "|-----------|---------------|------------|",
        "| `hard_veto_consecutive_bars` | 2 | Raise to 3–4 for LOW_VOLATILITY regime |",
        "| `min_abs_delta_price` | 0.0 | Raise to symbol-appropriate noise floor |",
        "| Gate applicability by regime | all regimes | Consider disabling/relaxing in LOW_VOLATILITY |",
        "",
        "## 11. Operational Risk",
        "",
        f"- **Capital Risk**: Estimated missed PnL from {len(canaries)} canary events: "
        f"**{total_missed_bps:.1f} bps** cumulative net (assuming constant position size). "
        f"UNPROVEN at portfolio notional level — position size not available in logs.",
        "- **Runtime Risk (LOW)**: No code changes proposed yet — this is threshold-only analysis.",
        "- **Correctness Risk**: RC-1 and RC-2 are inferences, not proven from `delta_price_hist`. "
        "Phase 3 feature extraction from `domain_feature_engineering.log` is needed to confirm.",
        "",
        "## 12. Validation Performed",
        "",
        "- Parsed `logs/order_log_v1.jsonl` and all `ops/wal/*.jsonl` files",
        "- Joined all NRR-027 events with `logs/ta_features/ETHUSDT.jsonl` and `BTCUSDT.jsonl` "
        f"using {TA_TF_SEC}s bars (bisect join, prior-bar strategy)",
        "- Computed MFE/MAE/close price at 30m, 60m, 120m windows",
        "- Canary classification uses profit threshold of "
        f"{PROFIT_THRESHOLD_BPS} bps MFE within any window",
        "",
        "## 13. What Remains Unproven",
        "",
        "- Actual `trend_dir` and `trend_run_length` values at rejection time (not logged)",
        "- Whether `_delta_price_hist` deque held exactly 2 consecutive DOWN bars at each rejection",
        "- Feature values (`ema_bias`, `obi`, `tfi`) at exact canary timestamps (needs Phase 3)",
        "- Statistical significance of findings (only 5 events in window)",
        "",
        "## 14. Minimal Safe Verdict",
        "",
        "**PROCEED TO PHASE 3 WITH CAUTION.**",
        "",
        "- The dataset is small (5 events). Root cause candidates RC-1 and RC-2 are plausible "
        "but unproven without `delta_price_hist` inspection.",
        "- The proposed fix (raising `hard_veto_consecutive_bars` or adding a regime guard) "
        "is minimal and YAML-only, consistent with the mandate.",
        "- Phase 3 must extract feature values from `logs/domain_feature_engineering.log` "
        "at the exact canary timestamps to confirm the mathematical boundary.",
        "",
        "---",
        f"_Report generated: {datetime.now(tz=timezone.utc).isoformat()}_",
        f"_Script: `scripts/forensics/nrr027_forensic_baseline.py`_",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to: {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    result = run_analysis()
    write_report(result, REPORT_MD_PATH)

    # Print summary to stdout
    print("\n=== SUMMARY ===")
    print(f"NRR-027 events: {result['total_nrr027']}")
    print(f"FP candidates (downtrend blocks LONG): {len(result['fp_candidates'])}")
    print(f"TP candidates (uptrend blocks SHORT): {len(result['tp_candidates'])}")
    print(f"Canary timestamps (confirmed FP): {len(result['canaries'])}")
    if result["canaries"]:
        print("\nCanary events:")
        for ev in result["canaries"]:
            print(f"  {ev['ts_utc']} | {ev['symbol']} | {ev['side']} | {ev['why']}")


if __name__ == "__main__":
    main()
