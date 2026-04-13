# Forensic Report: Legacy signal_weights, feature_neutrals, and BTC skew

Date: 2026-04-11

Repository: Phenix

Branch: Phenix_v2

## Scope

This report answers two concrete questions using only code and log evidence:

1. What is the current implementation status of legacy signal_weights and feature_neutrals in the codebase?
2. Do these legacy fields still participate in system decisions, and can they explain the observed BTC skew?

Evidence included:

- Python runtime code under apps/reference
- Live and rotated log files under logs/

Evidence intentionally excluded by request:

- Documentation
- JSON artifacts
- YAML configuration files

## Executive Summary

### Proven facts

- Legacy signal_weights and feature_neutrals are still loaded in the live Aurora decision path and forwarded into the active scoring interface from [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L358-L359) and [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L492-L493).
- The active QuadraticScoringKernel explicitly treats both fields as deprecated compatibility inputs and does not read them in scoring math, as stated in [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L142-L184).
- The active live decision score is driven by linear_score or features.pillar_sum, then by thresholding, shield attenuation, side_bias, and hysteresis in [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L204-L230), [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L320-L345), and [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L438-L466).
- In current code, signal_weights and feature_neutrals are not dynamically calculated from market state. They are configuration payloads retrieved and forwarded as dictionaries by [apps/reference/domains/decision_making/aurora_scoring_helpers.py](apps/reference/domains/decision_making/aurora_scoring_helpers.py#L145-L156) and [apps/reference/domains/decision_making/aurora_scoring_helpers.py](apps/reference/domains/decision_making/aurora_scoring_helpers.py#L352-L363).
- The active alpha_search Aurora adapter also stores and forwards these legacy fields, but it forwards them into the same QuadraticScoringKernel, which ignores them. See [apps/reference/domains/alpha_search/models/aurora_adapter.py](apps/reference/domains/alpha_search/models/aurora_adapter.py#L90-L117) and [apps/reference/domains/alpha_search/models/aurora_adapter.py](apps/reference/domains/alpha_search/models/aurora_adapter.py#L193-L194).
- In the currently retained live aurora_core log rotations, buy-side decision traces were not observed at all. Aggregated search across aurora_core.log and aurora_core.log.* returned BuyDecisionTraceCount = 0.
- In the same retained live aurora_core log set, sell-side decision traces were observed for more than BTC: BTCUSDT SELL = 77, ETHUSDT SELL = 78, SOLUSDT SELL = 149.
- In domain_execution_position.log, repeated bracket-health recovery failures are also not BTC-exclusive. Aggregated counts in the current file are BNBUSDT SL/TP = 249/249, XRPUSDT SL/TP = 233/233, BTCUSDT SL/TP = 205/205.

### Engineering conclusion

- Legacy signal_weights and feature_neutrals are interface debt, not active live decision drivers.
- The observed BTC skew in the current runtime evidence is not explained by legacy signal_weights or feature_neutrals.
- The available log evidence contradicts the stronger claim that the skew is exclusive to BTC. In the retained live aurora_core logs, ETH and SOL also appear sell-only at the decision-trace and signal levels.

## Evidence Boundary

The report relies on code and log evidence only.

Primary code evidence:

- [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py)
- [apps/reference/domains/decision_making/aurora_scoring_helpers.py](apps/reference/domains/decision_making/aurora_scoring_helpers.py)
- [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py)
- [apps/reference/domains/feature_engineering/calculation_engine.py](apps/reference/domains/feature_engineering/calculation_engine.py)
- [apps/reference/domains/feature_engineering/pillar_indicators.py](apps/reference/domains/feature_engineering/pillar_indicators.py)
- [apps/reference/domains/alpha_search/models/aurora_adapter.py](apps/reference/domains/alpha_search/models/aurora_adapter.py)
- [apps/reference/domains/alpha_search/runtime/scenario_worker.py](apps/reference/domains/alpha_search/runtime/scenario_worker.py)
- [apps/reference/domains/alpha_search/runtime/override_allowlist.py](apps/reference/domains/alpha_search/runtime/override_allowlist.py)
- [apps/reference/config_models.py](apps/reference/config_models.py)
- [apps/reference/domains/alpha_search/config_models.py](apps/reference/domains/alpha_search/config_models.py)

Primary log evidence:

- [logs/aurora_core.log.13](logs/aurora_core.log.13)
- [logs/domain_execution_position.log](logs/domain_execution_position.log)
- [logs/alpha_search_runtime/20260307_180725/aggregate/alpha_search_domain.log.1](logs/alpha_search_runtime/20260307_180725/aggregate/alpha_search_domain.log.1)

## Finding 1: Legacy fields are still present in the live Aurora interface

The live Aurora decision path still resolves both legacy fields before calling the scoring kernel:

- signal_weights is loaded in [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L358)
- feature_neutrals is loaded in [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L359)
- both are forwarded into compute kwargs in [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L492-L493)

The values are retrieved by simple config accessors rather than by runtime computation:

- signal_weights accessor: [apps/reference/domains/decision_making/aurora_scoring_helpers.py](apps/reference/domains/decision_making/aurora_scoring_helpers.py#L145-L156)
- feature_neutrals accessor: [apps/reference/domains/decision_making/aurora_scoring_helpers.py](apps/reference/domains/decision_making/aurora_scoring_helpers.py#L352-L363)

These helper functions do not perform scoring math. They only return dictionaries from per-symbol override surfaces or global decision config objects.

### Implication

The system still carries these fields through the live call chain, but only as compatibility payloads.

## Finding 2: The active scoring kernel explicitly ignores them

The decisive implementation detail is in [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L142-L184):

- the file marks signal_weights and feature_neutrals as deprecated
- the comments say they are accepted for call-site compatibility but not read by Quadratic
- the active live inputs list excludes both fields

The actual compute path then resolves the score input from either linear_score or features.pillar_sum in [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L204-L230).

There is no arithmetic branch in the active kernel that uses signal_weights or feature_neutrals to:

- change side
- change threshold
- change sizing score
- change stop-loss
- change take-profit

### Implication

In the current active scoring engine, these legacy fields do not participate in decision math.

## Finding 3: The live decision path is now driven by pillar_sum, not legacy weights/neutrals

The upstream aggregate entering the live kernel is pillar_sum.

Feature engineering builds pillar_sum in [apps/reference/domains/feature_engineering/calculation_engine.py](apps/reference/domains/feature_engineering/calculation_engine.py#L1307-L1319).

The aggregation function is implemented in [apps/reference/domains/feature_engineering/pillar_indicators.py](apps/reference/domains/feature_engineering/pillar_indicators.py#L356-L383), where tactician, operator, and strategist are combined into a weighted sum.

QuadraticScoringKernel then reads that aggregate from features.pillar_sum in [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L204-L230).

Decision direction is then chosen by threshold comparison and hysteresis in:

- [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L320-L345)
- [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L438-L466)

### Implication

The live Aurora side-selection chain is:

1. feature engineering produces pillar_sum
2. QuadraticScoringKernel converts pillar_sum into decision_score and sizing_score
3. thresholding, shield, side_bias, and hysteresis determine the final side

Legacy signal_weights and feature_neutrals are not in this chain.

## Finding 4: alpha_search still carries legacy fields, but does not restore their scoring effect

The alpha_search adapter still defines defaults and stores both legacy fields:

- defaults in [apps/reference/domains/alpha_search/models/aurora_adapter.py](apps/reference/domains/alpha_search/models/aurora_adapter.py#L36-L59)
- constructor storage in [apps/reference/domains/alpha_search/models/aurora_adapter.py](apps/reference/domains/alpha_search/models/aurora_adapter.py#L90-L117)
- kernel forwarding in [apps/reference/domains/alpha_search/models/aurora_adapter.py](apps/reference/domains/alpha_search/models/aurora_adapter.py#L193-L194)

Scenario overrides can inject these values in [apps/reference/domains/alpha_search/runtime/scenario_worker.py](apps/reference/domains/alpha_search/runtime/scenario_worker.py#L256-L262).

alpha_search also still warns about partial override combinations in [apps/reference/domains/alpha_search/runtime/override_allowlist.py](apps/reference/domains/alpha_search/runtime/override_allowlist.py#L205-L226), and those warnings are observable in [logs/alpha_search_runtime/20260307_180725/aggregate/alpha_search_domain.log.1](logs/alpha_search_runtime/20260307_180725/aggregate/alpha_search_domain.log.1#L14-L15).

However, this does not restore scoring influence, because the adapter passes the legacy fields into the same QuadraticScoringKernel that ignores them.

### Implication

The only proven active effect of these fields today is:

- compatibility parsing
- compatibility forwarding
- scenario override storage
- warning generation in alpha_search tooling

No proven scoring impact was found even in the active alpha_search adapter path.

## Finding 5: Contract models still expose legacy surfaces

The repository still exposes these fields in runtime model contracts:

- decision-level signal_weights in [apps/reference/config_models.py](apps/reference/config_models.py#L1320-L1360)
- decision-level feature_neutrals in [apps/reference/config_models.py](apps/reference/config_models.py#L1357-L1360)
- per-instrument feature_neutrals override in [apps/reference/config_models.py](apps/reference/config_models.py#L4903-L4912)

The alpha_search config model is more explicit and states directly that both fields are parsed for backward compatibility and ignored by QuadraticScoringKernel in [apps/reference/domains/alpha_search/config_models.py](apps/reference/domains/alpha_search/config_models.py#L56-L72).

### Implication

The codebase still exposes legacy surfaces at the contract layer, which explains why these fields still appear in helper functions, adapter constructors, override systems, and warnings.

## Finding 6: No evidence of live runtime observability for legacy fields

Aggregated search across current live aurora_core log rotations and domain_execution_position.log returned:

- signal_weights occurrences: 0
- feature_neutrals occurrences: 0

This result was computed over:

- logs/aurora_core.log
- logs/aurora_core.log.*
- [logs/domain_execution_position.log](logs/domain_execution_position.log)

### Implication

The current live runtime observability also supports the code conclusion: these legacy fields are not active runtime decision levers in live Aurora.

## Finding 7: The observed decision skew in retained live logs is not BTC-exclusive

### Live decision-trace counts

Aggregated search across aurora_core.log and aurora_core.log.* for QUADRATIC_DECISION_TRACE entries with a concrete side produced:

| Symbol | BUY | SELL |
| --- | ---: | ---: |
| BTCUSDT | 0 | 77 |
| ETHUSDT | 0 | 78 |
| SOLUSDT | 0 | 149 |

Global buy-side decision trace count across the same retained log set: 0.

### Concrete examples

BTC SELL decision trace and signal:

- [logs/aurora_core.log.13](logs/aurora_core.log.13#L1091-L1095)

ETH SELL signal example:

- [logs/aurora_core.log.13](logs/aurora_core.log.13#L1059)

SOL SELL signal example:

- [logs/aurora_core.log.13](logs/aurora_core.log.13#L1035)

### Implication

The currently retained live aurora_core evidence does not support the statement that sell skew is exclusive to BTC. The stronger supported statement is that the observed log window is globally sell-biased for the symbols that emitted concrete Aurora sides.

## Finding 8: Bracket-health error spam is also not BTC-exclusive

The active execution_position log shows the same -4130 bracket-health recovery failure pattern for BNBUSDT, XRPUSDT, and BTCUSDT, not only BTC.

Concrete examples:

- BNBUSDT examples in [logs/domain_execution_position.log](logs/domain_execution_position.log#L5-L6)
- XRPUSDT examples in [logs/domain_execution_position.log](logs/domain_execution_position.log#L9-L10)
- BTCUSDT examples in [logs/domain_execution_position.log](logs/domain_execution_position.log#L2159-L2160)

Aggregated counts in the current file:

| Symbol | SL failures | TP failures |
| --- | ---: | ---: |
| BNBUSDT | 249 | 249 |
| XRPUSDT | 233 | 233 |
| BTCUSDT | 205 | 205 |

### Implication

The execution_position recovery noise is not BTC-specific either. BTC is one participant in a broader repeated closePosition bracket-recovery failure pattern.

## Direct Answers

### Are old signal_weights and feature_neutrals still calculated by the system?

No, not in the sense of live scoring math.

What is still happening:

- they are parsed by model contracts
- they are loaded from config surfaces
- they are forwarded through live and alpha_search call interfaces
- they can be injected into alpha_search scenarios
- they can trigger alpha_search override warnings

What is not happening in the active Quadratic path:

- they are not used to build decision_score
- they are not used to choose BUY or SELL
- they are not used to widen or tighten live thresholds
- they are not used to size positions
- they are not used to compute TP or SL

### Where do they still influence decisions today?

No proven live decision influence was found.

No proven active alpha_search scoring influence was found either, because alpha_search forwards them into the same Quadratic kernel that ignores them.

Their only proven active effects today are non-scoring effects:

- compatibility surfaces
- override payload carriage
- warning generation in alpha_search override validation

### Can they explain the current BTC skew?

No.

The current code says they are ignored by the active kernel, and the current live logs show the skew through negative s_linear and sell-side decision traces, not through any observable legacy-field path. The retained live logs also show that the sell-only pattern is not unique to BTC.

## Root Cause Framing

### Proven

- The repository still exposes legacy fields in contracts and call signatures.
- The active kernel no longer consumes them.
- Live decision logs show sell-only side decisions for BTC, ETH, and SOL in the retained window.

### Inference

- The codebase currently contains interface debt from an older scoring regime: legacy fields remain visible at the edges while the active decision core has already migrated to pillar_sum-driven Quadratic scoring.
- This interface debt makes it easy to over-attribute current runtime behavior to legacy fields even though the active kernel ignores them.

### Unproven

- This report does not prove why pillar_sum is persistently negative for BTC, ETH, and SOL. It only proves that legacy signal_weights and feature_neutrals are not the active cause.

## Recommendations

1. Remove or hard-disable signal_weights and feature_neutrals in the live Aurora decision interface, or emit an explicit startup warning that they are ignored by QuadraticScoringKernel.
2. Reword alpha_search partial-override warnings so they do not imply current live scoring sensitivity if the active kernel still ignores these fields.
3. Add a per-symbol side-distribution runtime metric so sell-only or buy-only decision windows become observable without manual log forensics.
4. Add a dedicated runtime audit for pillar_sum and pillar_contribs by symbol. That is the shortest path to explaining the real source of the current sell bias.

## Final Verdict

The current active Aurora runtime still carries legacy signal_weights and feature_neutrals through helper functions, config contracts, adapters, and scenario tooling, but the active QuadraticScoringKernel does not use them in decision math. In the retained live logs, there is no evidence that these legacy fields influence live trade direction, threshold crossing, sizing, TP, or SL. They do not explain the present BTC skew. The retained runtime evidence also shows that the observed sell-only bias is not exclusive to BTC: ETH and SOL are also sell-only in the visible Aurora decision traces, and bracket-health -4130 spam is shared by BTC, XRP, and BNB.
