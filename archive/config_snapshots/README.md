# Archived Config Snapshots

These directories are **NOT loaded by runtime**. They are historical snapshots
preserved for reference only.

## aurora_baseline/

- **Original path:** `config/aurora_baseline/`
- **Archived:** 2026-03-14
- **Was it ever used in runtime?** No. Zero code references found — no loader, test, CI, or deployment script ever targeted this directory.
- **Historical meaning:** Pre-Phase-9 snapshot of the Aurora config tree. Created by an agent as a frozen baseline before the Quadratic Brain migration and multi-strategy diversification began. Represents the "all symbols on aurora-only, backtest mode, generic template weights" state.
- **Key differences from active `config/aurora/`:** backtest-only mode, all symbols assigned to aurora strategy, no absorption/shadow_telemetry/objective_engine, template weights (not calibrated), conservative TTLs and thresholds.

## mean_reversion/

- **Original path:** `config/mean_reversion/`
- **Archived:** 2026-03-14
- **Was it ever used in runtime?** No. Zero code references found — no loader, test, CI, or deployment script ever targeted this directory.
- **Historical meaning:** Isolated MR backtest profile created by an agent for testing the mean-reversion strategy in isolation. Only assigned DOGE + 1000PEPE to mean_reversion, kept all other symbols on aurora with template weights.
- **Key differences from active `config/aurora/`:** backtest-only mode, only 2 symbols, no squeeze/momentum veto filters, no objective engine, conservative BB parameters, BTC/XRP MR enabled (disabled in active config).

## Policy

Do **not** move these back into `config/`. The canonical runtime SSOT is
`config/aurora/` — see `config/README.md`.
