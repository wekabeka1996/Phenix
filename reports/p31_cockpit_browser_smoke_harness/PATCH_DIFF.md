# Patch Diff

## Files Added Or Updated

- `tools/deepseek-terminal-agent/scripts/run_cockpit_smoke_test.ps1`
- `tools/deepseek-terminal-agent/tests/test_cockpit_smoke.py`
- `reports/p31_cockpit_browser_smoke_harness/REPORT.md`
- `reports/p31_cockpit_browser_smoke_harness/HARNESS_USAGE.md`
- `reports/p31_cockpit_browser_smoke_harness/PATCH_DIFF.md`
- `reports/p31_cockpit_browser_smoke_harness/VALIDATION.md`
- `reports/p31_cockpit_browser_smoke_harness/LIMITATIONS.md`

## Diff Summary

- Added a repeatable pytest smoke harness for Cockpit session creation.
- Added a PowerShell wrapper to run the focused pytest from `tools/deepseek-terminal-agent`.
- The pytest harness:
  - inspects Playwright/Selenium/httpx/requests availability
  - starts dashboard via `python -m uvicorn`
  - uses a random localhost port
  - uses a temporary working directory and copied config
  - uses a dummy non-secret API key
  - verifies `/health`, `/chat`, `/chat/sessions`, `POST /chat/sessions`
  - verifies temp `.agent_memory/sessions/<id>/session.dsstate.json`

## Git Notes

The harness files were untracked when inspected, so `git diff --stat` and `git diff --name-only` showed no tracked diff before staging. `git status --short` showed:

```text
?? tools/deepseek-terminal-agent/scripts/run_cockpit_smoke_test.ps1
?? tools/deepseek-terminal-agent/tests/test_cockpit_smoke.py
```

After staging, the local commit records the complete file additions.
