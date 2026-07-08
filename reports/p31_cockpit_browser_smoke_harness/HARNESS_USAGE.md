# Harness Usage

Run from `tools/deepseek-terminal-agent`:

```powershell
python -m pytest tests/test_cockpit_smoke.py -q
```

Or use the PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_cockpit_smoke_test.ps1
```

## What It Does

- Inspects Python automation availability for Playwright, Selenium, `httpx`, and `requests`.
- Starts the Cockpit FastAPI dashboard on a random isolated `127.0.0.1` port.
- Uses a temporary working directory with copied dashboard config.
- Uses a dummy non-secret API key value.
- Calls:
  - `GET /health`
  - `GET /chat`
  - `GET /chat/sessions`
  - `POST /chat/sessions`
  - `GET /chat/sessions`
- Verifies `.agent_memory/sessions/<session_id>/session.dsstate.json` exists in the temporary directory.

## Safety

- Does not start Aurora runtime.
- Does not send LLM messages.
- Does not touch live/mainnet.
- Does not place/cancel/modify orders.
- Does not write to project `.agent_memory`; persistence is checked in a temporary memory root.
