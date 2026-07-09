# Risks and Residuals

We evaluated the risk profile of the integrated branch.

## Identified Risks
1.  **Multiple simultaneous file uploads in API**:
    - Risk: The attachments endpoint `/chat/sessions/{session_id}/attachments` is heavily tested under unit cases, but concurrent upload threads from subagents could cause race conditions in the target attachments directory.
    - Mitigation: The implementation uses atomic directory creation and locks where necessary.
2.  **Mock keys runtime override**:
    - Risk: Test suites use mock key parameters that override environment configurations.
    - Mitigation: Ensure `config/project_capsule.yaml` is clean on deploy to prevent loading test keys in production environments.
