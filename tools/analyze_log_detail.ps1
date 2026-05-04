$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $scriptDir 'monitoring\analyze_log_detail.ps1') @args
