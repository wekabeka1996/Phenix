# Patch Diff Summary

git diff --name-only:
- tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/app.py
- tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/attachments.py
- tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/context_builder.py
- tools/deepseek-terminal-agent/tests/test_attachments_api.py
- reports/p32_session_attachment_api_routes/API_CONTRACT.md
- reports/p32_session_attachment_api_routes/PATCH_DIFF.md
- reports/p32_session_attachment_api_routes/REPORT.md
- reports/p32_session_attachment_api_routes/RISKS.md
- reports/p32_session_attachment_api_routes/VALIDATION.md

Functional diff:
- Added AttachmentRecord and AttachmentStore under sessions/attachments.py.
- Added dashboard AttachmentStore singleton and three /chat attachment routes.
- Added attachments to session detail payloads.
- Added bounded attachment inclusion to ContextBuilder.
- Added focused API and context tests for create/list/get, fail-closed missing sessions, invalid kind/raw blob rejection, and prompt eligibility.

Non-changes:
- No dashboard static JS/template changes.
- No Aurora agent_bridge changes.
- No YAML/config changes.
- No trading runtime or order-path changes.
