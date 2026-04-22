# R7A ACCEPTANCE DECISION

**Package**: R7A — Sidecar Peak-Giveback Full Verification
**Date**: 2026-04-21
**Auditor**: Independent Agent 2

---

## Decision

# ACCEPTANCE_READY_WITH_NARROW_FIX

---

## Rationale

### What is correct

1. **Architecture**: Peak-giveback logic lives entirely within `PositionPolicySidecar`. No new truth owner is created. The close path reuses the standard CMD:CLOSE → CloseFlowFSM → DEC:CLOSE bridge. ManageFlowFSM remains the sole position lifecycle authority.

2. **Config contract**: `PositionPolicySidecarPeakGivebackConfig` uses `extra='forbid'` and all required fields (`Field(...)`). No default values, no silent fallbacks. Removing any field from YAML causes startup failure. All three fields (`enabled`, `edge_arm_usd`, `giveback_trigger_pct`) are present in `domains.yaml`.

3. **Trigger safety**: Cannot fire before arming, during close-in-progress, on stale data, in SHADOW/DISABLE mode, or after trigger (state resets). Entry fills reset state completely. All critical suppressions are preserved.

4. **Test coverage**: 41 tests pass covering peak giveback logic, sidecar lifecycle, config contracts, close bridge, and verb registration.

5. **Operator requirements met**: Logic under Sidecar ✅, config next to Sidecar config ✅, explicit enable ✅, explicit percentage ✅, no hardcodes ✅, no silent fallbacks ✅.

### What requires a narrow fix

**One schema `const` constraint violation**:

The JSON schema `cmd_position_policy_sidecar_close_request_v1.json` declares:
```json
"policy_source": { "type": "string", "const": "position_policy_sidecar" }
```

The peak giveback path emits:
```python
policy_source="position_policy_sidecar:peak_giveback"
```

This is a contract truth violation. It does not cause runtime failure today (no runtime schema validation), but it means the registered schema does not accurately describe the actual payload contract.

**Fix**: One-line schema edit — change `const` to `pattern` (see R7A_MINIMAL_FIX_PLAN.md).

### Why NOT `NOT_READY` or `MIXED_NOT_READY`

- The implementation is complete and correct
- The blocker is exactly one line in one schema file
- The blocker causes zero runtime failures
- The blocker does not indicate a design problem
- The previous agent's `MIXED_NOT_READY` was inflated by mixing unrelated XRP/TOCTOU findings

### Why NOT `ACCEPTANCE_READY`

- A schema `const` violation, however narrow, is a contract truth gap
- The project's reasoning constitution requires contract integrity
- Accepting without the fix would set precedent for undocumented schema drift

---

## Post-Fix Deployment Conditions

After applying the schema fix:

1. All 41 existing tests must continue to pass
2. A new payload-vs-schema conformance test should be added (recommended, not blocking)
3. Deploy with `enabled: true` on testnet
4. Monitor: arm events, trigger events, close request emissions
5. Track [U2: concurrent close race] and [U3: rapid oscillation] as observation items

---

## Residual Unproven Risks (Post-Fix)

| Risk | Type | Mitigation |
|------|------|-----------|
| Concurrent max_hold_close + peak_giveback | Integration | Idempotent_key prevents double-close; monitor telemetry |
| Rapid PnL oscillation re-triggering | Operational | By-design (new peak cycle); monitor trigger frequency |
| Real-market timing behavior | Runtime | Only provable via testnet observation |
| Downstream `policy_source` consumers | Integration | Audit after schema change |
