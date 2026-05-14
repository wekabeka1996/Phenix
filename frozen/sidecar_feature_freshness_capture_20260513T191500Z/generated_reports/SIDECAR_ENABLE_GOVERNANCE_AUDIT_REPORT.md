# SIDECAR_ENABLE_GOVERNANCE_AUDIT_REPORT

**Phase**: A5
**Date**: 2026-05-09
**Type**: Read-only governance audit
**Default behavior change**: NO
**Mode change**: NO
**Evidence basis**: Code + config + `POST_ENTRY_GIVEBACK_SIDECAR_DEEP_RESEARCH_REPORT.md`

---

## 1. Executive Verdict

**`MAINTAIN_ENABLE_WITH_REQUIRED_PATCHES`**

Current Sidecar `enable` mode is intentional, bounded by three independent enforcement layers (YAML config, Pydantic model validator, mediator guard chain), and does not own execution truth. The two observed sidecar-originated closes prove the action path functions end-to-end, not that it is profit-positive — profit improvement remains **UNPROVEN**. Two required patches must be applied before the next runtime collection window: (1) explicit governance documentation and a test for BRACKETS_PENDING lifecycle eligibility, and (2) formal marking of ACTION_SKIPPED as an unimplemented dead surface. No authority expansion is permitted until these are closed.

---

## 2. Current Mode and Config Source

| Field | Value |
|---|---|
| Config file | `config/aurora/domains.yaml` |
| Config key | `position_policy_sidecar.mode` |
| Config line | 535 |
| Value | `enable` |
| Enum class | `PositionPolicySidecarMode` |
| Enum file | `apps/reference/config/domains/execution_position.py:526-531` |
| Enum values | `disable` / `shadow` / `enable` |

The mode value is explicit — not inferred, not defaulted. The YAML key is required (Pydantic `Field(...)` with no default at line 805). A missing or invalid value would raise a validation error at startup.

---

## 3. Prior Approval / Validation Evidence

**No formal approval document exists.**

The closest validation artifact is `POST_ENTRY_GIVEBACK_SIDECAR_DEEP_RESEARCH_REPORT.md` (project root), which:

- Confirmed `mode: enable` is intentional in the current config
- Confirmed two sidecar-originated close chains reached `reconciled`
- Confirmed both closes were net negative
- Confirmed fee-aware shadow remains explicitly non-authoritative
- Explicitly declined to claim profit improvement

That report served as the gate for continued enable status. It did not constitute a formal approval — it constituted a decision to *not downgrade* given insufficient evidence of either benefit or harm. This audit formalizes the governance boundary that prior report implied.

**Prior enable status justification**: Mode=enable was set to allow bounded experimental action while execution truth remains in `execution_position`. The scope is explicitly bounded by config (forbidden capabilities = false) and code (mediator guard chain).

---

## 4. Current Action Scope Matrix

| Capability | Config value (domains.yaml) | Pydantic validator | Code guard (mediator.py:line) | Runtime proof | Verdict |
|---|---|---|---|---|---|
| soft_close_symbol_current_net_only | `true` | not forbidden | line 65-66 (scope check) | 2 close chains reconciled | **ALLOWED** |
| partial_reduce | `false` | raises ValueError (line 823-825) | line 63-64 (qty check), 67-68 (scope check) | 0 observed | **FORBIDDEN — triple-layer** |
| bracket_mutation | `false` | raises ValueError (line 827-829) | line 69-70 (scope check) | 0 observed | **FORBIDDEN — triple-layer** |
| exact_targeting | `false` | raises ValueError (line 831-833) | line 61-62 (target mode), 71-72 (scope check) | 0 observed | **FORBIDDEN — triple-layer** |
| fee_aware_authority | N/A — no config field | N/A | sidecar.py:568-570 (hardcoded constants) + schema const | authority_applied=false in 39 sampled rows | **FORBIDDEN — hardcoded** |
| peak_giveback_authority | `enabled: true, edge_arm_usd: 25.0, giveback_trigger_pct: 50.0` | — | arm/trigger checks in sidecar.py | 0 peak_giveback recommendations observed; arm never reached | **CONFIGURED but never triggered** |
| recommendation_only (shadow mode) | N/A — current mode is enable | — | `mode == ENABLE` guard before CMD emission | N/A | N/A (shadow not active) |

**Triple-layer enforcement for forbidden capabilities**:
1. YAML config sets the value to false
2. `PositionPolicySidecarConfig._validate_bounded_action_scope()` at `execution_position.py:821-835` raises `ValueError` if any forbidden capability is true — startup crash, not silent fallback
3. Mediator guard chain checks `allowed_scope` values before routing any command

A config drift that accidentally sets `partial_reduce: true` would crash the process at startup before the sidecar reaches runtime. This is the intended fail-closed behavior.

---

## 5. Owner-Boundary Proof

Sidecar does not directly emit exchange orders. The full close path with file:line anchors:

```
position_policy_sidecar.py:682 or :787
    → publish("CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST", PositionPolicyCloseRequest)

fsm.py:564-566 (bus.listen registration)
    → PositionPolicyMediator.on_position_policy_close_request()

position_policy_mediator.py:35-165 (10-guard chain)
    → if all guards pass: Message(op="CMD", verb="CLOSE", src="execution_position.position_policy_sidecar")
    → self._fsm.handle(close_msg) → DEC:CLOSE emitted

CloseExecutor (flows/close/close_executor.py)
    → exchange adapter (sidecar has no reference to adapter)
    → order placed on exchange

OrderGuardian.reconcile() (guardian/order_guardian.py:1133)
    → EVT:EXECUTION_CLOSE_RECONCILED emitted

PositionPolicyMediator.on_execution_close_reconciled() (mediator.py:166-188)
    → EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE (request_state="reconciled")
    → internal map entry purged
```

**Confirmed**: The sidecar class has no adapter field, no exchange client reference, and no direct order placement calls. Execution truth remains owned by `execution_position` throughout.

**Close request state lifecycle** (observable via `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE`):
- `suppressed` — mediator rejected the request
- `close_command_emitted` — CMD:CLOSE was dispatched
- `execution_submitted` — close order reached exchange (via CloseExecutor)
- `reconciled` — guardian confirmed close completion

All four state transitions are runtime-observable from `trade_lifecycle.jsonl` records.

---

## 6. Lifecycle-State Eligibility Matrix

**`has_active_lifecycle()` contract** (`fsm_manage.py:459-488`):
- Returns `True` if `state != ManageState.FLAT` (line 471)
- Returns `True` if `_closing_position` flag is set (line 473)
- Returns `True` if `position_qty` is non-zero (line 475)
- Returns `True` if any entry-side evidence exists (line 485)
- Returns `False` only when FLAT with no position qty and no entry evidence

This means all non-FLAT states — including BRACKETS_PENDING — pass the active lifecycle check.

| ManageState | Evaluation allowed | Recommendation allowed | Close request allowed | Current proof | Required guard |
|---|---|---|---|---|---|
| FLAT | Yes | No — `has_active_lifecycle()=False` | No — blocked at mediator:75-76 | mediator:75-76 | ✅ OK |
| OPENED | Yes | Yes | Yes | indirect (non-FLAT) | ✅ OK |
| BRACKETS_PENDING | Yes | Yes | **Yes — NOT blocked** | **2 runtime closes confirmed** | ⚠️ NEEDS DOCUMENTATION (PATCH-1) |
| BRACKETS_PLACED | Yes | Yes | Yes | indirect (non-FLAT) | ✅ OK |
| TRACKING | Yes | Yes | Yes | indirect (non-FLAT) | ✅ OK |
| PROTECTION_MISSING | Yes | Yes | Yes (non-FLAT) | indirect | ✅ acceptable (distressed state, close is reasonable) |
| EMIT_DEC_ADJUST | Yes | Yes | Yes (non-FLAT) | indirect | ✅ acceptable |
| ERROR | Yes | Yes | Yes (non-FLAT) | indirect | ⚠️ may race recovery paths — not tested |
| EMERGENCY | Yes | Yes | Yes (non-FLAT) | indirect | ⚠️ may race recovery paths — not tested |
| WAIT_MODE | Yes | Yes | Yes (non-FLAT) | indirect | ✅ likely safe |
| CLOSE_IN_PROGRESS | Sidecar evaluates | — | **No — suppressed** by `_closing_position` flag at mediator:77-79 | mediator:77-79 | ✅ OK |
| TERMINAL (post-close) | No — manage flow removed | — | No — no manage flow | mediator:73-74 | ✅ OK |

**BRACKETS_PENDING analysis**:

BRACKETS_PENDING means the fill has been received and confirmed, but bracket orders (SL/TP) are not yet placed on the exchange. In this state:
- The position is real and open (fill confirmed)
- The entry is known (`position_entry_price`, `entry_order_id` are set)
- Bracket protection is not yet active

A sidecar close in BRACKETS_PENDING is semantically valid: it closes a real open position before brackets are confirmed. The close flow (`CMD:CLOSE`) handles this correctly — it flattens the position, and bracket placement would be superseded by the close. The guardian reconciles the close normally.

This is **not a bug**. It is a sequencing edge case that must be explicitly documented as an accepted design decision because:
1. Both observed runtime sidecar closes occurred in BRACKETS_PENDING
2. No existing test explicitly covers this state
3. Without a test, the eligibility contract is informal

---

## 7. Runtime Recommendation / Close Request Samples

Source: `POST_ENTRY_GIVEBACK_SIDECAR_DEEP_RESEARCH_REPORT.md` (runtime window sampled from `logs/trade_lifecycle.jsonl`, `logs/order_log_v1.jsonl`)

**Event volume in sampled window** (~23.3k sidecar rows):

| Event type | Count |
|---|---|
| POSITION_POLICY_SIDECAR_SUPPRESSED | 23,036 |
| POSITION_POLICY_SIDECAR_SCORES | 54 |
| POSITION_POLICY_SIDECAR_EVALUATED | 54 |
| POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE | 39 |
| POSITION_POLICY_SIDECAR_MODE_ACTIVE | 33 |
| POSITION_POLICY_SIDECAR_RECOMMENDED | 2 |
| POSITION_POLICY_SIDECAR_CLOSE_REQUESTED | 2 |
| POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE | 6 |

The dominant event type (99%) is SUPPRESSED — the sidecar evaluates constantly but almost never reaches recommendation threshold. Raw volume should not be mistaken for active policy coverage.

**Top suppression reasons**:

| Reason | Count |
|---|---|
| no_manage_flow_for_symbol | 17,565 |
| manage_flow_has_no_active_lifecycle | 2,698 |
| features_snapshot_missing_or_stale | 2,365 |
| regime_snapshot_missing_or_stale | 318 |
| profitability_guard_active | 151 |
| post_fill_grace_active | 28 |
| manage_flow_close_in_progress | 2 |

**Observed recommendations and close chains**:

| Field | BNBUSDT | XRPUSDT |
|---|---|---|
| ts_ms | 1778346608252 | 1778347817840 |
| trigger_event | REGIME_DETECTED | PORTFOLIO_STATE_UPDATED |
| manage_state | BRACKETS_PENDING | BRACKETS_PENDING |
| policy_source | position_policy_sidecar | position_policy_sidecar |
| soft_close_pressure | 0.3451 | 0.3075 |
| unrealized_pnl_usdt | -9.3 | -8.98 |
| peak_edge_usd | 0.0 | 6.21 |
| giveback_pct | — | 244.6% |
| peak_giveback_state | peak_giveback_not_armed_below_edge | peak_giveback_not_armed_below_edge |
| requested_action | SOFT_CLOSE | SOFT_CLOSE |
| close_chain states | emitted → submitted → reconciled | emitted → submitted → reconciled |
| net_pnl | -10.19 USD | -8.76 USD |
| verdict | Late; already losing | Late; already losing |

Both recommendations fired while positions were already in loss territory. Neither was a profit-protection exit. Peak giveback never armed (arm threshold $25; both MFEs < $15).

The only profitable close in the same window (BTCUSDT, +$8.86) was a standard exchange TP bracket close — not sidecar-originated.

---

## 8. Negative Close Analysis

**What happened**: Sidecar scoring composite reached 0.3 threshold on BNBUSDT (via REGIME_DETECTED) and XRPUSDT (via PORTFOLIO_STATE_UPDATED) when both positions were already in loss. The composite score reflected adverse conditions (regime shift, deteriorating microstructure) — which correctly identified distress, but the distress had already manifested as negative PnL before the recommendation fired.

**What this does NOT mean**: That the sidecar close made outcomes worse. In both cases, positions continued to lose if held. The sidecar close may have limited further downside. Net outcomes being negative does not prove that the close timing was incorrect — it proves only that entry timing or market conditions produced losing trades regardless of exit mechanism.

**What this DOES mean**: Current scoring does not prevent firing into losses. The profitability guard (`min_unrealized_pnl_pct: 0.25`) is intended to suppress closes on profitable positions, but it does not prevent closes on losing ones. This is intentional — the sidecar is designed to cut losses, not just protect profits.

**Conclusion**: Two net-negative sidecar closes are insufficient evidence for harm. They are also insufficient evidence for benefit. The sample is too small (2 closes vs. undefined baseline rate) to evaluate strategy value.

---

## 9. Profit-Improvement Proof Status

**UNPROVEN.**

| Proof item | Status |
|---|---|
| At least one profitable sidecar close observed | NOT observed |
| Peak giveback ever armed in runtime | NOT observed (arm threshold $25, max sampled MFE $15) |
| Fee-aware shadow action would have improved realized PnL | NOT proven (shadow telemetry is informative, not prescriptive) |
| Sidecar reduces net drawdown vs. hold-to-bracket | NOT measured |
| Scoring fires before significant loss (early warning) | NOT demonstrated |

**Consequence**: No authority expansion is permitted until positive expectancy is demonstrated. This means:
- Peak giveback `edge_arm_usd` must not be lowered
- `giveback_trigger_pct` must not be lowered
- Fee-aware shadow must not be promoted to authority
- Recommendation thresholds must not change without replay/runtime proof

---

## 10. Authority Expansion Check

No authority has expanded since the prior validation artifact (`POST_ENTRY_GIVEBACK_SIDECAR_DEEP_RESEARCH_REPORT.md`):

| Check | Status |
|---|---|
| soft_close_symbol_current_net_only | still `true`, unchanged |
| partial_reduce | still `false`, forbidden |
| bracket_mutation | still `false`, forbidden |
| exact_targeting | still `false`, forbidden |
| fee_aware shadow_only | still `True`, hardcoded at sidecar.py:568 |
| fee_aware authority_applied | still `False`, hardcoded at sidecar.py:569 |
| Verb registry — all sidecar verbs | still `experimental`, except SUPPRESSED (`active`) |
| peak_giveback edge_arm_usd | still `25.0`, unchanged |
| giveback_trigger_pct | still `50.0`, unchanged |

The verb registry status of `experimental` for all action-bearing verbs (`POSITION_POLICY_SIDECAR_RECOMMENDED`, `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`, `POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE`) confirms that no authority has been promoted to stable/active outside the sidecar's own domain.

---

## 11. Downgrade Triggers

These are explicit conditions that would require downgrading mode. Current evidence does not meet any of them.

### Downgrade to `recommendation` (emit recommendations, no close commands)

```
Triggers (any one sufficient):
- 3+ consecutive sidecar closes net negative with zero profitable sidecar closes in a 30-day
  runtime window AND no evidence of loss-limiting benefit vs. bracket hold baseline
- Code review reveals mediator guard bypass path (close command reachable without guard chain)
- BRACKETS_PENDING close confirmed to cause orphaned bracket orders or duplicate execution
```

### Downgrade to `shadow` (no commands, no recommendations in registry)

```
Triggers (any one sufficient):
- Sidecar close request confirmed to bypass mediator and reach exchange adapter directly
- manage_flow._closing_position flag race condition confirmed to cause duplicate close submission
- Execution truth record contaminated by sidecar attribution (close_actor incorrectly attributed)
- Guardian unable to reconcile sidecar-originated close (orphaned order state)
```

### Disable

```
Triggers (any one sufficient):
- Sidecar emits syntactically invalid commands that reach the exchange
- Sidecar creates irreconcilable guardian state (audit trail broken)
- Sidecar causes process crash via unhandled exception in evaluation path
```

---

## 12. Continue-Enable Conditions

Enable mode remains acceptable while ALL of the following hold:

```
1. action scope unchanged:
   soft_close_symbol_current_net_only = true
   partial_reduce = false
   bracket_mutation = false
   exact_targeting = false

2. execution_position retains close truth ownership:
   sidecar has no exchange adapter reference
   all closes route through mediator → CMD:CLOSE → CloseExecutor

3. mediator rejects all requests outside bounded scope:
   10-guard chain remains intact
   no bypass path discovered

4. no new authority added:
   no fee-aware authority promotion
   no peak_giveback threshold reduction without replay proof
   no symbol scope expansion

5. execution instability absent:
   no duplicate close submissions
   no irreconcilable guardian state
   no orphaned bracket orders from sidecar closes
```

---

## 13. Required Patches

### PATCH-1: BRACKETS_PENDING eligibility documentation and test

**Status**: Required before next runtime collection window.

**Problem**: BRACKETS_PENDING is implicitly allowed by `has_active_lifecycle()` (returns True for any non-FLAT state). Both observed runtime sidecar closes occurred in this state. No existing test explicitly covers this eligibility path.

**Required actions**:

1. Add explicit documentation to `has_active_lifecycle()` (`fsm_manage.py:459`) stating that BRACKETS_PENDING is an active lifecycle state and sidecar close requests are intentionally permitted in this state.

2. Add a test to `tests/domains/execution_position/test_sidecar_modes_disable_shadow_enable.py` asserting that:
   - When manage_flow.state = BRACKETS_PENDING, `has_active_lifecycle()` returns True
   - Mediator does NOT suppress the close request on this basis alone
   - The close request proceeds to `close_command_emitted`

3. (Optional) Assess whether BRACKETS_PENDING should be explicitly blocked. Decision criteria:
   - If bracket orders occasionally arrive after a sidecar close and create orphaned exchange orders, consider adding a BRACKETS_PENDING guard to the mediator
   - If close flow cleanly supersedes pending brackets with no orphaned state, document as intentionally accepted

**Files to modify**:
- `apps/reference/domains/execution_position/flows/manage/fsm_manage.py` (comment only)
- `tests/domains/execution_position/test_sidecar_modes_disable_shadow_enable.py` (new test class)

---

### PATCH-2: ACTION_SKIPPED dead surface annotation

**Status**: Required before next runtime collection window.

**Problem**: `EVT:POSITION_POLICY_SIDECAR_ACTION_SKIPPED` is:
- Declared in `event_names.py:34-36`
- Listed in `OWNED_EVENT_NAMES` (`event_names.py:68`)
- Listed in `__all__` (`event_names.py:96`)
- Registered in `verb_registry_v1.yaml:191-194` as `status: experimental`
- Has a full schema at `schemas/position_policy_sidecar_action_skipped_v1.json`

But it has **no runtime emitter**. Tests explicitly assert it is NOT emitted (`test_position_policy_sidecar.py:209`). Any operator or monitor building against ACTION_SKIPPED will never see a row.

**Required actions** (choose one):

**Option A — Mark as unimplemented (minimal)**:
- Add comment to `event_names.py:34`: `# reserved: no runtime emitter — schema and registry defined, not yet implemented`
- Update `verb_registry_v1.yaml:193`: add `notes: "Reserved. Schema defined but no runtime emitter exists."` line

**Option B — Implement the emitter**:
- Emit ACTION_SKIPPED when: mode=enable, evaluation threshold met (RECOMMENDED would fire), but mediator suppresses the close request
- This creates a closed-loop: RECOMMENDED → mediator suppresses → ACTION_SKIPPED
- Useful for operator visibility into "sidecar wanted to act but was blocked"
- File: `position_policy_mediator.py` (emit on suppression path when source was a RECOMMENDED event)

**Recommendation**: Option A is sufficient for the current phase. Option B adds value but is a feature, not a governance patch.

---

## 14. Residual Risks

| Risk | Severity | Status | Mitigation |
|---|---|---|---|
| BRACKETS_PENDING sequencing: orphaned bracket orders if SL/TP exchange orders arrive after sidecar close | MEDIUM | **Not tested** | Guardian should handle via order cleanup; needs explicit test (PATCH-1) |
| ACTION_SKIPPED fake surface: operators/monitors see declared surface with zero rows | LOW | Active | Annotation required (PATCH-2) |
| Profit proof absent: 2-close sample insufficient to evaluate strategy expectancy | MEDIUM | Ongoing | Continue runtime collection; 30-day checkpoint |
| ERROR/EMERGENCY state eligibility: sidecar close may race internal recovery paths | LOW | Not tested | Low probability; document as accepted risk or add guard |
| Scoring fires into losses: no prevention of closes when PnL already negative | LOW | By design | profitability_guard guards profitable positions, not loss floors; document as accepted |
| Peak giveback never arms at $25: real-time MFEs too small for current threshold | MEDIUM | Ongoing | Shadow collection needed; do not lower threshold without replay proof |
| Fee-aware shadow informs but does not act: smaller edges visible but unactionable | LOW | By design | Non-authoritative by contract; no action needed |

---

## 15. Final Recommendation

**Verdict: `MAINTAIN_ENABLE_WITH_REQUIRED_PATCHES`**

Sidecar remains in current hybrid/testnet `enable` mode because:

1. **Bounded**: Current action scope is bounded at three independent layers (YAML, Pydantic validator, mediator guard chain). No capability outside `soft_close_symbol_current_net_only` can reach the exchange.
2. **Owner-safe**: Sidecar has no exchange adapter reference. All closes route through `execution_position`'s mediator, close flow, and guardian. Execution truth remains in execution_position.
3. **Contract-safe**: Mediator 10-guard chain is tested. Fee-aware shadow authority is hardcoded to false. Forbidden capabilities crash at startup if accidentally configured.
4. **Non-expanding**: All verb registry entries remain experimental. No authority was promoted. No thresholds were changed. Config values match prior validation artifact.
5. **Observable enough**: Close request state lifecycle (suppressed/emitted/submitted/reconciled) is fully observable from `trade_lifecycle.jsonl`. Two complete close chains were reconstructed from runtime evidence.
6. **Profit improvement UNPROVEN**: This means no authority expansion is permitted. Peak giveback thresholds stay frozen. Fee-aware shadow stays non-authoritative.
7. **Downgrade triggers explicit**: Three-tier downgrade ladder (recommendation → shadow → disable) with concrete, objective criteria.
8. **Two patches required**: BRACKETS_PENDING test and ACTION_SKIPPED annotation must be applied before this report can be considered closed.

---

## A5 DONE Criteria Checklist

| # | Criterion | Status |
|---|---|---|
| 1 | No default downgrade performed | ✅ mode unchanged |
| 2 | No trading threshold changed | ✅ no threshold changes |
| 3 | No new authority added | ✅ scope unchanged |
| 4 | Current mode source identified | ✅ config/aurora/domains.yaml:535 |
| 5 | Current action scope proven from config + code | ✅ triple-layer enforcement documented |
| 6 | At least one runtime close chain reconstructed | ✅ 2 chains reconstructed (BNBUSDT, XRPUSDT) |
| 7 | Lifecycle-state eligibility documented | ✅ 11-state matrix with BRACKETS_PENDING highlighted |
| 8 | Owner boundary verified | ✅ full close path traced with file:line anchors |
| 9 | Profit-improvement status explicitly marked | ✅ UNPROVEN |
| 10 | Final verdict is allowed enum value | ✅ MAINTAIN_ENABLE_WITH_REQUIRED_PATCHES |
| 11 | Report includes residual risks and follow-up requirements | ✅ Section 14 + PATCH-1/PATCH-2 |

**A5 DONE** (pending PATCH-1 and PATCH-2 closure).
