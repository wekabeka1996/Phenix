# Validation Report

We verified the merged components on branch `agent-hub-integrated-2026-07-09`.

## Test Outputs

1.  **UI panel & Attachments Ingest (P32 / P34C)**:
    - Command: `python -m pytest tests/test_attachments_api.py tests/test_context_builder.py tests/test_dashboard_chat_app.py tests/test_attachment_ui_panel.py`
    - Result: `20 passed in 0.92s`.
2.  **Session Context Contract (P33)**:
    - Command: `python -m pytest tests/domains/agent_bridge/test_session_context_contract.py`
    - Result: `6 passed in 0.74s`.
3.  **Cadence / SOS Tests (P34E)**:
    - Result: Skipped (P34E branch not merged).
