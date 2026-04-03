# OBI/TFI Runtime Influence Research

## Scope
This document records the evidence-based map of how OBI and TFI affect live runtime decisions in the current Phenix workspace.

## Facts
- Feature engineering emits OBI and TFI into the runtime features payload ([apps/reference/domains/feature_engineering/feature_engineering.py](../apps/reference/domains/feature_engineering/feature_engineering.py#L1428)).
- The mean-reversion handler caches the CMD payload in `_last_cmd_features` before veto evaluation, so veto logic reads the same runtime payload that the strategy bus carries ([apps/reference/domains/decision_making/mean_reversion_handler.py](../apps/reference/domains/decision_making/mean_reversion_handler.py#L1900)).
- Risk management reads raw OBI and TFI from `features` and folds them into `risk_score` ([apps/reference/domains/risk_management/risk_management.py](../apps/reference/domains/risk_management/risk_management.py#L289)).
- Aurora decision flow passes `features.get("obi")` into `EntryPlan.compute()` ([apps/reference/domains/decision_making/aurora_decision.py](../apps/reference/domains/decision_making/aurora_decision.py#L991)).

## Consumer Map

| surface | layer | file:line | consumer | formula / condition | direct_or_indirect | active_or_legacy | decision_effect |
|---|---|---|---|---|---|---|---|
| Risk score | L2 system/risk layer | [risk_management.py](../apps/reference/domains/risk_management/risk_management.py#L289) | Reads OBI and TFI from features, then applies mandatory risk-score weights | risk_score = abs(obi) * w_obi + abs(tfi) * w_tfi + abs(delta_price) / price * w_dp + applied_toxicity + applied_feature; risk_score > max_risk_score denies | direct | active | allow / deny via the risk threshold |
| Microstructure veto, TFI branch | L3 strategy layer | [mean_reversion_handler.py](../apps/reference/domains/decision_making/mean_reversion_handler.py#L666) | Reads raw TFI from cached CMD features | alpha = 2 / (span + 1); smoothed_tfi = alpha * tfi + (1 - alpha) * prev_ema; LONG adverse if below negative threshold, SHORT adverse if above threshold; missing or invalid TFI blocks; warmup blocks; adverse continuation or ambiguity blocks, absorption allows | direct | active, config-gated | allow / deny / defer |
| Microstructure veto, OBI confirm-only branch | L3 strategy layer | [mean_reversion_handler.py](../apps/reference/domains/decision_making/mean_reversion_handler.py#L702) | Reads raw OBI only inside the adverse-TFI branch | adverse OBI can confirm the block; non-adverse OBI allows; missing or invalid OBI blocks when confirm is enabled | direct | active, config-gated | can flip adverse TFI from block to allow |
| EntryPlan OBI modulation | execution-adjacent / entry-planning | [aurora_decision.py](../apps/reference/domains/decision_making/aurora_decision.py#L991) | Passes OBI into EntryPlan compute, with params hydrated from decision_making entry_plan config | raw_mult = 1 + obi_weight * obi_factor; obi_factor is negative for LONG and positive for SHORT; result is clamped to the configured multiplier bounds; missing OBI is neutral in the current loader path | direct | active | changes entry offset and fill aggressiveness, not side |
| DecisionContext flow bridge | observability-only / legacy-only surfaces | [decision_context.py](../apps/reference/domains/decision_making/decision_context.py#L300) and [readiness_gates.py](../apps/reference/domains/decision_making/readiness_gates.py#L434) | Parses OBI and TFI into FlowView and touches ctx.flow during readiness evaluation | combined_pressure is the mean of the available flow signals; is_buy_pressure and is_sell_pressure exist, but no downstream value-based trade decision consumer was proven in the inspected code | indirect | active but not proven live decision effect | readiness diagnostics and missing-field gating only |

## What Is Proven
- OBI and TFI are live runtime inputs in L2 risk scoring.
- TFI is a live runtime input in the mean-reversion microstructure veto.
- OBI is a live runtime input only as a confirm-only branch in the same veto.
- OBI is also a live runtime input in entry planning, where it modulates the entry offset rather than the trade side.

## What Is Not Proven
- DecisionContext convenience helpers such as combined_pressure, is_favorable_for_long, and is_favorable_for_short were not proven to affect live trade decisions.
- Alpha-search scenario weights and docs-only formulas were not proven to drive the live trading path.
- No additional live runtime consumer of raw OBI or TFI was proven outside the four consumers listed above.

## Contradictions and Drift
- `obi_missing_policy` is declared in the entry-plan schema, but the current loader hardcodes `ObiMissingPolicy.NEUTRAL` when building `EntryPlanParams` ([apps/reference/config_models.py](../apps/reference/config_models.py#L2336), [apps/reference/domains/decision_making/aurora_config_loader.py](../apps/reference/domains/decision_making/aurora_config_loader.py#L445)). That makes the field effectively inert today.
- The mean-reversion microstructure veto is present in code but disabled by default in YAML ([config/aurora/strategies/mean_reversion.yaml](../config/aurora/strategies/mean_reversion.yaml#L263)).

## Validation
Targeted runtime validation passed across the microstructure veto, veto config, entry-plan, and risk-management test sets. The focused pytest run completed with 90 passed.

## Bottom Line
OBI and TFI do affect live runtime decisions, but only in a bounded set of places: L2 risk scoring, L3 mean-reversion vetoing, and execution-adjacent entry planning. `DecisionContext.flow` and the documentation passports are bridge or descriptive surfaces, not proven live decision drivers.
