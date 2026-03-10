$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $scriptDir 'monitoring\restart_shadow_telemetry.ps1') @args
