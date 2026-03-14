# P2-C MR Momentum / Slope Separation Report

## 1. Executive Summary
- Added a new additive `momentum_separation_veto` contract for mean reversion.
- The new veto blocks late counter-trend fades when:
  - `%B` already wants a fade,
  - current BB width is already beyond a configured post-squeeze floor,
  - cumulative close drift over a small lookback is still moving against the intended fade.
- Live rollout is DOGE-only and `FLAT_LOW`-scoped via YAML.
- Execution, risk, orchestration, and the existing P2-A / P2-B contracts were not changed.
- This package is not a broad trend engine and does not add EMA stacks, regime redesign, or new execution behavior.

## 2. Scope
- Changed runtime/config files:
  - `apps/reference/config_models.py`
  - `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
  - `apps/reference/domains/decision_making/mean_reversion_handler.py`
  - `config/aurora/strategies/mean_reversion.yaml`
- Changed test files:
  - `tests/domains/feature_engineering/test_mean_reversion_momentum_slope_separation.py`
  - `tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py`
  - `tests/config/test_mean_reversion_yaml_contract.py`
- Documentation / tracking:
  - `reports/forensics/p2_mr_momentum_slope_separation_report.md`
  - `JOURNAL.md`
  - `TODO.md`
- Out of scope:
  - execution domain
  - risk sizing semantics
  - broad regime redesign
  - full momentum framework / EMA slope package
  - broader high-beta rollout beyond DOGE

## 3. New Contract
- New strict nested config model: `MRMomentumSeparationVetoConfig`
- New per-asset override field: `momentum_separation_veto`
- Runtime fields:
  - `enabled`
  - `lookback_bars`
  - `min_drift_pct`
  - `min_current_bb_width`
  - `regimes`
  - `sides`
- Runtime logic:
  - MR first computes the active fade side from `%B`.
  - P2-A narrow `FLAT_LOW` short hardening still runs first.
  - P2-B squeeze-expansion veto still runs next.
  - P2-C then checks cumulative drift over `lookback_bars`, but only if `current_bb_width >= min_current_bb_width`.
  - SHORT is vetoed when recent drift is sufficiently positive.
  - LONG is vetoed when recent drift is sufficiently negative.
- New neutral reason:
  - `momentum_separation_veto:<SIDE>:<signed_pct>%`
- Handler normalization:
  - `MOMENTUM_SEPARATION_VETO`

## 4. Red -> Green Evidence
### RED baseline
- `pytest tests/domains/feature_engineering/test_mean_reversion_momentum_slope_separation.py -q`
  - `5 failed in 1.41s`
  - failure cause: `MRStrategyConfig.__init__() got an unexpected keyword argument 'momentum_separation_veto'`
- `pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q`
  - collection error
  - `ImportError: cannot import name 'MRMomentumSeparationVetoConfig'`
- `pytest tests/config/test_mean_reversion_yaml_contract.py -q`
  - collection error
  - `ImportError: cannot import name 'MRMomentumSeparationVetoConfig'`

### GREEN after implementation
- `pytest tests/domains/feature_engineering/test_mean_reversion_momentum_slope_separation.py -q`
  - `7 passed in 0.68s`
- `pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q`
  - `2 passed in 0.87s`
- `pytest tests/config/test_mean_reversion_yaml_contract.py -q`
  - `4 passed in 1.26s`

### Coexistence / regression evidence
- `pytest tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py -q`
  - `4 passed in 1.47s`
- `pytest tests/domains/feature_engineering/test_mean_reversion_squeeze_expansion_veto.py -q`
  - `6 passed in 1.60s`
- `pytest tests/domains/test_mean_reversion_strategy.py -q`
  - `23 passed, 8 skipped in 1.63s`
- `pytest tests/domains/decision_making/test_mr_bar_gating.py -q`
  - `8 passed in 2.19s`
- `pytest tests/domains/decision_making/test_mean_reversion_handler_hardening_v1.py -q`
  - `11 passed in 2.06s`
- `pytest tests/domains/execution_position/test_split_brain_repro.py -q`
  - `5 passed in 9.87s`

### What the tests prove
- Late up-drift SHORT fades are blocked.
- Late down-drift LONG fades are blocked.
- Choppy, non-drifting fades still pass.
- P2-B squeeze traps still keep the P2-B reason.
- P2-A DOGE hardening still keeps the P2-A reason.
- Non-target symbols remain unchanged unless explicitly configured.
- YAML/typed config stays strict.

## 5. Design Notes
- Chosen formalism: simple cumulative close drift over a small lookback plus a current-width floor.
- Why this formalism:
  - it reuses existing `closes`, `%B`, regime, and BB width inputs
  - it is transparent to reason about in tests and reports
  - it avoids hidden state and avoids a new indicator stack
- Why this is not a broad trend engine:
  - no EMA stack
  - no separate trend state machine
  - no multi-factor directional model
  - no regime remapping
- Why this does not duplicate P2-B:
  - P2-B owns the `squeeze -> expansion -> breakout` class
  - P2-C only engages once current BB width is already above a configured floor
  - P2-B is evaluated first and keeps its reason on squeeze traps
- Why blast radius is minimal:
  - per-asset config
  - live YAML is DOGE-only
  - `FLAT_LOW` only
  - both sides are symmetric, but only within that narrow configured scope

## 6. Remaining Gaps
- Broader high-beta rollout is still undecided.
- Broader regime redesign remains out of scope.
- A separate package is still reasonable if MR later needs:
  - richer slope proxies
  - symbol-family generalization beyond DOGE
  - more explicit momentum-aware regime separation

## 7. Commands Run
- `pytest tests/domains/feature_engineering/test_mean_reversion_momentum_slope_separation.py -q`
- `pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q`
- `pytest tests/config/test_mean_reversion_yaml_contract.py -q`
- `pytest tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py -q`
- `pytest tests/domains/feature_engineering/test_mean_reversion_squeeze_expansion_veto.py -q`
- `pytest tests/domains/test_mean_reversion_strategy.py -q`
- `pytest tests/domains/decision_making/test_mr_bar_gating.py -q`
- `pytest tests/domains/decision_making/test_mean_reversion_handler_hardening_v1.py -q`
- `pytest tests/domains/execution_position/test_split_brain_repro.py -q`

## 8. Files Changed
- `apps/reference/config_models.py`
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `config/aurora/strategies/mean_reversion.yaml`
- `tests/domains/feature_engineering/test_mean_reversion_momentum_slope_separation.py`
- `tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py`
- `tests/config/test_mean_reversion_yaml_contract.py`
- `reports/forensics/p2_mr_momentum_slope_separation_report.md`
- `JOURNAL.md`
- `TODO.md`

## 9. JOURNAL / TODO
- Added a new P2-C implementation entry to `JOURNAL.md`.
- Marked P2-C complete in `TODO.md`.
- Left broader high-beta rollout and broader regime redesign as follow-up items.
