# CONTRACT AUDIT REPORT — 2026-03-14

## 1. Executive Verdict

**Registry health: 7/10 — FUNCTIONAL BUT INCONSISTENT**

The verb registry (`verb_registry_v1.yaml`) exists and the runtime schema validation pipeline (`VerbSchemaRegistry`) works correctly. However, the registry had drifted significantly from runtime reality:
- 20+ actively emitted contracts were missing from the registry
- 1 broken schema reference (wrong path)
- 1 duplicate entry
- 12+ entries with `owner: unknown`
- 8 orphan schema files on disk unreferenced by registry
- 1 duplicate schema file
- ~12 registry entries for contracts never emitted in current code (ghost/legacy)
- Mixed JSON Schema draft versions (draft-07 vs 2020-12)

Safe mechanical fixes applied in this package brought it to a cleaner state. Major architectural decisions remain documented for future packages.

---

## 2. Registry Sources of Truth Discovered

| # | Source | Location | Role |
|---|--------|----------|------|
| 1 | **Verb Registry (YAML)** | `apps/reference/dictionaries/verb_registry_v1.yaml` | Primary SSOT for bus event/command registration |
| 2 | **VerbSchemaRegistry** | `vfoundation/core/schema_registry.py` | Runtime JSON Schema validator (loads from #1) |
| 3 | **VERB_PAYLOAD_MAP** | `vfoundation/core/payloads.py` | Typed Pydantic payload union (11 pairs) |
| 4 | **NormalizedRejectReasons** | `apps/reference/domains/decision_making/normalized_reject_reasons.py` | 59 NRR codes |
| 5 | **WhyCode (vfoundation)** | `vfoundation/core/why_codes.py` | 49 enum members |
| 6 | **WhyCode (decision_making)** | `apps/reference/domains/decision_making/why_codes.py` | 55 enum members (forked, drifted) |
| 7 | **SchemaRegistry (lifecycle)** | `vfoundation/core/schema_version.py` | Schema version/deprecation tracking |
| 8 | **Op type definition** | `vfoundation/core/protocol.py` | `Literal["ASK","DEC","CMD","EVT","UPD","ERR"]` |

---

## 3. Schema Sources Discovered

**40 event/command JSON schema files** across locations:

| Location | Count | Draft Versions |
|----------|-------|---------------|
| `schemas/` (root) | 16 | Mixed draft-07 / 2020-12 |
| `apps/reference/schemas/` | 2 | 2020-12 |
| `apps/reference/domains/execution_position/schemas/` | 11 | draft-07 |
| `apps/reference/domains/decision_making/schemas/` | 3 | Mixed |
| `apps/reference/domains/feature_engineering/schemas/` | 3 | Mixed |
| `apps/reference/domains/position_tracking/schemas/` | 2 | Mixed |
| `apps/reference/domains/alpha_search/schemas/` | 1 | draft-07 |
| `apps/reference/domains/risk_management/schemas/` | 1 | draft-07 |
| `apps/reference/domains/regime_detector/schemas/` | 1 | draft-07 |

Additionally: 11 config validation schemas in `config/_schemas/` (not event schemas).

---

## 4. Inventory Totals by Status

| Status | Count | Notes |
|--------|-------|-------|
| ACTIVE_CONFIRMED | 36 | Emitted in code + registered + schema (where required) |
| ACTIVE_MISSING_SCHEMA | 32 | Emitted in code + registered, no schema |
| ACTIVE_MISSING_REGISTRY (fixed) | 20 | Were emitted in code but missing from registry — **added in this package** |
| ORPHAN_SCHEMA | 8 | Schema file exists, not referenced by registry |
| ORPHAN_REGISTRY_ENTRY | ~12 | In registry but no emit found in code |
| GHOST_EMIT | 0 | All code-emitted events now have registry entries |
| DUPLICATE_DEFINITION (fixed) | 1 | PROCESS_STRATEGY_BLOCKED — **removed duplicate in this package** |
| NEEDS_MANUAL_DECISION | 6 | See Section 5 |

**Post-fix registry: 87 entries (was 68).**

---

## 5. Critical Mismatches

### 5A. Contracts emitted in code but WERE missing from registry (fixed)

All 20 of these were added to the registry in this package:

| Contract | Owner | Classification |
|----------|-------|---------------|
| EVT:OBJECTIVE_REALIZED_V1 | objective_engine | runtime-critical |
| EVT:QUADRATIC_KERNEL_CRASH | decision_making | observability |
| EVT:FEATURE_DEFER_EXPIRED | decision_making | observability |
| EVT:LIMIT_ORDER_TIMEOUT | execution_position | runtime-critical |
| EVT:FALLBACK_MODE_ENTERED | execution_position | runtime-critical |
| EVT:FALLBACK_MODE_EXITED | execution_position | runtime-critical |
| EVT:EXPOSURE_MISMATCH | execution_position | observability |
| EVT:PENDING_EXPOSURE_EXPIRED | execution_position | observability |
| EVT:MANAGE_SKIPPED | execution_position | observability |
| EVT:PENDING_BRACKETS_STORED | execution_position | observability |
| EVT:PENDING_BRACKETS_CLEARED | execution_position | observability |
| EVT:LLM_INTENT_RECEIVED_V1 | shadow_telemetry | shadow-only |
| EVT:LLM_INTENT_ACCEPTED_V1 | shadow_telemetry | shadow-only |
| EVT:LLM_INTENT_REJECTED_V1 | shadow_telemetry | shadow-only |
| CMD:LLM_INTENT_SUBMIT_V1 | shadow_telemetry | shadow-only |
| EVT:NEOCORTEX_REGIME_PREDICTION | neocortex | shadow-only |
| EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED | neocortex | shadow-only |
| DEC:BATCH | execution_position | runtime-critical |
| ERR:EXECUTION_FAILED | execution_position | runtime-critical |
| ERR:FATAL_CONFIG_MISMATCH | execution_position | runtime-critical |

### 5B. vfoundation-internal events NOT added to registry (intentionally excluded)

These are internal vfoundation infrastructure events. They live below the application bus layer and follow wildcard policies. Adding them to the app-level registry would be misleading:

| Contract | Source | Reason excluded |
|----------|--------|----------------|
| EVT:STATE_TRANSITION | fsm_v2.py | Internal FSM observability |
| EVT:DOMAIN_STATUS | domain_bridge.py | Internal obs |
| EVT:TOPOLOGY_DRIFT_DETECTED | topology_auditor.py | Internal obs |
| EVT:INIT | meta_fsm_v2.py | Bootstrap internal |
| EVT:ENTROPY_SPIKE | meta_fsm_v2.py | Meta FSM internal |
| EVT:STABILIZED | meta_fsm_v2.py | Meta FSM internal |
| EVT:COOLDOWN_ELAPSED | meta_fsm_v2.py | Meta FSM internal |
| EVT:NORMAL_MODE_RESTORED | meta_fsm_v2.py | Meta FSM internal |
| EVT:RECOVERY_SIGNAL | meta_fsm_v2.py | Meta FSM internal |
| EVT:INFLIGHT | routing.py | Routing internal |
| EVT:CANCELLED | exchange/acl.py | ACL internal |
| EVT:DEDUP | exchange/acl.py | ACL internal |
| CMD:SWITCH_TO_LOW_RISK_MODE | meta_fsm_v2.py | Meta FSM internal |
| CMD:FORCE_RECOVER | meta_fsm_v2.py | Meta FSM internal |
| DEC:EVAL | CLI only | CLI tooling only |

### 5C. Registry entries with no matching code emit (orphan/legacy)

| Contract | Owner | Likely Status |
|----------|-------|--------------|
| EVT:EXPIRED | unknown | DEAD — no emit found |
| EVT:FILL | unknown | DEAD — only in VERB_PAYLOAD_MAP, no bus emit |
| EVT:MARKET_TICK_FORWARDED | market_data | DEAD — not implemented (tests skipped) |
| EVT:MR_SIGNAL_PRODUCED | unknown | DEAD — legacy pre-STRATEGY_SIGNAL_PRODUCED |
| EVT:NEOCORTEX_STATE_UPDATED | neocortex | DEAD — no emit found |
| EVT:ORCHESTRATOR_ERROR | unknown | DEAD — no emit found |
| EVT:ORDER_EXECUTED | unknown | DEAD — confused with TRADE_EXECUTED |
| EVT:PARTIAL_FILL | unknown | DEAD — no emit as distinct event |
| EVT:REJECTED | unknown | DEAD — only in VERB_PAYLOAD_MAP |
| EVT:TICK_RECEIVED | decision_making | DEAD — legacy tick-driven path |
| EVT:VERB | unknown | DEAD — appears to be a placeholder |
| DEC:CANCEL | unknown | DEAD — no code evidence |

**Recommendation: mark these DEPRECATED in a future cleanup wave. Do not delete yet.**

### 5D. Orphan schema files (on disk but not in registry)

| Schema File | Notes |
|-------------|-------|
| `schemas/bracket_order_v1.json` | Sub-schema, used internally by execution code |
| `schemas/bracket_error_v1.json` | Sub-schema, used internally |
| `schemas/order_rejected_event_v1.json` | Could be referenced by EVT:ORDER_REJECTED |
| `schemas/order_clipped_event_v1.json` | Observability sub-schema |
| `schemas/features_price_motion_v1.json` | Sub-block of FEATURES_CALCULATED |
| `schemas/portfolio_state_v1.json` | DUPLICATE of position_tracking version |
| `schemas/message_v1.json` | Generic envelope, not verb-specific |
| `apps/reference/schemas/order_logger_v1.json` | WAL/logging schema, not a bus event |

### 5E. WhyCode enum drift

Two independent `WhyCode` enums exist:
- `vfoundation/core/why_codes.py` — 49 members
- `apps/reference/domains/decision_making/why_codes.py` — 55 members (adds SIZING_* and SIGNAL_NEUTRAL)

They have drifted. The decision_making version has 6 extra members and omits NRR codes. **NEEDS_MANUAL_DECISION: unify or explicitly document the fork boundary.**

### 5F. Missing `why` support

No systematic `why` field requirement was found enforced at schema level. Individual schemas include `why` or `nrr` fields but there is no global contract requiring it. This is a **policy gap**, not a code bug.

---

## 6. Safe Fixes Applied

| Fix | Scope |
|-----|-------|
| Fixed broken schema ref: `schemas/order_ack_v1.json` → `apps/reference/schemas/order_ack_v1.json` | verb_registry_v1.yaml |
| Removed duplicate PROCESS_STRATEGY_BLOCKED entry (null-schema version) | verb_registry_v1.yaml |
| Fixed 6 `owner: unknown` entries with code-evidenced owners | verb_registry_v1.yaml |
| Fixed ANCHOR_UPDATED owner: `decision_making` → `market_data` (actual emitter) | verb_registry_v1.yaml |
| Promoted 5 `status: experimental` to `active` where emit evidence is clear | verb_registry_v1.yaml |
| Added 20 missing registry entries for actively emitted contracts | verb_registry_v1.yaml |

---

## 7. Tests Added / Results

**New test file:** `tests/contracts/test_contract_registry_audit.py`

| Test Class | Tests | Validated |
|-----------|-------|-----------|
| TestRegistrySchemaIntegrity | 2 | All schema refs resolve; no dead config namespace in schema paths |
| TestRegistryNoDuplicates | 1 | No duplicate (op, verb) pairs |
| TestFailClosedPolicies | 3 | CMD/DEC/ERR wildcard remain fail-closed |
| TestCoreContractsRegistered | 16 | All 16 core pipeline contracts present |
| TestSchemaRequiredContracts | 6 | Critical contracts have schemas on disk |
| **Total** | **28** | **28 passed, 0 failed** |

Existing tests also verified:
- `tests/ops/test_verb_registry_contracts.py` — 7 tests (pre-existing, still green)

---

## 8. Risks and Next Package Recommendations

### Immediate risks
1. **12 orphan registry entries** — dead contracts still in registry mislead consumers and agents. Recommend marking DEPRECATED in next wave.
2. **8 orphan schema files** — 1 is a duplicate (`portfolio_state_v1.json`). Recommend dedup and deciding on sub-schema registration.
3. **WhyCode fork** — two drifted enums create confusion. Needs explicit unification or boundary contract.
4. **Mixed JSON Schema drafts** — no runtime issue (jsonschema lib handles both) but inconsistency makes generation/validation tooling harder. Low priority.

### Recommended next steps
1. **Wave 1: Mark orphan registry entries DEPRECATED** — add `status: deprecated` to the 12 dead contracts
2. **Wave 2: Deduplicate schemas** — remove root `schemas/portfolio_state_v1.json` duplicate
3. **Wave 3: WhyCode unification** — decide if decision_making WhyCode should extend vfoundation's or declare independent surface
4. **Wave 4: Schema coverage push** — add schemas for high-traffic active contracts still at `schema: null` (ORDER_REJECTED, ORDER_STATE_CHANGED, ACCOUNT_UPDATE_RECEIVED)
5. **Wave 5: vfoundation event registration policy** — decide whether internal meta-FSM/routing events should be registered at all

---

## Appendix: Runtime Criticality Classification

### Runtime-Critical (pipeline breaks without these)
EVT:MARKET_TICK_RECEIVED, EVT:BAR_CLOSED, EVT:FEATURES_CALCULATED, EVT:REGIME_DETECTED, EVT:RISK_ASSESSMENT_COMPLETED, CMD:PROCESS_STRATEGY, EVT:STRATEGY_SIGNAL_PRODUCED, EVT:TRADE_INTENT_PROPOSED, EVT:TRADE_INTENT_REJECTED, CMD:OPEN, CMD:CLOSE, DEC:OPEN, DEC:CLOSE, EVT:ORDER_PLACED, EVT:TRADE_EXECUTED, EVT:PORTFOLIO_STATE_UPDATED, EVT:EXPOSURE_SUMMARY_UPDATED, EVT:ORDER_REJECTED, EVT:ORDER_STATE_CHANGED, EVT:SYSTEM_STRESS_STATE_UPDATED, ERR:OPEN, ERR:EXECUTION_FAILED, ERR:FATAL_CONFIG_MISMATCH, EVT:HTF_BARS_IMPORTED, EVT:ACCOUNT_UPDATE_RECEIVED, EVT:BALANCE_UPDATE_RECEIVED

### Observability-Only (monitoring, logging, telemetry — no pipeline impact)
EVT:DECISION_TRACE_EMITTED, EVT:DECISION_BLOCKED, EVT:STRATEGY_DECISION_BLOCKED, EVT:PROCESS_STRATEGY_BLOCKED, EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE, EVT:EXECUTION_GUARD_BLOCKED, EVT:EXECUTION_DIVERGENCE_DETECTED, EVT:EXIT_MATCH_ATTEMPTED, EVT:EXIT_MATCH_FAILED, EVT:EXECUTION_TIDY_PERFORMED, EVT:EXECUTION_CLOSE_RECONCILED, EVT:SYMBOL_TIDY, EVT:EXPOSURE_MISMATCH, EVT:PENDING_EXPOSURE_EXPIRED, EVT:MANAGE_SKIPPED, EVT:PENDING_BRACKETS_STORED, EVT:PENDING_BRACKETS_CLEARED, EVT:QUADRATIC_KERNEL_CRASH, EVT:REGIME_SHIFT_SUSPECTED, EVT:FEATURE_DEFER_EXPIRED, EVT:OBJECTIVE_REALIZED_V1, EVT:INTENT_DEFERRED, EVT:INTENT_DROPPED, EVT:ORDER_TIMEOUT, EVT:LIMIT_ORDER_TIMEOUT, EVT:FALLBACK_MODE_ENTERED, EVT:FALLBACK_MODE_EXITED, EVT:ORDER_ACK, EVT:ORDER_FILL, EVT:ALPHA_SCORE_CALCULATED

### Shadow/Experimental Only
EVT:LLM_INTENT_RECEIVED_V1, EVT:LLM_INTENT_ACCEPTED_V1, EVT:LLM_INTENT_REJECTED_V1, CMD:LLM_INTENT_SUBMIT_V1, EVT:NEOCORTEX_REGIME_PREDICTION, EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED, EVT:NEOCORTEX_SHADOW_INTENT, EVT:NEOCORTEX_ALERT

### Backtest-Only
EVT:FUNDING_UPDATE (listener exists, no runtime emitter), EVT:OI_UPDATE (same)

### Deprecated/Legacy (recommend marking DEPRECATED)
EVT:EXPIRED, EVT:FILL, EVT:MARKET_TICK_FORWARDED, EVT:MR_SIGNAL_PRODUCED, EVT:NEOCORTEX_STATE_UPDATED, EVT:ORCHESTRATOR_ERROR, EVT:ORDER_EXECUTED, EVT:PARTIAL_FILL, EVT:REJECTED, EVT:TICK_RECEIVED, EVT:VERB, DEC:CANCEL
