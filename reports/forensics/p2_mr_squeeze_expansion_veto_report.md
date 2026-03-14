# P2-B MR Squeeze-Expansion Veto Report

## 1. Executive Summary
- Додано вузький additive veto проти breakout-from-squeeze MR fades.
- Новий trap-class:
  - попередній BB width був squeeze-like
  - поточний BB width різко розширився
  - поточний width ще лишається у вузькому post-squeeze scope
  - `%B` already wants a fade entry
  - => MR signal vetoed
- Вето реалізовано як per-asset strict contract у YAML, без changes to execution, risk, cooldown, or orchestration semantics.
- P2-A DOGE hardening лишився чинним і з тим самим explicit reason.
- Межі пакета:
  - це не momentum/slope package
  - це не broad regime redesign
  - це не global ban на всі narrow-band signals

## 2. Scope

### Files changed
- `apps/reference/config_models.py`
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `config/aurora/strategies/mean_reversion.yaml`
- `tests/domains/feature_engineering/test_mean_reversion_squeeze_expansion_veto.py`
- `tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py`
- `tests/config/test_mean_reversion_yaml_contract.py`
- `reports/forensics/p2_mr_squeeze_expansion_veto_report.md`
- `JOURNAL.md`
- `TODO.md`

### Out of scope
- `execution_position`
- risk sizing / execution semantics
- EMA slope / trend engine
- momentum separation
- broad MR model redesign

## 3. New Contract

### New config surface
Per-asset MR override:
- `mean_reversion.assets.<SYMBOL>.strategy.squeeze_expansion_veto.enabled`
- `mean_reversion.assets.<SYMBOL>.strategy.squeeze_expansion_veto.squeeze_width_max`
- `mean_reversion.assets.<SYMBOL>.strategy.squeeze_expansion_veto.post_squeeze_width_max`
- `mean_reversion.assets.<SYMBOL>.strategy.squeeze_expansion_veto.expansion_ratio_min`
- `mean_reversion.assets.<SYMBOL>.strategy.squeeze_expansion_veto.regimes`
- `mean_reversion.assets.<SYMBOL>.strategy.squeeze_expansion_veto.sides`

### Runtime inputs
- current `bb.width`
- previous BB width rebuilt from `compute_bollinger_bands(closes[:-1])`
- active candidate side inferred from `%B` and existing `entry_threshold`
- current `flat_regime`

### Veto logic
Signal is vetoed only when all conditions hold:
1. veto is configured and enabled for that symbol
2. candidate side is in configured `sides`
3. current flat regime is in configured `regimes`
4. previous BB width `<= squeeze_width_max`
5. current BB width `<= post_squeeze_width_max`
6. `current_bb_width / previous_bb_width >= expansion_ratio_min`
7. `%B` already crossed the existing fade-trigger threshold

### Runtime reason
- `neutral:squeeze_expansion_veto:<SIDE>:<prev_width>-><curr_width>`

### Canonical YAML scope
- Configured only for `DOGEUSDT` in this package:
  - `enabled: true`
  - `squeeze_width_max: 0.010`
  - `post_squeeze_width_max: 0.020`
  - `expansion_ratio_min: 2.0`
  - `regimes: ["FLAT_LOW"]`
  - `sides: ["LONG", "SHORT"]`

This scope was chosen to keep blast radius minimal and because current live MR assignment is DOGE-centric.

## 4. Red -> Green Evidence

### RED baseline
RED was reproduced in a temp checkout reconstructed as `after P2-A / before P2-B`:
- temp path: `C:\Users\user\AppData\Local\Temp\phenix_p2b_red_after_p2a`

Command:
```text
pytest tests/domains/feature_engineering/test_mean_reversion_squeeze_expansion_veto.py -q
```
Result:
```text
collected 6 items
FFFFF
5 failed in 4.30s
```
What it proved:
- `MRStrategyConfig` had no `squeeze_expansion_veto` seam
- runtime evaluator had no squeeze-expansion veto path

Command:
```text
pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q
```
Result:
```text
collected 0 items / 1 error
ImportError: cannot import name 'MRSqueezeExpansionVetoConfig'
```
What it proved:
- strict config contract had no typed squeeze-expansion veto model
- handler wiring had no override path for the new veto

Command:
```text
pytest tests/config/test_mean_reversion_yaml_contract.py -q
```
Result:
```text
collected 0 items / 1 error
ImportError: cannot import name 'MRSqueezeExpansionVetoConfig'
```
What it proved:
- canonical YAML contract had no explicit squeeze-expansion schema

### GREEN after implementation
Command:
```text
pytest tests/domains/feature_engineering/test_mean_reversion_squeeze_expansion_veto.py -q
```
Result:
```text
collected 6 items
......
6 passed in 2.93s
```
What it proves:
- narrow squeeze + expansion + SHORT fade trigger is blocked
- symmetric LONG trap is blocked too
- non-expanding narrow signals still pass
- wider-band fades outside the post-squeeze scope still pass
- symbols without configured veto stay unchanged
- P2-A short hardening reason remains stable

Command:
```text
pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q
```
Result:
```text
collected 2 items
..
2 passed in 3.35s
```
What it proves:
- typed per-asset veto config is accepted
- handler wires it into runtime strategy config

Command:
```text
pytest tests/config/test_mean_reversion_yaml_contract.py -q
```
Result:
```text
collected 3 items
...
3 passed in 4.52s
```
What it proves:
- canonical YAML exposes the new contract
- invalid threshold ordering is rejected fail-closed
- misspelled keys are still rejected

Regression commands:
```text
pytest tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py -q
pytest tests/domains/test_mean_reversion_strategy.py -q
pytest tests/domains/decision_making/test_mr_bar_gating.py -q
pytest tests/domains/decision_making/test_mean_reversion_handler_hardening_v1.py -q
pytest tests/domains/execution_position/test_split_brain_repro.py -q
```
Results:
- `4 passed in 3.51s`
- `23 passed, 8 skipped in 3.89s`
- `8 passed in 4.83s`
- `11 passed in 4.83s`
- `5 passed in 24.81s`

## 5. Design Notes
- Я обрав саме цей veto формалізм, бо він використовує тільки вже наявні BB/close inputs:
  - previous width
  - current width
  - active `%B` trigger
  - regime/side scope
- Це не momentum/slope package, бо тут немає:
  - EMA slope
  - multi-bar directionality scoring
  - drift/momentum state machine
  - trend-strength model
- Це не дублює P2-A:
  - P2-A блокує вузький `FLAT_LOW` DOGE short regardless of expansion
  - P2-B блокує transition class `squeeze -> expansion -> fade trigger`
  - P2-B також симетрично покриває LONG side
- Blast radius мінімізований двома шарами:
  - per-asset YAML scope
  - runtime gating only inside configured `regimes`, `sides`, and width thresholds

## 6. Remaining Gaps
- P2-C still needed for momentum/slope separation.
  - This package does not detect trend drift once volatility is already fully expanded.
- Broader regime redesign remains out of scope.
- A broader high-beta family package may still be needed if MR expands beyond DOGE or if more high-beta assets are enabled live.
- Docs cleanup / contract wording follow-up still remains separately.

## 7. Commands Run
```text
pytest tests/domains/feature_engineering/test_mean_reversion_squeeze_expansion_veto.py -q
pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q
pytest tests/config/test_mean_reversion_yaml_contract.py -q
pytest tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py -q
pytest tests/domains/test_mean_reversion_strategy.py -q
pytest tests/domains/decision_making/test_mr_bar_gating.py -q
pytest tests/domains/decision_making/test_mean_reversion_handler_hardening_v1.py -q
pytest tests/domains/execution_position/test_split_brain_repro.py -q
```

## 8. Files Changed
- `apps/reference/config_models.py`
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `config/aurora/strategies/mean_reversion.yaml`
- `tests/domains/feature_engineering/test_mean_reversion_squeeze_expansion_veto.py`
- `tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py`
- `tests/config/test_mean_reversion_yaml_contract.py`
- `reports/forensics/p2_mr_squeeze_expansion_veto_report.md`
- `JOURNAL.md`
- `TODO.md`

## 9. JOURNAL / TODO
- `JOURNAL.md` updated with the P2-B implementation note, blocked trap-class, and RED->GREEN evidence.
- `TODO.md` updated to close P2-B and leave P2-C momentum/slope separation plus broader high-beta follow-up explicit.
