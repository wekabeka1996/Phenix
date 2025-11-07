#!/usr/bin/env pwsh
# Quick testnet startup script for Windows PowerShell

Write-Host "
╔════════════════════════════════════════════════════════════════╗
║          🚀 AURORA FSM TESTNET DEPLOYMENT                     ║
║              Status: 100% READY                                ║
╚════════════════════════════════════════════════════════════════╝
" -ForegroundColor Cyan

# Step 1: Verify configuration
Write-Host "[1/3] Verifying configuration..." -ForegroundColor Yellow
.venv/Scripts/python.exe verify_config.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Config verification failed!" -ForegroundColor Red
    exit 1
}

# Step 2: Run pre-flight checks
Write-Host "`n[2/3] Running pre-flight checks..." -ForegroundColor Yellow
.venv/Scripts/python.exe test_testnet_checks.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Pre-flight checks failed!" -ForegroundColor Red
    exit 1
}

# Step 3: Launch system
Write-Host "`n[3/3] Starting Aurora FSM on testnet..." -ForegroundColor Green
Write-Host "
📋 Quick Reference:
  - Mode: testnet (signal_threshold=0.15, kelly_boost=1.2)
  - Logs: Watch for [mode-resolver], REGIME_DETECTED, DECISION_EVAL
  - Success: Orders placed as MARKET with SL/TP brackets
  - Guide: See LOG_INVESTIGATION_GUIDE.md
" -ForegroundColor Cyan

.venv/Scripts/python.exe apps/reference/main.py
