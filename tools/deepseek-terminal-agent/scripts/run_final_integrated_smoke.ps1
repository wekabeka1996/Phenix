#Requires -Version 5.1
<#
.SYNOPSIS
    Run the repeatable Final Integrated Cockpit smoke validation tests.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\run_final_integrated_smoke.ps1
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

Write-Banner "Final Integrated Cockpit Smoke and API Validation Harness"

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Step "Running pytest validation tests..."

$testFiles = @(
    "tests/test_attachments_api.py",
    "tests/test_attachment_ui_panel.py",
    "tests/test_proposals_api.py",
    "tests/test_integrated_smoke.py"
)

foreach ($testFile in $testFiles) {
    Write-Step "Executing: $testFile"
    & $Python -m pytest $testFile -v -s
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Fail "Test $testFile failed with exit code $exitCode."
        exit 1
    }
}

Write-Ok "All integration, API, and static UI tests passed successfully."
exit 0
