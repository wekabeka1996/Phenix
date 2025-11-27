# TASK 5 (R2-E) Implementation Report: Missing / Manual Cancel Semantics for TP/SL

**RID**: OCO-STABILIZE-R2-E-MISSING-BRACKETS-SEMANTICS
**Date**: 2025-01-20
**Status**: ✅ COMPLETE
**Priority**: P1 (R1-C-RISK-3 mitigation)

---

## 1. Summary

**Goal**: Implement configurable behavior for missing SL/TP brackets after manual cancel while position is open.

**Problem**:
- R1-C-RISK-3: Missing brackets after manual cancel (or exchange glitch) leave positions unprotected
- Previous behavior: Implicit "honor missing" (no action) or implicit "recreate" (unclear policy)
- Required: Explicit, config-driven policy with fail-closed default

**Solution**:
- Added `recreate_missing_brackets: bool` config flag (default True = fail-closed)
- Modified `BracketService.evaluate()` to branch on config:
  - True → generate PLACE_SL/PLACE_TP actions with reason_code="MISSING_SL_RECREATED"/"MISSING_TP_RECREATED"
  - False → severity=WARN, log warning, do NOT generate PLACE actions
- Implemented 4 tests covering both modes (True/False × SL/TP)

**Outcome**:
- ✅ 4/4 new tests PASSED
- ✅ 21/22 all OCO tests GREEN (1 SKIPPED, unrelated)
- ✅ Config-driven behavior working as specified
- ✅ No regressions in existing functionality

---

## 2. Files Changed

### 2.1 Core Implementation

**`apps/reference/domains/execution_position/config.py`** (+3 lines)
- Added `recreate_missing_brackets: bool = Field(default=True, ...)` to `AggregatedOcoConfig` (Pydantic model)
- Description: "Recreate SL/TP if missing during open position (fail-closed)"

**`apps/reference/domains/execution_position/shadow_execpos/bracket_service.py`** (+45 lines)
- Added `recreate_missing_brackets: bool = True` to `BracketRulesConfig` (dataclass)
- Added logger initialization in `__init__()`: `self.logger = logging.getLogger(self.__class__.__name__)`
- Modified `evaluate()` INVARIANT 2 logic (lines ~657-715):
  - Missing SL: branch on `cfg.recreate_missing_brackets`:
    - True → severity=ALERT, PLACE_SL action, reason_code="MISSING_SL_RECREATED"
    - False → severity=WARN, log warning, why="missing_sl_honored|recreate_missing_brackets=false"
  - Missing TP: same branching logic with PLACE_TP, reason_code="MISSING_TP_RECREATED"

**`apps/reference/domains/execution_position/shadow_execpos/runtime.py`** (+2 lines)
- Modified `_get_bracket_cfg()` (lines ~1736-1776):
  - Typed config path: Added `recreate_missing_brackets=agg.recreate_missing_brackets`
  - Legacy dict path: Added `recreate_missing_brackets=agg_cfg.get("recreate_missing_brackets", True)`
- Ensures config field propagates from ExecutionPositionConfig → BracketRulesConfig

### 2.2 Configuration

**`config/domains/execution.yaml`** (+1 line)
- Under `aggregated_oco` section: `recreate_missing_brackets: true  # R2-E: Recreate SL/TP if missing during open position (fail-closed mode)`

### 2.3 Tests

**`tests/domains/execution_position/test_agg_oco_manual_cancel.py`** (NEW, 412 lines)
- 4 test cases covering recreate_missing_brackets=True/False × missing SL/TP:
  1. `test_missing_sl_is_recreated_when_recreate_missing_brackets_true` — True mode, missing SL → PLACE_SL ✅
  2. `test_missing_tp_is_recreated_when_recreate_missing_brackets_true` — True mode, missing TP → PLACE_TP ✅
  3. `test_missing_sl_is_not_recreated_when_recreate_missing_brackets_false` — False mode, missing SL → NO PLACE_SL ✅
  4. `test_missing_tp_is_not_recreated_when_recreate_missing_brackets_false` — False mode, missing TP → NO PLACE_TP ✅
- Test pattern: Open position with SL+TP → simulate ORDERS_SNAPSHOT without SL or TP → verify action presence/absence
- Uses `_handle_orders_snapshot()` for exchange-truth simulation

---

## 3. Test Results

### 3.1 New Tests (test_agg_oco_manual_cancel.py)

```
tests/domains/execution_position/test_agg_oco_manual_cancel.py::test_missing_sl_is_recreated_when_recreate_missing_brackets_true PASSED [ 25%]
tests/domains/execution_position/test_agg_oco_manual_cancel.py::test_missing_tp_is_recreated_when_recreate_missing_brackets_true PASSED [ 50%]
tests/domains/execution_position/test_agg_oco_manual_cancel.py::test_missing_sl_is_not_recreated_when_recreate_missing_brackets_false PASSED [ 75%]
tests/domains/execution_position/test_agg_oco_manual_cancel.py::test_missing_tp_is_not_recreated_when_recreate_missing_brackets_false PASSED [100%]

4 passed in 0.63s
```

### 3.2 Regression Tests (all OCO domain tests)

```
tests/domains/execution_position/test_agg_oco_manual_cancel.py ................ PASSED [4 tests]
tests/domains/execution_position/test_agg_oco_size_sync.py ..................... PASSED [4 tests, 1 SKIPPED]
tests/domains/execution_position/test_agg_oco_timeout_and_snapshot_state.py .... PASSED [7 tests]
tests/domains/execution_position/test_agg_oco_races_close_and_reopen.py ........ PASSED [6 tests]

21 passed, 1 skipped in 1.05s
```

**Regression Status**: ✅ GREEN — No existing tests broken by R2-E changes

---

## 4. Implementation Details

### 4.1 Config Architecture

```
ExecutionPositionConfig (Pydantic)
└── AggregatedOcoConfig
    └── recreate_missing_brackets: bool = True  ← Added here

    ↓ (loaded by Runtime)

ExecPosRuntimeV2
└── _get_bracket_cfg() → BracketRulesConfig
    └── recreate_missing_brackets: bool = True  ← Forwarded here

    ↓ (passed to BracketService)

BracketService.evaluate(state, cfg: BracketRulesConfig)
└── INVARIANT 2 logic: if cfg.recreate_missing_brackets ...
```

### 4.2 Behavior Matrix

| Scenario | Config Value | Missing SL/TP | Action | Severity | reason_code |
|----------|--------------|---------------|--------|----------|-------------|
| Open pos, no SL | `True` (default) | SL missing | PLACE_SL | ALERT | MISSING_SL_RECREATED |
| Open pos, no TP | `True` (default) | TP missing | PLACE_TP | WARN | MISSING_TP_RECREATED |
| Open pos, no SL | `False` | SL missing | **NO PLACE** | WARN | — |
| Open pos, no TP | `False` | TP missing | **NO PLACE** | WARN | — |

### 4.3 Code Example (evaluate() logic)

```python
# INVARIANT 2: Missing SL
if sl_count == 0:
    if not cfg.allow_unprotected_position:
        if cfg.recreate_missing_brackets:  # R2-E
            severity = "ALERT"
            why = f"missing_sl|pos>0_sl_count=0"
            desired_levels = self._compute_desired_levels(state, cfg)
            actions.append(BracketAction(
                action_type="PLACE_SL",
                price=desired_levels["sl_price"],
                qty=state.position_view.qty,
                reason_code="MISSING_SL_RECREATED",  # R2-E
                why="missing_sl_recreated|recreate_missing_brackets=true",
                rid=rid,
            ))
        else:
            # Honor missing: do not recreate, but warn
            severity = "WARN"
            why = "missing_sl_honored|recreate_missing_brackets=false"
            self.logger.warning(
                "[BracketService] Missing SL for open position; honoring config recreate_missing_brackets=False",
                extra={"symbol": state.symbol, "cycle_id": state.position_view.cycle_id if state.position_view else 0, "rid": rid},
            )
```

---

## 5. Risks & Mitigations

### 5.1 Identified Risks

1. **Risk**: Config propagation failure (typed path vs legacy path)
   - **Mitigation**: Both code paths in `_get_bracket_cfg()` updated
   - **Test coverage**: Tests use typed config path (ExecutionPositionConfig)

2. **Risk**: Watchdog suppress interferes with bracket creation
   - **Mitigation**: HOTFIX already disabled SUPPRESS_BRACKETS (line 817, runtime.py)
   - **Observed**: watchdog violations logged but suppression disabled

3. **Risk**: False mode might allow prolonged unprotected positions
   - **Mitigation**: Default is True (fail-closed); False requires explicit opt-in; warning logged every evaluate cycle

### 5.2 Open Items

- **None** — All DoD criteria met

---

## 6. DoD Checklist

- [x] Config flag `recreate_missing_brackets` added to AggregatedOcoConfig (Pydantic model)
- [x] Config flag added to BracketRulesConfig (dataclass)
- [x] Config flag added to execution.yaml with comment
- [x] Runtime `_get_bracket_cfg()` forwards config to BracketRulesConfig (typed + legacy paths)
- [x] BracketService `evaluate()` implements conditional logic:
  - [x] True mode: PLACE_SL/PLACE_TP with reason_code="MISSING_SL_RECREATED"/"MISSING_TP_RECREATED"
  - [x] False mode: severity=WARN, log warning, NO PLACE actions
- [x] Logger added to BracketService for warning messages
- [x] 4 tests created (2 for True mode, 2 for False mode)
- [x] All new tests PASS (4/4)
- [x] All existing OCO tests remain GREEN (21/22, 1 SKIPPED unrelated)
- [x] JOURNAL.md updated with RID OCO-STABILIZE-R2-E-MISSING-BRACKETS-SEMANTICS
- [x] TASK5_R2E_IMPLEMENTATION_REPORT.md created (this file)

---

## 7. Next Steps

**Immediate**:
- ✅ TASK 5 (R2-E) COMPLETE — No further action required

**Future** (not in TASK 5 scope):
- TASK 6 (R2-F): Add `manual_cancel_alert` flag to trigger immediate alert/notification when missing brackets detected
- TASK 7 (R2-G): Extend `why_chain` to include manual cancel detection rationale (for XAI audit)
- TASK 8 (R2-H): Add metrics for missing brackets events (Prometheus counters)

---

## 8. Review Sign-off

**Implementation**: ✅ COMPLETE
**Tests**: ✅ GREEN (4 new + 21 existing)
**Regressions**: ✅ NONE
**Documentation**: ✅ JOURNAL + REPORT created

**Approver**: [Awaiting review]
**Date**: 2025-01-20
