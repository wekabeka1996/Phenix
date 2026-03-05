"""
Post-Cancellation Price Drift Analyzer
======================================
Reads order_log_v1.jsonl, finds each ORDER_PLACED -> ORDER_CANCELLED pair,
then fetches Binance futures klines at T+5/10/15/20/25/30min after the cancel
to assess whether the regime-change cancellation was noise or gave a correct signal.

Usage:  python tools/post_cancel_price_drift.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import json
from datetime import datetime, timezone
from pathlib import Path
import urllib.request, urllib.parse

ROOT      = Path(__file__).resolve().parent.parent
ORDER_LOG = ROOT / "logs" / "order_log_v1.jsonl"
HORIZONS  = [5, 10, 15, 20, 25, 30, 45]

# ── helpers ──────────────────────────────────────────────────────────────────
def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows

def get_price_from_placed(rec: dict) -> float | None:
    """Extract limit price from ORDER_PLACED record."""
    # First try direct field
    for key in ("price", "limit_price", "entry_price"):
        v = rec.get(key)
        if v:
            try:
                f = float(v)
                if f > 0:
                    return f
            except Exception:
                pass
    # Try adapter_response
    ar = rec.get("adapter_response") or {}
    for key in ("price", "avgPrice"):
        v = ar.get(key)
        if v:
            try:
                f = float(v)
                if f > 0:
                    return f
            except Exception:
                pass
    return None

def fetch_kline_close(symbol: str, epoch_ms: int) -> float | None:
    url = ("https://fapi.binance.com/fapi/v1/klines?"
           + urllib.parse.urlencode({"symbol": symbol, "interval": "1m",
                                     "startTime": epoch_ms, "limit": 1}))
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
        return float(data[0][4]) if data else None
    except Exception as exc:
        print(f"    WARN Binance: {exc}", file=sys.stderr)
        return None

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 72)
    print("POST-CANCELLATION PRICE DRIFT ANALYSIS")
    print("=" * 72)

    all_events = load_jsonl(ORDER_LOG)
    print(f"\nTotal events: {len(all_events)}")

    placed_by_order_id: dict[str, dict] = {}
    for ev in all_events:
        if ev.get("event_type") in ("ORDER_PLACED", "ORDER_INTENT"):
            # Key by both order_id and client_order_id
            for k in ("order_id", "client_order_id"):
                v = ev.get(k)
                if v is not None:
                    placed_by_order_id[str(v)] = ev

    cancel_events = [e for e in all_events if e.get("event_type") == "ORDER_CANCELLED"]
    print(f"Cancellations : {len(cancel_events)}")
    print(f"Placed index  : {len(placed_by_order_id)} entries\n")

    rows = []
    skipped = 0
    for ev in cancel_events:
        symbol    = ev.get("symbol", "???")
        reason    = ev.get("reason") or ev.get("cancel_reason") or "?"
        ts_raw    = ev.get("timestamp")   # epoch ms int
        order_id  = str(ev.get("order_id") or "")

        # Parse timestamp
        cancel_ms = None
        if isinstance(ts_raw, (int, float)):
            cancel_ms = int(ts_raw)
        elif isinstance(ts_raw, str):
            try:
                dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                cancel_ms = int(dt.timestamp() * 1000)
            except Exception:
                pass

        if cancel_ms is None:
            skipped += 1
            continue

        # Find placed event
        placed   = placed_by_order_id.get(order_id, {})
        entry_px = get_price_from_placed(placed) if placed else None
        side     = (placed.get("side") or ev.get("side") or "?").upper()

        cancel_dt = datetime.fromtimestamp(cancel_ms / 1000, tz=timezone.utc)
        print(f"{'─'*72}")
        print(f"SYMBOL : {symbol}  SIDE: {side}  ORDER_ID: {order_id}")
        print(f"CANCEL : {cancel_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}  reason={reason}")
        print(f"ENTRY  : {entry_px:.4f}" if entry_px else "ENTRY  : (not found)")

        # Fetch future prices
        price_at: dict[int, float | None] = {}
        for h in HORIZONS:
            price_at[h] = fetch_kline_close(symbol, cancel_ms + h * 60_000)

        # Print drift table
        print()
        if entry_px:
            print(f"  {'Horizon':>7}  {'Price':>10}  {'Delta':>12}  Verdict")
            print(f"  {'─'*7}  {'─'*10}  {'─'*12}  {'─'*22}")
            for h in HORIZONS:
                px = price_at[h]
                if px is None:
                    print(f"  {h:>5}min  {'---':>10}")
                    continue
                d   = px - entry_px
                pct = d / entry_px * 100
                ok  = d > 0 if side in ("BUY", "LONG") else d < 0
                v   = "WIN  (cancel was premature)" if ok else "LOSS (cancel was correct)"
                print(f"  {h:>5}min  {px:>10.4f}  {d:>+10.4f} ({pct:>+.2f}%)  {v}")
        else:
            for h in HORIZONS:
                px = price_at[h]
                print(f"  T+{h:>2}min : {px:.4f}" if px else f"  T+{h:>2}min : N/A")

        rows.append({"symbol": symbol, "side": side, "cancel_ms": cancel_ms,
                     "reason": reason, "entry": entry_px, "prices": price_at})
        print()

    if skipped:
        print(f"(Skipped {skipped} events with no parseable timestamp)\n")

    # ── Summary ────────────────────────────────────────────────────────────────
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    noise = signal = no_data = 0
    for r in rows:
        if not r["entry"]:
            no_data += 1
            continue
        side = r["side"]
        px25 = r["prices"].get(25)
        px20 = r["prices"].get(20)
        px30 = r["prices"].get(30)
        judge = px25 or px30 or px20
        if judge is None:
            no_data += 1
            continue
        right = (judge > r["entry"]) if side in ("BUY", "LONG") else (judge < r["entry"])
        if right:
            noise += 1
        else:
            signal += 1

    total = noise + signal
    print(f"\n  Analysed: {total}  skipped (no price data): {no_data}")
    if total:
        print(f"  Premature cancels (NOISE)  : {noise}/{total}  ({noise/total*100:.0f}%)")
        print(f"  Correct cancels   (SIGNAL) : {signal}/{total}  ({signal/total*100:.0f}%)")
        if noise > signal:
            print("\n  VERDICT: Most cancellations were PREMATURE.")
            print("           Regime change was likely NOISE — system lost alpha.")
            print("           Consider: raise hysteresis_bars or add stale_regime_ttl_sec.")
        else:
            print("\n  VERDICT: System correctly identified regime change.")
            print("           Cancellations were justified — prices moved against the order side.")

if __name__ == "__main__":
    main()
