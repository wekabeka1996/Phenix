# R7A FINAL CLOSURE REPORT

**Package**: R7A-FINAL — Policy Source Schema Alignment and Closure
**Date**: 2026-04-21
**Scope**: One schema seam fix + conformance test + final closure

---

## Problem Framing

The R7A Sidecar Peak-Giveback implementation was found architecturally correct by an independent audit (verdict: `ACCEPTANCE_READY_WITH_NARROW_FIX`). One narrow blocker remained:

The JSON schema for `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST` declared `policy_source` as `const: "position_policy_sidecar"`, but the peak-giveback code path emits `policy_source = "position_policy_sidecar:peak_giveback"`. This was a contract truth gap between the published schema and the actual runtime payload.

---

## FACTS

### F1: Schema before fix (line 45)
```json
"policy_source": { "type": "string", "const": "position_policy_sidecar" }
```
This rejected any value other than the exact string `"position_policy_sidecar"`.

### F2: Schema after fix (line 45)
```json
"policy_source": { "type": "string", "pattern": "^position_policy_sidecar(:[a-z_]+)?$" }
```
This accepts:
- `"position_policy_sidecar"` — original scoring path ✅
- `"position_policy_sidecar:peak_giveback"` — R7A peak-giveback path ✅
- `"position_policy_sidecar:any_future_sub_source"` — extensible ✅
- Rejects `""`, `"random_policy"`, `"position_policy_sidecar:"` (trailing colon, no sub-source), `"roi_policy"` ✅

### F3: Runtime emission unchanged
No runtime code was modified. The sidecar continues to emit:
- `"position_policy_sidecar"` from the scoring close path
- `"position_policy_sidecar:peak_giveback"` from the peak-giveback close path

### F4: Mediator validation unchanged
The mediator at `position_policy_mediator.py:57` continues to use `.startswith("position_policy_sidecar")` which is semantically aligned with the schema pattern.

### F5: Three conformance tests added
| Test | Purpose | Result |
|------|---------|--------|
| `test_close_request_payload_conforms_to_schema_base_source` | Validates original scoring payload against schema | **PASS** |
| `test_close_request_payload_conforms_to_schema_peak_giveback_source` | Validates R7A peak-giveback payload against schema | **PASS** |
| `test_close_request_schema_rejects_invalid_policy_source` | Proves schema rejects `""`, `"random_policy"`, `"position_policy_sidecar:"`, `"roi_policy"` | **PASS** |

### F6: Full focused test suite — 44/44 PASS

```
tests/contracts/test_position_policy_sidecar_contracts.py       5/5 PASSED
  - test_position_policy_sidecar_verbs_are_registered_with_schema_paths
  - test_execution_position_domain_dict_exports_sidecar_events_and_self_imports
  - test_close_request_payload_conforms_to_schema_base_source            [NEW]
  - test_close_request_payload_conforms_to_schema_peak_giveback_source   [NEW]
  - test_close_request_schema_rejects_invalid_policy_source              [NEW]

tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py  3/3 PASSED
tests/domains/execution_position/test_position_policy_sidecar.py               21/21 PASSED
tests/domains/execution_position/test_close_producer_bridge_package6.py         7/7 PASSED
tests/config/test_execution_position_contracts.py                               8/8 PASSED

Total: 44 passed in 2.79s
```

---

## INFERENCES

### I1: Schema and runtime now agree
The pattern `^position_policy_sidecar(:[a-z_]+)?$` precisely matches both emitted `policy_source` values. The contract truth gap is closed.

### I2: The pattern is bounded, not overly permissive
The regex anchors (`^...$`) and the constrained sub-source format (`[a-z_]+`) prevent injection of arbitrary strings. Only `position_policy_sidecar` optionally followed by a colon and a lowercase-underscore sub-source name is accepted.

### I3: No behavioral change occurred
Zero runtime code modified. The schema alignment is purely a contract-truth correction. All existing sidecar behavior is preserved exactly.

---

## ASSUMPTIONS

### A1: No other consumers hard-match on the old `const` constraint
The old `const` was only in the JSON schema file, not in runtime validation code. The mediator uses `.startswith()` which already accepted both values. No downstream consumer is known to perform independent JSON Schema validation at runtime.

---

## UNKNOWNS

### U1: Runtime testnet behavior
The peak-giveback trigger has not been exercised under live market conditions. This is inherent to any pre-deployment state and is not a blocker — it's the purpose of testnet deployment.

---

## Exact Changes Made

### File 1: Schema fix
**File**: `apps/reference/domains/execution_position/schemas/cmd_position_policy_sidecar_close_request_v1.json`
**Line 45**: `const` → `pattern`

```diff
-    "policy_source": { "type": "string", "const": "position_policy_sidecar" },
+    "policy_source": { "type": "string", "pattern": "^position_policy_sidecar(:[a-z_]+)?$" },
```

### File 2: Conformance tests
**File**: `tests/contracts/test_position_policy_sidecar_contracts.py`
**Added**: 3 new tests + helper function `_close_request_payload()`

- `test_close_request_payload_conforms_to_schema_base_source` — positive: base source validates
- `test_close_request_payload_conforms_to_schema_peak_giveback_source` — positive: namespaced source validates
- `test_close_request_schema_rejects_invalid_policy_source` — negative: bad sources rejected

---

## What Was NOT Changed

- ❌ No runtime sidecar logic
- ❌ No config model changes
- ❌ No YAML config changes
- ❌ No mediator changes
- ❌ No trigger math or threshold changes
- ❌ No scoring logic changes
- ❌ No ROI, regime, entry, or XRP/TOCTOU logic
- ❌ No second schema created
- ❌ No parallel provenance fields added

---

## Final Acceptance Verdict

All acceptance criteria met:

| Criterion | Status |
|-----------|--------|
| Schema and runtime payload agree | ✅ Proven by conformance test |
| Conformance test exists and passes | ✅ 3 tests (2 positive, 1 negative) |
| All focused tests pass | ✅ 44/44 |
| No new blocker introduced | ✅ |
| No business logic modified | ✅ |
| No scope widened beyond R7A | ✅ |

---

# `ACCEPTANCE_READY`
