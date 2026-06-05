$logPath = "c:\Users\user\Music\Phenix\data\neocortex.log"
$cpPath = "c:\Users\user\Music\Phenix\data\checkpoints"

# --- LOG BASICS ---
$log = Get-Content $logPath -ErrorAction SilentlyContinue
if (-not $log) { Write-Host "ERROR: neocortex.log not found or empty"; exit 1 }

$lineCount = $log.Count
Write-Host "=== LOG BASICS ==="
Write-Host "Total lines: $lineCount"
Write-Host "First 5 lines:"
$log | Select-Object -First 5
Write-Host "---"
Write-Host "Last 5 lines:"
$log | Select-Object -Last 5

# --- CHECKPOINTS ---
Write-Host "`n=== CHECKPOINTS ==="
$cp = Get-ChildItem $cpPath -ErrorAction SilentlyContinue
$cpCount = ($cp | Measure-Object).Count
Write-Host "Checkpoint files: $cpCount"
if ($cp) {
    $cp | Sort-Object LastWriteTime | Select-Object Name, @{N='SizeKB';E={[math]::Round($_.Length/1024)}}, LastWriteTime | Format-Table -AutoSize
}

# --- SETTLEMENTS ---
Write-Host "=== SETTLEMENTS ==="
$settlements = $log | Select-String "Oracle settlement"
$settCount = $settlements.Count
Write-Host "Total settlements: $settCount"
if ($settCount -gt 0) {
    Write-Host "First settlement:"
    $settlements[0]
    Write-Host "Last settlement:"
    $settlements[-1]
}

if ($settCount -eq 0) { Write-Host "No settlements found, exiting."; exit 0 }

# --- REWARD VALUES ---
Write-Host "`n=== REWARD VALUES ==="
$r02 = 0; $r05 = 0; $rNeg1 = 0; $rOther = 0
foreach ($s in $settlements) {
    if ($s -match "reward=([-\d.]+)") {
        $r = $matches[1]
        if ($r -eq "0.200") { $r02++ }
        elseif ($r -eq "0.500") { $r05++ }
        elseif ($r -eq "-1.000") { $rNeg1++ }
        else { $rOther++ }
    }
}
Write-Host "reward=0.200 (new MR correct): $r02"
Write-Host "reward=0.500 (old MR correct): $r05"
Write-Host "reward=-1.000 (harsh penalty): $rNeg1"
Write-Host "reward=other: $rOther"

# --- PREDICTION DISTRIBUTION ---
Write-Host "`n=== PREDICTION DISTRIBUTION ==="
$predMap = @{}
foreach ($s in $settlements) {
    if ($s -match "predicted=(PREDICT_\w+)") {
        $p = $matches[1]
        if (-not $predMap.ContainsKey($p)) { $predMap[$p] = 0 }
        $predMap[$p]++
    }
}
foreach ($k in ($predMap.GetEnumerator() | Sort-Object Value -Descending)) {
    $pct = [math]::Round(100 * $k.Value / $settCount, 1)
    Write-Host "$($k.Name): $($k.Value) ($pct%)"
}

# --- REALIZED DISTRIBUTION ---
Write-Host "`n=== REALIZED DISTRIBUTION ==="
$realMap = @{}
foreach ($s in $settlements) {
    if ($s -match "realized=(PREDICT_\w+)") {
        $p = $matches[1]
        if (-not $realMap.ContainsKey($p)) { $realMap[$p] = 0 }
        $realMap[$p]++
    }
}
foreach ($k in ($realMap.GetEnumerator() | Sort-Object Value -Descending)) {
    $pct = [math]::Round(100 * $k.Value / $settCount, 1)
    Write-Host "$($k.Name): $($k.Value) ($pct%)"
}

# --- ACCURACY ---
Write-Host "`n=== ACCURACY ==="
$correct = ($settlements | Select-String "correct=True").Count
$wrong = ($settlements | Select-String "correct=False").Count
$accPct = if ($settCount -gt 0) { [math]::Round(100 * $correct / $settCount, 1) } else { 0 }
Write-Host "Correct: $correct ($accPct%)"
Write-Host "Wrong: $wrong"

# --- PPO UPDATES ---
Write-Host "`n=== PPO UPDATES ==="
$ppo = $log | Select-String "PPO update"
Write-Host "PPO updates: $($ppo.Count)"
if ($ppo.Count -gt 0) {
    Write-Host "First PPO:"
    $ppo[0]
    Write-Host "Last PPO:"
    $ppo[-1]
}

# --- ENTROPY ---
Write-Host "`n=== ENTROPY ==="
$entropy = $log | Select-String "entropy"
if ($entropy.Count -gt 0) {
    Write-Host "Total entropy lines: $($entropy.Count)"
    Write-Host "First:"
    $entropy[0]
    Write-Host "Last:"
    $entropy[-1]

    # Sample entropy values
    $entVals = @()
    foreach ($e in $entropy) {
        if ($e -match "entropy[=:]\s*([\d.eE+-]+)") {
            $entVals += [double]$matches[1]
        }
    }
    if ($entVals.Count -gt 0) {
        $entMin = ($entVals | Measure-Object -Minimum).Minimum
        $entMax = ($entVals | Measure-Object -Maximum).Maximum
        $entAvg = ($entVals | Measure-Object -Average).Average
        Write-Host "Entropy min: $entMin  max: $entMax  avg: $([math]::Round($entAvg, 6))"
    }
} else {
    Write-Host "No entropy lines found"
}

# --- SHADOW INTENTS ---
Write-Host "`n=== SHADOW INTENTS (last 5) ==="
$intents = $log | Select-String "Shadow Intent"
Write-Host "Total shadow intents: $($intents.Count)"
if ($intents.Count -gt 0) {
    $intents | Select-Object -Last 5 | ForEach-Object { $_ }
}

# --- ERRORS ---
Write-Host "`n=== ERRORS ==="
$errors = $log | Select-String "ERROR|Exception|Traceback"
Write-Host "Error lines: $($errors.Count)"
if ($errors.Count -gt 0) {
    $errors | Select-Object -First 10 | ForEach-Object { $_ }
}

Write-Host "`n=== ANALYSIS COMPLETE ==="
