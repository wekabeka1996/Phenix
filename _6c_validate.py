"""Minimal validation: import + syntax check for 6C module."""
import sys, os
sys.path.insert(0, r"c:\Users\user\Music\Phenix")
os.chdir(r"c:\Users\user\Music\Phenix")

print("=== STEP 1: Import startup_reconstruction ===")
try:
    from apps.reference.domains.execution_position.startup_reconstruction import StartupReconstruction
    print(f"OK: StartupReconstruction imported. Methods: {[m for m in dir(StartupReconstruction) if not m.startswith('__')]}")
except Exception as e:
    print(f"FAIL: {e}")

print("\n=== STEP 2: Import fsm and check wiring ===")
try:
    import inspect
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    src = inspect.getsource(ExecPosFSM._startup_reconstruct_runtime_bracket_truth)
    is_delegator = "self._startup_reconstruction.reconstruct" in src
    print(f"OK: ExecPosFSM._startup_reconstruct_runtime_bracket_truth is delegator: {is_delegator}")
    print(f"Body lines: {len(src.splitlines())}")
    print(f"Source:\n{src}")
except Exception as e:
    print(f"FAIL: {e}")

print("\n=== STEP 3: Check __init__ wiring ===")
try:
    init_src = inspect.getsource(ExecPosFSM.__init__)
    has_6c = "_startup_reconstruction = StartupReconstruction(self)" in init_src
    print(f"OK: __init__ wires StartupReconstruction: {has_6c}")
except Exception as e:
    print(f"FAIL: {e}")

print("\n=== STEP 4: Verify _startup_order_guardian_reconcile stays in fsm ===")
try:
    src_guard = inspect.getsource(ExecPosFSM._startup_order_guardian_reconcile)
    print(f"OK: _startup_order_guardian_reconcile in fsm.py, lines: {len(src_guard.splitlines())}")
    calls_6c = "_startup_reconstruct_runtime_bracket_truth" in src_guard
    print(f"   Calls _startup_reconstruct_runtime_bracket_truth: {calls_6c}")
except Exception as e:
    print(f"FAIL: {e}")

print("\n=== STEP 5: Verify restore_startup_from_snapshot_positions stays in fsm ===")
try:
    src_restore = inspect.getsource(ExecPosFSM.restore_startup_from_snapshot_positions)
    print(f"OK: restore_startup_from_snapshot_positions in fsm.py, lines: {len(src_restore.splitlines())}")
except Exception as e:
    print(f"FAIL: {e}")

print("\n=== STEP 6: Verify start_order_guardian stays in fsm ===")
try:
    src_start = inspect.getsource(ExecPosFSM.start_order_guardian)
    print(f"OK: start_order_guardian in fsm.py, lines: {len(src_start.splitlines())}")
except Exception as e:
    print(f"FAIL: {e}")

print("\n=== STEP 7: Check 6C module does NOT contain 6A/6B logic ===")
try:
    sr_src = inspect.getsource(StartupReconstruction)
    has_dark_read = "_run_restore_artifact_dark_read" in sr_src
    has_auth_read = "_run_restore_artifact_authoritative_read" in sr_src
    has_apply = "_apply_authoritative_restore_record" in sr_src
    has_persist = "_persist_restore_artifact_snapshot" in sr_src
    has_finalize = "_finalize_restore_authoritative_status" in sr_src
    print(f"Contains 6A dark-read: {has_dark_read}  (expected: False)")
    print(f"Contains 6A auth-read: {has_auth_read}  (expected: False)")
    print(f"Contains 6B apply:     {has_apply}  (expected: False)")
    print(f"Contains 6A persist:   {has_persist}  (expected: False)")
    print(f"Contains 6A finalize:  {has_finalize}  (expected: False)")
    if any([has_dark_read, has_auth_read, has_apply, has_persist, has_finalize]):
        print("BOUNDARY VIOLATION DETECTED")
    else:
        print("OK: No 6A/6B logic leaked into 6C")
except Exception as e:
    print(f"FAIL: {e}")

print("\n=== STEP 8: Run test file inline ===")
try:
    import pytest
    exit_code = pytest.main([
        "tests/domains/execution_position/test_startup_reconstruction.py",
        "-v", "--tb=short", "--no-header"
    ])
    print(f"\nPytest exit code: {exit_code}")
except Exception as e:
    print(f"FAIL running tests: {e}")

print("\n=== STEP 9: Run restore integration tests ===")
try:
    exit_code2 = pytest.main([
        "tests/domains/execution_position/test_restart_runtime_truth_reconstruction.py",
        "-v", "--tb=short", "--no-header"
    ])
    print(f"\nPytest exit code: {exit_code2}")
except Exception as e:
    print(f"FAIL running tests: {e}")

print("\n=== STEP 10: Run authoritative read tests ===")
try:
    exit_code3 = pytest.main([
        "tests/domains/execution_position/test_execution_restore_authoritative_read.py",
        "-v", "--tb=short", "--no-header"
    ])
    print(f"\nPytest exit code: {exit_code3}")
except Exception as e:
    print(f"FAIL running tests: {e}")

print("\n=== STEP 11: Run dark read tests ===")
try:
    exit_code4 = pytest.main([
        "tests/domains/execution_position/test_execution_restore_dark_read.py",
        "-v", "--tb=short", "--no-header"
    ])
    print(f"\nPytest exit code: {exit_code4}")
except Exception as e:
    print(f"FAIL running tests: {e}")

print("\n=== STEP 12: Run artifact writer tests ===")
try:
    exit_code5 = pytest.main([
        "tests/domains/execution_position/test_execution_restore_artifact_writer.py",
        "-v", "--tb=short", "--no-header"
    ])
    print(f"\nPytest exit code: {exit_code5}")
except Exception as e:
    print(f"FAIL running tests: {e}")

print("\n=== DONE ===")
