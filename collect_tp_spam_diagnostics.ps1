# ===================================================================
# TP/SL SPAM DIAGNOSTICS COLLECTOR
# ===================================================================
# Zbyraye vsi neobkhidni artefakty dlya diahnostyky infinite loop breketiv
# Usage: .\collect_tp_spam_diagnostics.ps1 [-Symbol ETHUSDT] [-Lines 120]
# ===================================================================

param(
    [string]$Symbol = "ETHUSDT",
    [int]$Lines = 120
)

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outputFile = "diagnostics_tp_spam_${Symbol}_${timestamp}.txt"
$logsDir = "C:\Users\user\Music\Phenix\logs"

Write-Host "Collecting TP/SL spam diagnostics for $Symbol..." -ForegroundColor Cyan
Write-Host "Output: $outputFile" -ForegroundColor Yellow
Write-Host ""

# ===================================================================
# HEADER
# ===================================================================
@"
================================================================
TP/SL SPAM DIAGNOSTICS REPORT
================================================================
Symbol: $Symbol
Timestamp: $timestamp
Lines per section: $Lines
================================================================

"@ | Out-File $outputFile -Encoding UTF8

# ===================================================================
# SECTION 1: Runtime Events (execpos_v2_runtime.jsonl)
# ===================================================================
Write-Host "[1/5] Extracting Runtime Events (execpos_v2_runtime.jsonl)..." -ForegroundColor Green

@"

================================================================
SECTION 1: RUNTIME EVENTS (execpos_v2_runtime.jsonl)
================================================================
Shows: POSITION_SYNC, TRADE_EXECUTED, BRACKETS planning, actions
Pattern: $Symbol events with context
================================================================

"@ | Out-File $outputFile -Append -Encoding UTF8

try {
    $runtimeLog = Join-Path $logsDir "execpos_v2_runtime.jsonl"
    if (Test-Path $runtimeLog) {
        Get-Content $runtimeLog | Select-String -Pattern $Symbol -Context 1 | Select-Object -Last $Lines | Out-File $outputFile -Append -Encoding UTF8
        Write-Host "  Runtime events collected" -ForegroundColor Gray
    } else {
        "File not found: $runtimeLog" | Out-File $outputFile -Append -Encoding UTF8
        Write-Host "  File not found: execpos_v2_runtime.jsonl" -ForegroundColor Yellow
    }
} catch {
    "Error reading runtime log: $_" | Out-File $outputFile -Append -Encoding UTF8
    Write-Host "  Error: $_" -ForegroundColor Red
}

# ===================================================================
# SECTION 2: Decision Management (domain_execution_management.log)
# ===================================================================
Write-Host "[2/5] Extracting Decision Management logs..." -ForegroundColor Green

@"

================================================================
SECTION 2: DECISION MANAGEMENT (domain_execution_management.log)
================================================================
Shows: DEC:PLACE_ORDER, DEC:CANCEL_ORDER, BRACKETS, POSITION_SYNC
Pattern: $Symbol DEC emissions
================================================================

"@ | Out-File $outputFile -Append -Encoding UTF8

try {
    $decLog = Join-Path $logsDir "domain_execution_management.log"
    if (Test-Path $decLog) {
        $pattern = "${Symbol}.*(PLACE_ORDER|CANCEL_ORDER|BRACKETS|POSITION_SYNC|ACCOUNT_UPDATE)"
        Get-Content $decLog | Select-String -Pattern $pattern -Context 1 | Select-Object -Last $Lines | Out-File $outputFile -Append -Encoding UTF8
        Write-Host "  DEC logs collected" -ForegroundColor Gray
    } else {
        "File not found: $decLog" | Out-File $outputFile -Append -Encoding UTF8
        Write-Host "  File not found: domain_execution_management.log" -ForegroundColor Yellow
    }
} catch {
    "Error reading DEC log: $_" | Out-File $outputFile -Append -Encoding UTF8
    Write-Host "  Error: $_" -ForegroundColor Red
}

# ===================================================================
# SECTION 3: Adapter Execution (binance_execution_adapter.log)
# ===================================================================
Write-Host "[3/5] Extracting Adapter execution logs..." -ForegroundColor Green

@"

================================================================
SECTION 3: ADAPTER EXECUTION (binance_execution_adapter.log)
================================================================
Shows: Processing DEC:PLACE_ORDER, POST /fapi/v1/order, Order placed/FAILED
Pattern: $Symbol TP/SL orders to exchange
================================================================

"@ | Out-File $outputFile -Append -Encoding UTF8

try {
    $adapterLog = Join-Path $logsDir "binance_execution_adapter.log"
    if (Test-Path $adapterLog) {
        $pattern = "${Symbol}.*(PLACE_ORDER|TAKE_PROFIT|STOP_MARKET|Order FAILED|Order placed)"
        Get-Content $adapterLog | Select-String -Pattern $pattern -Context 1 | Select-Object -Last $Lines | Out-File $outputFile -Append -Encoding UTF8
        Write-Host "  Adapter logs collected" -ForegroundColor Gray
    } else {
        "File not found: $adapterLog" | Out-File $outputFile -Append -Encoding UTF8
        Write-Host "  File not found: binance_execution_adapter.log" -ForegroundColor Yellow
    }
} catch {
    "Error reading adapter log: $_" | Out-File $outputFile -Append -Encoding UTF8
    Write-Host "  Error: $_" -ForegroundColor Red
}

# ===================================================================
# SECTION 4: Configuration Snapshot
# ===================================================================
Write-Host "[4/5] Extracting Configuration..." -ForegroundColor Green

@"

================================================================
SECTION 4: CONFIGURATION SNAPSHOT
================================================================
Shows: aggregated_oco settings, trailing, close config for $Symbol
Source: config/domains/execution.yaml
================================================================

"@ | Out-File $outputFile -Append -Encoding UTF8

try {
    $configFile = "C:\Users\user\Music\Phenix\config\domains\execution.yaml"
    if (Test-Path $configFile) {
        Get-Content $configFile | Out-File $outputFile -Append -Encoding UTF8
        Write-Host "  Config extracted" -ForegroundColor Gray
    } else {
        "File not found: $configFile" | Out-File $outputFile -Append -Encoding UTF8
        Write-Host "  File not found: execution.yaml" -ForegroundColor Yellow
    }
} catch {
    "Error reading config: $_" | Out-File $outputFile -Append -Encoding UTF8
    Write-Host "  Error: $_" -ForegroundColor Red
}

# ===================================================================
# SECTION 5: State Summary (recent runtime state snapshots)
# ===================================================================
Write-Host "[5/5] Extracting State Snapshots..." -ForegroundColor Green

@"

================================================================
SECTION 5: STATE SNAPSHOTS (execpos_v2_runtime.jsonl)
================================================================
Shows: sl_count, tp_count, position state, bracket state
Pattern: $Symbol state dumps
================================================================

"@ | Out-File $outputFile -Append -Encoding UTF8

try {
    $runtimeLog = Join-Path $logsDir "execpos_v2_runtime.jsonl"
    if (Test-Path $runtimeLog) {
        $pattern = "${Symbol}.*(sl_count|tp_count|position_view|bracket_state)"
        Get-Content $runtimeLog | Select-String -Pattern $pattern -Context 2 | Select-Object -Last 80 | Out-File $outputFile -Append -Encoding UTF8
        Write-Host "  State snapshots collected" -ForegroundColor Gray
    } else {
        "Already reported as missing above" | Out-File $outputFile -Append -Encoding UTF8
    }
} catch {
    "Error reading state snapshots: $_" | Out-File $outputFile -Append -Encoding UTF8
    Write-Host "  Error: $_" -ForegroundColor Red
}

# ===================================================================
# FOOTER & STATISTICS
# ===================================================================
@"

================================================================
COLLECTION COMPLETE
================================================================
Generated: $timestamp
Output file: $outputFile
Total sections: 5
================================================================

ANALYSIS CHECKLIST:
----------------------------------------------------------------
[x] Section 1: Runtime planuye PLACE_SL/PLACE_TP kozhen ACCOUNT_UPDATE?
[x] Section 1: sl_count/tp_count zavzhdy 0 (ne bachyt isnuyuchykh)?
[x] Section 2: DEC dublyuyutsya (odnakovi rivni, bahato PLACE_ORDER)?
[x] Section 2: Chy ye CANCEL between PLACE, chy tilky PLACE?
[x] Section 3: Usi DEC diyshly do /fapi/v1/order?
[x] Section 3: Chy ye khvyli Order FAILED -> povtornyy PLACE?
[x] Section 4: aggregated_oco.enabled=true? Aggressive DR policy?
[x] Section 5: position.qty stabilnyy chy zminyuyetsya kozhen update?
================================================================

"@ | Out-File $outputFile -Append -Encoding UTF8

Write-Host ""
Write-Host "Diagnostics collection COMPLETE!" -ForegroundColor Green
Write-Host "Report saved to: $outputFile" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "   1. Open $outputFile in editor" -ForegroundColor White
Write-Host "   2. Review checklist at the end" -ForegroundColor White
Write-Host "   3. Share findings for root cause analysis" -ForegroundColor White
Write-Host ""
