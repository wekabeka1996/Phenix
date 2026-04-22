with open('tests/domains/execution_position/test_execution_restore_artifact_writer.py', 'r') as f:
    text = f.read()

text = text.replace('fsm._restore_artifact_writer._observability_hook', 'fsm._startup_truth_orchestrator._restore_artifact_writer._observability_hook')
text = text.replace('patch("apps.reference.domains.execution_position.fsm.asyncio.sleep"', 'patch("apps.reference.domains.execution_position.startup_truth_orchestrator.asyncio.sleep"')

with open('tests/domains/execution_position/test_execution_restore_artifact_writer.py', 'w') as f:
    f.write(text)
