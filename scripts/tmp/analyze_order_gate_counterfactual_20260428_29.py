from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ORDER_LOG = ROOT / "logs" / "order_log_v1.jsonl"
RECORDER = ROOT / "data" / "recorder"
OUT_DIR = ROOT / "reports" / "forensics"
OUT_CSV = OUT_DIR / "order_gate_counterfactual_20260428_29.csv"
OUT_MD = OUT_DIR / "order_gate_counterfactual_20260428_29.md"

KYIV = timezone(timedelta(hours=3))
TP_BPS = 80.0
SL_BPS = 40.0
ROUNDTRIP_FEE_BPS = 8.0
NOTIONAL_USD = 5000.0


def fnum(v):
    try:
        x = float(v)
    except Exception:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def dt_utc(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def dt_kyiv(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, KYIV).strftime("%Y-%m-%d %H:%M:%S")


def load_bars(symbol: str, dates: list[str], tf: int = 180) -> list[dict]:
    rows: list[dict] = []
    for day in dates:
        path = RECORDER / day / f"{symbol}_{tf}.csv"
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            for row in csv.DictReader(f):
                ts = fnum(row.get("timestamp"))
                close = fnum(row.get("close"))
                high = fnum(row.get("high"))
                low = fnum(row.get("low"))
                open_ = fnum(row.get("open"))
                if ts is None or close is None or high is None or low is None or open_ is None:
                    continue
                row["_ts"] = int(ts)
                row["_close"] = close
                row["_high"] = high
                row["_low"] = low
                row["_open"] = open_
                rows.append(row)
    rows.sort(key=lambda r: r["_ts"])
    return rows


def nearest_entry_bar(bars: list[dict], ts_ms: int) -> tuple[int, dict] | None:
    candidates = [(i, r) for i, r in enumerate(bars) if r["_ts"] >= ts_ms]
    if candidates:
        return candidates[0]
    if bars:
        return len(bars) - 1, bars[-1]
    return None


def simulate(bars: list[dict], start_idx: int, side: str) -> dict:
    entry = bars[start_idx]
    entry_price = entry["_close"]
    if side == "BUY":
        tp = entry_price * (1 + TP_BPS / 10000.0)
        sl = entry_price * (1 - SL_BPS / 10000.0)
    else:
        tp = entry_price * (1 - TP_BPS / 10000.0)
        sl = entry_price * (1 + SL_BPS / 10000.0)

    max_fav_bps = -10**9
    max_adv_bps = -10**9
    terminal = None
    exit_price = None
    exit_ts = None
    bars_held = 0

    for i, row in enumerate(bars[start_idx:], start=0):
        bars_held = i + 1
        high = row["_high"]
        low = row["_low"]
        if side == "BUY":
            fav = (high / entry_price - 1.0) * 10000.0
            adv = (1.0 - low / entry_price) * 10000.0
            hit_tp = high >= tp
            hit_sl = low <= sl
        else:
            fav = (1.0 - low / entry_price) * 10000.0
            adv = (high / entry_price - 1.0) * 10000.0
            hit_tp = low <= tp
            hit_sl = high >= sl
        max_fav_bps = max(max_fav_bps, fav)
        max_adv_bps = max(max_adv_bps, adv)
        if hit_tp and hit_sl:
            terminal = "AMBIGUOUS_BOTH_IN_BAR"
            exit_price = sl
            exit_ts = row["_ts"]
            break
        if hit_tp:
            terminal = "TP"
            exit_price = tp
            exit_ts = row["_ts"]
            break
        if hit_sl:
            terminal = "SL"
            exit_price = sl
            exit_ts = row["_ts"]
            break

    if terminal is None:
        last = bars[-1]
        terminal = "OPEN_TO_LAST_BAR"
        exit_price = last["_close"]
        exit_ts = last["_ts"]

    if side == "BUY":
        gross_bps = (exit_price / entry_price - 1.0) * 10000.0
    else:
        gross_bps = (entry_price / exit_price - 1.0) * 10000.0
    net_bps = gross_bps - ROUNDTRIP_FEE_BPS
    return {
        "entry_price": entry_price,
        "entry_bar_ts": entry["_ts"],
        "exit_price": exit_price,
        "exit_ts": exit_ts,
        "terminal": terminal,
        "bars_held": bars_held,
        "gross_bps": gross_bps,
        "net_bps_fee8": net_bps,
        "gross_usd": NOTIONAL_USD * gross_bps / 10000.0,
        "net_usd_fee8": NOTIONAL_USD * net_bps / 10000.0,
        "mfe_bps": max_fav_bps,
        "mae_bps": max_adv_bps,
    }


def load_rejections() -> list[dict]:
    events = []
    with ORDER_LOG.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("event_type") == "DECISION_INTENT_REJECTED":
                ts = int(obj.get("timestamp") or obj.get("ts_ms") or 0)
                if 1777334400000 <= ts < 1777507200000:
                    events.append(obj)
    return events


def market_summary(symbols: set[str], dates: list[str]) -> list[dict]:
    out = []
    for symbol in sorted(symbols):
        bars = load_bars(symbol, dates, 180)
        if not bars:
            continue
        first = bars[0]
        last = bars[-1]
        hi = max(r["_high"] for r in bars)
        lo = min(r["_low"] for r in bars)
        ret_bps = (last["_close"] / first["_open"] - 1.0) * 10000.0
        range_bps = (hi / lo - 1.0) * 10000.0
        up_bars = sum(1 for r in bars if r["_close"] >= r["_open"])
        out.append({
            "symbol": symbol,
            "bars": len(bars),
            "first_utc": dt_utc(first["_ts"]),
            "last_utc": dt_utc(last["_ts"]),
            "open": first["_open"],
            "close": last["_close"],
            "ret_bps": ret_bps,
            "range_bps": range_bps,
            "up_bar_ratio": up_bars / len(bars),
        })
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dates = ["2026-04-28", "2026-04-29"]
    events = load_rejections()
    symbols = {e.get("symbol") for e in events if e.get("symbol")}
    bars_by_symbol = {s: load_bars(s, dates, 180) for s in symbols}

    rows = []
    for e in events:
        symbol = e["symbol"]
        side = e["side"]
        ts = int(e["timestamp"])
        bars = bars_by_symbol.get(symbol) or []
        nearest = nearest_entry_bar(bars, ts)
        if nearest is None:
            continue
        idx, entry_bar = nearest
        sim = simulate(bars, idx, side)
        meta = e.get("metadata") or {}
        rows.append({
            "rid": e.get("rid"),
            "ts_utc": dt_utc(ts),
            "ts_kyiv": dt_kyiv(ts),
            "symbol": symbol,
            "side": side,
            "regime": e.get("regime"),
            "regime_conf": e.get("regime_confidence"),
            "nrr_code": e.get("nrr_code"),
            "reject_reason": meta.get("reject_reason"),
            "deny_reason": meta.get("deny_reason"),
            "why": e.get("why"),
            "entry_bar_utc": dt_utc(sim["entry_bar_ts"]),
            **sim,
        })

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    by_reason = Counter(r["why"] for r in rows)
    by_terminal = Counter(r["terminal"] for r in rows)
    by_symbol_terminal = Counter((r["symbol"], r["terminal"]) for r in rows)
    by_gate = defaultdict(list)
    for r in rows:
        key = "confidence_gate" if "FIX-CONF-GATE-01" in str(r["why"]) else "directional_safety_gate"
        by_gate[key].append(r)

    mkt = market_summary(symbols, dates)
    total_gross = sum(r["gross_bps"] for r in rows)
    total_net = sum(r["net_bps_fee8"] for r in rows)
    winners = sum(1 for r in rows if r["net_bps_fee8"] > 0)
    losers = sum(1 for r in rows if r["net_bps_fee8"] <= 0)

    lines = []
    lines.append("# Order Gate Counterfactual 2026-04-28..2026-04-29")
    lines.append("")
    lines.append(f"Events analyzed: {len(rows)} from `{ORDER_LOG}`.")
    lines.append(f"Simulation: independent rejected intents, 180s recorder bars, TP={TP_BPS:.0f} bps, SL={SL_BPS:.0f} bps, fee-adjusted column assumes {ROUNDTRIP_FEE_BPS:.0f} bps roundtrip.")
    lines.append("")
    lines.append("## Totals")
    lines.append(f"- Terminals: {dict(by_terminal)}")
    lines.append(f"- Net winners/losers after fee8: {winners}/{losers}")
    lines.append(f"- Sum gross bps over independent events: {total_gross:.2f}; sum net bps fee8: {total_net:.2f}")
    lines.append(f"- Sum gross USD at {NOTIONAL_USD:.0f} notional each: {sum(r['gross_usd'] for r in rows):.2f}; net fee8 USD: {sum(r['net_usd_fee8'] for r in rows):.2f}")
    lines.append("")
    lines.append("## Gate Buckets")
    for key, vals in by_gate.items():
        lines.append(f"- {key}: count={len(vals)}, terminals={dict(Counter(v['terminal'] for v in vals))}, net_bps={sum(v['net_bps_fee8'] for v in vals):.2f}")
    lines.append("")
    lines.append("## Reject Reasons")
    for reason, count in by_reason.most_common():
        lines.append(f"- {count}x {reason}")
    lines.append("")
    lines.append("## Symbol x Terminal")
    for (symbol, terminal), count in sorted(by_symbol_terminal.items()):
        lines.append(f"- {symbol} {terminal}: {count}")
    lines.append("")
    lines.append("## Market Summary")
    for r in mkt:
        lines.append(f"- {r['symbol']}: bars={r['bars']} {r['first_utc']}..{r['last_utc']}, ret={r['ret_bps']:.1f} bps, range={r['range_bps']:.1f} bps, up_bar_ratio={r['up_bar_ratio']:.2f}")
    lines.append("")
    lines.append("## Event Detail")
    for r in rows:
        lines.append(
            f"- {r['ts_utc']} UTC / {r['ts_kyiv']} Kyiv {r['symbol']} {r['side']} "
            f"{r['terminal']} gross={r['gross_bps']:.1f}bps net8={r['net_bps_fee8']:.1f}bps "
            f"mfe={r['mfe_bps']:.1f}bps mae={r['mae_bps']:.1f}bps gate={r['why']}"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(OUT_MD)
    print(OUT_CSV)
    print("\n".join(lines[:80]))


if __name__ == "__main__":
    main()
