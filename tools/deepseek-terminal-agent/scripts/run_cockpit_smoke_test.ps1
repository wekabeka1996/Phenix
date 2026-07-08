#Requires -Version 5.1
<#
.SYNOPSIS
    Run the repeatable Cockpit chat session creation smoke test.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\run_cockpit_smoke_test.ps1
#>

$ErrorActionPreference = "Stop"

function Write-Step   { param($msg) Write-Host "  --> $msg" -ForegroundColor Cyan }
function Write-Ok     { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Fail   { param($msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red }
function Write-Banner { param($msg) Write-Host "" ; Write-Host "=== $msg ===" -ForegroundColor Cyan }

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentRoot   = Split-Path -Parent $ScriptDir
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $AgentRoot)
Set-Location $AgentRoot

Write-Banner "Cockpit Chat Session Creation Smoke Test Harness"

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Step "Running pytest smoke test: tests/test_cockpit_smoke.py"

$testScript = "tests/test_cockpit_smoke.py"
& $Python -m pytest $testScript -v -s

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Ok "Cockpit chat session creation smoke test passed successfully."
    Write-Host ""
    Write-Host "Verdict: P31B_HTTP_ONLY_SMOKE_READY_BROWSER_BLOCKED" -ForegroundColor Green
    Write-Host ""
    exit 0
} else {
    Write-Fail "Cockpit chat session creation smoke test failed with exit code $exitCode."
    exit 1
}
