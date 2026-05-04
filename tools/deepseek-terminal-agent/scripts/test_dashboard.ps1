#Requires -Version 5.1
<#
.SYNOPSIS
    Build, test, lint, and optionally health-check the dashboard.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\test_dashboard.ps1
#>

$ErrorActionPreference = "Stop"

function Write-Step   { param($msg) Write-Host "  --> $msg" -ForegroundColor Cyan }
function Write-Ok     { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Fail   { param($msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red }
function Write-Banner { param($msg) Write-Host "" ; Write-Host "=== $msg ===" -ForegroundColor Cyan }

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

# Add Docker to PATH if needed
$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    if (Test-Path $dockerBin) {
        $env:PATH += ";$dockerBin"
    }
}

Write-Banner "DeepSeek Terminal Agent -- Full Validation"

# 1. Build
Write-Step "Building Docker image..."
& docker compose build
if ($LASTEXITCODE -ne 0) { Write-Fail "Build failed."; exit 1 }
Write-Ok "Build passed."

# 2. pytest
Write-Step "Running pytest..."
& docker compose run --rm --entrypoint pytest deepseek-agent -q
if ($LASTEXITCODE -ne 0) { Write-Fail "pytest failed."; exit 1 }
Write-Ok "pytest passed."

# 3. compileall
Write-Step "Running compileall..."
& docker compose run --rm --entrypoint python deepseek-agent -m compileall src -q
if ($LASTEXITCODE -ne 0) { Write-Fail "compileall failed."; exit 1 }
Write-Ok "compileall passed."

# 4. ruff
Write-Step "Running ruff..."
& docker compose run --rm --entrypoint ruff deepseek-agent check src tests
if ($LASTEXITCODE -ne 0) { Write-Fail "ruff failed."; exit 1 }
Write-Ok "ruff passed."

# 5. Health check (optional, only if dashboard is already running)
Write-Step "Checking if dashboard is running for health check..."
try {
    $resp = Invoke-RestMethod "http://127.0.0.1:8787/health" -TimeoutSec 3 -ErrorAction Stop
    if ($resp.ok -eq $true) {
        Write-Ok "Health check passed: ok=$($resp.ok) service=$($resp.service)"
    }
} catch {
    Write-Host "  [INFO] Dashboard not running -- skipping health check." -ForegroundColor DarkGray
    Write-Host "         Run start_dashboard.ps1 first to test it." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "-------------------------------------------------------------" -ForegroundColor DarkGray
Write-Ok "All checks passed!"
Write-Host "-------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""
