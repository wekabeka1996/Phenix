# Kelly / TradeIntent Post-Acceptance Hygiene Report

## Scope

This package is a post-acceptance hygiene pass after the accepted Kelly / TradeIntent provenance repair.

Boundaries preserved:

- no runtime behavior change
- no Kelly math change
- no execution_position cleanup ownership work
- no historical WAL rewrite

## Cutover Boundary Recording Decision

The cutover boundary for trusted Kelly provenance should be recorded in two places:

1. docs/problem/decision_making_kelly_tradeintent_provenance_acceptance_reaudit_2026-04-25.md
2. apps/reference/domains/neocortex/docs/ARCHITECTURE.md

Reasoning:

- the acceptance re-audit report is the audit authority that already owns the pre-cutover trust warning
- the Neocortex architecture doc is the consumer-facing WAL -> dataset surface for ML/RL ingestion
- config passports were intentionally not chosen as the cutover source of truth because they describe YAML/config semantics, not runtime WAL provenance

## Files Inspected

- Copilot_Master_Roadmap.md
- docs/problem/decision_making_kelly_tradeintent_provenance_acceptance_reaudit_2026-04-25.md
- apps/reference/domains/neocortex/docs/ARCHITECTURE.md
- apps/reference/domains/neocortex/docs/API_DEPENDENCIES.md
- apps/reference/domains/neocortex/docs/NEOCORTEX_DOMAIN_CONCEPT.md
- apps/reference/domains/neocortex/docs/NEOCORTEX_DOMAIN_IMPLEMENTATION_PLAN.md
- apps/reference/domains/neocortex/docs/JOURNAL_R2_ppo_training.md
- apps/reference/domains/neocortex/docs/README.md
- apps/reference/domains/neocortex/docs/TESTING.md
- config/docs/Gemini/domains_passport_gemini.md
- config/docs/domains_passport.md
- config/docs/aurora_math_passport.md
- tests/domains/execution_position/test_trade_intent_open_intake.py
- tests/integration/test_decision_to_execution_flow.py
- tests/integration/test_ep01_2_entry_plan.py
- tests/integration/test_ep01_3_pending_entry_ttl.py
- tests/integration/test_ep01_4_tif_plumbing.py
- tests/contracts/test_aurora_tpsl_owner_ctx_schema_additive.py

## Files Changed

- docs/problem/decision_making_kelly_tradeintent_provenance_acceptance_reaudit_2026-04-25.md
- apps/reference/domains/neocortex/docs/ARCHITECTURE.md
- apps/reference/domains/neocortex/docs/NEOCORTEX_DOMAIN_IMPLEMENTATION_PLAN.md
- tests/domains/execution_position/test_trade_intent_open_intake.py
- tests/integration/test_decision_to_execution_flow.py

## What Changed

### 1. Provenance note for ML/RL consumers

- acceptance re-audit report now explicitly states where the cutover boundary should be recorded
- Neocortex architecture now carries a dataset-ingest note that pre-cutover `p`, `payoff_ratio_r`, and `size.kelly_fraction` from `EVT:TRADE_INTENT_PROPOSED` are untrusted for ML/RL training

### 2. Stale Neocortex sample cleanup

- the stale `kelly_fraction: "0.10"` example in Neocortex implementation docs was updated to `0.1666666666666666666666666667`
- the same section now states that pre-cutover WAL Kelly fields are untrusted training labels and that `kelly_alpha` / `uplift_factor` remain intentionally unapplied on the TradeIntent provenance seam

### 3. Residual test classification

| File | Classification | Action |
|---|---|---|
| tests/domains/execution_position/test_trade_intent_open_intake.py | stale current-truth example | updated sample constants to current accepted values because this is an active execution-boundary test and the Kelly fields are ignored by the intake seam |
| tests/integration/test_decision_to_execution_flow.py | historical fixture | left synthetic values in place and added a clarifying comment that they are payload-shape placeholders, not current Aurora Kelly truth |
| tests/integration/test_ep01_4_tif_plumbing.py | schema placeholder, acceptable | unchanged |
| tests/integration/test_ep01_3_pending_entry_ttl.py | schema placeholder, acceptable | unchanged |
| tests/integration/test_ep01_2_entry_plan.py | schema placeholder, acceptable | unchanged |
| tests/contracts/test_aurora_tpsl_owner_ctx_schema_additive.py | schema placeholder, acceptable | unchanged |

## What Was Intentionally Not Changed

- runtime Kelly resolution in apps/reference/domains/decision_making/intent/builder_validators.py
- runtime intent assembly in apps/reference/domains/decision_making/intent/builder.py and payload_assembler.py
- execution_position cleanup ownership work
- historical WAL contents under ops/wal/
- schema-placeholder tests whose purpose is contract acceptance rather than current decision_making truth
- config passports as a storage location for WAL cutover provenance
- `kelly_alpha` and `uplift_factor` semantics on the TradeIntent provenance seam

## Validation Output

```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\user\Music\Phenix
configfile: pytest.ini
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 9 items

tests\domains\execution_position\test_trade_intent_open_intake.py ...... [ 66%]
..                                                                       [ 88%]
tests\integration\test_decision_to_execution_flow.py .                   [100%]

============================== 9 passed in 2.08s ==============================
```

## Remaining Residuals

- Historical WAL rows before the Kelly provenance repair remain polluted and still require quarantine or explicit trust labeling for ML/RL use.
- The exact production cutover timestamp / first trusted WAL boundary is still not filled in with a concrete deployment marker.
- Some schema-placeholder tests still use generic Kelly values that are not current Aurora truth by design; this is acceptable as long as they are not cited as runtime provenance evidence.
- The runtime seam still intentionally leaves `kelly_alpha` and `uplift_factor` unapplied.

## Outcome

This hygiene pass improved audit clarity and ML/RL provenance guidance without changing runtime behavior.
