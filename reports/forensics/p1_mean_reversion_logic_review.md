# P1 Mean Reversion Logic Review

## 1. Executive Summary

### PROVEN

1. Current live `mean_reversion` is a 5-minute bar strategy, not a 1m or 3m live strategy. The active SSOT is `strategies.mean_reversion.timeframe_sec: 300`, while several comments and class names still say `1m` or `3m`.
2. Current live MR ownership is DOGE-only. `config/aurora/strategies.yaml` assigns `mean_reversion` only to `DOGEUSDT`.
3. The core MR signal engine is a symmetric Bollinger/%B fade model. It emits LONG when `%B < entry_threshold` and SHORT when `%B > 1 - entry_threshold`.
4. RSI is not a hard gate. It only adds a confidence bonus when oversold/overbought confirms an already-actionable band breach.
5. There is no explicit momentum veto, slope veto, breakout veto, or squeeze-expansion veto in the core MR evaluator.
6. Current MR open-risk signals bypass generic directional sanity and price-motion sanity because `mean_reversion.safety_gates.enabled=false`.
7. QoS anti-spam is not applied to MR in current domains SSOT. `domains.decision_making.qos.apply_to_strategies` excludes `mean_reversion`.
8. The March 13, 2026 DOGE sequence was strategy-valid under current code and config. The five SHORT signals all passed the active MR contract before the execution split-brain compounded the incident.
9. The March 13, 2026 DOGE sequence is a textbook low-volatility breakout-fade admission:
   - 08:34:59 UTC, SHORT, `bb_width=0.00879`, `%B=1.1416`, `RSI=62.4`, `FLAT_LOW`
   - 08:49:59 UTC, SHORT, `bb_width=0.01457`, `%B=1.0527`, `RSI=73.7`, `FLAT_LOW`
   - 09:04:59 UTC, SHORT, `bb_width=0.01845`, `%B=1.0154`, `RSI=75.3`, `FLAT_LOW`
   - 09:19:59 UTC, SHORT, `bb_width=0.02293`, `%B=0.9816`, `RSI=82.0`, `FLAT_LOW`
   - 09:44:59 UTC, SHORT, `bb_width=0.03111`, `%B=1.0374`, `RSI=80.5`, `FLAT_LOW`
10. The regime detector eventually caught up and flipped DOGE to `TREND_UP` by 09:54:59 UTC, but only after the MR strategy had already fired the sequence above.
11. Historical `logs/mean_reversion/bars_300s.jsonl` contains 426 actionable MR signals across DOGE, XRP, and BTC telemetry:
   - `DOGEUSDT`: 273
   - `XRPUSDT`: 129
   - `BTCUSDT`: 24
12. Historical actionable MR signals skew heavily to flat-low conditions:
   - `FLAT_LOW`: 204
   - `FLAT_NORMAL`: 167
   - `FLAT_HIGH`: 55
13. Historical flat-low SHORTs are common, not rare:
   - `DOGEUSDT`: 62
   - `XRPUSDT`: 23
   - `BTCUSDT`: 8
14. RSI-confirmation is optional often enough to matter:
   - 96 of 187 SHORTs fired without `rsi_overbought`
   - 139 of 239 LONGs fired without `rsi_oversold`
15. Repeated same-direction fading is not an isolated incident pattern. Using a simple "run length >= 3 within 30 minutes" scan on `bars_300s`, 75 run-events appear, mostly on DOGE.

### LIKELY

1. Current MR behaves like a valid band-fade model in truly sideways conditions, but it is not a momentum-aware mean reversion model. In practice it can degrade into a blind fade against expansion.
2. DOGE-like high-beta symbols likely need stricter guards than a one-size-fits-all global threshold.
3. Regime-conditioned short vetoes in `FLAT_LOW`, or at least stricter `FLAT_LOW` short thresholds, are more promising than a naive global cooldown tweak.
4. A lightweight squeeze-expansion veto looks useful as a narrow additive guard, but it is too narrow to be the only fix family.

### UNKNOWN

1. The true expectancy impact of candidate filters is not proven. The repo does not currently provide a clean outcome-labeled replay for all 426 historical MR signals.
2. A universal global `min_bb_width >= 0.015` may be too blunt, but the repo does not yet provide enough cross-symbol realized-trade evidence to pick the best universal floor.
3. Whether BTC should share DOGE-style hardening is unknown. The historical MR BTC sample is small and BTC is not currently assigned to live MR.

## 2. Scope and Sources

### Code reviewed

- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- `apps/reference/domains/feature_engineering/regime_mapping.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `apps/reference/domains/decision_making/decision_making.py`
- `apps/reference/domains/decision_making/strategy_gateway.py`
- `apps/reference/domains/decision_making/safety_gates.py`

### Config reviewed

- `config/aurora/strategies/mean_reversion.yaml`
- `config/aurora/strategies.yaml`
- `config/aurora/trading.yaml`
- `config/aurora/domains.yaml`

### Logs and artifacts reviewed

- `logs/mean_reversion/bars_300s.jsonl`
- `logs/mean_reversion/bars_300s.tsv`
- `logs/features/DOGEUSDT.log`
- `reports/forensics/mean_reversion_incident_research_2026-03-13.md`
- `reports/forensics/mean_reversion_incident_research_summary.md`
- `reports/forensics/mean_reversion_trade_inventory.csv`

### Secondary docs reviewed

- `config/docs/strategies_passport.md`
- `config/docs/mean_reversion_state_machine_passport.md`
- `config/docs/regime_passport.md`
- `config/docs/scoring_passport.md`
- `config/docs/aurora_math_passport.md`
- `config/docs/trading_passport.md`

### Missing or insufficient evidence

- `logs/order_log_v1.jsonl` was not present in the current workspace.
- `logs/trade_lifecycle.jsonl` was not present in the current workspace.
- No clean full-sample realized outcome table exists for all historical MR signals in `bars_300s`.
- No raw backtest harness was found that could safely convert this package into a true expectancy optimization without additional setup.

## 3. Current MR Contract

### MR CURRENT CONTRACT

| Layer | Current rule | Hard/soft | Evidence |
|---|---|---|---|
| Activation | `mean_reversion` activates from `strategies_registry.assignments`, not just `enabled=true` | Hard | `mean_reversion_handler.py:320-402` |
| Live scope | Current live assigned symbol is `DOGEUSDT` only | Hard | `strategies.yaml:24-45` |
| Timeframe | Handler processes only `CMD:PROCESS_STRATEGY` with `tf_sec == timeframe_sec == 300` | Hard | `mean_reversion_handler.py:1244-1275`, `mean_reversion.yaml:19-22` |
| Warmup | `min_bars` must be reached before signal generation | Hard | `mean_reversion_strategy.py:330`, `mean_reversion.yaml:130-135` |
| Cooldown | Per-symbol cooldown blocks new MR signals after an actionable signal | Hard | `mean_reversion_strategy.py:335-340`, `mean_reversion.yaml:143-144`, `DOGE cooldown_sec: 660` |
| Raw regime mapping | `TREND_UP`, `TREND_DOWN`, `HIGH_VOLATILITY`, `UNCERTAIN` map to `None`; `LOW_VOLATILITY` maps to `FLAT_LOW`; `MEAN_REVERSION` maps by ATR% | Hard | `regime_mapping.py:77-134` |
| Allowlist | Only `flat_regime.name` values are compared to `allowed_regimes`; empty list fails closed | Hard | `mean_reversion_strategy.py:354-361` |
| Band-width gate | `min_bb_width <= bb_width <= max_bb_width` required | Hard | `mean_reversion_strategy.py:438-451` |
| Entry trigger | LONG if `%B < entry_threshold`; SHORT if `%B > 1 - entry_threshold` | Hard | `mean_reversion_strategy.py:453-487` |
| RSI role | Adds confidence only; does not veto a signal | Soft booster | `mean_reversion_strategy.py:467-480` |
| Liquidity gate | If enabled and `liquidity_kappa` missing, fail closed; else require `kappa >= kappa_min` | Hard | `mean_reversion_handler.py:1212-1238` |
| Objective seam | Computes multiplier and objective score; current YAML uses `enforcement_mode: OBSERVE`, so it rescales but does not gate | Soft in current live YAML | `mean_reversion_handler.py:790-933`, `pretrade_kernel.py:144-169`, `mean_reversion.yaml:57-60,74-76,91-93,108-110` |
| Strategy safety gates | `DecisionMaking._propose_trade_intent()` always calls `apply_safety_gates`, but MR disables them in strategy YAML | Hard bypass of generic sanity | `decision_making.py:297-330`, `mean_reversion.yaml:33-38`, `safety_gates.py:198-203,241-242` |
| Downstream generic gates | readiness, risk, arbitration, flip, exposure, TTL, warmup still apply after `EVT:STRATEGY_SIGNAL_PRODUCED` | Hard | `strategy_gateway.py` |

### Hard Gate vs Soft Signal vs Confidence Booster

#### Hard gates

- assignment must include `mean_reversion`
- strategy profile must exist and be enabled
- symbol asset config must exist and be enabled
- `tf_sec` must match the handler timeframe
- `min_bars` must be reached
- cooldown must be inactive
- raw regime must map to a flat regime
- mapped flat regime must be allowlisted
- Bollinger width must be inside the configured range
- liquidity gate must pass if enabled
- downstream generic decision gates must pass

#### Soft signal logic

- `%B` is the actual entry trigger
- target side is symmetric fade:
  - LONG below the lower band
  - SHORT above the upper band
- target is mid-band or opposite band depending on `tp_to_mid`
- stop is ATR-based with regime stop multiplier

#### Confidence boosters

- base confidence
- band-distance confidence slope
- optional RSI bonus
- objective multiplier in current `OBSERVE` configuration

### Current live parameter facts that matter

- DOGE override:
  - `bb_window: 40`
  - `bb_num_std: 2.5`
  - `min_bb_width: 0.005`
  - `entry_threshold: 0.05`
  - `tp_to_mid: false`
  - `cooldown_sec: 660`
- Strategy safety gates are disabled for MR.
- Objective gate is configured `OBSERVE`, not `GATE`.
- `allowed_regimes` includes `MEAN_REVERSION`, but the runtime compare path checks only `FlatRegime.name`, so that token is currently semantically inert.

## 4. DOGE Incident Re-analysis Through Pure Strategy Lens

### What passed

The March 13, 2026 DOGE trade sequence passed because:

1. DOGE was the only live-assigned MR symbol.
2. The handler accepted 5m bars and the runtime was on 5m.
3. The raw regime was still mapping into `FLAT_LOW` / `LOW_VOLATILITY` when the fade signals fired.
4. DOGE's local `min_bb_width` was only `0.005`.
5. The strategy only required an upper-band breach via `%B`; it did not require trend rejection, momentum exhaustion, or breakout invalidation.
6. Strategy-level directional sanity and price-motion sanity were disabled.
7. Objective gate was not configured to hard-block.

### Why it passed

The strategy saw a sequence of bars that were still narrow enough to satisfy DOGE's permissive local width floor, while `%B` stayed above the upper-band boundary. That is exactly what the current signal formula interprets as a valid SHORT fade.

The sequence was not blocked by trend logic because there is no explicit trend logic inside MR signal evaluation. It was not blocked by strategy safety gates because those are disabled for MR. It was not blocked by RSI because RSI is optional confirmation, not a required precondition.

### Was this a classic squeeze-breakout fade?

`PROVEN YES`, in the sense relevant to this package.

The key evidence is the March 13 DOGE sequence in `bars_300s`:

| UTC | Signal | Width | %B | RSI | Flat regime |
|---|---|---:|---:|---:|---|
| 08:34:59 | SHORT | 0.00879 | 1.1416 | 62.4 | FLAT_LOW |
| 08:49:59 | SHORT | 0.01457 | 1.0527 | 73.7 | FLAT_LOW |
| 09:04:59 | SHORT | 0.01845 | 1.0154 | 75.3 | FLAT_LOW |
| 09:19:59 | SHORT | 0.02293 | 0.9816 | 82.0 | FLAT_LOW |
| 09:44:59 | SHORT | 0.03111 | 1.0374 | 80.5 | FLAT_LOW |

Then by 09:54:59 UTC the raw regime had turned `TREND_UP`.

Any reasonable quant review would classify:

- Trade 1 as `anti-trend fade / breakout fade trap`
- Trade 2 as `breakout fade trap`
- Trades 3-5 as increasingly late fades against a strengthening move

### What would have blocked it, and at what cost

Using the lightweight pass-rate replay on `bars_300s`:

| Candidate family | Historical signals kept | Historical signals blocked | March 13 DOGE shorts blocked | Comment |
|---|---:|---:|---:|---|
| Global `min_bb_width >= 0.015` | 108 | 318 | 2 of 5 | Catches the first two signals, but globally very blunt |
| DOGE-only `min_bb_width >= 0.015` | 202 | 224 | 2 of 5 | Same incident coverage, lower collateral damage |
| Hard RSI confirmation | 191 | 235 | 1 of 5 | Blocks the first signal only |
| Squeeze-expansion veto | 417 | 9 | 1 of 5 | Surgical, but too narrow alone |
| Block `FLAT_LOW` SHORTs | 333 | 93 | 5 of 5 | Strong incident coverage with moderate cost |
| Naive 3-bar momentum veto | 135 | 291 | 2 of 5 | Too destructive as-is |

Conclusion: the March 13 incident can be blocked several ways, but not all candidate families are equally clean. The data favors regime- and symbol-aware hardening over a blind global threshold increase.

## 5. False-Positive Archetypes

Detailed inventory: `reports/forensics/p1_mean_reversion_false_positive_archetypes.md`

### Archetype A: Low-bandwidth breakout fade

- Signature: SHORT above upper band or LONG below lower band while band width is still low and recent bandwidth is expanding.
- Evidence:
  - March 13 DOGE 08:34:59 and 08:49:59 UTC
  - DOGE 2026-02-12 06:29:59 (`width=0.01363`, `%B=1.1833`, `RSI=84.8`)
  - XRP 2026-02-21 09:34:59 (`width=0.01322`, `%B=1.1738`, `RSI=93.1`)
- Verdict: `PROVEN`

### Archetype B: Repeated same-direction fading during drift trend

- Signature: 3 or more same-side MR signals within 30 minutes while price continues drifting in the adverse direction.
- Evidence:
  - 75 run-events in `bars_300s`
  - DOGE examples include 4-6 signal runs on 2026-02-12, 2026-02-13, and the March 13 incident
- Verdict: `PROVEN`

### Archetype C: Unconfirmed fades because RSI is optional

- Signature: the fade signal fires on band breach alone without RSI exhaustion confirmation.
- Evidence:
  - 96 of 187 SHORTs lack `rsi_overbought`
  - 139 of 239 LONGs lack `rsi_oversold`
  - DOGE alone: 60 SHORTs and 102 LONGs without RSI confirmation
- Verdict: `PROVEN`

## 6. Candidate Filter / Threshold Families

Detailed matrix: `reports/forensics/p1_mean_reversion_filter_candidate_matrix.md`

### Highest-value families

1. Symbol-specific width hardening
   - Why: DOGE actionable widths cluster lower than XRP.
   - Replay signal-cost: DOGE-only `min_bb_width >= 0.015` blocks 224 of 426 historical signals, versus 318 for a global floor.
   - Verdict: `LIKELY` strong candidate for a future implementation package.

2. Regime-conditioned short veto in `FLAT_LOW`
   - Why: the entire March 13 DOGE incident sat inside `FLAT_LOW`, and blocking `FLAT_LOW` SHORTs removes all 5 incident shorts at moderate cost.
   - Replay signal-cost: blocks 93 of 426 signals.
   - Verdict: `LIKELY` strong candidate.

3. Squeeze-expansion veto
   - Why: catches a narrow but high-toxicity pattern with very low collateral damage.
   - Replay signal-cost: blocks only 9 of 426 signals.
   - Limitation: misses the first March 13 SHORT.
   - Verdict: `LIKELY` additive candidate, but not a standalone solution.

4. Momentum / slope / drift veto
   - Why: the core MR engine is currently blind to directionality.
   - Replay proxy using a naive 3-bar monotonic veto is too destructive, which means the family is real but the naive form is poor.
   - Verdict: `LIKELY` candidate family, but it needs careful design.

### Lower-value or noisier families

1. Pure global width tightening
   - Likely too blunt without symbol grouping.
2. Pure hard RSI gating
   - Removes many signals but only catches 1 of the 5 March 13 shorts.
3. Cooldown-only tweaks
   - Current cooldown does not protect against the first toxic entry. This is secondary at best.
4. Blind multi-bar confirmation
   - Likely useful only if made regime- and symbol-aware.

## 7. Symbol-Specific Findings

### Current live assignment

- `PROVEN`: only DOGE is live-assigned to MR today.

### Historical actionable width distributions

From `bars_300s` actionable signals:

| Symbol | Actionable count | Median width |
|---|---:|---:|
| BTCUSDT | 24 | 0.01083 |
| DOGEUSDT | 273 | 0.00960 |
| XRPUSDT | 129 | 0.01321 |

### How blunt is `0.015`?

Share of historical actionable signals below `0.015`:

| Symbol | Below 0.015 |
|---|---:|
| BTCUSDT | 20 of 24 (83.3%) |
| DOGEUSDT | 224 of 273 (82.1%) |
| XRPUSDT | 74 of 129 (57.4%) |

### Verdict

1. `PROVEN`: DOGE and XRP do not share the same actionable width distribution.
2. `LIKELY`: DOGE-like high-beta symbols deserve a stricter family than XRP-like or major symbols.
3. `UNKNOWN`: BTC needs the same hardening, because the historical MR BTC sample is small and BTC is not currently live-assigned to MR.

Recommended future grouping for implementation testing:

- majors
- mid-beta
- high-beta meme / alt

## 8. Lightweight Experiment / Replay Findings

This package did not run a true PnL backtest. It ran a lightweight replay over `logs/mean_reversion/bars_300s.jsonl` to compare signal pass-rate and incident coverage for candidate filter families.

### What the replay can prove

- relative bluntness vs surgical behavior
- whether a candidate would have blocked the March 13 DOGE shorts
- whether the candidate looks global or symbol-specific

### What the replay cannot prove

- expectancy
- win rate
- drawdown impact
- best final parameter values

### Main replay takeaways

1. The global `0.015` width floor is too blunt to be accepted as proven final policy.
2. DOGE-only width hardening is materially less destructive than a global width floor.
3. A `FLAT_LOW` short veto covers the incident best among simple rule families.
4. A squeeze-expansion veto is attractive as a low-collateral additive guard.
5. A naive multi-bar momentum veto is too destructive, but the family remains worth designing more carefully.

## 9. Documentation Drift

Detailed appendix: `reports/forensics/p1_mean_reversion_doc_drift_appendix.md`

Key drifts:

1. `1m` / `3m` naming persists in comments, type names, and registry notes, while the live MR timeframe is 5m.
2. `allowed_regimes` examples and configs still include `MEAN_REVERSION`, but runtime compare logic only checks `FlatRegime.name`, so that token is currently a no-op.
3. Older incident summary phrasing pushed an immediate `min_bb_width >= 0.015` fix. This package downgrades that from "obvious next fix" to "candidate family that still needs implementation testing."

## 10. Decision-Ready Recommendations

### Recommended next implementation packages

1. **P2 MR high-beta / DOGE hardening**
   - Scope: DOGE-only or high-beta-group width floor + regime-conditioned short hardening.
   - Why: best balance between incident coverage and collateral damage.

2. **P2 MR squeeze-expansion veto**
   - Scope: additive guard based on recent band-width expansion plus band breach.
   - Why: cheap, surgical protection against a clearly toxic archetype.

3. **P2 MR momentum-separation package**
   - Scope: trend/slope/drift veto for counter-trend fades.
   - Why: fixes the structural blind spot, but needs careful design to avoid killing too much edge.

4. **P2 MR contract cleanup / doc-sync**
   - Scope: 5m naming, `allowed_regimes` semantics, RSI role, and filter ownership.
   - Why: current docs and config labels invite the wrong mental model during future tuning.

### What should remain research-only for now

- universal global threshold selection
- BTC hardening rules
- ATR-relative expansion thresholds
- any "best number" claims without realized-trade replay

### What should not be touched first

- `cooldown_sec` as the primary answer
- generic risk or execution knobs
- execution-position logic, which is already a separate closed package

## 11. Commands Run

Key commands used for this package:

```powershell
Get-Content apps/reference/domains/feature_engineering/mean_reversion_strategy.py
Get-Content apps/reference/domains/decision_making/mean_reversion_handler.py
Get-Content apps/reference/domains/decision_making/decision_making.py
Get-Content apps/reference/domains/feature_engineering/regime_mapping.py
Get-Content config/aurora/strategies/mean_reversion.yaml
Get-Content config/aurora/strategies.yaml
Get-Content config/aurora/domains.yaml
Get-Content reports/forensics/mean_reversion_trade_inventory.csv
Get-Content reports/forensics/mean_reversion_incident_research_summary.md
Get-Content logs/mean_reversion/bars_300s.jsonl -TotalCount 20
```

```powershell
@'
import json
from collections import Counter, defaultdict
path='logs/mean_reversion/bars_300s.jsonl'
count=Counter()
by_symbol=defaultdict(Counter)
with open(path,'r',encoding='utf-8') as f:
    for line in f:
        row=json.loads(line)
        sig=(row.get('signal') or {}).get('type')
        count[sig]+=1
        by_symbol[row.get('symbol')][sig]+=1
print('SIGNAL COUNTS', dict(count))
for sym,c in sorted(by_symbol.items()):
    print(sym, dict(c))
'@ | python -
```

```powershell
@'
import json
path='logs/mean_reversion/bars_300s.jsonl'
with open(path,'r',encoding='utf-8') as f:
    for line in f:
        row=json.loads(line)
        if row.get('symbol')=='DOGEUSDT' and str(row.get('ts_human','')).startswith('2026-03-13 '):
            print(row)
'@ | python -
```

```powershell
@'
import json
from collections import defaultdict
path='logs/mean_reversion/bars_300s.jsonl'
rows=[]
by_symbol=defaultdict(list)
with open(path,'r',encoding='utf-8') as f:
    for line in f:
        row=json.loads(line)
        by_symbol[row.get('symbol')].append(row)
for sym in by_symbol:
    by_symbol[sym].sort(key=lambda r:r.get('ts_human'))
# replay matrix code omitted here in prose, but this was the shell path used
'@ | python -
```

No pytest or runtime behavior tests were run in this package because the task was research-only and no production code or YAML was changed.
