<#
.SYNOPSIS
    Restart shadow_telemetry HTTP API with a fresh (or supplied) bearer token.
    Run from the repo root: .\tools\restart_shadow_telemetry.ps1

.PARAMETER Token
    Optional. Use an existing token instead of generating a new one.
    Example: .\tools\restart_shadow_telemetry.ps1 -Token "my-secret-token"

.PARAMETER Port
    HTTP port for shadow_telemetry. Default: 8443 (matches config/aurora/domains.yaml).

.PARAMETER Host_
    Listen host. Default: 127.0.0.1.

.PARAMETER LogLevel
    Uvicorn log level. Default: INFO.
#>
param(
    [string]$Token     = "",
    [int]   $Port      = 8443,
    [string]$Host_     = "127.0.0.1",
    [string]$LogLevel  = "INFO"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SHADOW_PID_PORT = $Port

function Find-ShadowPid {
    $tcpRows = netstat -ano | Select-String "127\.0\.0\.1:$SHADOW_PID_PORT\s+.*LISTENING"
    if ($tcpRows) {
        # Last token is PID
        $pid_ = ($tcpRows[0] -split '\s+')[-1]
        return [int]$pid_
    }
    return $null
}

# ── 1. Stop existing shadow_telemetry if running ──────────────────────────────
$existingPid = Find-ShadowPid
if ($existingPid) {
    Write-Host "[shadow_telemetry] Stopping PID $existingPid (port $Port)..."
    Stop-Process -Id $existingPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Write-Host "[shadow_telemetry] Stopped."
} else {
    Write-Host "[shadow_telemetry] No existing process on port $Port."
}

# ── 2. Generate or use supplied token ─────────────────────────────────────────
if (-not $Token) {
    $Token = & python -c "import secrets; print(secrets.token_hex(32))"
    Write-Host "[shadow_telemetry] Generated new token."
}

# ── 3. Write token to .shadow_token (gitignored file) for reference ───────────
$tokenFile = Join-Path $PSScriptRoot "..\tools\.shadow_token"
$Token | Out-File -FilePath $tokenFile -Encoding ascii -NoNewline
Write-Host "[shadow_telemetry] Token saved to tools/.shadow_token (gitignored)."

# ── 4. Set env var for the new process ────────────────────────────────────────
$env:SHADOW_TELEMETRY_BEARER_TOKEN = $Token

# ── 5. Start shadow_telemetry in background ───────────────────────────────────
Write-Host "[shadow_telemetry] Starting shadow_telemetry API on ${Host_}:$Port..."

$startArgs = @(
    "-m", "apps.reference.domains.shadow_telemetry.main",
    "--config-dir", "config/aurora",
    "--host", $Host_,
    "--port", "$Port",
    "--log-level", $LogLevel
)

$proc = Start-Process -FilePath "python" `
    -ArgumentList $startArgs `
    -WorkingDirectory (Split-Path $PSScriptRoot -Parent) `
    -NoNewWindow `
    -PassThru `
    -RedirectStandardOutput "logs/shadow_telemetry_stdout.log" `
    -RedirectStandardError  "logs/shadow_telemetry_stderr.log"

Start-Sleep -Seconds 2

# ── 6. Validate ───────────────────────────────────────────────────────────────
try {
    $health = Invoke-RestMethod -Uri "http://${Host_}:${Port}/health" -Method Get -TimeoutSec 5
    Write-Host "[shadow_telemetry] ✅ Health OK: status=$($health.status), queue_depth=$($health.queue_depth)"
} catch {
    Write-Warning "[shadow_telemetry] ⚠️  Health check failed: $_"
    Write-Warning "Check logs/shadow_telemetry_stderr.log for startup errors."
}

# ── 7. Print token for Custom GPT / LLM tool auth setup ─────────────────────
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  BEARER TOKEN  →  Copy this into your LLM tool auth settings:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  $Token" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Custom GPT: Actions → Authentication → Bearer → paste above" -ForegroundColor Cyan
Write-Host "  OpenAPI servers.url: https://YOUR-NGROK-URL.ngrok-free.app" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "[shadow_telemetry] PID: $($proc.Id)"
Write-Host "[shadow_telemetry] Logs: logs/shadow_telemetry_stdout.log / shadow_telemetry_stderr.log"
