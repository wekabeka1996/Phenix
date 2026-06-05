# Execution Position — Integrated Remediation Plan After Cross-Model Review

Status: planning artifact  
Scope: read-only audit synthesis; no code changes yet  
Target domain: `execution_position`

## Verdict

The remediation work must not start with broad cleanup. It must start with money-impacting runtime safety defects and contract closure.

The best base plan is the four-phase plan that begins with Foundation & Contracts, then Risk & Execution Safety, then State & Consistency, then Async/Telemetry. The schema-dedup/dead-code plan is useful but belongs after runtime safety stabilization.

## Rejected as first work

Do not start with:
- schema deduplication;
- broad bridge refactor;
- deleting dead code;
- large typing conversion;
- base classes for all guardian bridges;
- generic cleanup for aesthetics.

These are maintenance improvements, not first safety closures.

## Accepted first-order defect classes

1. Contract/registry drift for action-bearing events and commands.
2. Open-intake `extra="ignore"` contract hole.
3. Missing instrument config fallback to generic constants.
4. Bracket partial-success race and duplicate SL/TP risk.
5. Watchdog duplicate partial-fill emission.
6. `_closing_position` lifecycle cleanup risk.
7. Size-blind exposure flip semantics.
8. Pending bracket WAL corrupt-row silent skip.
9. Async DEC/WAL without terminal outcome if event loop is unavailable.
10. Cleanup loop swallowing cancellation.
11. Adapter mode/credentials fallback into `testnet` or `shadow_mode`.
12. Sidecar action-bearing mode contract visibility.

## Final implementation order

### Package 0 — Contract Registry Closure

Goal:
- Synchronize source, schemas, domain dictionary, and verb registry for already-existing action-bearing surfaces.

Must include:
- `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`
- `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE`
- `EVT:BRACKET_PLACEMENT_FAILED`
- external-open request surfaces if source/domain_dict/registry disagree

Validation:
- registry/domain_dict/schema presence test
- no new unregistered emitted command/event in `execution_position`

### Package 1 — Ingress and Config Fail-Closed

Goal:
- Close unsafe ingress/config fallbacks before touching executor behavior.

Must include:
- `TradeIntentOpenIntake.extra = forbid`
- `TradeIntentOpenOrder.extra = forbid`
- numeric Decimal validator accepting valid scientific notation
- missing `config.instruments.<symbol>` fail-closed, no generic contract constants as active fallback
- adapter mode cannot silently fallback to `testnet` or `shadow_mode` in live-like modes
- idempotent key policy: explicit key or explicit reject

Validation:
- typoed payload field rejected
- `qty="1E-7"` accepted if semantically valid
- missing instrument symbol raises config error
- live/hybrid missing credentials fail fast
- no exchange call without idempotent key where required

### Package 2 — Execution Safety Guardrails

Goal:
- Prevent duplicate protective orders, ghost executions, and stuck close state.

Must include:
- `BracketManager.place_brackets_parallel()` handles partial success explicitly
- retry only failed side or rollback successful sibling before fallback
- watchdog emits partial-fill delta only, not repeated cumulative fills
- `_closing_position` clears under all failure/early-return paths
- `_cleanup_loop()` re-raises or breaks on `asyncio.CancelledError`
- no-loop DEC scheduling emits terminal failure/reject, not only WAL decision

Validation:
- SL success + TP timeout does not create duplicate SL/TP
- repeated `PARTIALLY_FILLED` same cumulative qty emits no duplicate trade execution
- close build failure clears close-in-progress flag
- cancelled cleanup task terminates
- adapter-present/no-loop path records terminal failure

### Package 3 — Exposure and Risk Math

Goal:
- Make exposure checks size-aware and Decimal-safe.

Must include:
- flip semantics based on net notional/qty, not only side
- tiny opposite-side order cannot free full existing exposure
- directional margin after subtraction clamped at zero
- remove float conversion from notional/margin comparisons
- soft clip either computes true max allowed notional or is renamed/documented as hard clamp

Validation:
- tiny SELL against huge LONG does not bypass limits
- large flip still blocked if directional ratio exceeds max
- Decimal-only tests for shadow_notional/portfolio_notional
- soft clip returns mathematically allowed partial qty or explicit zero-clamp reason

### Package 4 — State, Restore, and Fill Identity

Goal:
- Remove silent state corruption and partial-fill amnesia.

Must include:
- `pending_brackets_wal.py` corrupt row becomes explicit degraded restore/fail-fast signal
- `OrderGuardian` symbol discovery through explicit store protocol, no private `_data` fallback
- `PARTIALLY_FILLED` does not pop pending entry metadata
- fill dedupe without `tradeId` includes quantity/timestamp/cumulative proof
- restore state mutation is explicitly marked/sanctioned as restore-apply, not normal transition

Validation:
- corrupt WAL startup test
- guardian works on in-memory and ledger-backed store
- two partial fills without tradeId are not collapsed incorrectly
- restore apply preserves exact-vs-unknown semantics

### Package 5 — Sidecar Action-Bearing Contract

Goal:
- Make sidecar `enable` mode truthful, bounded, and contract-visible.

Must include:
- registry/schema/domain_dict closure for sidecar close request
- explicit tests for `disable`, `shadow`, `enable`
- no close request during close-in-progress
- duplicate recommendation/close suppression
- stale features/regime/portfolio fail closed or suppress
- action-bearing behavior documented as not recommendation-only

Validation:
- `shadow` never emits close command
- `enable` emits close only through mediator under valid freshness and ownership
- repeated micro-events do not spam close commands

### Package 6 — Boundary Policy and Typing Hygiene

Goal:
- Reduce decomposition rot after safety is stabilized.

Must include:
- replace direct peer private accesses with FSM delegates or protocols
- close deferred boundary violations
- introduce typed return structures for high-risk dicts
- avoid large broad refactor unless tests exist

Validation:
- AST boundary-policy test
- mypy/pyright for changed surfaces
- no behavior change except documented delegate routing

### Package 7 — Schema Dedup and Dead Code

Goal:
- Maintenance cleanup after critical behavior is protected.

Must include:
- `$ref` shared schema blocks for duplicated snapshots
- remove/mark dormant observability modules
- delete true dead code only after import/call-site proof
- avoid removing shadow-only tools unless intentionally retired

Validation:
- schema validation
- import graph proof
- existing tests unchanged

## First implementation prompt

Start with Package 0 and Package 1 only. Do not touch bracket/risk/sidecar code yet.

Acceptance requires:
- failing regression tests before patch where possible;
- minimal code change;
- explicit validation output;
- AGENT_REPORT with proven facts, files changed, tests run, risks, and unproven areas.
