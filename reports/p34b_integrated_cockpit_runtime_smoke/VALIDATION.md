AGENT_IDENTITY:
  agent_number: 2
  agent_name: primary-integrated-cockpit-smoke
  machine: primary
  task_id: P34B_INTEGRATED_COCKPIT_RUNTIME_SMOKE
  branch: agent-hub-integrated-2026-07-09
  worktree: C:\Users\wekab\Music\Phenix-integrated-smoke
  commit: 5837ae4fa1ca35cb8d59c5023e9f8161a28ca76f
  started_at: 2026-07-09T10:39:16+03:00
  finished_at: 2026-07-09T10:47:00+03:00

# Integrated Cockpit Runtime Smoke Validation Report

This report documents the validation execution results of the integrated smoke test harness.

---

## 1. Pytest Integration Test Run

### Command
```bash
pytest tools/deepseek-terminal-agent/tests/test_integrated_smoke.py -v -s
```

### Output
```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0 -- C:\Users\wekab\Music\Phenix\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\wekab\Music\Phenix-integrated-smoke\tools\deepseek-terminal-agent
configfile: pyproject.toml
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0, timeout-2.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tools\deepseek-terminal-agent\tests\test_integrated_smoke.py::test_integrated_cockpit_smoke 
Starting integrated Cockpit dashboard on port 60666...
Dashboard server started successfully.
Verifying GET /chat...
Verifying POST /chat/sessions...
Verifying GET /chat/sessions...
Verifying POST /chat/sessions/3515d02cbec84470a5f14bc6d2b34626/attachments...
Verifying rejection of raw binary fields...
Verifying listing attachments...
Verifying GET /chat/attachments/attachment-2e21093e712b42c0a1839af774ec2962...
Verifying context inspection contains bounded summary...
Verifying missing P33 endpoint status...
P33 GET status: 404
Cleaning up server subprocess...

--- Subprocess Server Stdout ---
INFO:     127.0.0.1:60669 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:60670 - "GET /chat HTTP/1.1" 200 OK
INFO:     127.0.0.1:60671 - "POST /chat/sessions HTTP/1.1" 201 Created
INFO:     127.0.0.1:60672 - "GET /chat/sessions HTTP/1.1" 200 OK
INFO:     127.0.0.1:60673 - "POST /chat/sessions/3515d02cbec84470a5f14bc6d2b34626/attachments HTTP/1.1" 201 Created
INFO:     127.0.0.1:60675 - "POST /chat/sessions/3515d02cbec84470a5f14bc6d2b34626/attachments HTTP/1.1" 400 Bad Request
INFO:     127.0.0.1:60676 - "GET /chat/sessions/3515d02cbec84470a5f14bc6d2b34626/attachments HTTP/1.1" 200 OK
INFO:     127.0.0.1:60677 - "GET /chat/attachments/attachment-2e21093e712b42c0a1839af774ec2962 HTTP/1.1" 200 OK
INFO:     127.0.0.1:60678 - "POST /chat/sessions/3515d02cbec84470a5f14bc6d2b34626/context HTTP/1.1" 200 OK
INFO:     127.0.0.1:60680 - "GET /chat/sessions/3515d02cbec84470a5f14bc6d2b34626/session-context HTTP/1.1" 404 Not Found

--- Subprocess Server Stderr ---
INFO:     Started server process [42772]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:60666 (Press CTRL+C to quit)

Integrated Cockpit smoke validation complete.
PASSED

============================== 1 passed in 5.22s ==============================
```

---

## 2. PowerShell Script Wrapper Run

### Command
```powershell
powershell -ExecutionPolicy Bypass -File tools/deepseek-terminal-agent/scripts/run_integrated_smoke_test.ps1
```

### Output
```text
=== Integrated Cockpit Runtime Smoke Test Harness ===
  --> Running pytest integrated smoke: tests/test_integrated_smoke.py
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0 -- C:\Python314\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\wekab\Music\Phenix-integrated-smoke\tools\deepseek-terminal-agent
configfile: pyproject.toml
plugins: anyio-4.12.1, aiohttp-1.1.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tests/test_integrated_smoke.py::test_integrated_cockpit_smoke 
Starting integrated Cockpit dashboard on port 60687...
Dashboard server started successfully.
Verifying GET /chat...
Verifying POST /chat/sessions...
Verifying GET /chat/sessions...
Verifying POST /chat/sessions/a458ffef9ecf46238f1c5b90ee7ec008/attachments...
Verifying rejection of raw binary fields...
Verifying listing attachments...
Verifying GET /chat/attachments/attachment-565f57fb98314ee28de8cd856cd58826...
Verifying context inspection contains bounded summary...
Verifying missing P33 endpoint status...
P33 GET status: 404
Cleaning up server subprocess...

--- Subprocess Server Stdout ---
INFO:     127.0.0.1:64459 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:64800 - "GET /chat HTTP/1.1" 200 OK
INFO:     127.0.0.1:64802 - "POST /chat/sessions HTTP/1.1" 201 Created
...
INFO:     127.0.0.1:60927 - "GET /chat/sessions/a458ffef9ecf46238f1c5b90ee7ec008/session-context HTTP/1.1" 404 Not Found

--- Subprocess Server Stderr ---
INFO:     Started server process [21480]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:60687 (Press CTRL+C to quit)

Integrated Cockpit smoke validation complete.
PASSED

============================== 1 passed in 9.29s ==============================
  [OK] Integrated Cockpit smoke validation passed successfully.
```
