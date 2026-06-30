# Runtime observation log

Observation date: 2026-06-28, Europe/Minsk. All requests were local HTTP GET requests.

1. Verified ports 18080 and 18081 were free. Verified Uvicorn 0.41.0 was available.
2. Started Aurora FastAPI on `127.0.0.1:18080`. `GET /agent-feed/v0/health` returned 200 and `read_only=true`.
3. First Cockpit production launch failed closed because `APP_URL` was missing. No HTTP listener or request resulted.
4. Restarted Cockpit with the required non-secret environment and the reproducible P2 startup helper. Cockpit listened on `0.0.0.0:18081`, initialized the trading agent with `armed=false`, and reported provider profiles as not configured.
5. Ran 10 sequential polls through `GET http://127.0.0.1:18081/api/agent-feed/v0/packet`, requesting BTCUSDT and ETHUSDT. Cockpit forwarded each poll to Aurora over the approved GET endpoint.
6. All 10 polls returned 200. Samples were written to `samples/runtime_agent_feed_packets.jsonl`.
7. Verified SQLite rows increased from 0 to 10 and latest packet id matched the tenth response.
8. Requested the dedicated execution-readiness endpoint. It returned 200 and `runtime_available=false` because the standalone API process did not own initialized `ExecPosFSM` state.
9. Verified Cockpit remained `armed=false`, `status=stopped`.
10. Attempted in-app UI inspection. No browser surface was available in this session (`[]`). Production `/economics` delivery returned 200 with a 653-byte SPA shell.
11. Stopped Aurora temporarily and repeated the Cockpit packet GET. Cockpit returned visible HTTP 502 with `{"error":"fetch failed","read_only":true}`. SQLite remained at 10 rows.
12. Restarted Aurora and verified recovery health returned 200.
13. No POST, PATCH, DELETE, port 7102, port 8443, execution submit, dispatch, or order call was used.
