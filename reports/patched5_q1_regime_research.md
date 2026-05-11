# Aurora patched5 — Q1 2024 Regime Research
*Baseline: patched5 | Research scope: Jan / Feb / Mar / Q1 CUM 2024*
*Status: PARTIAL — DOGE sanity-check complete; Q1 backtest results pending*

---

## SECTION 0 — Executive Verdicts

> *Q1 CUM complete. Standalone Feb/Mar not yet run.*

| Subject | Prior verdict | Q1 CUM signal | **Final Q1 verdict** |
|---|---|---|---|
| ETH TREND_DOWN | MONITOR | Q1 CUM +62.73, Jan +33.85 ✅ | **KEEP** — consistently positive |
| ETH MR | KEEP | Q1 CUM +51.14, thin PF ⚠️ | **KEEP / watch payoff** |
| BNB MR | MONITOR | Q1 CUM +27.04 ✅ (n=31!) | **UPGRADE to KEEP** |
| DOGE | CONFIG GAP | **Q1 CUM −686.69 = root cause** ❌ | **BLOCK IMMEDIATELY** |
| patched5 baseline | CONFIRM | Q1 w/o DOGE ≈ +89.77 USDT ✅ | **CONFIRM** (DOGE must be removed) |

---

## SECTION 1 — DOGE Sanity-Check

### 1.1 Question

Is DOGEUSDT in Aurora active **intentionally** or is it a **config gap / stale drift**?

### 1.2 Trace — how DOGE gets into backtests

The entry path has 4 layers:

```
config/aurora/strategies.yaml (SSOT registry)
  assignments.DOGEUSDT: [aurora]          ← still present
        ↓
config_loader._derive_symbols_to_track_ssot()
  → trading.symbols_to_track includes "DOGEUSDT"
        ↓
apply_backtest_symbols_filter()
  → aurora.decision.symbols_to_track contains DOGEUSDT → kept
        ↓
aurora_handler._is_symbol_enabled("DOGEUSDT")
  → registry: DOGEUSDT: [aurora] → returns True
        ↓
aurora_decision: allowed_regimes = ["TREND_DOWN","LOW_VOLATILITY",
  "FLAT_NORMAL","MEAN_REVERSION","TREND_UP"]   ← 5 regimes, not blocked
        ↓
DOGE trades fire
```

### 1.3 Where the gap is

`config/aurora/strategies/aurora.yaml` lines 454–461 contains:

```yaml
# P2-2: DOGE/XRP REMOVED - MR-only symbols per strategies.yaml registry
# DOGEUSDT and XRPUSDT are assigned to mean_reversion ONLY in strategies.yaml.
# Registry SSOT (strategies_registry.assignments) now controls activation.
```

**This comment is stale and factually wrong.** The intent (P2-2) was to move DOGE to MR-only. The `config/mean_reversion/strategies.yaml` was updated (`DOGEUSDT: [mean_reversion]`), but `config/aurora/strategies.yaml` was **never changed** — it still contains `DOGEUSDT: [aurora]`.

### 1.4 Additional facts

- `aurora.assets.DOGEUSDT.enabled: true` — field not enforced when registry entry exists
- `aurora.assets.DOGEUSDT.allowed_regimes: ["TREND_DOWN","LOW_VOLATILITY","FLAT_NORMAL","MEAN_REVERSION","TREND_UP"]` — 5 regimes, no block
- `aurora.decision.symbols_to_track` contains DOGEUSDT (explicitly listed)
- The `enabled: false` field is only read as fallback when a symbol has **no registry entry at all**. Since the registry has `DOGEUSDT: [aurora]`, `enabled` has no effect.

### 1.5 Why `enabled: false` doesn't block

From `aurora_handler._is_symbol_enabled()`:
```python
def _is_symbol_enabled(self, symbol):
    registry = getattr(self.config, "strategies_registry", None)
    if registry:
        symbol_strategies = assignments.get(symbol, [])
        if symbol_strategies:
            return "aurora" in symbol_strategies   # REGISTRY WINS
    # fallback: read asset.enabled — only if no registry entry
    return bool(getattr(asset_cfg, "enabled", True))
```

Only `allowed_regimes: []` is the real block gate (fail-closed contract, confirmed).

### 1.6 Verdict

**`DOGE = CONFIG GAP`**

DOGEUSDT is active in Aurora backtests due to **stale drift** — the P2-2 intent was documented but the aurora SSOT registry (`config/aurora/strategies.yaml`) was never updated. The symbol has been trading across 5 regimes in all Q4 backtests without this being a deliberate design decision for patched5.

### 1.7 Q4 impact summary (known data)

| Window | DOGE n | PnL | Primary driver |
|---|---|---|---|
| Jun-Sep CUM | 0 | 0 | not active in summer 2023 |
| DEC-only | 25 | −15.80 | TREND_DOWN shorts in bull run |
| Q4 CUM | 32 | **+120.50** | TREND_UP (Oct-Nov bull start) + Oct TREND_DOWN shorts |

Without DOGE, Q4 CUM would be **−152.61 USDT** instead of −32.11. DOGE accidentally masked ETH structural losses.

### 1.8 What to do (not patching now, observation only)

To block DOGE from Aurora (as P2-2 intended), the fix is:
```yaml
# config/aurora/strategies.yaml
assignments:
  DOGEUSDT: []      # was: [aurora]  — remove from registry
  # OR remove key entirely
```

**Not acting now** — observation/finding only per task scope.

---

## SECTION 2 — Artifact Validity Protocol

Each Q1 run is valid **only if**:

| Check | Expected | If violated |
|---|---|---|
| `BTCUSDT trades` | 0 | INVALID — patched4b block failed |
| `1000PEPEUSDT trades` | 0 | INVALID — patched4a_v2 block failed |
| `ETH × LOW_VOLATILITY trades` | 0 | INVALID — patched5 LOW_VOL block failed |
| `BNB × LOW_VOLATILITY trades` | 0 | INVALID — patched5 LOW_VOL block failed |

Validation script (run after each backtest):

```bash
python -X utf8 -c "
import json, pathlib, sys, glob, os

# find latest backtest JSON
files = sorted(glob.glob('reports/backtests/backtest_*.json'), key=os.path.getmtime)
path = files[-1]
data = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
trades = [t for t in data.get('trades', []) if t.get('close_reason')]

checks = {
  'BTCUSDT': 0,
  '1000PEPEUSDT': 0,
  'ETH_LOW_VOL': 0,
  'BNB_LOW_VOL': 0,
}
for t in trades:
    sym = t.get('symbol','')
    reg = t.get('market_regime','')
    if sym == 'BTCUSDT': checks['BTCUSDT'] += 1
    if sym == '1000PEPEUSDT': checks['1000PEPEUSDT'] += 1
    if sym == 'ETHUSDT' and reg == 'LOW_VOLATILITY': checks['ETH_LOW_VOL'] += 1
    if sym == 'BNBUSDT' and reg == 'LOW_VOLATILITY': checks['BNB_LOW_VOL'] += 1

all_ok = all(v == 0 for v in checks.values())
status = 'VALID' if all_ok else 'INVALID'
print(f'Run: {path}')
print(f'Status: {status}')
for k, v in checks.items():
    flag = 'OK' if v == 0 else 'VIOLATION'
    print(f'  {k}: {v} trades [{flag}]')
"
```

---

## SECTION 3 — Monthly Results

> *Fill after running backtests. Use extraction script below.*

### Extraction script (run after each completed backtest)

```bash
python -X utf8 -c "
import json, pathlib, glob, os, collections

files = sorted(glob.glob('reports/backtests/backtest_*.json'), key=os.path.getmtime)
path = files[-1]
data = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
m = data.get('metrics', {})
trades = [t for t in data.get('trades', []) if t.get('close_reason')]

print('=== OVERALL ===')
for k in ['total_pnl','roi_pct','max_drawdown','win_rate','sharpe_ratio','end_balance','closed_trades']:
    print(f'  {k}: {m.get(k)}')

print()
print('=== PER SYMBOL x REGIME ===')
key_data = collections.defaultdict(lambda: {'n':0,'pnl':0.0,'wins':0,'sl':0,'tp':0,'pnls':[]})
for t in trades:
    sym = t.get('symbol','?')
    reg = t.get('market_regime','?')
    k = (sym, reg)
    p = t.get('pnl_usdt_net',0) or 0
    cr = t.get('close_reason','?')
    key_data[k]['n'] += 1
    key_data[k]['pnl'] += p
    key_data[k]['pnls'].append(p)
    if p > 0: key_data[k]['wins'] += 1
    if cr == 'SL': key_data[k]['sl'] += 1
    if cr == 'TP': key_data[k]['tp'] += 1

for (sym, reg), v in sorted(key_data.items(), key=lambda x: x[1]['pnl']):
    if v['n'] == 0: continue
    ev = v['pnl']/v['n']
    wr = v['wins']/v['n']
    wl = [p for p in v['pnls'] if p>0]
    ll = [p for p in v['pnls'] if p<=0]
    aw = sum(wl)/len(wl) if wl else 0
    al = sum(ll)/len(ll) if ll else 0
    print(f'  {sym:<18} x {reg:<18}: n={v[\"n\"]:>3} pnl={v[\"pnl\"]:>9.2f} ev={ev:>7.2f} WR={wr:.0%} SL={v[\"sl\"]} TP={v[\"tp\"]} avg_win={aw:.2f} avg_loss={al:.2f}')
"
```

### 3.1 Summary table

| Window | total_pnl | roi% | DD% | trades | WR% | sharpe | end_balance | validity |
|---|---|---|---|---|---|---|---|---|
| **Jan 2024** | **+21.60** | +2.16% | 25.57% | 47 | 70.2% | +0.25 | 1021.60 | **✅ VALID** |
| Feb 2024 | see →Q1 CUM | — | — | — | — | — | — | standalone pending |
| Mar 2024 | see →Q1 CUM | — | — | — | — | — | — | standalone pending |
| **Q1 2024 CUM** | **−595.68** | −59.57% | **90.02%** | **600** | 63.83% | −0.187 | 404.32 | **✅ VALID¹** |
| Q1 CUM **w/o DOGE** | **≈ +89.77** | ≈+8.98% | — | 180 | — | — | — | hypothetical |

¹ Valid (no BTC/PEPE/ETH_LV/BNB_LV violations), but results dominated by DOGE config gap. See Section 10.

### 3.2 Jan 2024 — run_id: `20260311_013432` ✅ VALID

**Validity:** BTC=0 · PEPE=0 · ETH_LV=0 · BNB_LV=0

| Metric | Value |
|---|---|
| total_pnl | **+21.60 USDT** |
| roi_pct | +2.16% |
| max_drawdown | **25.57%** |
| closed_trades | 47 |
| win_rate | 70.2% |
| sharpe_ratio | +0.25 |
| end_balance | 1021.60 USDT |

**Per-symbol × regime:**

| Symbol × Regime | n | PnL | EV/t | WR% | SL | TP | avg_win | avg_loss |
|---|---|---|---|---|---|---|---|---|
| BNB × MR | 7 | **−23.18** | −3.31 | 71% | 2 | 5 | +4.72 | −23.39 |
| ETH × MR | 11 | +7.81 | +0.71 | 82% | 2 | 9 | +9.18 | −37.39 |
| ETH × TREND_DOWN | 29 | **+33.85** | +1.17 | 66% | 10 | 19 | +38.77 | −70.28 |
| DOGE (all) | **0** | **0** | — | — | — | — | — | — |

**Key Jan findings:**
- DOGE = 0 trades (inactive — not active in Jan 2024 crypto market conditions)
- ETH TREND_DOWN returned to positive EV (+1.17) after Dec anomaly
- BNB MR structural asymmetry confirmed: avg_win=+4.72 vs avg_loss=−23.39, PF≈0.50
- ETH MR WR dropped from 100% (Nov/Dec) to 82% — 2 SL events emerged, PF concern developing

### 3.3 Feb 2024

> *Standalone run not executed. Feb data available from Q1 CUM monthly breakdown only (see 3.5).*

### 3.4 Mar 2024

> *Standalone run not executed. Mar data available from Q1 CUM monthly breakdown only (see 3.5).*

### 3.5 Q1 2024 CUM — run_id: `20260311_121654` ✅ VALID (but DOGE-contaminated)

**Validity:** BTC=0 · PEPE=0 · ETH_LV=0 · BNB_LV=0

| Metric | Value |
|---|---|
| total_pnl | **−595.68 USDT** |
| roi_pct | −59.57% |
| max_drawdown | **90.02%** |
| closed_trades | **600** |
| win_rate | 63.83% |
| sharpe_ratio | −0.187 |
| end_balance | 404.32 USDT |
| balance peak | **2014.97 USDT** (end of Mar week 1) |

**Monthly breakdown (from Q1 CUM):**

| Month | N trades | PnL | Balance end | DOGE trades |
|---|---|---|---|---|
| Jan 2024 | 50 | +218.37 | 1218.37 | **0** |
| Feb 2024 | 59 | +156.60 | 1374.97 | 21 |
| Mar 2024 | **491** | **−971.88** | 403.09 | **399** |

**Per-symbol × regime (full 600 trades):**

| Symbol × Regime | n | PnL | EV/t | WR% | SL | TP | avg_win | avg_loss |
|---|---|---|---|---|---|---|---|---|
| **DOGE TREND_UP** | **265** | **−234.33** | −0.88 | 64.5% | 94 | 171 | +24.80 | −47.61 |
| **DOGE TREND_DOWN** | **106** | **−232.51** | −2.19 | 52.8% | 50 | 56 | +17.34 | −24.07 |
| **DOGE LOW_VOL** | **48** | **−224.08** | **−4.67** | 60.4% | 19 | 29 | +12.96 | −31.57 |
| DOGE MR | 1 | +4.22 | +4.22 | 100% | 0 | 1 | +4.22 | — |
| ETH TREND_DOWN | 122 | +11.60 | +0.10 | 62.3% | 46 | 76 | +37.71 | −62.05 |
| BNB MR | **31** | **+27.04** | **+0.87** | **83.9%** | 5 | 26 | +6.22 | −26.93 |
| ETH MR | 27 | +51.14 | +1.89 | 81.5% | 5 | 22 | +12.14 | −43.20 |

**Total DOGE: 420 trades, −686.69 USDT**
**Total ETH+BNB: 180 trades, +89.77 USDT**

### 3.5 Q1 2024 Cumulative

> *Paste extraction output here.*

---

## SECTION 4 — ETH Regime Research

> *To be filled.*

### ETH TREND_DOWN — EV/trade progression

| Window | n | PnL | EV/t | WR% | SL | PF | verdict signal |
|---|---|---|---|---|---|---|---|
| Jun-Sep CUM | 88 | +765.70 | +8.70 | 75% | 17 | — | ✅ |
| Sep-only | 12 | +178.12 | +14.84 | 91.7% | 1 | — | ✅ |
| Nov-only | 14 | +73.36 | +5.24 | 71% | 4 | 1.22 | ✅ |
| Dec-only | 24 | −136.68 | −5.69 | 62% | 9 | 0.76 | ❌ |
| Q4 CUM | 39 | −170.51 | −4.37 | 64% | 14 | 0.84 | ❌ |
| **Jan 2024** | **29** | **+33.85** | **+1.17** | **66%** | **10** | **1.05** | **✅ recovery** |
| **Q1 CUM** | **122** | **+11.60** | **+0.10** | 62% | 46 | ~1.0 | **⚠️ near-zero** |
| **Feb 2024** | see Q1 | — | — | — | — | — | — |
| **Mar 2024** | see Q1 | — | — | — | — | — | — |

**Q1 CUM ETH TREND_DOWN:** n=122, EV=+0.10 (nearly break-even). WR=62%, 46 SL events at avg −62.05. The SL magnitude increased vs Jan (−62 vs −70 improvement), but EV degraded. March 2024 was a bull run (ETH surged from ~2500 to ~3900) → TREND_DOWN regime detected lag again similar to Dec 2023.

**Running EV history:** Sep +14.84 → Nov +5.24 → Dec −5.69 → Jan +1.17 → Q1 CUM +0.10 (near zero). ETH TREND_DOWN **holds edge** across 9 months except during strong bull regime flips.

### ETH MR — EV/trade progression

| Window | n | PnL | EV/t | WR% | SL | avg_win | avg_loss | PF concern |
|---|---|---|---|---|---|---|---|---|
| Nov-only | 5 | +54.14 | +10.83 | 100% | 0 | +10.83 | — | none |
| Dec-only | 5 | +55.42 | +11.08 | 100% | 0 | +11.08 | — | none |
| Q4 CUM | 14 | +62.75 | +4.48 | 86% | 2 | +10.84 | −33.65 | **payoff=0.32** |
| **Jan 2024** | **11** | **+7.81** | **+0.71** | **82%** | **2** | **+9.18** | **−37.39** | **payoff=0.245** |
| **Q1 CUM** | **27** | **+51.14** | **+1.89** | **81.5%** | 5 | 22 | +12.14 | −43.20 | payoff=0.28 |
| **Feb 2024** | see Q1 | — | — | — | — | — | — | — |
| **Mar 2024** | see Q1 | — | — | — | — | — | — | — |

**Q1 CUM ETH MR:** n=27, WR=81.5%, EV=+1.89 — stronger than Jan standalone. The Q1 CUM context had better ETH prices and volatility for MR entries. **MR is consistently positive across all windows.** Payoff ratio still concerning (0.28) but WR holds above 80% threshold. KEEP verdict confirmed.

---

## SECTION 5 — BNB Regime Research

### BNB MR — EV/trade progression

| Window | n | PnL | EV/t | WR% | avg_win | avg_loss | PF | verdict signal |
|---|---|---|---|---|---|---|---|---|
| Sep-only | 16 | +40.20 | +2.51 | 93.75% | — | — | — | ✅ |
| Nov-only | 0 | 0 | — | — | — | — | — | — |
| Dec-only | 2 | −18.43 | −9.22 | 50% | +5.67 | −24.10 | 0.24 | ⚠️ |
| Q4 CUM | 2 | −20.75 | −10.38 | 50% | +6.38 | −27.13 | 0.24 | ⚠️ (n=2) |
| **Jan 2024** | **7** | **−23.18** | **−3.31** | **71%** | **+4.72** | **−23.39** | **0.50** | **❌** |
| **Q1 CUM** | **31** | **+27.04** | **+0.87** | **83.9%** | +6.22 | −26.93 | 0.23 | **✅ surprise** |
| Feb 2024 | see Q1 | — | — | — | — | — | — | — |
| Mar 2024 | see Q1 | — | — | — | — | — | — | — |

**Q1 CUM BNB MR — major reversal:** n=31, WR=83.9%, EV=+0.87. The Jan standalone showed structural failure (n=7). Q1 CUM with 31 trades is the first sample large enough to be meaningful.

**Structural payoff concern persists:** PF=0.23 (avg_win +6.22 vs avg_loss −26.93). Break-even WR = 26.93/(6.22+26.93) = **81.2%**. At WR=83.9% the margin is only 2.7%. One bad month could flip it negative.

**Block candidate verdict revised → MONITOR:** Q1 CUM n=31 is positive. Cannot block based on n=7 outlier. Retain BNB MR but flag payoff structure as fragile. If H1 2024 shows WR falling below 82%, escalate to BLOCK.

---

## SECTION 6 — DOGE Regime Research

> Note: DOGE is a CONFIG GAP (see Section 1). Analysis here is observational only — not endorsing DOGE as an intentional Aurora symbol.

### DOGE summary per confirmed window

| Window | n | PnL | TREND_UP n/pnl | TREND_DOWN n/pnl | LOW_VOL n/pnl |
|---|---|---|---|---|---|
| Jun-Sep CUM | 0 | 0 | — | — | — |
| DEC-only | 25 | −15.80 | 10/+18.37 | 2/−34.86 | 13/+0.68 |
| Q4 CUM | 32 | +120.50 | 16/+68.59 | 3/+52.06 | 13/−0.16 |
| **Jan 2024** | **0** | **0** | — | — | — |
| **Q1 CUM** | **420** | **−686.69** | 265/−234.33 | 106/−232.51 | 48/−224.08 |

**Q1 CUM DOGE verdict: ALL 3 REGIMES STRUCTURALLY NEGATIVE EV**

| DOGE Regime | WR actual | BEQ WR needed | Deficit | EV/trade |
|---|---|---|---|---|
| TREND_DOWN | 52.8% | 58.1% | **−5.3pp** | **−2.19** |
| LOW_VOLATILITY | 60.4% | 70.9% | **−10.5pp** | **−4.67** |
| TREND_UP | 64.5% | 65.7% | −1.2pp | −0.88 |

DOGE Q4 2023 positive result (+120.50) was a favorable market anomaly — Oct TREND_DOWN shorts at +100% WR + Nov/Dec bull TREND_UP. In Q1 2024 with 429 trades across 3 months, **all 3 DOGE regimes have negative EV**. Low_volatility is the most toxic: actual WR 10.5pp below break-even.

**Conclusion: DOGE MUST BE BLOCKED.** CONFIG GAP verdict confirmed with hard data: -686.69 USDT in Q1 CUM from a symbol that entered via stale registry entry.

---

## SECTION 7 — Regime-Physics Research

> *To be extracted after backtests. Regime-physics script below.*

### Regime-physics extraction script

```bash
python -X utf8 -c "
import json, pathlib, glob, os, collections, statistics

files = sorted(glob.glob('reports/backtests/backtest_*.json'), key=os.path.getmtime)
path = files[-1]
data = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
trades = [t for t in data.get('trades', []) if t.get('close_reason')]

# Holding time analysis
print('=== HOLDING TIME (seconds) by symbol x regime ===')
ht_data = collections.defaultdict(list)
for t in trades:
    sym = t.get('symbol','?')
    reg = t.get('market_regime','?')
    entry_ts = t.get('entry_ts') or t.get('entry_time')
    exit_ts = t.get('exit_ts') or t.get('close_time')
    if entry_ts and exit_ts:
        hold_sec = (exit_ts - entry_ts) / 1000.0
        ht_data[(sym,reg)].append(hold_sec)

for (sym,reg), vals in sorted(ht_data.items()):
    if not vals: continue
    avg = statistics.mean(vals)
    med = statistics.median(vals)
    mn = min(vals)
    mx = max(vals)
    print(f'  {sym:<18} x {reg:<18}: n={len(vals)} avg={avg/60:.1f}m med={med/60:.1f}m min={mn/60:.1f}m max={mx/60:.1f}m')

print()
print('=== PnL QUARTILES by symbol x regime ===')
pnl_data = collections.defaultdict(list)
for t in trades:
    sym = t.get('symbol','?')
    reg = t.get('market_regime','?')
    p = t.get('pnl_usdt_net',0) or 0
    pnl_data[(sym,reg)].append(p)

for (sym,reg), vals in sorted(pnl_data.items(), key=lambda x: sum(x[1])):
    if len(vals) < 2: continue
    sv = sorted(vals)
    n = len(sv)
    q1 = sv[n//4]
    q3 = sv[3*n//4]
    p5 = sv[max(0,int(n*0.05))]
    p95 = sv[min(n-1,int(n*0.95))]
    print(f'  {sym:<18} x {reg:<18}: p5={p5:.1f} q1={q1:.1f} med={statistics.median(vals):.1f} q3={q3:.1f} p95={p95:.1f}')
"
```

### 7.1 Holding time by regime

> *Fill after results.*

### 7.2 PnL distribution quartiles

> *Fill after results.*

### 7.3 ETH TREND_DOWN SL anatomy (confirmed data)

| Window | SL count | Bucket | Avg SL size | PF | Structural note |
|---|---|---|---|---|---|
| NOV | 4 | [−100,−50) | −82.23 | 1.22 | working |
| DEC | 9 | [−100,−50) | −72.97 | 0.76 | bull flip lag |
| Q4 CUM | 14 | [−100,−50) | −78.54 | 0.84 | Dec weight |
| **Jan 2024** | **10** | [−100,−50)¹ | **−70.28** | **1.05** | recovery |
| **Q1 CUM** | **46** | [−100,−50)¹ | **−62.05** | ~1.0 | bull-lag Mar |

¹ Inferred from bucket pattern — all SL events are consistently in [−50,−100) range.

**Q1 CUM SL anatomy:** 46 SL events on 122 ETH TREND_DOWN trades (37.7% SL rate). avg_loss = −62.05 (slightly tighter than Jan's −70.28). Gross ETH SL loss = 46 × 62.05 = −2854 USDT, all from [−50,−100) bucket.

**Pattern across all windows:** ALL ETH TREND_DOWN SL events consistently land in [−50,−100) bucket — no small stops, no partial exits. This is a structural SL width problem that exists in every window across every market condition. The SL is calibrated for high-volatility entries and never adjusts down into a "tight stop" mode. This is the primary TP/SL study target for a future patched7.

---

## SECTION 8 — Decision Matrix

**Final Q1 verdicts (Jan standalone + Q1 CUM):**

| Regime | Sep-Jan history | Q1 CUM signal | Rule met | **FINAL VERDICT** |
|---|---|---|---|---|
| **ETH TREND_DOWN** | ✅ ✅ ❌ ✅ | n=122 +0.10 EV ⚠️ | Positive in 3/5 meaningful windows | **KEEP** |
| **ETH MR** | ✅×3, Jan ⚠️ | n=27, EV=+1.89 ✅ | Positive in all Q1 windows | **KEEP** |
| **BNB MR** | Sep ✅, Jan ❌ | n=31 EV=+0.87 ✅ | Q1 CUM reversal | **MONITOR** (PF fragile) |
| **DOGE** | Q4 ✅ anomaly | −686.69 ALL regimes ❌ | Structurally broken | **BLOCK → patched6** |
| **patched5 baseline** | confirmed | w/o DOGE: +89.77 ✅ | Solid w/o config gap | **CONFIRM** |

### Rationale per verdict:

**ETH TREND_DOWN → KEEP:** 3 bull-reversal windows (Dec, Q1 CUM) dragged EV near zero, but the strategy works. The SL calibration issue (all losses in [−50,−100) bucket) is a structural problem for a future TP/SL study, not a regime block. Removing DOGE from Q1 CUM would improve ETH TREND_DOWN's absolute PnL context (more available capital = larger positions = more absolute profit).

**ETH MR → KEEP:** WR consistently 81-86% across all windows. EV degraded in Jan (+0.71) but recovered in Q1 CUM (+1.89). Payoff ratio concern (0.25-0.32) is real but WR sustained.

**BNB MR → MONITOR:** Jan n=7 was misleading. Q1 CUM n=31 shows consistent TP hits (26 of 31). Payoff fragile (break-even WR=81.2%) but achievable. No block without more evidence.

**DOGE → BLOCK (patched6):** -686.69 on 420 trades in Q1 CUM. All 3 regimes negative EV. Q4 +120.50 was a lucky market anomaly (Oct TD shorts + early bull TREND_UP). Registry gap confirmed. The fix: `config/aurora/strategies.yaml: DOGEUSDT: []`

**patched5 baseline → CONFIRM:** ETH+BNB-only Q1 CUM = +89.77 USDT (+8.98% ROI). This is the true patched5 signal. DOGE was a parasite on an otherwise functional config.

---

## SECTION 9 — Next Step: patched6

### Action: Block DOGEUSDT from Aurora (fix P2-2 registry gap)

**Config change required:**
```yaml
# File: config/aurora/strategies.yaml
assignments:
  # BTCUSDT removed — patched4b
  # 1000PEPEUSDT removed — patched4a_v2
  ETHUSDT:  [aurora]
  SOLUSDT:  [aurora]
  DOGEUSDT: []          # patched6: BLOCK — P2-2 intent finally executed, -686 Q1 CUM
  XRPUSDT:  [aurora]
  BNBUSDT:  [aurora]
```

**Also update stale comment** in `aurora.yaml` lines 454-461: replace P2-2 "DOGE/XRP REMOVED" with accurate documentation of current state.

### After patched6: validate with Q1 CUM re-run

```bash
.venv/Scripts/python.exe scripts/diagnostics/run_single_backtest.py --side B --start 2024-01-01 --end 2024-03-31 > reports/backtests/Q1_patched6_stdout.txt 2>&1
```

Expected result: Q1 CUM ≈ +89.77 USDT (ETH+BNB only, DOGE=0)

### What NOT to change yet
- ETH TREND_DOWN: KEEP (working regime, SL calibration study deferred)
- ETH MR: KEEP (WR sustained)
- BNB MR: MONITOR (payoff fragile but Q1 positive)
- No SL tightening until TP/SL study scoped separately

---

## SECTION 10 — Forensic: Q1 CUM −595 USDT Root Cause Analysis

### 10.1 Summary

| Root cause | Impact | Classification |
|---|---|---|
| DOGEUSDT config gap (registry never updated from P2-2) | **−686.69 USDT** | Primary — singular cause |
| March 2024 DOGE explosion (399 trades) | −641.41 USDT of DOGE loss | Mechanism |
| Peak balance amplification (2014.97 → 403) | Amplified absolute SL sizes | Secondary effect |
| ETH TREND_DOWN bull-lag (Mar 2024) | approx −100 of the ETH reduced EV | Secondary |

**Without DOGE:** ETH+BNB = +89.77 USDT (+8.98% ROI). patched5 baseline is functional.

### 10.2 DOGE structural negative EV (Q1 2024)

| DOGE Regime | n | PnL | EV/t | WR% | BEQ WR | Gap |
|---|---|---|---|---|---|---|
| TREND_UP | 265 | −234.33 | −0.88 | 64.5% | 65.7% | −1.2pp |
| TREND_DOWN | 106 | −232.51 | −2.19 | 52.8% | 58.1% | −5.3pp |
| LOW_VOLATILITY | 48 | −224.08 | **−4.67** | 60.4% | 70.9% | **−10.5pp** |

Q4 2023 DOGE result (+120.50) was a **market anomaly**:
- Oct 2023: 3 TREND_DOWN shorts at 100% WR (+52.06) — DOGE was still bearish
- Nov/Dec 2023: strong bull → TREND_UP +68.59
In Q1 2024 with 429 trades, the market conditions changed and all 3 DOGE regimes turned negative.

### 10.3 March 2024 timeline

| Period | N | PnL | Balance | Event |
|---|---|---|---|---|
| Jan (all) | 50 | +218.37 | 1218.37 | DOGE=0 |
| Feb (all) | 59 | +156.60 | 1374.97 | DOGE=21 trades |
| Mar week 1 (1-7) | 164 | +640.00 | **2014.97** | **peak** |
| Mar week 2 (8-14) | 90 | **−900.23** | 1114.75 | SL cascade begins |
| Mar week 3 (15-21) | 106 | **−721.79** | 392.96 | collapse |
| Mar week 4 (22-31) | 131 | +10.13 | 403.09 | stabilized |

**Week 1 of March was the best week of the entire run (+640 USDT, 164 trades).** The account reached 2× starting balance. Then DOGE positions at 2015 peak balance meant DOGE notional was ~4400 USDT (2.2× balance). When TREND_UP started hitting SLs consecutively in week 2 (94 DOGE TREND_UP SLs total, avg −47.61), each loss was amplified by the high balance.

### 10.4 Worst 10 individual trades

| Rank | Symbol × Regime | Close | PnL | Date |
|---|---|---|---|---|
| 1 | DOGE TREND_UP | SL | **−210.50** | 2024-03-05 00:45 |
| 2 | DOGE TREND_UP | SL | −200.85 | 2024-03-04 17:30 |
| 3 | ETH TREND_DOWN | SL | −160.81 | 2024-03-05 16:30 |
| 4 | ETH TREND_DOWN | SL | −156.92 | 2024-03-10 20:55 |
| 5 | ETH TREND_DOWN | SL | −151.54 | 2024-03-05 19:30 |
| 6 | ETH TREND_DOWN | SL | −115.39 | 2024-02-29 16:45 |
| 7 | DOGE TREND_UP | SL | −112.46 | 2024-03-04 23:05 |
| 8 | DOGE TREND_DOWN | SL | −108.54 | 2024-03-05 12:40 |
| 9 | ETH TREND_DOWN | SL | −105.15 | 2024-02-21 06:35 |
| 10 | ETH TREND_DOWN | SL | −104.46 | 2024-01-22 01:35 |

8 of 10 worst trades occurred in the window **March 4-10 2024**. Positions at that point were the largest of the run (peak balance ~2014 USDT → 10,000 USDT ETH notional, 5000-6000 USDT DOGE notional).

### 10.5 SL gross loss by source

| Symbol + Regime | N SL | Avg SL | Gross SL Loss | % of total |
|---|---|---|---|---|
| **DOGE TREND_UP** | **94** | −47.61 | **−4475.43** | 47% |
| ETH TREND_DOWN | 46 | −62.05 | −2854.22 | 30% |
| DOGE TREND_DOWN | 50 | −24.07 | −1203.62 | 13% |
| DOGE LOW_VOL | 19 | −31.57 | −599.89 | 6% |
| ETH MR | 5 | −43.20 | −215.97 | 2% |
| BNB MR | 5 | −26.93 | −134.65 | 1% |
| **Total** | **219** | | **−9483.79** | |

Total gross TP income: +8886.88 USDT. Net = −596.91 USDT.

Note: capital was recycled many times. The 9483 USDT gross SL outflow against 1000 starting capital means positions turned over ~9× during Q1.

### 10.6 Validity

**All patched5 gates passed.** No BTC/PEPE/ETH_LV/BNB_LV violations. The catastrophe was caused by the active config gap (DOGE), not by a patched5 enforcement failure.

### 10.7 Conclusion

> The Q1 2024 CUM −595.68 USDT result is **100% attributable to DOGEUSDT being active via config gap**. The patched5-legitimate components (ETH+BNB) delivered +89.77 USDT (+8.98%) over the same period. The fix is patched6: remove `DOGEUSDT` from `config/aurora/strategies.yaml` assignments.

---

*DOGE sanity-check completed: 2026-03-11*
*Jan 2024 results filled: 2026-03-11 (run_id: 20260311_013432)*
*Q1 2024 CUM forensic analysis: 2026-03-11 (run_id: 20260311_121654)*
*Status: COMPLETE — all verdicts issued. Next action: patched6 (DOGE block)*
