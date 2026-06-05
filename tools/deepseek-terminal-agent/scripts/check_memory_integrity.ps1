#Requires -Version 5.1
param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

function Write-Step { param($msg) if (-not $Quiet) { Write-Host "  --> $msg" -ForegroundColor Cyan } }
function Write-Ok   { param($msg) if (-not $Quiet) { Write-Host "  [OK] $msg" -ForegroundColor Green } }
function Write-Warn { param($msg) Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red }

function Test-JsonFile {
    param([string]$Path)
    try {
        Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json | Out-Null
        return $true
    } catch {
        Write-Fail "Invalid JSON: $Path"
        Write-Host $_.Exception.Message
        return $false
    }
}

function Test-JsonlFile {
    param([string]$Path)
    $LineNumber = 0
    try {
        foreach ($Line in Get-Content -Encoding UTF8 $Path) {
            $LineNumber += 1
            if ([string]::IsNullOrWhiteSpace($Line)) {
                continue
            }
            $Line | ConvertFrom-Json | Out-Null
        }
        return $true
    } catch {
        Write-Fail ("Invalid JSONL: {0}:{1}" -f $Path, $LineNumber)
        Write-Host $_.Exception.Message
        return $false
    }
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

$MemoryRoot = Join-Path $ProjectRoot ".agent_memory"
if (-not (Test-Path $MemoryRoot)) {
    Write-Warn ".agent_memory does not exist; integrity check skipped."
    exit 0
}

$Failed = $false
$SessionsRoot = Join-Path $MemoryRoot "sessions"
$ArtifactsRoot = Join-Path $MemoryRoot "artifacts"
$MemoryAtomsPath = Join-Path $MemoryRoot "memory_atoms.dsmem.jsonl"
$SpinesPath = Join-Path $MemoryRoot "session_spines.dsspine.jsonl"

Write-Step "Checking memory atom store"
if ((Test-Path $MemoryAtomsPath) -and -not (Test-JsonlFile $MemoryAtomsPath)) { $Failed = $true }

Write-Step "Checking session spines"
if ((Test-Path $SpinesPath) -and -not (Test-JsonlFile $SpinesPath)) { $Failed = $true }

Write-Step "Checking session files"
if (Test-Path $SessionsRoot) {
    foreach ($SessionDir in Get-ChildItem -Path $SessionsRoot -Directory) {
        $StatePath = Join-Path $SessionDir.FullName "session.dsstate.json"
        $TurnsPath = Join-Path $SessionDir.FullName "turns.dsctx.jsonl"
        $EventsPath = Join-Path $SessionDir.FullName "events.dsctx.jsonl"
        if ((Test-Path $StatePath) -and -not (Test-JsonFile $StatePath)) { $Failed = $true }
        if ((Test-Path $TurnsPath) -and -not (Test-JsonlFile $TurnsPath)) { $Failed = $true }
        if ((Test-Path $EventsPath) -and -not (Test-JsonlFile $EventsPath)) { $Failed = $true }
    }
}

Write-Step "Checking artifacts"
if (Test-Path $ArtifactsRoot) {
    foreach ($ArtifactPath in Get-ChildItem -Path $ArtifactsRoot -Filter *.dsartifact.json -File) {
        if (-not (Test-JsonFile $ArtifactPath.FullName)) { $Failed = $true }
    }
}

if ($Failed) {
    Write-Fail "Memory integrity check failed."
    exit 1
}

Write-Ok "Memory integrity check passed."
