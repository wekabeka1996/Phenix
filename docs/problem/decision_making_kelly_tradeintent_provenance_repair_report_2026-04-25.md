# TradeIntent Kelly Provenance Repair Report

## Scope

This package repairs Kelly metadata provenance at the decision_making intent boundary with the smallest safe patch.

Non-goals preserved:
- no ML probability estimator
- no live sizing redesign
- no execution_position behavior change
- no WAL rewrite
- no schema migration
- no broad decision_making refactor

## Confirmed Root Cause

Before this patch the active IntentBuilder path emitted schema-required Kelly fields from masked compatibility values instead of truthful strategy config provenance:

- p was hardcoded to 0.75
- payoff_ratio_r was hardcoded to 2.0
- size.kelly_fraction read decision.kelly.fraction if present and silently fell back to 0.1

That behavior polluted new TRADE_INTENT_PROPOSED payloads and WAL rows with non-SSOT metadata unrelated to the loaded Aurora config.

## Code Changed

Changed runtime surfaces:
- apps/reference/domains/decision_making/intent/builder_validators.py
- apps/reference/domains/decision_making/intent/builder.py
- apps/reference/domains/decision_making/intent/payload_assembler.py

Changed tests and docs:
- tests/domains/decision_making/test_intent_builder_validators.py
- tests/domains/decision_making/test_intent_builder_payload_contract.py
- tests/domains/decision_making/test_intent_builder_reservation_cleanup.py
- tests/unit/llm/test_llm_intent_builder_contract.py
- tests/domains/execution_position/test_intent_boundary_audit.py
- tests/bootstrap/test_schema_registry_activation.py
- apps/reference/domains/decision_making/docs/EVENTS.md

## New Runtime Behavior

IntentBuilder now resolves Kelly metadata only from config.strategies.{strategy_id}.decision.kelly.

Resolved fields:
- p
- payoff_ratio_r
- kelly_fraction
- trace.kelly_provenance

Exact formula now used:

1. Start from decision.kelly.base_probability.
2. Clamp to [0, 1].
3. Clamp again to [p_min, p_max].
4. Read payoff_ratio_r from config.
5. Compute full Kelly as:

   kelly_fraction_full = p - (1 - p) / payoff_ratio_r

6. Fail closed if full Kelly is negative.
7. Apply the documented cap:

   kelly_fraction = min(kelly_fraction_full, kelly_cap)

For the live Aurora config inspected in this package:
- p = 0.5
- payoff_ratio_r = 1.5
- kelly_fraction_full = 0.1666666666666666666666666667
- kelly_cap = 0.25
- final kelly_fraction = 0.1666666666666666666666666667

## Why This Is Faithful And Minimal

- It removes the silent fallback and the hardcoded payload values.
- It does not invent a score_01 or probability model on the hot path.
- It uses only semantics already evidenced in config and docs for base_probability, p_min, p_max, payoff_ratio_r, and kelly_cap.
- It carries provenance additively under trace, which the live schema already permits.
- It does not alter execution_position routing, open submission, or downstream sizing behavior.

## Explicitly Unchanged / Unproven

These config fields remain recorded but unapplied in Kelly boundary math because this package did not prove their accepted semantics on the active intent path:
- kelly_alpha
- uplift_factor

Historical WAL rows emitted before this patch remain polluted and were not rewritten.

## Validation

Focused tests passed:
- tests/domains/decision_making/test_intent_builder_validators.py
- tests/domains/decision_making/test_intent_builder_payload_contract.py
- tests/domains/decision_making/test_intent_builder_reservation_cleanup.py
- tests/unit/llm/test_llm_intent_builder_contract.py
- tests/domains/execution_position/test_intent_boundary_audit.py::test_decision_making_trace_intent_crosses_validated_boundary_and_starts_execpos_routing

What these tests prove:
- builder no longer reads legacy decision.kelly.fraction even if injected by a test double
- real loaded Aurora config exposes no fraction field
- emitted payload p/payoff_ratio_r/kelly_fraction now match explicit config-derived values
- missing Kelly config now fails closed instead of falling back to 0.1
- additive trace provenance crosses the validated boundary without changing execution routing

Acceptance-list tests also passed:
- tests/bootstrap/test_schema_registry_activation.py
- tests/integration/test_ep01_4_tif_plumbing.py

One broader exploratory run of the full tests/domains/execution_position/test_intent_boundary_audit.py file exposed an unrelated pre-existing fixture/config issue in execution_position cleanup ownership resolution. The touched downstream boundary test itself passed when run directly.

## Docs / Passport Impact

- Updated apps/reference/domains/decision_making/docs/EVENTS.md to reflect current runtime truth at the intent boundary.
- No passport rewrite was made in this package because the ambiguous kelly_alpha and uplift_factor semantics remain unresolved rather than reinterpreted.
