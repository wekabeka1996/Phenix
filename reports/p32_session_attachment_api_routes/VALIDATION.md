# Validation

Environment:
- worktree: C:\Users\wekab\Music\Phenix-p32b-attachments-api
- branch: p32b-attachments-api-primary-20260708
- package root: tools/deepseek-terminal-agent

Commands:
- python -m pytest tests/test_attachments_api.py
  - result: 4 passed
- python -m pytest tests/test_context_builder.py
  - result: 5 passed
- python -m pytest tests/test_dashboard_chat_app.py
  - result: 9 passed

Observed coverage:
- POST /chat/sessions/{session_id}/attachments creates persisted metadata.
- GET /chat/sessions/{session_id}/attachments lists session-bound records.
- GET /chat/attachments/{attachment_id} returns detail and validates owning session.
- Missing sessions return 404.
- Invalid kind and raw blob-shaped payloads return 400.
- ContextBuilder includes only include_in_prompt=True attachment summaries/source refs.

Known validation note:
- An initial pytest command used a repo-root path while already inside tools/deepseek-terminal-agent, so pytest reported the file was not found. The corrected command passed.
