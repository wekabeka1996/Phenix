# Runtime observation log

Observation date: 2026-06-29, Europe/Minsk.

1. Confirmed Aurora main and its fresh feature mirror were active. Did not restart main processes.
2. Added and tested the main event-bus publisher plus safe mirror relay.
3. Ran one-shot relay; it published BTCUSDT/ETHUSDT from a 245 MB mirror using a bounded 2 MiB / 1,000-line tail.
4. Started relay watch, Aurora read host on 18080, and Cockpit on 18081.
5. Confirmed the atomic directory contained market, readiness, and index files with no temp residue.
6. Ran ten Cockpit→Aurora GET packet polls. All returned 200 and were persisted.
7. Confirmed Cockpit remained `armed=false`, `status=stopped`.
8. Confirmed `/economics` served HTTP 200. Rendered-browser inspection was unavailable because browser discovery returned `[]`.
9. Observed a normal mirror update; relay atomically refreshed all publication files. No source log rotation occurred.
10. No POST/PATCH/DELETE, 7102 bridge use, 8443 bridge use, dispatch, execution submit, order, runtime restart, or WAL deletion occurred.

The user's restart rule is recorded: if a future restart is necessary, delete only `ops/wal/*.json` before it. It was not triggered in P3.
