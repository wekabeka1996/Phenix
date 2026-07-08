# No-order runtime validation

Profile: `AURORA_RUNTIME_PROFILE=agent_bridge_observation_only`.

Commands:

```text
.venv/Scripts/python.exe -m apps.reference.main
.venv/Scripts/python.exe -m uvicorn apps.reference.api.main:app --host 127.0.0.1 --port 18080
PORT=18081 PHENIX_CORE_API_URL=http://127.0.0.1:18080 npx tsx server.ts
npx tsx scripts/p2-observe-agent-feed.ts
```

Observed:

- P8 publisher active; public testnet exchange-info fresh; parity history/ack loader active.
- Runtime acknowledgement file absent by design.
- Aurora log: execution submission false, consequential listeners false, adapter absent.
- Read host 18080; Cockpit 18081; Cockpit `armed=false`, `status=stopped`.
- Ten GET polls succeeded and persisted.
- Cockpit targeted 18080 only; it did not connect to 7102 or 8443.
- Runtime log scan: zero order/create/place/cancel/modify/amend and signed/authenticated request matches.

Aurora's internal existing 7102 listener was not used by AgentFeed or Cockpit.
