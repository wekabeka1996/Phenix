# Judge Hybrid Testnet Bridge Plan

Executive verdict: JUDGE_BRIDGE_REQUIRES_NEW_RUNTIME_SEAM, SAME_DIRECTION_ONLY_TESTNET_PILOT_IS_THE_ONLY_DEFENSIBLE_FIRST_STEP.

## Evidence Anchors

- reports/judge/judge_aurora_joint_calibration_current_window/report.md
- docs/LLM_JUDGE/JUDGE_CURRENT_WINDOW_TRADING_READINESS_2026-05-24.md
- apps/reference/utils/trading_modes.py
- apps/reference/bootstrap/preflight.py
- apps/reference/domains/neocortex/main.py
- apps/reference/domains/decision_making/authority_bridge.py
- apps/reference/domains/alpha_search/backtest_plugin.py
- config/alpha_search.yaml

## What Is Now Proven

### 1. Judge confidence and live Aurora score are not the same control surface

- Judge confidence is a shadow-only Judge-domain field.
- Live Aurora decisions currently depend on pillar_sum and Aurora score lineage, then pass through regime, NRR, liquidity, objective, and execution gates.
- The current Judge experts use legacy linear formulas and do not consume pillar_sum directly.

### 2. Current-window joint calibration is not strong enough for Judge direction authority

From the current 14-slice joint calibration:

- same-direction Judge vs Aurora threshold proxy: 31.8624%
- Aurora-neutral: 39.1929%
- opposite-direction: 28.9447%
- Judge confidence vs Aurora confidence proxy correlation: 0.45467
- Judge confidence vs abs(pillar_sum) correlation: -0.123802

This means the current Judge layer is neither a clean duplicate of Aurora nor a clean superset of it.

### 3. The current 0.6-0.9 target band is still not bridge-safe as a direct authority window

For rows in 0.6-0.9:

- same-direction: 25.6826%
- Aurora-neutral: 48.6348%
- opposite-direction: 25.6826%
- total_net_pnl_pct: 8.6643

This is useful as research evidence but not sufficient as a direct live authority threshold.

### 4. Hybrid mode already exists, but it is not a Judge bridge

The existing hybrid contract is:

- market_data: live
- feature_engineering: live
- decision_making: live
- risk_management: testnet
- execution_position: testnet
- audit_trail: live

That is a domain-mode split, not a Judge authority handoff.

### 5. Current Judge runtime is not wired into the live Aurora decision loop

The current Judge experts, chamber, shadow plans, and Policy Cortex entry point are wired under alpha_search/backtest_plugin.

No current live Aurora runtime or decision_making runtime path instantiates these Judge experts directly.

Therefore, a Judge bridge is a new integration seam, not a config switch.

## Review Of The External Audit

### Confirmed

- The linear-vs-nonlinear mismatch is real: Judge experts use legacy weighted-centered formulas while Aurora runtime uses pillar_sum-driven Aurora scoring.
- The current Judge expert config does not consume pillar_sum.
- The current Judge expert config also does not consume sentiment_state, obi_close, or funding_rate.
- Policy Cortex is shadow-only and degrades unknown surfaces to UNKNOWN / fail_closed_unknown reasoning.

### Needs qualification

- The registry-coverage risk is real, but the description "only TREND_UP:BUY and HIGH_VOLATILITY exist" is too coarse. The registry contains more than those literal surfaces, but coverage is still sparse relative to the live market state space.
- The claim about exact stale-regime percentages and exact maximum staleness needs direct measurement on current artifacts, not just code inspection.
- The statement that Judge is already evaluating all active live strategies should be narrowed: the currently materialized Judge path in this workspace is a shadow/backtest path, not the live Aurora runtime loop.

### Bridge implication from the review

The bridge must preserve structural humility:

- do not assume Judge and Aurora are mathematically interchangeable
- do not assume Policy Cortex can already be a hard authority gate
- do not assume existing hybrid mode already provides a Judge runtime hook

## Defensible First Bridge Scope

### Hard boundaries that must remain unchanged in phase 1

- keep trading mode = hybrid_live_data_testnet_exec
- keep neocortex_enforcement_mode = shadow
- keep existing Aurora hard gates fail-closed where they already apply
- keep risk_management and execution_position on testnet
- do not let Judge bypass symbol enabled flags
- do not let Judge bypass regime allowlists
- do not let Judge bypass NRR, readiness, liquidity, objective, or execution gates

### What Judge may do in phase 1

Judge may act only as a bounded conditional confirmer on testnet candidates that already satisfy Aurora structural gates.

Recommended first authority slice:

- same direction as Aurora thresholded side proxy
- symbol already enabled in Aurora config
- regime already allowlisted for that symbol
- no opposite-direction override
- no Aurora-neutral promotion in phase 1
- no disabled-symbol promotion in phase 1
- no blocked-regime promotion in phase 1

### Confidence window for phase 1

Use only the 0.7-0.8 Judge bucket for the first bounded pilot.

Why:

- it is the strongest positive Judge bucket on the current joint table among the higher-confidence actionable ranges
- 0.8-0.9 is already negative on current-window aggregate
- 0.9-1.0 is materially negative and operationally dangerous as an overconfident slice
- 0.6-0.7 is not strong enough to justify authority expansion yet

### What phase 1 must explicitly refuse

- Judge opposite-direction overrides
- Judge-led entry when Aurora is neutral
- Judge-led activation on currently disabled symbols
- Judge-led activation on regimes outside the symbol allowlist
- Policy Cortex UNKNOWN as a hard allow or hard deny rule

## Phase Plan

### Phase A: Runtime observability seam

Add a live-testnet observability seam that records for each Aurora candidate:

- Aurora side
- Judge side
- pillar_sum
- Judge confidence
- Aurora threshold proxy or active threshold
- same-direction / neutral / opposite classification
- symbol enabled flag
- regime allowlisted flag
- final downstream gate outcome

Goal:

- prove bridge custody on live data plus testnet execution without changing authority yet

### Phase B: Shadow-only bridge evaluator in the live path

Add a Judge bridge evaluator that runs inside the live decision flow but returns diagnostics only.

Outputs should include:

- bridge posture = same_direction_confirm / aurora_neutral / opposite_conflict / blocked_by_symbol / blocked_by_regime / blocked_by_hard_gate
- pilot eligibility boolean
- bridge reason codes

Goal:

- prove that the bridge logic is stable before any authority is granted

### Phase C: Same-direction-only testnet pilot

Only after phase B stability is proven:

- allow Judge to tag a candidate as pilot-eligible only in 0.7-0.8
- keep Aurora as the structural owner of entry generation
- let Judge affect only a bounded pilot action such as confirm-or-decline on testnet within already-eligible Aurora candidates

Goal:

- test whether Judge adds value as a confirmer without letting it create a new trade universe

### Phase D: Evaluate Aurora-neutral and regime-expansion paths separately

Only after phase C has evidence:

- evaluate Aurora-neutral plus Judge-positive rows as a separate research package
- evaluate disabled-symbol or regime-expansion ideas as a separate research package

These must not be mixed into the first bridge pilot.

## Minimal Code Package For The Bridge

The smallest defensible implementation package is:

1. emit a live-path bridge observability payload in Aurora decision flow
2. add a Judge bridge evaluator that consumes existing Judge outputs or an equivalent live Judge inference surface
3. keep the evaluator shadow-only first
4. add a narrow testnet pilot flag for same-direction 0.7-0.8 only

What this package is not:

- not a global Judge authority rollout
- not a symbol-enable expansion package
- not a regime allowlist expansion package
- not a replacement for Aurora scoring

## Operational Recommendation Right Now

- build the bridge as a same-direction confirmer inside the existing hybrid_live_data_testnet_exec operating mode
- do not let Judge author new trade directions in phase 1
- do not let Policy Cortex UNKNOWN decide phase 1 actions
- use the new joint calibration report as the guardrail baseline before any bridge code is merged
