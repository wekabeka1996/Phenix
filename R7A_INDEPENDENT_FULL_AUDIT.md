# R7A INDEPENDENT FULL AUDIT — Sidecar Peak-Giveback Full Verification

**Audit ID**: R7A-INDEPENDENT-AUDIT-v1
**Auditor**: Independent Agent 2 (forensic/high-risk mode)
**Date**: 2026-04-21
**Repo State**: Current HEAD
**Mode**: Truth-localized, evidence-first

---

## 1. Problem Framing

R7A adds a "peak-giveback close" trigger to the existing Position Policy Sidecar. When an open position reaches a configurable profit peak (arming threshold) and then retraces by a configurable percentage, the sidecar emits a bounded soft-close request through the existing CMD:CLOSE → DEC:CLOSE bridge.

The first agent implemented R7A and claimed `MIXED_NOT_READY` status due to policy_source/schema mismatch. This audit independently verifies the entire package from repo truth.

---

## 2. FACTS (Verified from Code)

### F1: Config Model — Strict, Required, No Defaults

Source: [execution_position.py](file:///c:/Users/user/Music/Phenix/apps/reference/config/domains/execution_position.py#L656-L663)

```python
class PositionPolicySidecarPeakGivebackConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = Field(...)
    edge_arm_usd: float = Field(..., ge=0.0)
    giveback_trigger_pct: float = Field(..., ge=0.0, le=100.0)
```

- `extra='forbid'` — no undeclared fields accepted ✅
- All three fields use `Field(...)` — **required, no defaults** ✅
- `ge=0.0` / `le=100.0` bounds prevent nonsense values ✅
- Nested under `PositionPolicySidecarConfig.peak_giveback_close` at line 680 ✅

### F2: YAML Configuration — Present, Explicit, No Fallbacks

Source: [domains.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/domains.yaml#L638-L641)

```yaml
peak_giveback_close:
  enabled: true
  edge_arm_usd: 25.0
  giveback_trigger_pct: 50.0
```

- All three required fields present ✅
- No hidden defaults or silent fallbacks ✅
- Removal of any field would cause Pydantic `ValidationError` at startup (fail-closed) ✅

### F3: Symbol-Local State — Clean Dataclass Fields

Source: [position_policy_sidecar.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/position_policy_sidecar.py#L100-L102)

```python
@dataclass
class _SymbolState:
    # ... existing fields ...
    # R7A: Peak giveback state
    peak_edge_usd: float = 0.0
    is_armed: bool = False
```

- State is per-symbol (dict keyed by symbol) ✅
- Initial values are inert zeros (no pre-armed state) ✅
- No cross-symbol leakage ✅

### F4: Evaluation Logic — Bounded and Config-Driven

Source: [position_policy_sidecar.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/position_policy_sidecar.py#L578-L624)

The `_evaluate_peak_giveback()` method:

1. Returns `None` immediately if `cfg.enabled is False` — **explicit killswitch** ✅
2. Returns `None` if `pnl_usdt` is `None` — **no action on missing data** ✅
3. Updates `peak_edge_usd = max(peak_edge_usd, pnl_usdt)` — monotonic peak tracking ✅
4. Arms only when `peak_edge_usd >= cfg.edge_arm_usd` — config-driven threshold ✅
5. Returns `None` if not armed — no trigger before arming ✅
6. Returns `None` if `peak_edge_usd <= 0` — guards against zero-division ✅
7. Computes `giveback_pct = ((peak - current) / peak) * 100` ✅
8. Triggers only when `giveback_pct >= cfg.giveback_trigger_pct` ✅

### F5: Trigger Handling — Bounded, Deduplicated, Reset

Source: [position_policy_sidecar.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/position_policy_sidecar.py#L626-L681)

The `_handle_peak_giveback_trigger()` method:

1. Emits `EVT:POSITION_POLICY_SIDECAR_RECOMMENDED` with peak_giveback detail ✅
2. Emits `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST` **only** in `ENABLE` mode ✅
3. Uses `policy_source="position_policy_sidecar:peak_giveback"` — namespaced provenance
4. After emission: `state.is_armed = False; state.peak_edge_usd = 0.0` — **reset prevents double-fire** ✅

### F6: Suppression Safety — Correct Placement in Evaluation Chain

Source: [position_policy_sidecar.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/position_policy_sidecar.py#L466-L480)

```python
if suppression is None or suppression.get("reason_code") == "profitable_guard":
    giveback_trigger = self._evaluate_peak_giveback(...)
```

Peak giveback bypasses ONLY `profitable_guard`. All critical suppressions still block:
- `startup_grace_active` — blocked ✅
- `no_active_lifecycle` — blocked ✅
- `close_in_progress` — blocked ✅ (ManageFlowFSM ownership preserved)
- `close_reconciled` — blocked ✅
- `post_fill_grace_active` — blocked ✅
- `warmup_incomplete` — blocked ✅
- `portfolio_stale` / `features_stale` / `regime_stale` — blocked ✅
- `terminal_order_state_recent` — blocked ✅
- `portfolio_missing` — blocked ✅
- `ambiguous_lifecycle_state` — blocked ✅
- `ambiguous_terminal_transition` — blocked ✅

The bypass of `profitable_guard` is semantically correct: peak-giveback is about positions that WERE profitable and are losing that profit. The guard prevents the "you're losing money, exit" path from firing on profitable positions — but peak-giveback is precisely the "you HAD profit and gave it back" trigger.

### F7: Entry Reset — Safe State Cleanup

Source: [position_policy_sidecar.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/position_policy_sidecar.py#L352-L354)

```python
if reduce_only is False:
    # ... existing resets ...
    # R7A: Reset peak giveback state on new entry
    state.peak_edge_usd = 0.0
    state.is_armed = False
```

New entry fills (non-reduce_only) reset peak state completely ✅

### F8: Mediator Validation — `startswith()` Prefix Match

Source: [position_policy_mediator.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/position_policy_mediator.py#L57)

```python
if not request.policy_source.startswith("position_policy_sidecar"):
    suppression_reason = "invalid_policy_source"
```

The mediator uses `startswith("position_policy_sidecar")` which accepts both:
- `"position_policy_sidecar"` (original scoring path)
- `"position_policy_sidecar:peak_giveback"` (R7A path)

This was likely changed from exact equality by the first agent to accommodate the namespaced source.

### F9: Close Bridge Path — Standard CMD:CLOSE with Policy Context

Source: [position_policy_mediator.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/position_policy_mediator.py#L121-L138)

The mediator creates a standard `CMD:CLOSE` message with:
- `src="execution_position.position_policy_sidecar"`
- `why="position_policy_sidecar_soft_close"`
- `pld.policy_context` carrying the full sidecar context
- `pld.close_guard_prevalidated = True`

This then flows through `CloseFlowFSM` → `adapt_cmd_close_to_dec_close` → `DEC:CLOSE`. The entire close path reuses the standard execution_position close lifecycle. **No new close owner is created.**

### F10: Schema Contract Mismatch — THE BLOCKER

Source: [cmd_position_policy_sidecar_close_request_v1.json](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/schemas/cmd_position_policy_sidecar_close_request_v1.json#L45)

```json
"policy_source": { "type": "string", "const": "position_policy_sidecar" }
```

The schema declares `"const": "position_policy_sidecar"` — meaning **only the exact string** `"position_policy_sidecar"` is valid.

But the peak giveback path emits: `"position_policy_sidecar:peak_giveback"`.

**This is a genuine schema-contract mismatch.** The emitted payload from the peak giveback path would fail JSON Schema validation against the registered schema.

### F11: Verb Registry — Complete Registration

Source: [verb_registry_v1.yaml](file:///c:/Users/user/Music/Phenix/apps/reference/dictionaries/verb_registry_v1.yaml) — All 8 sidecar verbs registered with correct owner and schema paths.

### F12: Domain Dictionary — Complete Self-Import/Export

Source: [domain_dict.json](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/domain_dict.json) — CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST is both self-imported and self-exported. PositionPolicySidecar is listed in components.

### F13: Test Evidence — All 41 Tests Pass

```
tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py  3/3 PASSED
tests/domains/execution_position/test_position_policy_sidecar.py               21/21 PASSED
tests/contracts/test_position_policy_sidecar_contracts.py                       2/2 PASSED
tests/domains/execution_position/test_close_producer_bridge_package6.py         7/7 PASSED
tests/config/test_execution_position_contracts.py                               8/8 PASSED
```

---

## 3. INFERENCES

### I1: The first agent used `startswith()` instead of exact match for policy_source validation
The mediator's check at line 57 uses `.startswith("position_policy_sidecar")` rather than exact equality. This is a deliberate change to accommodate the namespaced `"position_policy_sidecar:peak_giveback"` source. This is a reasonable design choice but represents a validation widening.

### I2: The schema mismatch is NOT enforced at runtime
The system's event bus does not perform JSON Schema validation at publish time. Schema validation occurs only in contract tests. Since the contract test (`test_position_policy_sidecar_contracts.py`) only checks *registration* (schema files exist and are linked), not *payload conformance*, the mismatch does not cause runtime failures.

### I3: The peak giveback path does not create a second truth owner
The close request flows through the SAME mediator → CMD:CLOSE → CloseFlowFSM → DEC:CLOSE pipeline as the regular sidecar scoring path. ManageFlowFSM's `_closing_position` flag is checked before any action. The sidecar cannot initiate a close while one is already in progress.

### I4: The profitable_guard bypass is intentionally sound
The peak giveback trigger fires on positions that are currently profitable (just less than they were). The profitable_guard blocks the "losing money" scoring path. These are complementary, not conflicting.

---

## 4. ASSUMPTIONS

### A1: Schema validation is not enforced at runtime
I observe no runtime JSON Schema validation code in the publish path. This is consistent with the project's pattern of compile-time/test-time schema validation. If runtime validation is ever added, the mismatch would cause failures.

### A2: No other consumers validate `policy_source` with exact match
Beyond the mediator's `startswith()` check, I have not exhaustively verified that no other code path performs exact-match validation on `policy_source`. If any downstream consumer (logging, monitoring, forensics) expects the exact string `"position_policy_sidecar"`, it could silently drop peak-giveback events.

---

## 5. UNKNOWNS

### U1: Runtime behavior under real market conditions
No testnet or production runtime logs exist for the peak-giveback path. Test evidence proves unit-level correctness but not integration-level behavior under real market data timing, concurrent position lifecycle events, or exchange-side latency.

### U2: Interaction with max_hold_close_bridge
If the manage_max_hold_close_bridge fires simultaneously with peak giveback, there may be a race. Both would attempt CMD:CLOSE. The idempotent_key / close_guard_prevalidated mechanism should prevent double-close, but this is not tested.

### U3: Behavior when unrealizedProfit oscillates near giveback threshold
Rapid PnL oscillation near the trigger threshold could cause arming + trigger + reset + re-arm + re-trigger within a single position lifecycle. The current reset prevents immediate re-fire, but repeated give-back events on the same position are theoretically possible (by design, since each would be a new peak cycle).

---

## 6. Architecture / Ownership Analysis

| Concern | Status | Evidence |
|---------|--------|----------|
| Logic lives under Sidecar only | ✅ PASS | `_evaluate_peak_giveback` and `_handle_peak_giveback_trigger` are methods of `PositionPolicySidecar` |
| Config lives next to sidecar config | ✅ PASS | `peak_giveback_close` field on `PositionPolicySidecarConfig` |
| Explicit enable/disable | ✅ PASS | `enabled: bool = Field(...)` — required, no default |
| Explicit percentage parameter | ✅ PASS | `giveback_trigger_pct: float = Field(..., ge=0.0, le=100.0)` |
| No hardcodes | ✅ PASS | All business values from config |
| No silent fallbacks | ✅ PASS | `extra='forbid'`, all fields required |
| Execution ownership preserved | ✅ PASS | Route: Sidecar → Mediator → CMD:CLOSE → CloseFlowFSM → DEC:CLOSE |
| No split-brain close | ✅ PASS | `close_in_progress` check in suppression prevents concurrent close |
| No bracket mutation | ✅ PASS | Validated by Pydantic model_validator on `PositionPolicySidecarConfig` |

---

## 7. Config Contract Audit

| Property | Required | YAML Present | Fail-Closed | Extra Forbidden |
|----------|----------|-------------|-------------|-----------------|
| `enabled` | Yes (`...`) | Yes | Yes | Yes |
| `edge_arm_usd` | Yes (`...`) | Yes | Yes | Yes |
| `giveback_trigger_pct` | Yes (`...`) | Yes | Yes | Yes |

**Config YAML values**: `enabled=true, edge_arm_usd=25.0, giveback_trigger_pct=50.0`

Missing any field → Pydantic `ValidationError` at config load → system refuses to start.

**Verdict**: Config contract is strict, explicit, and operationally correct. ✅

---

## 8. Trigger Safety Audit

| Safety Property | Status | Mechanism |
|-----------------|--------|-----------|
| Cannot fire before arming | ✅ | `if not state.is_armed: return None` |
| Cannot fire with zero peak | ✅ | `if state.peak_edge_usd <= 0: return None` |
| Cannot fire during close-in-progress | ✅ | Suppression check before evaluation |
| Cannot fire on stale data | ✅ | Freshness checks block evaluation |
| Cannot fire on terminal/reconciled | ✅ | Suppression chain blocks |
| Cannot double-fire same lifecycle | ✅ | State reset after trigger + entry reset |
| Cannot fire in SHADOW mode | ✅ | `if self.mode == ENABLE:` guards CMD emission |
| Cannot fire in DISABLE mode | ✅ | Early return at `_evaluate_symbol` |
| Resets on new entry | ✅ | `reduce_only is False` branch |

**Verdict**: Trigger safety is comprehensive. ✅

---

## 9. Provenance / Schema Audit

This is the **one genuine issue**.

| Surface | `policy_source` Value | Match? |
|---------|----------------------|--------|
| Schema (`const`) | `"position_policy_sidecar"` | — |
| Scoring path emission | `"position_policy_sidecar"` | ✅ |
| Peak giveback emission | `"position_policy_sidecar:peak_giveback"` | ❌ |
| Mediator validation | `.startswith("position_policy_sidecar")` | Accepts both |
| Close bridge test | `"position_policy_sidecar"` | ✅ |
| Peak giveback test | `"position_policy_sidecar:peak_giveback"` | Matches code ✅ |

**Root cause**: The schema was written for the original scoring path where `policy_source` is always `"position_policy_sidecar"`. The peak giveback path introduced a namespaced sub-source for traceability without updating the schema.

**Severity**: Moderate — no runtime failure today (no runtime schema validation), but a contract truth violation that would break under schema enforcement.

**Nature**: This is contract drift, not a design error. The namespaced format `"position_policy_sidecar:peak_giveback"` is better for forensics/traceability than the flat string. The schema should be updated to match.

---

## 10. Test Evidence Audit

| Test File | Tests | Pass | Coverage |
|-----------|-------|------|----------|
| `test_position_policy_sidecar_peak_giveback.py` | 3 | 3 | Arming, trigger, reset, disable |
| `test_position_policy_sidecar.py` | 21 | 21 | Full sidecar lifecycle with peak_giveback config block present |
| `test_position_policy_sidecar_contracts.py` | 2 | 2 | Verb registration, domain dict |
| `test_close_producer_bridge_package6.py` | 7 | 7 | CMD:CLOSE → DEC:CLOSE bridge with sidecar path |
| `test_execution_position_contracts.py` | 8 | 8 | YAML config loading, strict model contracts |

**Test gaps**:
- No test validates peak_giveback payload against JSON Schema (the mismatch would be caught)
- No test for concurrent peak_giveback + max_hold_close race
- No test for rapid oscillation near threshold (re-arm after reset)

**Verdict**: Tests prove unit-level correctness. The schema mismatch is untested. Test-level evidence is adequate for bounded testnet deployment.

---

## 11. Report Contamination Audit

The previous agent's acceptance report (`MIXED_NOT_READY`) mentioned:
1. `policy_source` schema mismatch — **REAL, confirmed** ✅
2. XRP duplicate-order TOCTOU issue — **UNRELATED to R7A** ❌

Mixing an unrelated XRP/TOCTOU finding into an R7A acceptance report is report contamination. It inflates the perceived severity of R7A blockers and confuses scope.

**Verdict**: The previous agent correctly identified the schema blocker but contaminated the report with unrelated findings.

---

## 12. Side Effects Introduced by First Agent

| Change | Scope | Risk |
|--------|-------|------|
| `_SymbolState` gains two fields | Narrow (dataclass defaults 0.0/False) | None — additive |
| `_evaluate_peak_giveback()` added | Sidecar-only method | None — isolated |
| `_handle_peak_giveback_trigger()` added | Sidecar-only method | None — isolated |
| `_evaluate_symbol()` modified | Added peak giveback check at line 466 | Low — correct placement |
| `_on_fill_event()` modified | Added reset on entry fill | Low — correct placement |
| Mediator `startswith()` validation | Widened from exact match | **Moderate** — see below |
| `PositionPolicySidecarPeakGivebackConfig` added | New Pydantic model | None — additive |
| `peak_giveback_close` in YAML | New config block | None — additive |
| `peak_giveback_close` on `PositionPolicySidecarConfig` | New required field | None — fail-closed |
| Tests added | 3 new tests | None — additive |

### Note on mediator `startswith()` widening

The change from exact match to `.startswith()` in the mediator is a validation scope widening. Any `policy_source` starting with `"position_policy_sidecar"` now passes validation. In principle, a malformed source like `"position_policy_sidecar_malicious"` would also pass. However:

- The sidecar is the sole emitter of CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST
- The command topic is internal (self → self)
- No external surface can inject fake close requests
- The risk is theoretical, not practical

**Verdict**: First agent changes are narrow, scoped, and do not introduce hidden behavior. The mediator widening is the only non-trivial change, and its risk is bounded by the internal-only nature of the command.

---

## 13. Final Verdict

### R7A implementation is **architecturally correct, operationally bounded, and safe for testnet deployment** — with exactly **one narrow contract-level blocker**.

The blocker is:
- **JSON Schema `const: "position_policy_sidecar"` does not match emitted `"position_policy_sidecar:peak_giveback"`**
- This is contract drift, not a design flaw
- It causes no runtime failure today
- It would cause failures if runtime schema validation were ever enabled
- The fix is a one-line schema change

### Answers to Required Audit Questions

| Q# | Question | Answer |
|----|----------|--------|
| Q1 | Sidecar-only? | **Yes** — all logic in `PositionPolicySidecar`, config in `PositionPolicySidecarConfig` |
| Q2 | Config-driven, no hidden defaults? | **Yes** — all fields required with `Field(...)`, `extra='forbid'`, no business fallbacks |
| Q3 | Preserves execution ownership? | **Yes** — uses standard CMD:CLOSE → CloseFlowFSM → DEC:CLOSE path |
| Q4 | Bounded and safe under lifecycle conditions? | **Yes** — suppression chain prevents fire during close/stale/warmup/terminal states |
| Q5 | Stealth contract drift? | **One instance** — `policy_source` schema `const` vs emitted namespaced value |
| Q6 | Provenance design correct or "made to pass"? | **Mostly correct** — mediator `startswith()` is a valid prefix-match approach; schema just needs alignment |
| Q7 | Blocker real and narrow? | **Yes** — exactly one schema `const` vs code emission mismatch |
| Q8 | Safe for bounded testnet? | **Yes, with the narrow fix** — no runtime failure without fix, but contract truth is violated |
| Q9 | Smallest corrective package? | One-line schema update (see R7A_MINIMAL_FIX_PLAN.md) |
| Q10 | Unproven risks after acceptance? | Concurrent close race, rapid oscillation, real-market timing (see UNKNOWNS above) |

---

## 14. Recommendations

1. **Apply the minimal schema fix** (see R7A_MINIMAL_FIX_PLAN.md)
2. **Add a payload-vs-schema conformance test** for the peak giveback close request
3. **Do NOT broaden the scope** — R7A as-is plus schema fix is complete
4. **Deploy to testnet** with `enabled: true` and monitor peak/arm/trigger telemetry
5. **Track U2 (concurrent close race)** as a future hardening item, not an R7A blocker
