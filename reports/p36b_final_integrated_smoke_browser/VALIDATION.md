AGENT_IDENTITY:
  agent_number: 2
  agent_name: primary-final-smoke-browser-validator
  machine: primary
  task_id: P36B_FINAL_INTEGRATED_SMOKE_AND_BROWSER_PROOF
  branch: agent-hub-integrated-2026-07-09
  worktree: C:\Users\wekab\Music\Phenix-integrated-smoke
  commit: a194cb739658483c2d62e21484c89ae398cd0670
  started_at: 2026-07-09T17:05:49+03:00
  finished_at: 2026-07-09T17:38:00+03:00

# Final Integrated Cockpit Smoke & Browser Validation Report

This document records the validation execution outputs.

---

## 1. Automated Test Suite Run

### Command
```bash
powershell -ExecutionPolicy Bypass -File tools/deepseek-terminal-agent/scripts/run_final_integrated_smoke.ps1
```

### Output
```text
=== Final Integrated Cockpit Smoke and API Validation Harness ===
  --> Running pytest validation tests...
  --> Executing: tests/test_attachments_api.py
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0 -- C:\Python314\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\wekab\Music\Phenix-integrated-smoke\tools\deepseek-terminal-agent
configfile: pyproject.toml
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 4 items

tests/test_attachments_api.py::test_create_list_get_attachment_routes PASSED
tests/test_attachments_api.py::test_attachment_routes_fail_closed_for_missing_session PASSED
tests/test_attachments_api.py::test_attachment_route_rejects_invalid_kind_and_raw_blob_fields PASSED
tests/test_attachments_api.py::test_context_builder_includes_only_prompt_eligible_attachment_refs PASSED

============================== 4 passed in 0.50s ==============================
  --> Executing: tests/test_attachment_ui_panel.py
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0 -- C:\Python314\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\wekab\Music\Phenix-integrated-smoke\tools\deepseek-terminal-agent
configfile: pyproject.toml
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 2 items

tests/test_attachment_ui_panel.py::test_attachment_panel_markup_supports_required_kinds PASSED
tests/test_attachment_ui_panel.py::test_attachment_panel_js_uses_p32b_routes_and_compact_rendering PASSED

============================== 2 passed in 0.02s ==============================
  --> Executing: tests/test_proposals_api.py
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0 -- C:\Python314\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\wekab\Music\Phenix-integrated-smoke\tools\deepseek-terminal-agent
configfile: pyproject.toml
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 2 items

tests/test_proposals_api.py::test_create_list_get_proposals PASSED
tests/test_proposals_api.py::test_proposal_rejections_for_forbidden_fields PASSED

============================== 2 passed in 0.47s ==============================
  --> Executing: tests/test_integrated_smoke.py
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0 -- C:\Python314\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\wekab\Music\Phenix-integrated-smoke\tools\deepseek-terminal-agent
configfile: pyproject.toml
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tests/test_integrated_smoke.py::test_integrated_cockpit_smoke 
Starting integrated Cockpit dashboard on port 49890...
Dashboard server started successfully.
Verifying GET /chat...
Verifying POST /chat/sessions...
Verifying GET /chat/sessions...
Verifying POST /chat/sessions/a737f42f901a406499e368ce3f6312b9/attachments...
Verifying rejection of raw binary fields...
Verifying listing attachments...
Verifying GET /chat/attachments/attachment-4af7024c3fe74360b045ddf479b6c886...
Verifying context inspection contains bounded summary...
Verifying missing P33 endpoint status...
P33 GET status: 404
Verifying Proposal Ledger API...
Verifying Forbidden Proposal Fields Rejection...
Cleaning up server subprocess...

--- Subprocess Server Stdout ---
INFO:     127.0.0.1:49893 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:49895 - "GET /chat HTTP/1.1" 200 OK
INFO:     127.0.0.1:49896 - "POST /chat/sessions HTTP/1.1" 201 Created
INFO:     127.0.0.1:49897 - "GET /chat/sessions HTTP/1.1" 200 OK
INFO:     127.0.0.1:49898 - "POST /chat/sessions/a737f42f901a406499e368ce3f6312b9/attachments HTTP/1.1" 201 Created
INFO:     127.0.0.1:49899 - "POST /chat/sessions/a737f42f901a406499e368ce3f6312b9/attachments HTTP/1.1" 400 Bad Request
INFO:     127.0.0.1:49900 - "GET /chat/sessions/a737f42f901a406499e368ce3f6312b9/attachments HTTP/1.1" 200 OK
INFO:     127.0.0.1:49901 - "GET /chat/attachments/attachment-4af7024c3fe74360b045ddf479b6c886 HTTP/1.1" 200 OK
INFO:     127.0.0.1:49902 - "POST /chat/sessions/a737f42f901a406499e368ce3f6312b9/context HTTP/1.1" 200 OK
INFO:     127.0.0.1:49903 - "GET /chat/sessions/a737f42f901a406499e368ce3f6312b9/session-context HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:49904 - "POST /chat/sessions/a737f42f901a406499e368ce3f6312b9/agent-proposals HTTP/1.1" 201 Created
INFO:     127.0.0.1:49905 - "GET /chat/sessions/a737f42f901a406499e368ce3f6312b9/agent-proposals HTTP/1.1" 200 OK
INFO:     127.0.0.1:49906 - "GET /chat/agent-proposals/proposal-4abbc04654a14ad6905f093ee735ff70 HTTP/1.1" 200 OK
INFO:     127.0.0.1:49907 - "POST /chat/sessions/a737f42f901a406499e368ce3f6312b9/agent-proposals HTTP/1.1" 400 Bad Request

--- Subprocess Server Stderr ---
INFO:     Started server process [13296]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:49890 (Press CTRL+C to quit)

Integrated Cockpit smoke validation complete.
PASSED

============================== 1 passed in 3.62s ==============================
  [OK] All integration, API, and static UI tests passed successfully.
```
