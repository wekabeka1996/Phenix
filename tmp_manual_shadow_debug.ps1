$ErrorActionPreference='Stop'
$baseNgrok='https://unfrictionally-polyvinylidene-alyvia.ngrok-free.dev'
$baseLocal='http://127.0.0.1:8443'

$token=$env:SHADOW_TELEMETRY_BEARER_TOKEN
if(-not $token){ $token=$env:AURORA_SHADOW_TELEMETRY_BEARER_TOKEN }
if(-not $token -and $env:SHADOW_TELEMETRY_BEARER_TOKENS){
  $token=($env:SHADOW_TELEMETRY_BEARER_TOKENS -split ',')[0].Trim()
}
if(-not $token){
  Write-Output 'NO_TOKEN_IN_ENV'
  exit 0
}

function ErrBody($e){
  if($e.Exception.Response){
    $r=New-Object IO.StreamReader($e.Exception.Response.GetResponseStream())
    return $r.ReadToEnd()
  }
  return ''
}

function HashHex([string]$t){
  $sha=[Security.Cryptography.SHA256]::Create()
  $b=[Text.Encoding]::UTF8.GetBytes($t)
  return ([BitConverter]::ToString($sha.ComputeHash($b))).Replace('-','').ToLowerInvariant()
}

$snap=Invoke-RestMethod -Uri ($baseLocal+'/snapshots/latest?symbol=1000PEPEUSDT') -Method Get
$src=[ordered]@{
  snapshot_id=[string]$snap.snapshot_id
  symbol=[string]$snap.symbol
  ts_ms=[int64]$snap.ts_ms
  features=$snap.features
  bar=$snap.bar
} | ConvertTo-Json -Depth 20 -Compress
$digest=HashHex $src
$ref=[decimal]$snap.bar.close
$payload=[ordered]@{
  intent_id=[guid]::NewGuid().ToString()
  ts_ms=[int64][DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  symbol='1000PEPEUSDT'
  side='SELL'
  order=[ordered]@{
    type='LIMIT'
    limit_price=([string]::Format([Globalization.CultureInfo]::InvariantCulture,'{0:F8}',$ref))
    qty='1000'
    time_in_force='GTC'
  }
  brackets=[ordered]@{
    tp_price=([string]::Format([Globalization.CultureInfo]::InvariantCulture,'{0:F8}',($ref*[decimal]'0.9970')))
    sl_price=([string]::Format([Globalization.CultureInfo]::InvariantCulture,'{0:F8}',($ref*[decimal]'1.0015')))
  }
  snapshot_ref=[ordered]@{
    snapshot_id=[string]$snap.snapshot_id
    inputs_digest=$digest
  }
  model_meta=[ordered]@{
    model='manual_debug'
    temperature=0.0
    prompt_hash='manualdebug0000000000000000000000'
  }
  why_short='manual debug post'
  idempotency_key=('manual-'+[guid]::NewGuid().ToString())
} | ConvertTo-Json -Depth 20 -Compress
$headers=@{
  Authorization=('Bearer '+$token)
  'Content-Type'='application/json'
}

'LOCAL_POST_BEGIN'
try {
  $r=Invoke-WebRequest -Uri ($baseLocal+'/intents/llm/v1') -Method Post -Headers $headers -Body $payload
  'LOCAL_STATUS='+$r.StatusCode
  $r.Content
} catch {
  'LOCAL_ERROR='+$_.Exception.Message
  ErrBody $_
}

'NGROK_POST_BEGIN'
try {
  $r=Invoke-WebRequest -Uri ($baseNgrok+'/intents/llm/v1') -Method Post -Headers $headers -Body $payload
  'NGROK_STATUS='+$r.StatusCode
  $r.Content
} catch {
  'NGROK_ERROR='+$_.Exception.Message
  ErrBody $_
}
