#Requires -Version 5.1
param(
    [string]$BackupPath
)

$ErrorActionPreference = "Stop"

function Write-Step { param($msg) Write-Host "  --> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

$BackupRoot = Join-Path $ProjectRoot ".agent_memory_backups"
if (-not $BackupPath) {
    $Latest = Get-ChildItem -Path $BackupRoot -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if (-not $Latest) {
        Write-Fail "No backup directory found in $BackupRoot"
        exit 1
    }
    $BackupPath = $Latest.FullName
}

$ResolvedBackup = Resolve-Path $BackupPath -ErrorAction Stop
$SourceMemory = Join-Path $ResolvedBackup ".agent_memory"
if (-not (Test-Path $SourceMemory)) {
    Write-Fail "Backup path does not contain .agent_memory: $ResolvedBackup"
    exit 1
}

$TargetMemory = Join-Path $ProjectRoot ".agent_memory"
if (Test-Path $TargetMemory) {
    $SafetyRoot = Join-Path $BackupRoot ("pre_restore_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
    Write-Step "Backing up current .agent_memory to $SafetyRoot before restore"
    New-Item -ItemType Directory -Path $SafetyRoot -Force | Out-Null
    Move-Item $TargetMemory (Join-Path $SafetyRoot ".agent_memory") -Force
}

Write-Step "Restoring memory from $ResolvedBackup"
Copy-Item $SourceMemory $TargetMemory -Recurse -Force

Write-Ok "Memory restore completed."
Write-Host "RESTORED_FROM=$ResolvedBackup"
