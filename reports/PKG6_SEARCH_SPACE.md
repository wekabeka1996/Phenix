# PKG6 SEARCH SPACE

Label:

ETH+BTC PROXY / RESEARCH-ONLY / NOT FULL-UNIVERSE

## Search Principle

PKG-6 starts from the v1-safe overlay, not from the raw proxy baseline.

Fixed base for all optimized arms:

- proxy universe: `ETHUSDT` tradable + `BTCUSDT` context
- strategy assignment: `ETHUSDT -> aurora`
- overlay anchor: `config/overlays/march_candidate_v1_block_eth_trend_down.yaml`
- fail-closed fallback rejection: enabled

The search cube is deliberately small and only includes fields whose runtime effect is confirmed in current code.

## Family A — Context / Participation Refinement

### A1. ETH signal threshold

- YAML path: `strategies.aurora.assets.ETHUSDT.signal_threshold.value`
- Current default: `0.008`
- Search range: `0.0070 .. 0.0095` step `0.0005`
- Runtime evidence:
  - `apps/reference/domains/decision_making/aurora_decision.py` resolves per-symbol `signal_threshold` before kernel compute.
- Reason for inclusion:
  - v1 is already safe but sparse; small threshold movement can modestly change participation without reopening blocked regimes.
- Expected mechanism:
  - lower values admit more signals; higher values preserve selectivity and may reduce marginal churn.

### A2. ETH mean-reversion entry offset multiplier

- YAML path: `strategies.aurora.assets.ETHUSDT.volatility_entry_logic.regime_multipliers.MEAN_REVERSION`
- Current default: `0.25`
- Search range: `0.15 .. 0.35` step `0.05`
- Runtime evidence:
  - `apps/reference/domains/decision_making/aurora_decision.py` uses `volatility_entry_logic.regime_multipliers` to offset maker entry price by ATR-scaled distance.
- Reason for inclusion:
  - this is a direct participation-quality knob on the v1 regime surface, not a broad strategy mutation.
- Expected mechanism:
  - smaller multiplier moves entry closer to anchor price; larger multiplier demands deeper pullbacks and may trade less but cleaner.

### A3. ETH mean-reversion TP multiplier

- YAML path: `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.tp_mult.MEAN_REVERSION`
- Current default: `0.80`
- Search range: `0.75 .. 1.00` step `0.05`
- Runtime evidence:
  - `apps/reference/domains/decision_making/aurora_tpsl.py` reads `exit.regime_tpsl.tp_mult` to build target price.
- Reason for inclusion:
  - v1 profitability is concentrated in mean-reversion slices, so small TP retuning is a direct way to test whether upside capture can improve without adding toxic exposure.
- Expected mechanism:
  - higher TP multiplier may increase upside per trade but risks reducing hit rate; lower values preserve fast exits and safety.

## Family B — Scoring / Weight Refinement

### B1. ETH macro_resid weight

- YAML path: `strategies.aurora.assets.ETHUSDT.weights.macro_resid`
- Current default: `0.25`
- Search range: `0.20 .. 0.32` step `0.02`
- Runtime evidence:
  - `apps/reference/domains/decision_making/aurora_scoring_helpers.py` reads per-symbol `weights` and `aurora_decision.py` passes them into the active scoring kernel.
- Reason for inclusion:
  - macro context remains the main reason BTC anchor is required; small reweighting is a direct test of whether v1 can use that context more efficiently.
- Expected mechanism:
  - lower value reduces anchor-context dominance; higher value strengthens contextual confirmation.

### B2. ETH TFI weight

- YAML path: `strategies.aurora.assets.ETHUSDT.weights.tfi`
- Current default: `0.093`
- Search range: `0.05 .. 0.14` step `0.01`
- Runtime evidence:
  - same scoring-path evidence as B1.
- Reason for inclusion:
  - TFI is a direct microstructure directional feature; small changes can alter entry quality without changing regime policy.
- Expected mechanism:
  - higher TFI weight sharpens directional confirmation; lower weight reduces sensitivity to transient flow noise.

### B3. ETH depth_imbalance weight

- YAML path: `strategies.aurora.assets.ETHUSDT.weights.depth_imbalance`
- Current default: `-0.256`
- Search range: `-0.32 .. -0.18` step `0.02`
- Runtime evidence:
  - same scoring-path evidence as B1.
- Reason for inclusion:
  - current weight is materially negative and therefore highly causal; bounded retuning can test whether v1 is over- or under-penalizing ask-dominance.
- Expected mechanism:
  - more negative values make the model more conservative under sell-pressure; less negative values recover participation.

## Explicit Exclusions

Excluded from PKG-6 search:

- `allowed_regimes` reopening of `TREND_DOWN`
  - reason: that would directly reopen the proven toxic ETH cluster.
- broad `signal_weights` reshuffling across many features
  - reason: patch-family explosion and weak causal traceability.
- non-verified or passport-only knobs
  - reason: not allowed by package rules.
- business-logic changes
  - reason: no code blocker remains after PKG-5.

## Search Budget Shape

- total parameters in bounded cube: `6`
- context / participation knobs: `3`
- scoring / weight knobs: `3`

This stays under the package hard limit and remains human-defensible.