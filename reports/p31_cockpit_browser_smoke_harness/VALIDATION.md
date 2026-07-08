# Validation

## Commands Run

```powershell
git status --short --branch
git branch --show-current
git switch -c p31-cockpit-smoke-harness
```

Automation inspection:

```powershell
@'
mods = ['playwright', 'selenium', 'httpx', 'requests']
for mod in mods:
    try:
        __import__(mod)
        print(f'{mod}:OK')
    except Exception as exc:
        print(f'{mod}:MISSING:{type(exc).__name__}:{exc}')
'@ | python -
```

Result:

```text
playwright:MISSING:ModuleNotFoundError:No module named 'playwright'
selenium:MISSING:ModuleNotFoundError:No module named 'selenium'
httpx:OK
requests:OK
```

Focused pytest:

```powershell
python -m pytest tests/test_cockpit_smoke.py -q
```

Result:

```text
1 passed in 1.84s
```

PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_cockpit_smoke_test.ps1
```

Result:

```text
automation=AutomationStatus(playwright='missing:ModuleNotFoundError', selenium='missing:ModuleNotFoundError', httpx='available', requests='available')
1 passed in 1.82s
Verdict: P31B_HTTP_ONLY_SMOKE_READY_BROWSER_BLOCKED
```
