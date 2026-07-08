# Staged Diff Summary

The following changes are staged for the multi-machine synchronization baseline commit:

*   **Total Files Changed/Added**: 190 files
*   **Total Insertions**: 13,138 lines
*   **Total Deletions**: 62 lines

## Key Components Staged
1.  **Cockpit UI & Client fixes**:
    - Adds rendering updates for Simple Chat session list drawers and titles.
    - Adds `config/project_capsule.yaml` to root layout dependencies.
2.  **Aurora agent_bridge & contracts**:
    - Formulates `SessionContextV1` JSON Schema contract.
    - Implements Pydantic `session_context_contract.py` structure.
    - Implements disk adapter `session_context_read_model.py`.
    - Integrates read-only `GET /agent-session-context/v0/{session_id}` route.
3.  **Validation Test Suites**:
    - Registers pytest validations for the session context contract, dry-run ledgers, compiler formats, and FSM integrations.
4.  **Forensics Tools**:
    - Commits localized scripts to parse trade placements, timezone contexts, and decision log events.
5.  **Multi-Agent Reports**:
    - Integrates full documentation indexes for P7, P8, P9, P10, P11, P12, P13, P14, P15, P16, P17, P26, P31, P33.
