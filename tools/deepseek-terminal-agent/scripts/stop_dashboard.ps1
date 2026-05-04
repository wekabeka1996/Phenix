#Requires -Version 5.1
<#
.SYNOPSIS
    Stop the DeepSeek Terminal Agent Dashboard.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\stop_dashboard.ps1
#>

$ErrorActionPreference = "Stop"

function Write-Step { param($msg) Write-Host "  --> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Fail { param($msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "=== Stop DeepSeek Dashboard ===" -ForegroundColor Cyan

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

Write-Step "Stopping dashboard service..."
& docker compose stop dashboard
if ($LASTEXITCODE -ne 0) {
    Write-Fail "docker compose stop dashboard returned exit code $LASTEXITCODE"
    exit 1
}
Write-Ok "Dashboard stopped."
Write-Host ""
Write-Host "  To start again:" -ForegroundColor DarkGray
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\start_dashboard.ps1" -ForegroundColor DarkGray
Write-Host ""
