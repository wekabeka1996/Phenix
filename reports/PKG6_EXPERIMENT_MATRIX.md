# PKG6 EXPERIMENT MATRIX

Label:

ETH+BTC PROXY / RESEARCH-ONLY / NOT FULL-UNIVERSE

## Arm 0 — Raw Baseline Reference

- Reference run: `20260314_170343`
- Config delta vs canonical proxy baseline: none
- Role:
  - historical reference only
  - not part of optimization anchor
- Hypothesis:
  - none; this arm exists only to measure how far the v1-safe surface has already moved from the toxic baseline.
- Success condition:
  - not applicable
- Failure condition:
  - not applicable

## Arm 1 — V1 Safety Anchor

- Reference run: `20260314_172657`
- Base delta:
  - `config/overlays/march_candidate_v1_block_eth_trend_down.yaml`
- Role:
  - current best proxy result
  - main safety anchor for PKG-6
- Hypothesis:
  - bounded refinement should beat this arm only if it preserves its clean drawdown profile.
- Success condition:
  - not applicable; this is the benchmark anchor.
- Failure condition:
  - any candidate that only beats raw baseline but not this arm is not a PKG-6 winner.

## Arm 2 — Scoring-First Over V1

- Base: Arm 1
- Variable delta set:
  - `weights.macro_resid`
  - `weights.tfi`
  - `weights.depth_imbalance`
- Hypothesis:
  - the first honest alpha hint may come from small rebalancing of context and microstructure weights while keeping v1 participation policy fixed.
- Success condition:
  - beats v1 on at least one meaningful performance axis while keeping drawdown near v1 and remaining fallback-free.
- Failure condition:
  - no material improvement over v1, or improved ROI only by materially worsening drawdown or churn.

## Arm 3 — Mixed Minimal Over V1

- Base: Arm 1
- Variable delta set:
  - `signal_threshold.value`
  - `volatility_entry_logic.regime_multipliers.MEAN_REVERSION`
  - `exit.regime_tpsl.tp_mult.MEAN_REVERSION`
  - `weights.macro_resid`
- Hypothesis:
  - the first honest alpha hint may require a tiny combination of participation control and one contextual scoring refinement, still fully inside the v1-safe regime surface.
- Success condition:
  - improves v1 on ROI and/or Sharpe without breaking drawdown integrity and without reopening toxic behavior.
- Failure condition:
  - candidate wins only through inactivity, overtrading, or unsafe drawdown giveback.

## Optional Arm 4 — Cautious Recovery

Not included in PKG-6.

Reason:

- no sufficiently narrow, runtime-backed, causal control was proven safe for reopening ETH participation beyond the v1 regime block without drifting into broad regime mutation.

That keeps PKG-6 aligned with its safety-first package rules.

## Trial Budget

- Arm 2 scoring-first: bounded Optuna study, small trial budget
- Arm 3 mixed minimal: bounded Optuna study, small trial budget

The budget is intentionally sized to rank hypotheses, not to exhaustively fit March.