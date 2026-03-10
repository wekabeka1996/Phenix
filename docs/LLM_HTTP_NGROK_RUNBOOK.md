# LLM HTTP + ngrok Runbook

Shadow Telemetry API — Custom GPT Actions Exposure
Branch: `stable_11_11` | Last updated: 2026-03-04

---

## Executive Summary

The Shadow Telemetry service is a FastAPI process
(`apps.reference.domains.shadow_telemetry.main`) that serves:

* read-path market snapshots (`GET /snapshots/*`)
* write-path LLM trade intent ingress (`POST /intents/llm/v1`)

ngrok terminates TLS and provides a stable HTTPS URL that Custom GPT
Actions can call.  The local API runs on plain HTTP on `localhost:8443`
(TLS disabled for local dev; ngrok handles HTTPS end-to-end).  Bearer
authentication is required on the write endpoint and is enforced at the
application layer.

**Security model in one sentence:**
ngrok HTTPS → local HTTP → FastAPI bearer-auth + symbol-allowlist +
rate-limit + LIMIT_ONLY_POLICY → IPC → main Aurora process.

---

## Prerequisites Checklist

| Item | Command to verify |
|------|-------------------|
| Python ≥ 3.11 in `.venv` | `.venv\Scripts\python.exe --version` |
| pip deps installed | `.venv\Scripts\pip show fastapi uvicorn` |
| ngrok installed | `ngrok version` |
| ngrok authenticated | `ngrok config check` |
| Bearer token env var set | `echo %SHADOW_TELEMETRY_BEARER_TOKEN%` |
| Config: `tls: false` (see Step 2) | `grep tls config\aurora\domains.yaml` |

---

## Step-by-Step Setup

### Step 1 — Install ngrok (Windows)

**Option A: winget (recommended)**

```cmd
winget install ngrok.ngrok
```

**Option B: manual**

1. Download the Windows ZIP from https://ngrok.com/download
2. Extract `ngrok.exe` to a directory on your `PATH` (e.g. `C:\tools\`)
3. Verify: `ngrok version`

---

### Step 2 — Authenticate ngrok

```cmd
ngrok config add-authtoken YOUR_NGROK_AUTHTOKEN
```

Free tier provides one HTTPS tunnel.  Paid tier provides stable subdomains.

> **Stable subdomain (recommended for Custom GPT):** If you have a paid
> plan, reserve a subdomain and use `ngrok http --domain=your-sub.ngrok.app 8443`.
> This avoids having to update the OpenAPI `servers.url` on every restart.

---

### Step 3 — Disable local TLS (ngrok handles HTTPS)

The default config at `config/aurora/domains.yaml` has `tls: true`.
Because ngrok terminates TLS, the local API should run on plain HTTP.

Edit `config/aurora/domains.yaml`, find the `shadow_telemetry.api` block
and set `tls: false`:

```yaml
shadow_telemetry:
  api:
    host: "127.0.0.1"   # bind localhost-only; ngrok connects here
    port: 8443
    tls: false           # ngrok terminates TLS
```

> **Why localhost-only?** Binding `127.0.0.1` means only ngrok (running on
> the same machine) can reach the port. Do not bind `0.0.0.0` in
> production unless behind a firewall.

---

### Step 4 — Set the Bearer Token

Open a new cmd window (or add to your shell profile):

```cmd
set SHADOW_TELEMETRY_BEARER_TOKEN=your-secret-token-here
```

Rules:
* Minimum 32 characters recommended.
* Generate with: `.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"`
* The same token must be pasted into Custom GPT Actions → Authentication.
* To rotate: change the env var and restart the service; update Custom GPT auth.

Multiple tokens (e.g. separate CI token):

```cmd
set SHADOW_TELEMETRY_BEARER_TOKENS=token-one,token-two
```

---

### Step 5 — Activate the Virtual Environment

All commands below assume `.venv` is at the repo root.

```cmd
cd C:\Users\user\Music\Phenix
.venv\Scripts\activate
```

Verify:

```cmd
python --version
pip show uvicorn fastapi
```

---

### Step 6 — Start the Shadow Telemetry API

```cmd
python -m apps.reference.domains.shadow_telemetry.main ^
    --config-dir config/aurora ^
    --host 127.0.0.1 ^
    --port 8443 ^
    --log-level INFO
```

Expected startup log lines (look for ALL three):

```
ShadowTelemetry startup complete: ingest=tcp://127.0.0.1:7101 egress=tcp://127.0.0.1:7102 ...
Starting ShadowTelemetry API host=127.0.0.1 port=8443 tls=False ...
INFO:     Application startup complete.
```

> **Note:** The IPC ingest (`tcp://127.0.0.1:7101`) and egress
> (`tcp://127.0.0.1:7102`) sockets connect to the main Aurora process.
> If Aurora is not running, the API still starts but snapshots will be
> empty and IPC writes will queue/fail.  The `/health` endpoint remains
> available and reports `queue_depth`.

---

### Step 7 — Start the ngrok Tunnel

In a **separate** cmd window:

```cmd
ngrok http 8443
```

With a stable subdomain (paid plan):

```cmd
ngrok http --domain=your-sub.ngrok.app 8443
```

ngrok prints a forwarding URL, e.g.:

```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8443
```

Copy the HTTPS URL — this is your `NGROK_URL`.

---

### Step 8 — Update OpenAPI servers.url

Open `docs/LLM_ACTIONS_OPENAPI.yaml` and replace the placeholder:

```yaml
servers:
  - url: https://YOUR-NGROK-URL.ngrok-free.app
    description: ngrok HTTPS tunnel (update on each restart)
```

Then re-paste the updated YAML into Custom GPT Actions (see Operator
Procedure below).

**CLI helper (print current ngrok public URL):**

```cmd
curl -s http://localhost:4040/api/tunnels | .venv\Scripts\python.exe -c ^
"import sys,json; t=json.load(sys.stdin)['tunnels']; print(t[0]['public_url'])"
```

ngrok exposes a local inspect UI at http://localhost:4040 which also
lists all active tunnels.

---

### Step 9 — Smoke Tests

Replace `NGROK_URL` with your actual ngrok URL and `TOKEN` with your bearer token.

**9a. Health check (no auth required)**

```cmd
curl -s https://NGROK_URL/health
```

Expected response:

```json
{"status":"healthy","service":"shadow_telemetry","ts_ms":...,"queue_depth":0}
```

**9b. Latest snapshot**

```cmd
curl -s "https://NGROK_URL/snapshots/latest?symbol=BNBUSDT"
```

Returns `404` if no snapshot has arrived yet (Aurora not publishing).
Returns snapshot JSON when Aurora is running and publishing.

**9c. Snapshot tail**

```cmd
curl -s "https://NGROK_URL/snapshots/tail?symbol=BNBUSDT&limit=5"
```

Expected:

```json
{"items": [...], "next_cursor": null}
```

**9d. POST intent (write path)**

Minimal valid payload (adapt symbol, price, qty to current market):

```cmd
curl -s -X POST "https://NGROK_URL/intents/llm/v1" ^
  -H "Authorization: Bearer TOKEN" ^
  -H "Content-Type: application/json" ^
  -H "Idempotency-Key: test-001" ^
  -d "{\"symbol\":\"BNBUSDT\",\"side\":\"BUY\",\"order\":{\"type\":\"LIMIT\",\"limit_price\":\"600.00\",\"qty\":\"0.01\"},\"why_short\":\"smoke test\"}"
```

Expected 202 response:

```json
{"intent_id":"...","request_id":"...","state":"queued"}
```

**PowerShell equivalent (9d):**

```powershell
$body = @{
    symbol     = "BNBUSDT"
    side       = "BUY"
    order      = @{ type = "LIMIT"; limit_price = "600.00"; qty = "0.01" }
    why_short  = "smoke test"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method POST `
  -Uri "https://NGROK_URL/intents/llm/v1" `
  -Headers @{ Authorization = "Bearer TOKEN"; "Idempotency-Key" = "ps-test-001" } `
  -ContentType "application/json" `
  -Body $body
```

---

## Stopping the Services

1. In the uvicorn window: `Ctrl+C`
2. In the ngrok window: `Ctrl+C`

---

## Rotating the ngrok URL

Free-tier ngrok assigns a new URL on every start.

After a restart:

1. Copy the new HTTPS URL from the ngrok console.
2. Edit `docs/LLM_ACTIONS_OPENAPI.yaml` → `servers[0].url`.
3. In Custom GPT → Configure → Actions → Edit the action schema → paste
   the updated YAML → Save.

To avoid this churn: upgrade to ngrok paid and use `--domain`.

---

## Security Notes

| Topic | Rule |
|-------|------|
| Bearer token placement | Header only: `Authorization: Bearer <token>`. Never in URL query params. |
| Token storage | Store in OS secrets manager or `.env` (git-ignored). Never commit to repo. |
| Symbol allowlist | Only symbols in `config/aurora/domains.yaml → shadow_telemetry.api.write.symbol_allowlist` are accepted. Currently: `["BNBUSDT"]`. |
| Endpoint exposure | ngrok forwards ALL paths on port 8443. The only paths that exist are `/health`, `/snapshots/latest`, `/snapshots/tail`, `/intents/llm/v1`, `/intents/status`. No file-browsing or debug endpoints. |
| Rate limiting | 30 requests/min per auth subject (configurable in config). |
| LIMIT_ONLY_POLICY | `allow_limit_only: true` — market orders rejected at the application layer. |
| TLS | ngrok provides TLS 1.3. Local transport is HTTP on loopback only. |
| x-openai-isConsequential | `true` on POST endpoint — Custom GPT will prompt the user before executing. |

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `uvicorn` crashes at startup: `TLS enabled but cert/key are missing` | `tls: true` in config but no cert env vars | Set `tls: false` in `config/aurora/domains.yaml` (Step 3) |
| `uvicorn` crashes: `No bearer tokens configured` | `SHADOW_TELEMETRY_BEARER_TOKEN` not set | `set SHADOW_TELEMETRY_BEARER_TOKEN=...` before starting |
| `curl: (7) Failed to connect` to ngrok URL | ngrok not running or URL changed | Restart ngrok, copy new URL |
| HTTP 401 `AUTH_MISSING` | No `Authorization` header in request | Add `Authorization: Bearer TOKEN` header |
| HTTP 401 `AUTH_SCHEME_INVALID` | Using `Basic` or no scheme prefix | Use `Bearer` scheme |
| HTTP 403 `AUTH_FORBIDDEN` | Wrong token | Check env var matches Custom GPT secret |
| HTTP 400 `SCHEMA_INVALID` | Malformed JSON or missing required field | Check schema: `symbol`, `side`, `order.limit_price`, `order.qty`, `why_short` are required |
| HTTP 400 `SYMBOL_NOT_ALLOWED` | Symbol not in allowlist or not in LLM orchestration symbols | Add symbol to `symbol_allowlist` in config; restart |
| HTTP 429 | Rate-limit (30/min per auth token) | Wait 60 s or use different token subject |
| HTTP 409 `IDEMPOTENCY_CONFLICT` | Same `Idempotency-Key` with different payload | Use a new unique `Idempotency-Key` |
| HTTP 503 `IPC_UNAVAILABLE` | Aurora main process not running or IPC endpoint unreachable | Start Aurora; check `tcp://127.0.0.1:7102` is listening |
| HTTP 503 `IPC_QUEUE_OVERFLOW` | Command queue full (overflow_policy: fail_closed) | Aurora command consumer is slow; check Aurora logs |
| HTTP 503 `AUTH_NOT_CONFIGURED` | Write enabled but auth_tokens set is empty at runtime | Restart with correct `SHADOW_TELEMETRY_BEARER_TOKEN` |
| `GET /snapshots/latest` returns 404 | No snapshot written yet | Wait for Aurora to publish `EVT:FEATURES_CALCULATED` events |
| ngrok `ERR_NGROK_3004` | Auth token invalid or expired | Re-run `ngrok config add-authtoken ...` |
| ngrok `ERR_NGROK_108` | Tunnel limit reached (free tier = 1) | Stop other ngrok tunnels or upgrade plan |
| Custom GPT "Action failed" with no status | Request timed out | Check uvicorn is running; retry |
| Config mismatch: symbol rejected | `symbol_allowlist` in config doesn't include the symbol you sent | Edit `config/aurora/domains.yaml`, restart service |

---

## IPC Dependency Map

```
Custom GPT
    │  HTTPS
    ▼
ngrok (TLS termination)
    │  HTTP
    ▼
Shadow Telemetry API  :8443
    │  TCP JSONL                   │  TCP JSONL
    ▼                              ▼
Aurora ingest tap            Aurora command ingress
tcp://127.0.0.1:7101         tcp://127.0.0.1:7102
(read-path: events in)       (write-path: intents out)
```

Shadow Telemetry does NOT require the ingest tap to be live in order to
accept POST intents.  The write path uses `7102` (egress).  If
`queue_depth` on `/health` grows unboundedly, the Aurora command consumer
on `7102` is not draining.

---

## Custom GPT Operator Procedure

### A. Create or Update the Custom GPT

1. Go to https://chatgpt.com → top-left menu → **My GPTs** → **Create a GPT**
   (or open an existing GPT and click **Edit**).
2. In the **Configure** tab, fill in Name and Description.
3. Scroll to **Actions** → click **Create new action** (or **Edit** if one exists).

---

### B. Paste the OpenAPI Schema

1. Open `docs/LLM_ACTIONS_OPENAPI.yaml` in any text editor.
2. Replace the placeholder in `servers[0].url`:
   ```yaml
   servers:
     - url: https://abc123.ngrok-free.app
   ```
   with your actual current ngrok URL.
3. In the Custom GPT Actions editor, select **Schema** tab.
4. Paste the full YAML content.
5. Click **Format** — the editor should show green checkmarks for all paths.

---

### C. Set Authentication

1. In the Actions editor, click **Authentication**.
2. Select **API Key**.
3. Set **Auth Type** to `Bearer`.
4. Paste your bearer token (same value as `SHADOW_TELEMETRY_BEARER_TOKEN`).
5. Click **Save**.

> **Security:** The token is stored encrypted by OpenAI. Never paste it
> into the schema itself or the GPT system prompt.

---

### D. Test Actions Inside Custom GPT

Use the **Test** button in the Actions editor (top-right) to run:

**Test 1 — Health (no auth)**

```
GET /health
```

Expected: `{"status":"healthy",...}`
If this fails: ngrok tunnel is down or wrong URL in schema.

**Test 2 — Latest Snapshot**

```
GET /snapshots/latest?symbol=BNBUSDT
```

Expected: JSON snapshot object with `snapshot_id`.
If 404: Aurora is not running / not publishing snapshots yet.

**Test 3 — Post Intent (consequential)**

The GPT editor will show a confirmation prompt before executing because
`x-openai-isConsequential: true` is set.

Provide a sample body:

```json
{
  "symbol": "BNBUSDT",
  "side": "BUY",
  "order": {"type": "LIMIT", "limit_price": "600.50", "qty": "0.01"},
  "brackets": {"tp_price": "620.00", "sl_price": "590.00"},
  "snapshot_ref": {"snapshot_id": "snap-abc123", "inputs_digest": "abcdef12"},
  "why_short": "operator smoke test",
  "idempotency_key": "ops-test-20260304-001"
}
```

Expected: HTTP 202 `{"intent_id":"...","request_id":"...","state":"queued"}`

If HTTP 400 `SNAPSHOT_REF_REQUIRED`: first call GET /snapshots/latest,
use the real `snapshot_id` from the response.

---

### E. Recommended GPT System Prompt Fragment

Add to the Custom GPT system prompt to guide behavior:

```
You are a trading assistant for the Aurora system.
Before submitting any trade intent:
1. Call getLatestSnapshot to get current market context and snapshot_id.
2. Confirm the intent with the user (symbol, side, price, qty, rationale).
3. Only then call submitLLMIntent with snapshot_ref populated.
4. Always use LIMIT orders. MARKET orders are rejected by policy.
5. Include a concise why_short (max 80 chars) explaining the trade rationale.
```

---

### F. Rotating the Token in Custom GPT

1. Generate a new token: `.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"`
2. Update `SHADOW_TELEMETRY_BEARER_TOKEN` env var on the server.
3. Restart the Shadow Telemetry service.
4. In Custom GPT → Configure → Actions → Authentication → update the token.
5. Test with GET /health to confirm connectivity.

Old token is immediately invalid after service restart.
