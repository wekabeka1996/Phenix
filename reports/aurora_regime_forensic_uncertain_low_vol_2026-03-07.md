# Aurora / Phenix Regime Forensic Audit

## Scope

Objective: strict audit of `UNCERTAIN` and `LOW_VOLATILITY` behavior using runtime evidence only.

Sources used:
- `reports/aurora_forensic_report_2026-03-06_2026-03-07.md`
- `reports/aurora_forensic_2026-03-06_2026-03-07_trades.csv`
- `reports/aurora_forensic_2026-03-06_2026-03-07_counterfactual.csv`
- `reports/aurora_forensic_2026-03-06_2026-03-07_conflicts.csv`
- `reports/aurora_forensic_2026-03-06_2026-03-07_summary.json`
- `logs/domain_regime_detector.log`
- `config/aurora/regime.yaml`
- `config/aurora/strategies/aurora.yaml`
- `config/aurora/strategies/mean_reversion.yaml`
- `config/aurora/strategies.yaml`

Evidence window from reconstructed trades: `2026-03-05 22:00:00 UTC` to `2026-03-07 11:32:15 UTC`.

## Evidence Limits

- Trade PnL is the existing forensic estimate: entry from `ACCOUNT_UPDATE_RECEIVED`, exit from the last pre-close mark before the position disappeared.
- `UNCERTAIN` entries have no recorder-derived `MAE/MFE` in the current reconstructed dataset (`0/17`), so the UNCERTAIN verdict relies on realized outcomes, regime timing, and config/runtime consistency.
- `LOW_VOLATILITY` has recorder-derived `MAE/MFE` for `10/15` entries. The remaining `5/15` are evaluated from realized outcomes plus regime timing only.
- No config was changed in this audit.

## Config Facts That Matter

- `config/aurora/regime.yaml` sets `uncertain_cutoff: 0.52`.
- In `logs/domain_regime_detector.log`, reconstructed `UNCERTAIN` entries all carried `confidence=0.42`; this is the detector's floor state, not a strong directional regime.
- `config/aurora/strategies/aurora.yaml`:
  - `ETHUSDT` allows `UNCERTAIN` and `LOW_VOLATILITY`.
  - `ETHUSDT` also sets `regime_sizing: LOW_VOLATILITY: 0.0`.
  - `SOLUSDT` allows `LOW_VOLATILITY` but not `UNCERTAIN`.
  - `BTCUSDT` allows `LOW_VOLATILITY` but not `UNCERTAIN`.
- `config/aurora/strategies/mean_reversion.yaml` does not use `LOW_VOLATILITY` / `UNCERTAIN` gating. Its own whitelist is `FLAT_LOW`, `FLAT_NORMAL`, `FLAT_HIGH`, `MEAN_REVERSION`.

## Structural Config/Runtime Mismatches

- `aurora` traded `UNCERTAIN` on `BTCUSDT` and `SOLUSDT` even though those symbols' `allowed_regimes` exclude `UNCERTAIN`.
- `aurora` traded `LOW_VOLATILITY` on `ETHUSDT` even though `ETHUSDT` has `regime_sizing: LOW_VOLATILITY: 0.0`.
- Reconstructed trades show `mean_reversion` on `XRPUSDT`, but `config/aurora/strategies.yaml` assigns `XRPUSDT` to `md_amr`.
- `reports/aurora_forensic_2026-03-06_2026-03-07_conflicts.csv` shows `md_amr` issuing a `SOLUSDT` short intent while `config/aurora/strategies.yaml` assigns `SOLUSDT` to `aurora`.

Conclusion from these mismatches: YAML policy is not reliably enforced at runtime. Any launch recommendation must therefore include an enforcement requirement, not only parameter changes.

## Step 1: UNCERTAIN Audit

### UNCERTAIN Summary

- Trades opened in `UNCERTAIN`: `17`
- System net PnL in `UNCERTAIN`: `-141.67`
- By strategy:

| Strategy | Count | Win Rate | Net PnL* | Avg Hold Min |
| --- | ---: | ---: | ---: | ---: |
| aurora | 13 | 69.2% | -109.55 | 26.96 |
| mean_reversion | 4 | 25.0% | -32.12 | 35.50 |

- Detector behavior:
  - previous `UNCERTAIN` confidence at entry was always `0.42`
  - `8/17` UNCERTAIN entries were followed by a non-UNCERTAIN regime flip within `30m`
- Interpretation:
  - `UNCERTAIN` behaved like a transition / indeterminate state, not a regime with stable tradable edge.
  - High win rate did not translate into positive expectancy. Losses were concentrated in aurora longs on `ETHUSDT` and `SOLUSDT`.

### UNCERTAIN Grouped Table

| Strategy | Symbol | Side | Count | Win Rate | Net PnL* | Avg Hold Min | Exit Mix |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| aurora | BTCUSDT | SHORT | 3 | 66.7% | 18.03 | 46.68 | UNKNOWN:3 |
| aurora | ETHUSDT | LONG | 5 | 60.0% | -163.30 | 28.74 | SL:3, UNKNOWN:2 |
| aurora | ETHUSDT | SHORT | 1 | 100.0% | 65.69 | 17.17 | UNKNOWN:1 |
| aurora | SOLUSDT | LONG | 3 | 66.7% | -67.72 | 12.61 | SL:1, TP:1, UNKNOWN:1 |
| aurora | SOLUSDT | SHORT | 1 | 100.0% | 37.76 | 11.70 | TP:1 |
| mean_reversion | DOGEUSDT | LONG | 2 | 0.0% | -53.51 | 46.82 | SL:2 |
| mean_reversion | XRPUSDT | LONG | 2 | 50.0% | 21.38 | 24.18 | SL:1, UNKNOWN:1 |

### UNCERTAIN Trade Table

| Symbol | Strategy | Side | Entry UTC | Exit | PnL* | Hold Min | Next Regime | Min To Next | Entry Note |
| --- | --- | --- | --- | --- | ---: | ---: | --- | ---: | --- |
| ETHUSDT | aurora | LONG | 2026-03-06 10:28:25 | SL | 1.02 | 18.78 | MEAN_REVERSION | 6.65 | flip to buy |
| XRPUSDT | mean_reversion | LONG | 2026-03-06 11:57:08 | SL | -19.89 | 10.48 | MEAN_REVERSION | 37.93 | FLAT_NORMAL oversold |
| DOGEUSDT | mean_reversion | LONG | 2026-03-06 11:57:08 | SL | -33.01 | 14.63 | LOW_VOLATILITY | 52.93 | FLAT_LOW oversold |
| ETHUSDT | aurora | LONG | 2026-03-06 11:32:27 | SL | -97.51 | 69.18 | MEAN_REVERSION | 62.62 | flip to buy |
| DOGEUSDT | mean_reversion | LONG | 2026-03-06 12:12:09 | SL | -20.50 | 79.00 | LOW_VOLATILITY | 37.92 | FLAT_LOW oversold |
| BTCUSDT | aurora | SHORT | 2026-03-06 14:10:41 | UNKNOWN | -49.18 | 15.91 | HIGH_VOLATILITY | 24.40 | hold sell |
| ETHUSDT | aurora | LONG | 2026-03-06 14:31:32 | SL | -142.50 | 19.06 | MEAN_REVERSION | 38.45 | enter buy |
| SOLUSDT | aurora | LONG | 2026-03-06 14:34:12 | SL | -117.01 | 25.22 | HIGH_VOLATILITY | 0.87 | flip to buy |
| ETHUSDT | aurora | LONG | 2026-03-06 15:00:07 | UNKNOWN | 75.62 | 21.79 | MEAN_REVERSION | 9.87 | flip to buy |
| ETHUSDT | aurora | LONG | 2026-03-06 17:05:21 | UNKNOWN | 0.07 | 14.89 | LOW_VOLATILITY | 144.65 | hold buy |
| SOLUSDT | aurora | SHORT | 2026-03-06 17:15:16 | TP | 37.76 | 11.70 | MEAN_REVERSION | 59.73 | flip to sell |
| ETHUSDT | aurora | SHORT | 2026-03-06 17:20:14 | UNKNOWN | 65.69 | 17.17 | LOW_VOLATILITY | 129.77 | hold sell |
| SOLUSDT | aurora | LONG | 2026-03-06 17:45:07 | TP | 31.44 | 3.88 | MEAN_REVERSION | 29.88 | hold buy |
| SOLUSDT | aurora | LONG | 2026-03-06 17:50:10 | UNKNOWN | 17.85 | 8.75 | MEAN_REVERSION | 24.83 | hold buy |
| XRPUSDT | mean_reversion | LONG | 2026-03-06 17:36:02 | UNKNOWN | 41.27 | 37.88 | MEAN_REVERSION | 38.98 | FLAT_LOW oversold |
| BTCUSDT | aurora | SHORT | 2026-03-06 18:30:45 | UNKNOWN | 17.19 | 67.54 | MEAN_REVERSION | 4.25 | hold sell |
| BTCUSDT | aurora | SHORT | 2026-03-06 19:40:02 | UNKNOWN | 50.02 | 56.59 | LOW_VOLATILITY | 29.97 | flip to sell |

### UNCERTAIN Verdict

- Real edge in `UNCERTAIN`: **not demonstrated**
- Why:
  - net PnL is materially negative
  - `UNCERTAIN` confidence is fixed at the detector floor (`0.42`)
  - nearly half the entries are followed by a regime change within `30m`
  - runtime already violated existing UNCERTAIN bans on `BTCUSDT` and `SOLUSDT`

## Step 2: LOW_VOLATILITY Audit

### LOW_VOLATILITY Summary

- Trades opened in `LOW_VOLATILITY`: `15`
- System net PnL in `LOW_VOLATILITY`: `-83.88`
- By strategy:

| Strategy | Count | Win Rate | Net PnL* | Avg Hold Min |
| --- | ---: | ---: | ---: | ---: |
| aurora | 9 | 55.6% | -30.19 | 123.81 |
| mean_reversion | 6 | 66.7% | -53.70 | 156.77 |

- Detector behavior:
  - entry confidence range: `0.5769` to `0.9317`, average `0.7401`
  - only `1/15` LOW_VOL entries was followed by a regime change within `30m`
- Interpretation:
  - LOW_VOL was usually stable and confirmed, not a noisy flicker state.
  - The negative result is therefore not explained primarily by detector instability.

### LOW_VOL Policy Active At Entry

| Strategy | Symbol | Relevant Policy From YAML |
| --- | --- | --- |
| aurora | ETHUSDT | `sl_pct 0.019`, LOW_VOL `sl_mult 0.70`, LOW_VOL `tp_mult 0.75`, `regime_sizing LOW_VOLATILITY: 0.0` |
| aurora | SOLUSDT | `sl_pct 0.0135`, LOW_VOL `sl_mult 0.65`, LOW_VOL `tp_mult 0.70`, `regime_sizing LOW_VOLATILITY: 0.9` |
| aurora | BTCUSDT | `sl_pct 0.005`, LOW_VOL `sl_mult 0.80`, LOW_VOL `tp_mult 1.50`, `regime_sizing LOW_VOLATILITY: 0.7` |
| mean_reversion | DOGEUSDT | `sl_atr_mult 1.5`, `tp_to_mid false`, allowed regimes are `FLAT_*` / `MEAN_REVERSION` only |
| mean_reversion | XRPUSDT | `sl_atr_mult 2.0`, `tp_to_mid true`, allowed regimes are `FLAT_*` / `MEAN_REVERSION` only |

Important distinction:
- For `mean_reversion`, external `LOW_VOLATILITY` is context, not the strategy's own gating vocabulary.
- Therefore a global LOW_VOL decision should not be projected onto MR without first unifying `LOW_VOLATILITY` with `FLAT_LOW/NORMAL/HIGH`.

### LOW_VOL Trade Table

| Symbol | Strategy | Side | Entry UTC | Prev LOW_VOL Conf | Next Regime | Min To Next | Stop | Target | PnL* | MAE/SL | MFE/TP | Entry Note |
| --- | --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| DOGEUSDT | mean_reversion | LONG | 2026-03-06 13:48:01 | 0.6825 | MEAN_REVERSION | 77.07 | 0.091867 | 0.093603 | -94.05 | n/a | n/a | FLAT_HIGH near lower BB |
| DOGEUSDT | mean_reversion | LONG | 2026-03-06 14:00:02 | 0.6825 | MEAN_REVERSION | 65.05 | 0.090680 | 0.094214 | -84.09 | n/a | n/a | FLAT_HIGH oversold |
| XRPUSDT | mean_reversion | LONG | 2026-03-06 20:27:02 | 0.7197 | UNCERTAIN | 17.98 | 1.351479 | 1.359212 | 14.01 | n/a | n/a | FLAT_LOW near lower BB |
| SOLUSDT | aurora | SHORT | 2026-03-06 20:36:20 | 0.7475 | UNCERTAIN | 58.67 | 85.365682 | 84.435987 | 20.99 | n/a | n/a | hold sell |
| BTCUSDT | aurora | LONG | 2026-03-06 20:40:19 | 0.6232 | MEAN_REVERSION | 394.73 | 67590.316659 | 68268.934297 | 58.79 | n/a | n/a | hold buy |
| ETHUSDT | aurora | LONG | 2026-03-06 19:38:24 | 0.9317 | UNCERTAIN | 116.60 | 1955.192460 | 2000.052713 | -22.82 | 0.30 | -0.19 | flip to buy |
| ETHUSDT | aurora | SHORT | 2026-03-07 00:43:16 | 0.8646 | MEAN_REVERSION | 116.77 | 2009.978581 | 1969.438402 | -0.01 | 0.06 | 0.12 | hold sell |
| DOGEUSDT | mean_reversion | LONG | 2026-03-06 14:12:03 | 0.6825 | MEAN_REVERSION | 53.03 | 0.089635 | 0.095005 | 2.70 | 0.44 | 0.21 | FLAT_HIGH oversold |
| ETHUSDT | aurora | LONG | 2026-03-07 00:59:55 | 0.8646 | MEAN_REVERSION | 100.12 | 1951.638545 | 1992.200925 | -0.03 | 0.20 | 0.11 | hold buy |
| ETHUSDT | aurora | SHORT | 2026-03-07 01:27:56 | 0.8646 | MEAN_REVERSION | 72.10 | 2006.584313 | 1966.112594 | 0.04 | 0.04 | 0.02 | hold sell |
| BTCUSDT | aurora | SHORT | 2026-03-06 22:19:36 | 0.6232 | MEAN_REVERSION | 295.45 | 68550.723595 | 67867.947464 | 0.46 | 0.32 | 0.50 | enter sell |
| DOGEUSDT | mean_reversion | SHORT | 2026-03-07 01:03:06 | 0.5769 | MEAN_REVERSION | 81.93 | 0.091695 | 0.091148 | 42.81 | 0.85 | 0.93 | FLAT_LOW near upper BB |
| ETHUSDT | aurora | LONG | 2026-03-07 01:31:37 | 0.8646 | MEAN_REVERSION | 68.42 | 1947.961329 | 1988.447282 | 0.04 | 0.21 | 0.60 | flip to buy |
| SOLUSDT | aurora | LONG | 2026-03-06 22:51:22 | 0.6704 | MEAN_REVERSION | 213.67 | 84.169531 | 85.102429 | -87.65 | 1.28 | 0.60 | enter buy |
| DOGEUSDT | mean_reversion | LONG | 2026-03-07 09:03:06 | 0.7034 | HIGH_VOLATILITY | 146.98 | 0.089926 | 0.090694 | 64.91 | 0.68 | 1.07 | FLAT_LOW oversold |

### LOW_VOL By Aurora Symbol

| Symbol | Count | Win Rate | Net PnL* |
| --- | ---: | ---: | ---: |
| BTCUSDT | 2 | 100.0% | 59.25 |
| ETHUSDT | 5 | 40.0% | -22.77 |
| SOLUSDT | 2 | 50.0% | -66.66 |

### LOW_VOL Failure Classification

| Trade | Classification | Evidence |
| --- | --- | --- |
| DOGE 2026-03-06 13:48 LONG | other | external LOW_VOL but MR internal regime is `FLAT_HIGH`; no `MAE/MFE`; failure mode not isolatable |
| DOGE 2026-03-06 14:00 LONG | other | same as above; taxonomy mismatch plus no path stats |
| XRP 2026-03-06 20:27 LONG | other | profitable; no failure |
| SOL 2026-03-06 20:36 SHORT | other | profitable; no failure |
| BTC 2026-03-06 20:40 LONG | other | profitable; no failure |
| ETH 2026-03-06 19:38 LONG | wrong entry timing | entered far from local low, never had positive MFE, later exited negative without touching stop |
| ETH 2026-03-07 00:43 SHORT | no volatility edge | entry was near local high, but MFE reached only 12% of target and trade finished flat-to-negative |
| DOGE 2026-03-06 14:12 LONG | other | profitable but weak; MFE only 21% of target |
| ETH 2026-03-07 00:59 LONG | wrong entry timing | long entry not near local low; MFE only 11% of target |
| ETH 2026-03-07 01:27 SHORT | other | profitable scratch; no failure |
| BTC 2026-03-06 22:19 SHORT | other | profitable scratch; entry location was favorable |
| DOGE 2026-03-07 01:03 SHORT | other | profitable; almost reached target |
| ETH 2026-03-07 01:31 LONG | TP too ambitious | MFE reached 60% of target in stable low-vol and trade exited near flat |
| SOL 2026-03-06 22:51 LONG | no volatility edge | stable low-vol regime, MFE only 60% of target, MAE exceeded stop, wider SL did not make it profitable |
| DOGE 2026-03-07 09:03 LONG | other | profitable TP |

### Step 4: LOW_VOL TP/SL Counterfactual

Counterfactual grid tested on LOW_VOL trades:
- TP multipliers: `0.75x`, `1.0x`, `1.25x`, `1.5x`, `2.0x`
- SL multipliers: `0.5x`, `0.75x`, `1.0x`, `1.25x`

Result on LOW_VOL losing trades:
- Losing LOW_VOL trades: `6`
- `0/6` became profitable under any tested TP/SL combination
- For every tested grid point:
  - `5` remained `LOSS_EXIT`
  - `1` remained `SL`

Verdict from the counterfactual:
- LOW_VOL losses are **not primarily a stop-distance problem**
- LOW_VOL losses are **not primarily a target-distance problem**
- LOW_VOL losses are mainly an **entry-edge / symbol-selection / enforcement problem**

This is especially clear on the aurora LOW_VOL losers:
- `ETHUSDT` losers used wide stops already and still failed to generate enough favorable excursion.
- `SOLUSDT` LOW_VOL long lost despite a stable detector state; widening the stop did not turn it profitable.

## Final Verdict

### A. Should UNCERTAIN Become Hard No-Trade?

**YES**

Reason:
- `UNCERTAIN` is negative at the system level (`-141.67`)
- detector confidence is pinned to the floor state (`0.42`)
- `8/17` entries are followed by a regime change within `30m`
- runtime already traded `UNCERTAIN` where YAML said it should not

### B. What Should Happen To LOW_VOLATILITY?

**KEEP BUT NARROW SYMBOL SET**

Reason:
- LOW_VOL detector evidence is mostly stable, not flickering
- LOW_VOL is not uniformly bad: `BTCUSDT` aurora LOW_VOL was positive (`+59.25`)
- LOW_VOL losses were not repaired by TP/SL counterfactuals
- loss concentration is symbol-specific, especially `SOLUSDT` and `ETHUSDT` aurora
- `mean_reversion` is not directly controlled by the LOW_VOL taxonomy, so a global LOW_VOL disable would overreach the evidence

## LAUNCH DECISION

### UNCERTAIN

Recommendation: **HARD NO-TRADE = YES**

Launch rule for next run:
- no new entries when external regime is `UNCERTAIN`
- this must be enforced in the runtime path, not trusted to YAML alone

### LOW_VOLATILITY

Recommendation: **KEEP BUT NARROW SYMBOL SET**

Launch rule for next run:
- keep LOW_VOL only for `BTCUSDT` aurora
- suspend LOW_VOL for `ETHUSDT` aurora
- suspend LOW_VOL for `SOLUSDT` aurora until it shows stable positive expectancy
- do not disable `mean_reversion` from this evidence alone; first reconcile `LOW_VOLATILITY` vs `FLAT_*` taxonomy

## Concrete YAML Recommendations

These are evidence-based policy recommendations only. They were not applied in this audit.

1. `config/aurora/strategies/aurora.yaml`
   - Remove `UNCERTAIN` from `ETHUSDT.allowed_regimes`
   - Remove `LOW_VOLATILITY` from `ETHUSDT.allowed_regimes` for next run, or treat `regime_sizing LOW_VOLATILITY: 0.0` as a hard block
   - Remove `LOW_VOLATILITY` from `SOLUSDT.allowed_regimes` for next run
   - Keep `LOW_VOLATILITY` on `BTCUSDT`

2. `config/aurora/regime.yaml`
   - Keep the detector thresholds unchanged for now
   - Treat the detector output `UNCERTAIN` as a routing state to no-trade, not a tradable regime

3. `config/aurora/strategies/mean_reversion.yaml`
   - No immediate LOW_VOL change
   - First decide whether external `LOW_VOLATILITY` should map to `FLAT_LOW` only, or remain separate from MR gating

4. `config/aurora/strategies.yaml`
   - Use the strategy registry as an actual enforcement source of truth
   - Current runtime evidence shows assignment drift (`XRPUSDT` trading as `mean_reversion`, `SOLUSDT` receiving `md_amr` intent)

## Hard Launch Recommendation For Next Run

**NO-GO** unless both conditions are true:
- `UNCERTAIN` is hard-blocked in the execution/decision path
- aurora LOW_VOL exposure is narrowed before launch

If those two controls are enforced, the fail-closed recommendation is:
- `UNCERTAIN`: block entirely
- `LOW_VOLATILITY`: allow only `BTCUSDT` aurora; do not widen beyond that until new evidence exists
