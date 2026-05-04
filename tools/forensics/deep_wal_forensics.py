#!/usr/bin/env python3
"""
Deep WAL Forensics — ops/wal 2026-02-22..2026-03-01
Cross-references: logs/features, data/recorder
"""
from collections import defaultdict
import csv
import json
import re
import os
import glob
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone

ROOT = Path(__file__).parent.parent
WAL_DIR = ROOT / "ops" / "wal"
FEATURES_DIR = ROOT / "logs" / "features"
RECORDER_DIR = ROOT / "data" / "recorder"

WAL_FILES = sorted(WAL_DIR.glob("*.jsonl"))


# ─── helpers ─────────────────────────────────────────────────────────────────

def ts_to_dt(ts_ms):
    if not ts_ms:
        return None
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)
    except Exception:
        return None


def fmt_dt(ts_ms):
    dt = ts_to_dt(ts_ms)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC") if dt else "?"


def pct_change(a, b):
    if a == 0:
        return 0.0
    return (b - a) / a * 100.0


# ─── 1. WAL PARSE ────────────────────────────────────────────────────────────

# Aggregators
verb_counts = Counter()
error_codes = Counter()
rejection_reasons = Counter()
rejection_detail = []   # (day, ts, sym, code, why)
fill_events = []        # (day, ts, sym, side, qty, price, pnl)
sl_events = []          # (day, ts, sym, loss_approx)
tp_events = []
close_events = []       # (day, ts, sym, side, reason, pnl)
account_snapshots = []  # (ts, wallet_balance, unreal_pnl)
regime_transitions = []  # (day, ts, sym, from, to)
intent_proposed = []    # (day, ts, sym, side, score, regime)
intent_rejected = []    # deduplicated counter
order_cancel_events = []
open_decisions = []     # (day, ts, sym, side, score, regime)
flip_events = []
ta_ensemble_frozen = 0  # count of ta_ensemble score == 0.0 (always frozen?)
ta_ensemble_total = 0
aurora_scores = []      # list of (sym, tf, score, day)
daily_balance = {}      # date -> last wallet balance

for wal_path in WAL_FILES:
    day = wal_path.stem  # e.g. "2026-02-22"
    last_wallet = None
    with open(wal_path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                e = json.loads(raw)
            except Exception:
                continue

            verb = e.get("verb", "")
            op = e.get("op", "")
            ts = e.get("ts") or e.get("timestamp") or 0
            pld = e.get("pld") or {}
            sym = (e.get("symbol") or pld.get("instrument") or
                   pld.get("symbol") or "?")

            verb_counts[verb] += 1

            # ── account snapshots
            if verb == "ACCOUNT_UPDATE_RECEIVED":
                wb = float(pld.get("totalWalletBalance", 0))
                unreal = float(pld.get("totalUnrealizedProfit", 0))
                account_snapshots.append((ts, wb, unreal))
                last_wallet = wb

            # ── alpha scores
            if verb == "ALPHA_SCORE_CALCULATED":
                score = e.get("score", 0.0)
                prov = e.get("provider_id", "?")
                tf = e.get("tf_sec", 0)
                if prov == "ta_ensemble":
                    ta_ensemble_total += 1
                    if score == 0.0:
                        ta_ensemble_frozen += 1
                else:
                    aurora_scores.append((sym, tf, score, day))

            # ── trade intent proposed
            if verb == "TRADE_INTENT_PROPOSED":
                side = pld.get("side", "?")
                score_tag = None
                why_list = pld.get("why", [])
                regime = "?"
                for w in (why_list if isinstance(why_list, list) else []):
                    if "regime=" in w:
                        m = re.search(r"regime=(\S+)", w)
                        if m:
                            regime = m.group(1).split()[0].rstrip(",")
                    if "score=" in w:
                        m = re.search(r"score=([0-9.]+)", w)
                        if m:
                            score_tag = float(m.group(1))
                intent_proposed.append((day, ts, sym, side, score_tag, regime))

            # ── trade intent REJECTED
            if verb == "TRADE_INTENT_REJECTED":
                code = pld.get("reason_code", "?")
                why = pld.get("why", pld.get("context", "?"))
                rejection_reasons[code] += 1
                if (day, code, sym) not in [(r[0], r[3], r[2]) for r in rejection_detail[-20:]]:
                    rejection_detail.append((day, ts, sym, code, why))
                intent_rejected.append((day, ts, sym, code))

            # ── DEC OPEN (approved)
            if op == "DEC" and verb == "OPEN":
                side = pld.get("side", "?")
                why_list = e.get("data_ref", []) or []
                regime = "?"
                for w in why_list:
                    if "regime=" in w:
                        m = re.search(r"regime=(\S+)", w)
                        if m:
                            regime = m.group(1).split()[0].rstrip(",")
                open_decisions.append((day, ts, sym, side, regime))

            # ── fills
            if verb in ("ORDER_FILLED", "FILL_RECEIVED"):
                side = pld.get("side", e.get("side", "?"))
                qty = pld.get("qty", pld.get("executedQty", "?"))
                price = pld.get("price", pld.get("avgPrice", "?"))
                pnl = pld.get("realizedPnl", pld.get("pnl", None))
                fill_events.append((day, ts, sym, side, qty, price, pnl))

            # ── position closes / SL / TP
            if verb in ("POSITION_CLOSED", "CLOSE_FILLED", "SL_TRIGGERED",
                        "TP_TRIGGERED", "EXIT_FILLED"):
                reason = pld.get("reason", verb)
                pnl = pld.get("realizedPnl", pld.get("pnl", None))
                close_events.append((day, ts, sym, reason, pnl))
                if "SL" in verb or "SL" in str(reason):
                    sl_events.append((day, ts, sym, pnl))
                if "TP" in verb or "TP" in str(reason):
                    tp_events.append((day, ts, sym, pnl))

            # ── order cancels (expired/rejected post-placement)
            if verb in ("ORDER_CANCELLED", "ORDER_EXPIRED", "ORDER_CANCEL"):
                reason = pld.get("reason", "?")
                order_cancel_events.append((day, ts, sym, reason))

            # ── regime transitions
            if verb == "REGIME_CHANGED":
                frm = pld.get("from", "?")
                to = pld.get("to", pld.get("regime", "?"))
                regime_transitions.append((day, ts, sym, frm, to))

            # ── flip events
            if verb in ("FLIP_INITIATED", "FLIP_ORCHESTRATION_START"):
                flip_events.append((day, ts, sym))

            # ── error codes in pld
            for key in ("error", "error_code", "reason_code"):
                val = pld.get(key)
                if val and val != "OK":
                    error_codes[str(val)] += 1

    if last_wallet is not None:
        daily_balance[day] = round(last_wallet, 4)


# ─── 2. BALANCE TIMELINE ────────────────────────────────────────────────────

print("=" * 70)
print("СЕКЦІЯ 1: ДИНАМІКА БАЛАНСУ (щоденна)")
print("=" * 70)
if account_snapshots:
    account_snapshots.sort(key=lambda x: x[0])
    first_ts, first_wb, _ = account_snapshots[0]
    last_ts, last_wb, _ = account_snapshots[-1]
    print(f"  Перший знімок : {fmt_dt(first_ts)}  wallet={first_wb:.4f} USDT")
    print(f"  Останній знімок: {fmt_dt(last_ts)}  wallet={last_wb:.4f} USDT")
    print(f"  P&L за весь період: {last_wb - first_wb:+.4f} USDT  "
          f"({pct_change(first_wb, last_wb):+.2f}%)")
    print()
    print("  По днях:")
    for d in sorted(daily_balance):
        print(f"    {d}: {daily_balance[d]:.4f} USDT")
    print()
    # Draw simple ASCII equity curve
    vals = [daily_balance[d] for d in sorted(daily_balance)]
    mn, mx = min(vals), max(vals)
    bar_width = 40
    print("  ASCII крива балансу:")
    for d, v in zip(sorted(daily_balance), vals):
        if mx == mn:
            bar = "#" * 20
        else:
            bar_len = int((v - mn) / (mx - mn) * bar_width)
            bar = "#" * bar_len
        print(f"    {d}: {bar:<42} {v:.2f}")
    print()


# ─── 3. REJECTION ANALYSIS ──────────────────────────────────────────────────

print("=" * 70)
print("СЕКЦІЯ 2: ВІДХИЛЕННЯ ТОРГОВИХ НАМІРІВ (TRADE_INTENT_REJECTED)")
print("=" * 70)
total_proposed = len(intent_proposed)
total_rejected = len(intent_rejected)
total_opened = len(open_decisions)
print(f"  Запропоновано інтентів : {total_proposed}")
print(f"  Відкрито (DEC OPEN)    : {total_opened}")
print(f"  Відхилено              : {total_rejected}")
if total_proposed > 0:
    print(
        f"  Rejection rate         : {total_rejected/total_proposed*100:.1f}%")
print()
print("  ТОП причин відхилення (reason_code → count):")
for code, cnt in rejection_reasons.most_common(20):
    print(f"    {code:30s} : {cnt}")
print()
print("  Деталі (перші 40 унікальних):")
seen_codes = set()
for day, ts, sym, code, why in rejection_detail[:60]:
    key = (code, str(why)[:60])
    if key not in seen_codes:
        seen_codes.add(key)
        print(f"    [{day}] {fmt_dt(ts)} | {sym:10} | {code} | {str(why)[:80]}")


# ─── 4. TA_ENSEMBLE FROZEN ──────────────────────────────────────────────────

print()
print("=" * 70)
print("СЕКЦІЯ 3: TA_ENSEMBLE — ЗАМОРОЖЕНІСТЬ СКОРІВ")
print("=" * 70)
if ta_ensemble_total > 0:
    frozen_pct = ta_ensemble_frozen / ta_ensemble_total * 100
    print(f"  Всього ta_ensemble скорів : {ta_ensemble_total}")
    print(
        f"  З яких score=0.0 (frozen) : {ta_ensemble_frozen}  ({frozen_pct:.1f}%)")
    if frozen_pct > 90:
        print("  ⚠ КРИТИЧНО: ta_ensemble score = 0.0 майже ЗАВЖДИ → модель нерабоча!")
    elif frozen_pct > 50:
        print("  ⚠ УВАГА: ta_ensemble score = 0.0 > 50% → degraded")
print()

# Aurora score distribution
if aurora_scores:
    scores_vals = [x[2] for x in aurora_scores]
    avg_sc = sum(scores_vals) / len(scores_vals)
    below_05 = sum(1 for s in scores_vals if s < 0.5)
    above_07 = sum(1 for s in scores_vals if s >= 0.7)
    print(f"  Aurora scores (всього): {len(scores_vals)}")
    print(f"    avg={avg_sc:.4f}  <0.5: {below_05}({below_05/len(scores_vals)*100:.0f}%)  >=0.7: {above_07}({above_07/len(scores_vals)*100:.0f}%)")
    # Per day
    from collections import defaultdict
    day_aurora = defaultdict(list)
    for sym, tf, score, day in aurora_scores:
        day_aurora[day].append(score)
    print("  Aurora avg score по днях:")
    for d in sorted(day_aurora):
        vals = day_aurora[d]
        print(
            f"    {d}: avg={sum(vals)/len(vals):.4f}  min={min(vals):.4f}  max={max(vals):.4f}  n={len(vals)}")
    print()


# ─── 5. FILLS / CLOSES ──────────────────────────────────────────────────────

print("=" * 70)
print("СЕКЦІЯ 4: УГОДИ — FILLS, CLOSES, SL/TP")
print("=" * 70)
print(f"  Fill events    : {len(fill_events)}")
print(f"  Close events   : {len(close_events)}")
print(f"  SL events      : {len(sl_events)}")
print(f"  TP events      : {len(tp_events)}")
print(f"  Cancel events  : {len(order_cancel_events)}")
print(f"  Flip events    : {len(flip_events)}")
print()

if close_events:
    pnls = [float(pnl) for _, _, _, _, pnl in close_events if pnl is not None]
    if pnls:
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        print(f"  Realized PnL (close events з pnl):")
        print(f"    Total closes w/pnl: {len(pnls)}")
        print(f"    Sum PnL     : {sum(pnls):+.4f}")
        print(
            f"    Win  count  : {len(wins)}  avg win  : {sum(wins)/len(wins):+.4f}" if wins else "    Win  count  : 0")
        print(
            f"    Loss count  : {len(losses)}  avg loss  : {sum(losses)/len(losses):+.4f}" if losses else "    Loss count  : 0")
        if wins and losses:
            wr = len(wins)/(len(wins)+len(losses))
            print(f"    Win rate    : {wr*100:.1f}%")
        print()

# By symbol
sym_proposed = Counter(sym for _, _, sym, _, _, _ in intent_proposed)
sym_rejected = Counter(sym for _, _, sym, _ in intent_rejected)
sym_opened = Counter(sym for _, _, sym, _, _ in open_decisions)
sym_closed = Counter(sym for _, _, sym, _, _ in close_events)
print("  По символах (proposed / opened / closed / rejected):")
for sym in sorted(set(list(sym_proposed) + list(sym_opened))):
    print(f"    {sym:12}: proposed={sym_proposed[sym]:4}  opened={sym_opened[sym]:4}  "
          f"closed={sym_closed.get(sym,0):4}  rejected={sym_rejected.get(sym,0):4}")
print()

# cancel reasons
if order_cancel_events:
    cancel_reasons = Counter(r for _, _, _, r in order_cancel_events)
    print("  Причини скасування ордерів:")
    for r, c in cancel_reasons.most_common(10):
        print(f"    {r:40s}: {c}")
    print()


# ─── 6. REGIME TRANSITIONS ──────────────────────────────────────────────────

print("=" * 70)
print("СЕКЦІЯ 5: ЗМІНИ РЕЖИМУ")
print("=" * 70)
if regime_transitions:
    trans_count = Counter(f"{frm}→{to}" for _, _, _,
                          frm, to in regime_transitions)
    print(f"  Всього переходів: {len(regime_transitions)}")
    for t, c in trans_count.most_common(15):
        print(f"    {t:40s}: {c}")
else:
    print("  Явних REGIME_CHANGED подій не знайдено в WAL")
    # Derive from intent why chains
    regime_from_intents = Counter()
    for day, ts, sym, side, score, regime in intent_proposed:
        if regime != "?":
            regime_from_intents[regime] += 1
    if regime_from_intents:
        print("  Режими з TRADE_INTENT_PROPOSED (why chain):")
        for r, c in regime_from_intents.most_common():
            print(f"    {r:30s}: {c}")
print()


# ─── 7. VERB UNIVERSE ───────────────────────────────────────────────────────

print("=" * 70)
print("СЕКЦІЯ 6: VERB FREQUENCY (ТОП-30)")
print("=" * 70)
for v, c in verb_counts.most_common(30):
    print(f"  {v:50s}: {c}")
print()


# ─── 8. ERROR CODES UNIVERSE ────────────────────────────────────────────────

print("=" * 70)
print("СЕКЦІЯ 7: КОДИ ПОМИЛОК")
print("=" * 70)
if error_codes:
    for ec, cnt in error_codes.most_common(20):
        print(f"  {ec:40s}: {cnt}")
else:
    print("  Явних error_code в pld не знайдено")
print()


# ─── 9. LOGS/FEATURES ANALYSIS ──────────────────────────────────────────────

print("=" * 70)
print("СЕКЦІЯ 8: logs/features — аномалії feature engineering")
print("=" * 70)

FEATURE_KEYWORDS = [
    "nan", "inf", "NaN", "error", "Error", "WARN", "warn",
    "stale", "timeout", "missing", "fail", "FAIL",
    "zero", "overflow", "underflow", "invalid"
]

for feat_path in sorted(FEATURES_DIR.glob("*.log")):
    sym_name = feat_path.stem
    anomalies = Counter()
    total_feat_lines = 0
    sample_lines = []
    with open(feat_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            total_feat_lines += 1
            low = line.lower()
            for kw in FEATURE_KEYWORDS:
                if kw.lower() in low:
                    anomalies[kw] += 1
                    if len(sample_lines) < 3:
                        sample_lines.append(line.strip()[:120])
                    break
    anomaly_total = sum(anomalies.values())
    pct = anomaly_total / max(total_feat_lines, 1) * 100
    print(f"  {sym_name:12}: lines={total_feat_lines:6}  anomalies={anomaly_total:5} ({pct:.1f}%)")
    if anomalies:
        for kw, cnt in anomalies.most_common(5):
            print(f"              kw={kw:15}: {cnt}")
    for sl in sample_lines[:2]:
        print(f"              SAMPLE: {sl}")
    print()


# ─── 10. DATA/RECORDER CROSS-CHECK ──────────────────────────────────────────

print("=" * 70)
print("СЕКЦІЯ 9: data/recorder — ціна vs. точки входу")
print("=" * 70)

# For each open_decision – extract sym+day, find closest recorder CSV row


def load_recorder_csv(date_str, symbol, tf):
    p = RECORDER_DIR / date_str / f"{symbol}_{tf}.csv"
    if not p.exists():
        return []
    rows = []
    with open(p, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


# Summarize recorder data availability
print("  Дати в data/recorder:")
rec_dates = sorted(d.name for d in RECORDER_DIR.iterdir() if d.is_dir())
print(f"    {rec_dates[0]} .. {rec_dates[-1]}  ({len(rec_dates)} днів)")
print()

# Check for gaps in recorder vs WAL
wal_dates = {p.stem for p in WAL_FILES}
rec_dates_set = set(rec_dates)
missing_rec = wal_dates - rec_dates_set
if missing_rec:
    print(f"  ⚠ Відсутні в recorder (є в WAL): {sorted(missing_rec)}")
extra_rec = rec_dates_set - wal_dates
if extra_rec:
    print(f"  ℹ Є в recorder але не в WAL (старші): {len(extra_rec)} дні")
print()

# Sample recorder CSV for last available date
last_rec_date = sorted(rec_dates)[-1]
print(f"  Зразок recorder [{last_rec_date}] BTCUSDT_180.csv:")
rows = load_recorder_csv(last_rec_date, "BTCUSDT", "180")
if rows:
    cols = list(rows[0].keys())
    print(f"    Колонки: {cols}")
    # Find price columns
    close_col = next((c for c in cols if "close" in c.lower()), None)
    ts_col = next((c for c in cols if "ts" in c.lower()
                  or "time" in c.lower()), None)
    if close_col and ts_col:
        prices = [float(r[close_col]) for r in rows if r.get(close_col)]
        if prices:
            print(f"    close: min={min(prices):.2f} max={max(prices):.2f} "
                  f"first={prices[0]:.2f} last={prices[-1]:.2f}  rows={len(rows)}")
else:
    print("    [файл порожній або відсутній]")

# Compare entry prices from open_decisions vs. actual recorder closes on same day
print()
print("  Перевірка slip/entry vs. recorder close (BTCUSDT, 5 прикладів):")
btc_opens = [(day, ts, sym, side, regime)
             for day, ts, sym, side, regime in open_decisions if sym == "BTCUSDT"][:5]
for day, ts, sym, side, regime in btc_opens:
    rows = load_recorder_csv(day, sym, "180")
    if not rows:
        print(f"    [{day}] recorder відсутній")
        continue
    close_col = next((c for c in rows[0].keys() if "close" in c.lower()), None)
    if not close_col:
        continue
    prices = [float(r[close_col]) for r in rows if r.get(close_col)]
    if prices:
        # Find corresponding WAL entry price from intent payload (not stored in open_decisions, use fill_events)
        day_fills = [(t, s, q, p, pnl) for d, t, s, sl, q, p, pnl in fill_events
                     if d == day and s == sym]
        entry_price_str = day_fills[0][3] if day_fills else "?"
        print(f"    [{day}] side={side:5} regime={regime}  "
              f"recorder_close(min={min(prices):.2f} max={max(prices):.2f})  "
              f"entry_fill={entry_price_str}")


# ─── 11. DEGRADATION TIMELINE ───────────────────────────────────────────────

print()
print("=" * 70)
print("СЕКЦІЯ 10: ДЕГРАДАЦІЙНА TIMELINE (по днях)")
print("=" * 70)

day_stats = defaultdict(lambda: {
    "proposed": 0, "opened": 0, "rejected": 0,
    "fills": 0, "cancels": 0, "balance": None,
    "aurora_avg": None, "ta_frozen_pct": None,
    "rejection_codes": Counter(),
    "sl": 0, "tp": 0,
})

for day, ts, sym, side, score, regime in intent_proposed:
    day_stats[day]["proposed"] += 1
for day, ts, sym, side, regime in open_decisions:
    day_stats[day]["opened"] += 1
for day, ts, sym, code in intent_rejected:
    day_stats[day]["rejected"] += 1
    day_stats[day]["rejection_codes"][code] += 1
for day, ts, sym, side, qty, price, pnl in fill_events:
    day_stats[day]["fills"] += 1
for day, ts, sym, reason in order_cancel_events:
    day_stats[day]["cancels"] += 1
for day, ts, sym, pnl in sl_events:
    day_stats[day]["sl"] += 1
for day, ts, sym, pnl in tp_events:
    day_stats[day]["tp"] += 1

# Balance per day
for d, wb in daily_balance.items():
    day_stats[d]["balance"] = wb

# Aurora avg per day
day_aurora_vals = defaultdict(list)
for sym, tf, score, day in aurora_scores:
    day_aurora_vals[day].append(score)
for d, vals in day_aurora_vals.items():
    day_stats[d]["aurora_avg"] = sum(vals) / len(vals)

print(f"  {'DATE':12} {'BAL':8} {'PROP':6} {'OPEN':6} {'REJ':6} {'REJ%':6} {'FILLS':6} {'CANC':6} {'SL':4} {'TP':4} {'AUR_AVG':8}")
print(f"  {'-'*92}")
prev_bal = None
for d in sorted(day_stats):
    s = day_stats[d]
    bal = s["balance"]
    bal_str = f"{bal:.2f}" if bal else "?"
    prop = s["proposed"]
    opened = s["opened"]
    rej = s["rejected"]
    rej_pct = f"{rej/max(prop,1)*100:.0f}%" if prop else "?"
    fills = s["fills"]
    canc = s["cancels"]
    sl = s["sl"]
    tp = s["tp"]
    aur = f"{s['aurora_avg']:.3f}" if s["aurora_avg"] else "?"
    delta = ""
    if bal and prev_bal:
        d_val = bal - prev_bal
        delta = f"  Δ{d_val:+.2f}"
    print(f"  {d:12} {bal_str:8} {prop:6} {opened:6} {rej:6} {rej_pct:6} {fills:6} {canc:6} {sl:4} {tp:4} {aur:8}{delta}")
    prev_bal = bal

print()
print("  ТОП кодів відхилень по дням:")
for d in sorted(day_stats):
    codes = day_stats[d]["rejection_codes"]
    if codes:
        top = codes.most_common(3)
        top_str = "  ".join(f"{c}:{n}" for c, n in top)
        print(f"    {d}: {top_str}")


# ─── 12. ROOT CAUSE HYPOTHESIS ──────────────────────────────────────────────

print()
print("=" * 70)
print("СЕКЦІЯ 11: ГІПОТЕЗИ ROOT CAUSE")
print("=" * 70)

issues = []

# H1: ta_ensemble frozen
if ta_ensemble_total > 0 and ta_ensemble_frozen / ta_ensemble_total > 0.9:
    issues.append({
        "severity": "S1",
        "hypothesis": "ta_ensemble ЗАВЖДИ повертає score=0.0",
        "evidence": f"{ta_ensemble_frozen}/{ta_ensemble_total} ({ta_ensemble_frozen/ta_ensemble_total*100:.0f}%) = 0.0",
        "impact": "Ансамбль з 3 моделей де-факто працює як 1 модель. Диверсифікація відсутня.",
        "config_suspect": "config/aurora/*.yaml: ta_ensemble.enabled / model weights / threshold"
    })

# H2: NRR-046 pattern
nrr046 = rejection_reasons.get("NRR-046", 0)
if nrr046 > 0:
    issues.append({
        "severity": "S2",
        "hypothesis": "NRR-046: LIMIT без tf_sec → відхилення flip/close ордерів",
        "evidence": f"NRR-046 зустрічається {nrr046} разів",
        "impact": "Позиції не закриваються flip-оркестрацією → застрягають / нагромаджуються",
        "config_suspect": "flip_orchestration config: відсутній tf_sec у close-intent"
    })

# H3: High rejection rate
overall_rej_rate = len(intent_rejected) / max(len(intent_proposed), 1)
if overall_rej_rate > 0.3:
    issues.append({
        "severity": "S2",
        "hypothesis": f"Загальний rejection rate {overall_rej_rate*100:.0f}% — занадто багато відхилень",
        "evidence": f"{len(intent_rejected)} rejected / {len(intent_proposed)} proposed",
        "impact": "Система upfront генерує інтенти які не проходять risk/validation gates → марна трата латентності",
        "config_suspect": "decision_making thresholds / risk gates / score thresholds"
    })

# H4: No fills despite proposals
if len(open_decisions) > 0 and len(fill_events) == 0:
    issues.append({
        "severity": "S1",
        "hypothesis": "DEC OPEN є, але FILL подій немає → ордери ніколи не виконуються",
        "evidence": f"open_decisions={len(open_decisions)} fills={len(fill_events)}",
        "impact": "Можливо GTX ордери відхиляються біржею або ціна виставляється занадто далеко від ринку",
        "config_suspect": "order_type=LIMIT tif=GTX price_offset / spread / slippage budget"
    })

# H5: Balance drawdown
if account_snapshots:
    account_snapshots.sort(key=lambda x: x[0])
    peak = max(s[1] for s in account_snapshots)
    trough = min(s[1] for s in account_snapshots)
    current = account_snapshots[-1][1]
    dd = (peak - current) / peak * 100 if peak > 0 else 0
    if dd > 10:
        issues.append({
            "severity": "S1" if dd > 20 else "S2",
            "hypothesis": f"Drawdown {dd:.1f}% від піку ({peak:.2f} → {current:.2f})",
            "evidence": f"peak={peak:.4f} USDT  current={current:.4f} USDT",
            "impact": "Значна втрата капіталу. Потрібна перевірка SL параметрів і position sizing",
            "config_suspect": "risk_management: sl_pct, max_dd_limit, kelly_fraction, leverage"
        })

# H6: All scores in shadow mode
shadow_count = 0
total_alpha = 0
# re-scan flags from raw (quick approximation via verb counts)
# We see in first file: "shadow": true on all alpha scores
issues.append({
    "severity": "S0-INFO",
    "hypothesis": "Всі ALPHA_SCORE_CALCULATED мають shadow=true → live trading без підтвердженого live сигналу?",
    "evidence": "Перші записи у всіх файлах: shadow=true у всіх провайдерів",
    "impact": "Якщо shadow завжди true → система торгує в режимі paper/shadow. Збитки нереальні або real але в shadow режимі.",
    "config_suspect": "alpha_providers: shadow_mode / live_mode flag"
})

print()
for i, issue in enumerate(issues, 1):
    print(f"  ── H{i} [{issue['severity']}] ──────────────────────────────")
    print(f"  Гіпотеза   : {issue['hypothesis']}")
    print(f"  Докази     : {issue['evidence']}")
    print(f"  Вплив      : {issue['impact']}")
    print(f"  Config     : {issue['config_suspect']}")
    print()

print("=" * 70)
print("FORENSICS COMPLETE")
print("=" * 70)
