# Kelly / TradeIntent Provenance Acceptance Re-Audit

## Verdict

ACCEPTED_WITH_RESIDUALS

The repaired decision_making intent boundary is acceptable, behavior-bounded, and contract-safe for current runtime use.

The verdict is not plain ACCEPTED because three non-blocking residuals remain outside the repaired hot path:

- historical WAL rows emitted before the repair still contain synthetic Kelly provenance
- several unrelated tests still encode old sample payload constants and therefore are not trustworthy examples of current decision_making truth
- at least one ancillary doc example outside the audited boundary still shows stale Kelly sample data

These residuals do not falsify the repaired runtime behavior, but they do matter for audit hygiene, documentation hygiene, and ML/RL data consumers.

## FACTS

- Current runtime source in apps/reference/domains/decision_making/intent/builder_validators.py no longer defines or uses resolve_kelly_fraction. It now resolves Kelly metadata through resolve_kelly_metadata.
- Current runtime source in apps/reference/domains/decision_making/intent/builder.py calls resolve_kelly_metadata inside a fail-closed try/except block and returns early on ValueError after logging and recording blocked state.
- Current runtime source in apps/reference/domains/decision_making/intent/payload_assembler.py no longer hardcodes p or payoff_ratio_r. Both are caller-supplied, and trace.kelly_provenance is added only as additive trace metadata.
- Current typed config model in apps/reference/config/shared/atoms.py defines KellyConfig with base_probability, kelly_cap, kelly_alpha, payoff_ratio_r, p_min, p_max, and uplift_factor. It does not define fraction.
- Current live Aurora SSOT in config/aurora/strategies/aurora.yaml defines:
  - base_probability = 0.5
  - payoff_ratio_r = 1.5
  - p_min = 0.45
  - p_max = 0.65
  - kelly_cap = 0.25
  - kelly_alpha = 0.8
  - uplift_factor = 0.2
- Current trade intent schema in apps/reference/domains/decision_making/intent/schemas/trade_intent_v1.json still requires p, payoff_ratio_r, and size.kelly_fraction, and allows top-level trace as object|null with additionalProperties: true.
- Current routing envelope in apps/reference/contracts/trade_intent_envelope.py is extra="ignore" and owns only routing fields.
- Current typed execution intake in apps/reference/domains/execution_position/trade_intent_open_intake.py accepts the intent payload but does not model or forward p, payoff_ratio_r, or kelly_fraction into CMD:OPEN.
- Exact Kelly-targeted git diff shows the intended local repair and no new Kelly redesign surface. The changed runtime surfaces are limited to builder_validators.py, builder.py, payload_assembler.py, and the corresponding tests/docs.

### Direct Live-Config Probe

A live ConfigLoader + IntentBuilder probe was run against the current workspace state.

Observed facts from that probe:

- loaded config.strategies.aurora.decision.kelly has no fraction attribute
- its model class has no fraction field
- resolve_kelly_metadata returned:
  - p = 0.5
  - payoff_ratio_r = 1.5
  - kelly_fraction = 0.1666666666666666666666666667
- provenance.source_path = config.strategies.aurora.decision.kelly
- provenance records kelly_alpha and uplift_factor as unapplied_config_fields rather than silently applying them
- the WAL-facing TradeIntent payload captured from patched wal.append emitted:
  - p = 0.5
  - payoff_ratio_r = 1.5
  - size.kelly_fraction = 0.1666666666666666666666666667
  - trace.kelly_provenance populated with source path, formula, p bounds, payoff_ratio_r, cap, and unapplied fields

### Direct Execution Intake Probe

A direct parse_trade_intent_open_intake probe was run with a payload containing:

- p = 0.5
- payoff_ratio_r = 1.5
- size.kelly_fraction = 0.1666666666666666666666666667
- trace.kelly_provenance present

Observed facts from the resulting CMD:OPEN payload:

- contains_p = false
- contains_payoff_ratio_r = false
- contains_kelly_fraction_top_level = false
- contains_trace = false
- CMD:OPEN keys are limited to order, symbol, strategy, regime, stop/target, valid_for_ms, and metadata fields already owned by the execution intake seam

### Residual Pattern Classification

- Current audited runtime source files contain no remaining hot-path matches for:
  - hardcoded p = 0.75
  - hardcoded payoff_ratio_r = 2.0
  - silent kelly_fraction = 0.1 fallback
  - decision.kelly.fraction hot-path reads
  - resolve_kelly_fraction usage
- Residual old-signature hits do remain in unrelated test samples, for example:
  - tests/integration/test_ep01_4_tif_plumbing.py
  - tests/integration/test_ep01_3_pending_entry_ttl.py
  - tests/contracts/test_aurora_tpsl_owner_ctx_schema_additive.py
  - tests/domains/execution_position/test_trade_intent_open_intake.py
- These remaining test hits are schema or intake sample payloads, not current decision_making runtime producers.
- Residual old-signature hits also remain in historical forensic documentation, which is expected because those files describe the pre-repair defect.
- An ancillary doc example remains stale in apps/reference/domains/neocortex/docs/NEOCORTEX_DOMAIN_IMPLEMENTATION_PLAN.md where size.kelly_fraction is still shown as 0.10.
- Archived historical WAL still contains many TRADE_INTENT_PROPOSED rows with p = 0.75, payoff_ratio_r = 2.0, and size.kelly_fraction = 0.1. Example rows were re-confirmed in ops/wal/2026-04-20.jsonl.

## INFERENCES

- The repair is root-local and did not broaden into sizing redesign, risk management redesign, objective engine redesign, or execution_position redesign.
- Future WAL provenance is now truthful for the audited Kelly fields because the emitted payload is sourced from live typed config and the provenance block records the exact boundary formula and source path.
- Execution behavior impact is bounded to metadata/provenance because execution_position routing and typed intake do not consume the repaired Kelly fields.
- The current repair is fail-closed where the old implementation was synthetic and permissive. Invalid or incomplete Kelly config now blocks intent emission instead of silently serializing 0.1.
- Regression protection exists where it matters: current targeted tests would fail if the old synthetic reader, hardcoded literals, or legacy fraction masking were reintroduced into the audited boundary.

## ASSUMPTIONS

- config/aurora/strategies/aurora.yaml remains authoritative SSOT for the current live Aurora strategy family.
- No unseen downstream consumer outside the audited execution_position path has started treating trace.kelly_provenance as execution-authoritative.
- The acceptance target is the current checked-out workspace state, not already-archived WAL data.

## UNKNOWNS

- The exact deployment cutover timestamp after which all newly written WAL rows became truthful is not encoded in the repo state inspected here.
- Whether every external analytics consumer already versions or masks pre-repair Kelly metadata is unknown.
- Whether the stale sample payloads in unrelated tests/docs are intentionally frozen legacy fixtures or accidental drift is unknown.

## Old vs New Provenance Map

| Field | Old provenance | New provenance | Acceptance status |
|---|---|---|---|
| p | Hardcoded literal 0.75 in payload assembly | decision.kelly.base_probability, clamped to [0,1] then to [p_min, p_max] in resolve_kelly_metadata | truthful |
| payoff_ratio_r | Hardcoded literal 2.0 in payload assembly | decision.kelly.payoff_ratio_r from typed config | truthful |
| size.kelly_fraction | Non-SSOT decision.kelly.fraction read with silent 0.1 fallback | min(full_kelly, kelly_cap), where full_kelly = p - (1 - p) / payoff_ratio_r | truthful and fail-closed |
| trace.kelly_provenance | absent | additive trace metadata with source path, p bounds, payoff_ratio_r, formula, cap, and unapplied fields | truthful additive seam |

## Formula and Bounds Verification

The current boundary formula is:

full_kelly = p - (1 - p) / payoff_ratio_r

The current boundary steps are:

1. Read decision.kelly.base_probability.
2. Clamp to [0, 1].
3. Clamp again to [p_min, p_max].
4. Read payoff_ratio_r.
5. Reject if payoff_ratio_r <= 0.
6. Reject if p_min > p_max.
7. Reject if kelly_cap < 0.
8. Compute full_kelly.
9. Reject if full_kelly < 0.
10. Emit kelly_fraction = min(full_kelly, kelly_cap).

Verified live-Aurora values:

- p raw = 0.5
- p bounded = 0.5
- payoff_ratio_r = 1.5
- full_kelly = 0.1666666666666666666666666667
- kelly_cap = 0.25
- emitted kelly_fraction = 0.1666666666666666666666666667

Interpretation of kelly_cap on the audited boundary:

- It acts as a hard upper cap on the computed full Kelly fraction.
- It is not currently applied as a fractional-Kelly multiplier.

Interpretation of kelly_alpha and uplift_factor on the audited boundary:

- They remain unresolved config debt for this seam.
- They are explicitly preserved in provenance as unapplied_config_fields.
- This is acceptable for the audited repair because silently applying them would have been an unproven behavior change.

## Schema / Trace Safety Verification

- trade_intent_v1 already permits top-level trace as object|null with additionalProperties: true.
- trace.kelly_provenance therefore fits the existing additive schema contract and does not require a schema migration.
- tests/bootstrap/test_schema_registry_activation.py now validates a trade intent payload containing trace.kelly_provenance.
- The routing envelope in apps/reference/contracts/trade_intent_envelope.py is intentionally extra="ignore" and therefore does not become coupled to the new trace payload.
- The typed execution intake in apps/reference/domains/execution_position/trade_intent_open_intake.py keeps extra="ignore" semantics and continues to normalize only the execution-owned open-intake seam.

## Execution Behavior Impact

Observed execution-boundary effect:

- decision_making now emits truthful Kelly metadata and additive trace provenance
- execution_position routing and typed open intake continue to ignore those Kelly fields for behavior

Bounded impact statement:

- The repair changes boundary metadata truth, WAL truth, and trace diagnostics.
- The repair does not change the fields that the audited execution open-intake path uses to construct CMD:OPEN.
- The repair therefore has bounded downstream execution impact on the audited seam.

## Tests Run With Exact Output

Kelly / decision_making slice:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\user\Music\Phenix
configfile: pytest.ini
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 27 items

tests\domains\decision_making\test_intent_builder_validators.py ........ [ 29%]
..                                                                       [ 37%]
tests\domains\decision_making\test_intent_builder_payload_contract.py .. [ 44%]
                                                                         [ 44%]
tests\domains\decision_making\test_intent_builder_reservation_cleanup.py . [ 48%]
..                                                                       [ 55%]
tests\unit\llm\test_llm_intent_builder_contract.py .....                 [ 74%]
tests\unit\decision_making\test_fail_closed_config.py .......            [100%]

============================= 27 passed in 1.16s ==============================
```

Schema / execution slice:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\user\Music\Phenix
configfile: pytest.ini
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 27 items

tests\bootstrap\test_schema_registry_activation.py ............          [ 44%]
tests\domains\execution_position\test_intent_boundary_audit.py .......   [ 70%]
tests\domains\execution_position\test_trade_intent_open_intake.py ...... [ 92%]
..                                                                       [100%]

============================= 27 passed in 6.76s ==============================
```

What these tests materially prove:

- test_intent_builder_validators.py guards against reintroducing legacy decision.kelly.fraction reads and proves the loaded real Aurora config has no fraction field
- test_intent_builder_payload_contract.py guards against reintroducing hardcoded p and payoff_ratio_r and guards additive trace.kelly_provenance
- test_fail_closed_config.py passed in the same audited run, confirming the repair does not break the current fail-closed expectation set
- test_schema_registry_activation.py proves the schema accepts the additive trace.kelly_provenance payload
- test_trade_intent_open_intake.py and test_intent_boundary_audit.py prove the execution boundary still routes and normalizes correctly

## Remaining Risks

- Historical WAL rows emitted before the repair remain semantically polluted for Kelly provenance.
- Unrelated stale test fixtures with old sample constants can mislead future auditors if treated as current runtime truth.
- At least one ancillary doc example remains stale and could mislead future documentation readers.
- kelly_alpha and uplift_factor semantics remain unresolved config debt. This is currently bounded because they are explicit and unapplied, not silently interpreted.

## Docs / Passports Update Judgment

Blocking acceptance updates:

- none found beyond the already-updated decision_making EVENTS.md boundary doc

Non-blocking follow-up updates recommended:

- refresh stale sample payloads in unrelated tests if they are meant to reflect current decision_making truth rather than generic schema placeholders
- refresh stale ancillary doc examples such as apps/reference/domains/neocortex/docs/NEOCORTEX_DOMAIN_IMPLEMENTATION_PLAN.md if that document is expected to mirror the live trade intent payload

Passport judgment:

- no additional passport update is required for this repair to be accepted on the audited hot path
- if any external passport or runbook reproduces sample TradeIntent Kelly values as authoritative examples, it should be synchronized with the repaired boundary semantics in a separate cleanup task

Cutover recording judgment:

- the authoritative cutover boundary should be recorded in this acceptance re-audit report because it is the audit artifact that already owns the pre-cutover trust warning
- the same cutover boundary should be mirrored in apps/reference/domains/neocortex/docs/ARCHITECTURE.md next to the WAL -> dataset guidance used by ML/RL consumers
- config passports are intentionally not the cutover source of truth because they describe SSOT YAML/config semantics, not runtime WAL provenance

## Historical WAL Judgment For ML / RL Consumers

Historical WAL should be quarantined or at minimum explicitly labeled for any ML/RL or analytics consumer that uses p, payoff_ratio_r, or size.kelly_fraction from EVT:TRADE_INTENT_PROPOSED.

Reason:

- archived rows were re-confirmed to contain synthetic Kelly metadata unrelated to current SSOT provenance
- those rows are suitable as historical operational artifacts, but not as truthful Kelly-supervised labels

Recommended handling:

1. Record the exact cutover boundary in this report as a deployment timestamp, commit/deploy identifier, or first trusted WAL file/offset.
2. Mirror the same boundary in apps/reference/domains/neocortex/docs/ARCHITECTURE.md so WAL -> dataset builders have a consumer-facing provenance anchor.
3. Treat all pre-cutover TradeIntent Kelly metadata as untrusted for training.
4. Either quarantine pre-cutover rows from training or attach a provenance-trust label so the fields are masked or down-weighted.

## Final Acceptance Judgment

The repaired Kelly / TradeIntent provenance boundary satisfies the requested acceptance bar for current runtime operation.

- No audited runtime hot-path synthetic Kelly constants remain.
- No audited non-SSOT decision.kelly.fraction read remains.
- No silent 0.1 fallback remains on the audited boundary.
- Future WAL provenance is truthful on the audited boundary.
- Execution behavior impact is explicitly proven to be bounded.
- Current targeted tests fail the acceptance bar if old synthetic boundary behavior is reintroduced.

Acceptance is therefore granted with residual hygiene follow-up only, not with a runtime correctness blocker.
