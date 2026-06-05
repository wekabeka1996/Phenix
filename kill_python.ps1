# Kill all Python processes
Write-Host "Killing all Python processes..." -ForegroundColor Yellow

# Kill python.exe processes
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        Write-Host "Terminating Python process: $($_.Id) - $($_.ProcessName)" -ForegroundColor Red
        Stop-Process -Id $_.Id -Force -ErrorAction Stop
        Write-Host "Successfully terminated process $($_.Id)" -ForegroundColor Green
    } catch {
        Write-Host "Process $($_.Id) already terminated or access denied" -ForegroundColor Yellow
    }
}

# Kill pythonw.exe processes (windowless Python)
Get-Process pythonw -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        Write-Host "Terminating PythonW process: $($_.Id) - $($_.ProcessName)" -ForegroundColor Red
        Stop-Process -Id $_.Id -Force -ErrorAction Stop
        Write-Host "Successfully terminated process $($_.Id)" -ForegroundColor Green
    } catch {
        Write-Host "Process $($_.Id) already terminated or access denied" -ForegroundColor Yellow
    }
}

Write-Host "Done killing Python processes." -ForegroundColor Green
