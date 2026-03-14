# P1 Mean Reversion Documentation Drift Appendix

## Scope

This appendix records documentation and contract-language drift found during the P1 MR logic review. It does not change runtime behavior.

## Drift 1: 1m / 3m naming survives after live 5m migration

### Evidence

- `config/aurora/strategies/mean_reversion.yaml:2-4`
  - header still says `3m Mean Reversion Strategy Configuration`
- `config/aurora/strategies.yaml:21-23`
  - registry comment still describes MR as `1m bars`
- `apps/reference/config_models.py:556-566`
  - typed config class is still `MeanReversion1mStrategyConfig`
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:105-132`
  - core runtime config dataclass still documents itself as `Mean Reversion 1m Strategy`

### Current truth

- live SSOT timeframe is `300` seconds
- current live MR assignment is DOGE-only

### Status

- `PROVEN DRIFT`

## Drift 2: `allowed_regimes` wording implies `MEAN_REVERSION` is meaningful inside MR allowlist

### Evidence

- `config/aurora/strategies/mean_reversion.yaml:24-26,188-190`
  - allowlist includes `MEAN_REVERSION`
- `mean_reversion_strategy.py:354-361`
  - runtime compares only `flat_regime.name`
- `regime_mapping.py:77-134`
  - raw `MEAN_REVERSION` is first mapped into `FLAT_LOW`, `FLAT_NORMAL`, or `FLAT_HIGH`

### Current truth

The token `MEAN_REVERSION` inside MR `allowed_regimes` is currently a semantic no-op. The core compare path only checks mapped `FlatRegime.name`.

### Status

- `PROVEN DRIFT`

## Drift 3: older incident summary overstates the next tuning move

### Evidence

- `reports/forensics/mean_reversion_incident_research_summary.md:11-14`
  - summary recommends immediate `min_bb_width >= 0.015`

### Current truth

After the P1 logic review, `0.015` is a candidate family, not a proven universal answer:

- global `0.015` blocks 318 of 426 historical actionables
- DOGE-only `0.015` looks materially cleaner
- `FLAT_LOW` short hardening and squeeze-expansion veto also look credible

### Status

- `PROVEN DRIFT IN RECOMMENDATION STRENGTH`

## Drift 4: safety-gate mental model is easy to get wrong

### Evidence

- `mean_reversion.yaml:33-38` disables MR safety gates
- `decision_making.py:297-330` always calls `apply_safety_gates(...)`
- `safety_gates.py:198-203,241-242` returns ALLOW when safety gates are not applied

### Current truth

The generic gate machinery exists, but current live MR explicitly opts out of those directional and price-motion protections.

### Status

- `PROVEN CLARIFICATION GAP`

## Recommended doc-sync follow-up

1. Normalize all MR-facing docs to "5m live strategy with legacy 1m/3m names in code only".
2. Clarify that MR `allowed_regimes` consumes mapped flat regimes, not raw regime labels.
3. Clarify that RSI is a confidence bonus, not a hard gate.
4. Reframe `0.015` from "obvious next fix" to "candidate tuning family".

