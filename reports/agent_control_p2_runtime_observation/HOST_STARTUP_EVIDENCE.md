# Host startup evidence

## Aurora

Command shape:

`TRADING_ENV=development python -m uvicorn apps.reference.api.main:app --host 127.0.0.1 --port 18080 --log-level info`

Initial PID: 19772. Recovery PID after the deliberate failure-visibility check: 21556. Uvicorn logged successful application startup and listened on `127.0.0.1:18080`.

The development host warned that RBAC/signing development defaults were in use. This observation therefore proves local runtime behavior only and is not production security approval.

## Cockpit

Command shape:

`node --import tsx scripts/p2-agent-feed-observation-host.ts`

Port: 18081. PID: 12736.

Non-secret environment used:

- `NODE_ENV=production`
- `APP_URL=http://127.0.0.1:18081`
- `PHENIX_CORE_API_URL=http://127.0.0.1:18080`
- `PHENIX_SHADOW_API_URL=http://127.0.0.1:18080`
- `PHENIX_TRADING_SYMBOL=BTCUSDT`
- `PHENIX_TRADING_SYMBOLS=BTCUSDT,ETHUSDT`
- `ALLOW_LOCAL_WORKSPACE_BRIDGE=false`
- `P2_COCKPIT_PORT=18081`

No credential or secret value was read, printed, or changed. Cockpit logged `Trading agent initialized`, while its state endpoint proved `armed=false` and `status=stopped`.

The initial production launch attempt failed because `APP_URL` was absent. Adding the required non-secret URL resolved the environment blocker. Ports 7102 and 8443 were never listeners or targets for this package.
