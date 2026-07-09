#Requires -Version 5.1
<#
.SYNOPSIS
    Run the repeatable Integrated Cockpit smoke validation test.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\run_integrated_smoke_test.ps1
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

Write-Banner "Integrated Cockpit Runtime Smoke Test Harness"

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Step "Running pytest integrated smoke: tests/test_integrated_smoke.py"

$testScript = "tests/test_integrated_smoke.py"
& $Python -m pytest $testScript -v -s

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Ok "Integrated Cockpit smoke validation passed successfully."
    exit 0
} else {
    Write-Fail "Integrated Cockpit smoke validation failed with exit code $exitCode."
    exit 1
}
