# Snapshot ownership report

## Observed card ownership

- Global market: bounded portfolio journal fallback plus explicit missing market snapshots.
- BTCUSDT symbol market: stale bounded decision-ledger regime fallback; current close price missing.
- ETHUSDT symbol market: stale bounded decision-ledger regime fallback; current close price missing.
- Feature signals: missing current snapshot features for both requested symbols.
- Position life: fresh bounded portfolio journal fallback; no runtime lifecycle reconciliation.
- Business warnings: fresh bounded order-log tail; advisory only.
- Execution body: bounded decision trace plus missing runtime execution owner in the standalone API process.

No card family was proven to use an in-process runtime-owned market snapshot in this observation. The transport is operational, but the fresh BTCUSDT/ETHUSDT snapshot ownership gap remains real.

Opaque source refs and diagnostics made the source mode visible. Cockpit consumption required only HTTP responses; it did not access Aurora files.
