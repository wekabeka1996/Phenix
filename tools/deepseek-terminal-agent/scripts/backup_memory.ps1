#Requires -Version 5.1
param(
    [string]$DestinationRoot = ".agent_memory_backups"
)

$ErrorActionPreference = "Stop"

function Write-Step { param($msg) Write-Host "  --> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

$MemoryDir = Join-Path $ProjectRoot ".agent_memory"
if (-not (Test-Path $MemoryDir)) {
    Write-Warn ".agent_memory does not exist; nothing to back up."
    exit 0
}

if ([System.IO.Path]::IsPathRooted($DestinationRoot)) {
    $BackupRoot = $DestinationRoot
} else {
    $BackupRoot = Join-Path $ProjectRoot $DestinationRoot
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Target = Join-Path $BackupRoot $Stamp

Write-Step "Creating memory backup at $Target"
New-Item -ItemType Directory -Path $Target -Force | Out-Null
Copy-Item $MemoryDir (Join-Path $Target ".agent_memory") -Recurse -Force

Write-Ok "Memory backup created."
Write-Host "BACKUP_PATH=$Target"
