#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Запуск QuantumTraderX testnet у shadow mode

.DESCRIPTION
    Активує venv та запускає систему через python -m apps.reference.main
    Можна закрити VS Code після запуску — система працює у терміналі.

.EXAMPLE
    .\start_testnet.ps1

.NOTES
    Ctrl+C для зупинки
#>

# Перевірка директорії
$ProjectRoot = $PSScriptRoot
if (-not (Test-Path "$ProjectRoot\.venv\Scripts\Activate.ps1")) {
    Write-Host "❌ ERROR: venv not found in $ProjectRoot\.venv" -ForegroundColor Red
    Write-Host "Run: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

# Перехід в project root
Set-Location $ProjectRoot
Write-Host "📂 Working directory: $ProjectRoot" -ForegroundColor Cyan

# Активація venv
Write-Host "🔧 Activating venv..." -ForegroundColor Green
& "$ProjectRoot\.venv\Scripts\Activate.ps1"

# Перевірка Python
$PythonPath = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonPath) {
    Write-Host "❌ ERROR: Python not found in venv" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Python: $($PythonPath.Source)" -ForegroundColor Green

# Вивід інфо
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "🚀 Starting QuantumTraderX Testnet (Shadow Mode)" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "Mode:     Shadow (read-only, no real trades)" -ForegroundColor White
Write-Host "Network:  Binance Futures TESTNET" -ForegroundColor White
Write-Host "Logs:     logs\domain_execution_management.log" -ForegroundColor White
Write-Host ""
Write-Host "🛑 Press Ctrl+C to stop" -ForegroundColor Red
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

# Запуск системи
try {
    python -m apps.reference.main
} catch {
    Write-Host ""
    Write-Host "❌ ERROR: System crashed" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    exit 1
} finally {
    Write-Host ""
    Write-Host "🛑 System stopped" -ForegroundColor Yellow
}
