$logPath = "c:\Users\user\Music\Phenix\data\neocortex.log"
$log = Get-Content $logPath

# Extract all entropy values with timestamps
$ppo = $log | Select-String "PPO update complete"
$total = $ppo.Count
Write-Host "Total PPO updates: $total"

# Sample every 100th to show trajectory
Write-Host "`n=== ENTROPY TRAJECTORY (sampled) ==="
$step = [math]::Max(1, [math]::Floor($total / 30))
for ($i = 0; $i -lt $total; $i += $step) {
    $line = $ppo[$i].ToString()
    if ($line -match "(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})") { $ts = $matches[1] }
    if ($line -match "'entropy':\s*([\d.eE+-]+)") { $ent = $matches[1] }
    if ($line -match "'grad_norm':\s*([\d.eE+-]+)") { $gn = $matches[1] }
    if ($line -match "'policy_loss':\s*([-\d.eE+-]+)") { $pl = $matches[1] }
    Write-Host "PPO #$i  $ts  entropy=$ent  grad_norm=$gn  policy_loss=$pl"
}
# Always show last
$last = $ppo[-1].ToString()
if ($last -match "(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})") { $ts = $matches[1] }
if ($last -match "'entropy':\s*([\d.eE+-]+)") { $ent = $matches[1] }
if ($last -match "'grad_norm':\s*([\d.eE+-]+)") { $gn = $matches[1] }
Write-Host "PPO #$($total-1) (last)  $ts  entropy=$ent  grad_norm=$gn"

# Accuracy over time - first quarter vs last quarter
Write-Host "`n=== ACCURACY OVER TIME ==="
$settlements = $log | Select-String "Oracle settlement"
$sCount = $settlements.Count
$q = [math]::Floor($sCount / 4)

for ($qi = 0; $qi -lt 4; $qi++) {
    $start = $qi * $q
    $end = if ($qi -eq 3) { $sCount - 1 } else { ($qi + 1) * $q - 1 }
    $slice = $settlements[$start..$end]
    $cor = ($slice | Select-String "correct=True").Count
    $tot = $slice.Count
    $pct = [math]::Round(100 * $cor / $tot, 1)

    $firstLine = $slice[0].ToString()
    $lastLine = $slice[-1].ToString()
    $t1 = ""; $t2 = ""
    if ($firstLine -match "(\d{2}:\d{2}:\d{2})") { $t1 = $matches[1] }
    if ($lastLine -match "(\d{2}:\d{2}:\d{2})") { $t2 = $matches[1] }

    Write-Host "Q$($qi+1) ($t1-$t2): $cor/$tot = $pct%"
}

# Prediction distribution per quarter
Write-Host "`n=== PREDICTION EVOLUTION (per quarter) ==="
$classes = @("PREDICT_TREND_UP", "PREDICT_TREND_DOWN", "PREDICT_MEAN_REVERSION", "PREDICT_HIGH_VOLATILITY", "PREDICT_EXHAUSTION")
for ($qi = 0; $qi -lt 4; $qi++) {
    $start = $qi * $q
    $end = if ($qi -eq 3) { $sCount - 1 } else { ($qi + 1) * $q - 1 }
    $slice = $settlements[$start..$end]
    $tot = $slice.Count

    $firstLine = $slice[0].ToString()
    $t1 = ""
    if ($firstLine -match "(\d{2}:\d{2}:\d{2})") { $t1 = $matches[1] }

    Write-Host "Q$($qi+1) ($t1, n=$tot):"
    foreach ($cls in $classes) {
        $cnt = ($slice | Select-String "predicted=$cls").Count
        $pct = [math]::Round(100 * $cnt / $tot, 1)
        $short = $cls -replace "PREDICT_", ""
        Write-Host "  $($short): $cnt ($pct%)"
    }
}

# Confidence stats from shadow intents
Write-Host "`n=== SHADOW INTENT CONFIDENCE (last 50) ==="
$intents = $log | Select-String "Shadow Intent"
$lastIntents = $intents | Select-Object -Last 50
foreach ($intent in $lastIntents) {
    $line = $intent.ToString()
    if ($line -match "Shadow Intent: (\w+) \(conf=([-\d.]+), val=([-\d.]+)\)") {
        $regime = $matches[1]
        $conf = $matches[2]
        $val = $matches[3]
        if ($line -match "(\d{2}:\d{2}:\d{2})") { $ts = $matches[1] }
        Write-Host "$ts  $regime  conf=$conf  val=$val"
    }
}
