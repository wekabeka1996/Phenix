#Requires -Version 5.1
<#
.SYNOPSIS
    Start the DeepSeek Terminal Agent Dashboard.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\start_dashboard.ps1
#>

param(
    [switch]$Update,
    [switch]$CleanContainers,
    [switch]$VerifyOnly,
    [switch]$PrivateLan,
    [ValidateRange(1, 65535)]
    [int]$Port = 8787,
    [string]$EnvironmentLabel = "BINANCE_FUTURES_TESTNET"
)

# Do NOT set ErrorActionPreference = Stop — it interferes with native docker calls
$ErrorActionPreference = "Continue"

function Write-Step   { param($msg) Write-Host "  --> $msg" -ForegroundColor Cyan }
function Write-Ok     { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Fail   { param($msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red }
function Write-Warn   { param($msg) Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Banner { param($msg) Write-Host "" ; Write-Host "=== $msg ===" -ForegroundColor Cyan }

function Invoke-LocalScript {
    param(
        [string]$Name,
        [string[]]$Arguments = @()
    )
    $ScriptPath = Join-Path $ScriptDir $Name
    & powershell -ExecutionPolicy Bypass -File $ScriptPath @Arguments | Out-Host
    return $LASTEXITCODE
}

function Test-DashboardReady {
    try {
        $health = Invoke-RestMethod $StartupHealthUrl -TimeoutSec 2 -ErrorAction Stop
        $null = Invoke-RestMethod "$LocalBaseUrl/config-status" -TimeoutSec 2 -ErrorAction Stop
        $null = Invoke-RestMethod "$LocalBaseUrl/models" -TimeoutSec 2 -ErrorAction Stop
        $chat = Invoke-WebRequest "$LocalBaseUrl/chat" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        return ($health.ok -eq $true) -and ($chat.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Test-PrivateIPv4 {
    param([string]$Address)
    $parsed = $null
    if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$parsed)) { return $false }
    $bytes = $parsed.GetAddressBytes()
    if ($bytes.Length -ne 4) { return $false }
    return (
        $bytes[0] -eq 10 -or
        ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
        ($bytes[0] -eq 192 -and $bytes[1] -eq 168)
    )
}

function Get-PrivateLanAddress {
    $addresses = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName())
    return $addresses |
        Where-Object { Test-PrivateIPv4 $_.IPAddressToString } |
        Select-Object -First 1 -ExpandProperty IPAddressToString
}

function Write-AccessUrls {
    Write-Host "DASHBOARD_READY"
    Write-Host "Health: $StartupHealthUrl"
    Write-Host "Local: $LocalBaseUrl/arena"
    if ($PrivateLan) {
        $lanAddress = Get-PrivateLanAddress
        if ($lanAddress) {
            Write-Host "LAN: http://${lanAddress}:$Port/arena"
        } else {
            Write-Warn "No RFC1918 IPv4 address was detected; LAN URL is unavailable."
        }
        Write-Host "Windows Firewall guidance (run as administrator only if needed):"
        Write-Host "New-NetFirewallRule -DisplayName 'Phenix Cockpit $Port' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private"
    }
}

Write-Banner "DeepSeek Terminal Agent Dashboard"

# Locate project root (parent of scripts/)
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Write-Step "Project root: $ProjectRoot"
Set-Location $ProjectRoot

$LocalBaseUrl = "http://127.0.0.1:$Port"
$StartupHealthUrl = "$LocalBaseUrl/health"
$env:DASHBOARD_PORT = "$Port"
$env:DASHBOARD_ENVIRONMENT_LABEL = $EnvironmentLabel
$env:DASHBOARD_STARTUP_HEALTH_URL = $StartupHealthUrl
if ($PrivateLan) {
    $env:DASHBOARD_BIND_ADDRESS = "0.0.0.0"
    $env:DASHBOARD_PRIVATE_LAN_ENABLED = "true"
    $env:DASHBOARD_ALLOWED_HOSTS = "127.0.0.1,localhost,testserver,private-lan"
    $env:DASHBOARD_ALLOWED_ORIGINS = "http://127.0.0.1:$Port,http://localhost:$Port,private-lan"
} else {
    $env:DASHBOARD_BIND_ADDRESS = "127.0.0.1"
    $env:DASHBOARD_PRIVATE_LAN_ENABLED = "false"
    $env:DASHBOARD_ALLOWED_HOSTS = "127.0.0.1,localhost,testserver"
    $env:DASHBOARD_ALLOWED_ORIGINS = "http://127.0.0.1:$Port,http://localhost:$Port"
}

if ($Update) {
    $CleanContainers = $true
}

# 1. Ensure Docker binary is on PATH
$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    if (Test-Path $dockerBin) {
        $env:PATH += ";$dockerBin"
        Write-Warn "Added Docker to PATH for this session."
    } else {
        Write-Fail "Docker not found. Install Docker Desktop."
        exit 1
    }
}
$v = & docker --version 2>&1
Write-Ok "Docker: $v"

# 2. Check Docker Compose plugin
$cv = & docker compose version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Docker Compose not found. Upgrade Docker Desktop."
    exit 1
}
Write-Ok "Compose: $cv"

# 3. Check Docker daemon — use 'docker ps' which is simpler than 'docker info'
Write-Step "Checking Docker daemon..."
$daemonReady = $false
for ($attempt = 1; $attempt -le 5; $attempt++) {
    $out = & docker ps 2>&1
    if ($LASTEXITCODE -eq 0) {
        $daemonReady = $true
        break
    }
    Write-Warn "Daemon not ready yet (attempt $attempt/5) -- waiting 3s..."
    Start-Sleep -Seconds 3
}
if (-not $daemonReady) {
    Write-Fail "Docker daemon is not responding after 5 attempts."
    Write-Host "  Make sure Docker Desktop is fully started (whale icon stable in tray)." -ForegroundColor Yellow
    Write-Host "  Then run this script again." -ForegroundColor Yellow
    exit 1
}
Write-Ok "Docker daemon is running."

# 4. Check .env exists
Write-Step "Checking .env file..."
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Warn ".env not found -- created from .env.example."
        Write-Host "  Edit .env and set DEEPSEEK_API_KEY=sk-your-key-here" -ForegroundColor Yellow
        Write-Host "  Then run this script again." -ForegroundColor Yellow
        exit 1
    } else {
        Write-Fail ".env not found and no .env.example either."
        exit 1
    }
}
Write-Ok ".env exists."

# 5. Verify DEEPSEEK_API_KEY is non-empty (do NOT print the value)
Write-Step "Verifying DEEPSEEK_API_KEY..."
$keyLine = Select-String -Path ".env" -Pattern "^DEEPSEEK_API_KEY=.+" -Quiet
if (-not $keyLine) {
    Write-Fail "DEEPSEEK_API_KEY is missing or empty in .env"
    Write-Host "  Edit .env and add: DEEPSEEK_API_KEY=sk-your-key-here" -ForegroundColor Yellow
    exit 1
}
Write-Ok "DEEPSEEK_API_KEY is set (value not shown)."

if ($VerifyOnly) {
    Write-Step "Running memory integrity check..."
    if ((Invoke-LocalScript -Name "check_memory_integrity.ps1" -Arguments @("-Quiet")) -ne 0) {
        Write-Fail "Memory integrity check failed."
        exit 1
    }
    Write-Ok "Memory integrity check passed."

    Write-Step "Checking dashboard endpoints..."
    if (Test-DashboardReady) {
        Write-Ok "Dashboard endpoints are healthy."
        Write-AccessUrls
        exit 0
    }
    Write-Fail "Dashboard is not ready. Start it first or rerun without -VerifyOnly."
    exit 1
}

if ($Update) {
    Write-Step "Creating .agent_memory backup before update..."
    if ((Invoke-LocalScript -Name "backup_memory.ps1") -ne 0) {
        Write-Fail "Memory backup failed."
        exit 1
    }
    Write-Ok "Memory backup completed."
}

if ($CleanContainers) {
    Write-Step "Stopping project containers..."
    & docker compose down --remove-orphans
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "docker compose down --remove-orphans failed."
        exit 1
    }
    Write-Ok "Containers stopped."

    Write-Step "Removing stopped project containers..."
    & docker compose rm -fsv
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "docker compose rm -fsv failed."
        exit 1
    }
    Write-Ok "Stopped containers removed."
}

# 6. Build Docker images
Write-Step "Building Docker images (may take ~90s on first run)..."
$buildArgs = @("compose", "build")
if ($Update) {
    $buildArgs += "--pull"
}
& docker @buildArgs
if ($LASTEXITCODE -ne 0) {
    Write-Fail "docker compose build failed."
    exit 1
}
Write-Ok "Images built."

if ($Update) {
    Write-Step "Running memory integrity check after rebuild..."
    if ((Invoke-LocalScript -Name "check_memory_integrity.ps1" -Arguments @("-Quiet")) -ne 0) {
        Write-Fail "Memory integrity check failed after update."
        exit 1
    }
    Write-Ok "Memory integrity check passed."
}

# 7. Start dashboard
Write-Step "Starting dashboard service..."
& docker compose up -d dashboard
if ($LASTEXITCODE -ne 0) {
    Write-Fail "docker compose up -d dashboard failed."
    Write-Host "  Logs: docker compose logs --tail=50 dashboard" -ForegroundColor Yellow
    exit 1
}
Write-Ok "Dashboard container started."

# 8. Wait for /health to respond
Write-Step "Waiting for dashboard to be ready (up to 20s)..."
$ready = $false
for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Seconds 1
    if (Test-DashboardReady) { $ready = $true; break }
}

if ($ready) {
    Write-Ok "Dashboard is ready."
} else {
    Write-Warn "Dashboard did not respond in 20s -- may still be starting."
    Write-Host "  Check: docker compose logs --tail=50 dashboard" -ForegroundColor Yellow
    exit 1
}
Write-AccessUrls
