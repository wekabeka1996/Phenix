import glob
import re

for file in glob.glob('tests/domains/execution_position/**/*.py', recursive=True):
    with open(file, 'r', encoding='utf8') as f:
        text = f.read()

    # Handle patch.object(fsm, '_persist_restore_artifact_snapshot'
    text = re.sub(
        r"patch\.object\(fsm,\s*[\"']_persist_restore_artifact_snapshot[\"']",
        "patch.object(fsm._startup_truth_orchestrator, \"_persist_restore_artifact_snapshot\"",
        text
    )
    
    # Check for other Mock tracking (e.g., call_count on the loop which was mapped)
    text = re.sub(
        r"patch\.object\(fsm,\s*[\"']_restore_artifact_loop[\"']",
        "patch.object(fsm._startup_truth_orchestrator, \"_restore_artifact_loop\"",
        text
    )
    
    # test_execution_restore_dark_read.py::test_startup_reconcile_records_dark_read_status_without_changing_authority
    # This one fails with missing startup truth artifact because previously FSM mocked out dark reader directly.
    # It might create something? Let's check `test_degraded_startup_truth_surface_makes_unknown_reconstructed` also
    
    with open(file, 'w', encoding='utf8') as f:
        f.write(text)
