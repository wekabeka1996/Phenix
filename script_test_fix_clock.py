with open('tests/domains/execution_position/test_execution_restore_artifact_writer.py', 'r') as f:
    text = f.read()

text = text.replace('patch("apps.reference.domains.execution_position.fsm.get_clock"', 'patch("apps.reference.domains.execution_position.startup_truth_orchestrator.get_clock"')

with open('tests/domains/execution_position/test_execution_restore_artifact_writer.py', 'w') as f:
    f.write(text)
