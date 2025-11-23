"""
Legacy ExecPos FSM Test Suite
==============================

This package contains tests for the legacy FSM stack:
- ExecPosFSM (fsm_open.py)
- ManageFlowFSM (fsm_manage.py)
- CloseFlowFSM (fsm_close.py)

**Status**: TEST-ONLY (runtime uses V2RuntimeFacade exclusively)

All tests in this package are marked with `@pytest.mark.execpos_legacy`.

**DO NOT** add new tests here. Use `tests/domains/execution_position/shadow_execpos/`
for V2 runtime tests.

See:
- docs/EXEC_POSITION_LEGACY_CLEANUP_PLAN_S1.md
- docs/EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md
"""
