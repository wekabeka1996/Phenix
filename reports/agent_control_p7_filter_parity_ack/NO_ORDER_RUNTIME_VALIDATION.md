# No-order runtime validation

Environment: `AURORA_RUNTIME_PROFILE=agent_bridge_observation_only`.

Commands:

```text
.venv/Scripts/python.exe -m apps.reference.main
.venv/Scripts/python.exe -m uvicorn apps.reference.api.main:app --host 127.0.0.1 --port 18080
PORT=18081 PHENIX_CORE_API_URL=http://127.0.0.1:18080 npx tsx server.ts
npx tsx scripts/p2-observe-agent-feed.ts
```

Observed runtime:

- Aurora log: `execution_submission=false`, `consequential_listeners=false`, `adapter=None`.
- Public exchange-info cache: testnet, successful unsigned public refresh.
- Read host: 127.0.0.1:18080; Cockpit: 18081.
- Cockpit: `armed=false`, `status=stopped`.
- Cockpit target: 18080 only; no Cockpit connection to 7102 or 8443.
- Ten packet requests: GET, ten HTTP 200.
- Final bounded P7 logs: zero order/create/place/cancel/modify/amend and zero signing/authentication matches.

The Aurora process itself owns its pre-existing internal 7102 listener; the read bridge and Cockpit do not target it.
