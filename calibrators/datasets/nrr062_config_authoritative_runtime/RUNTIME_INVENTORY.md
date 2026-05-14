# RUNTIME_INVENTORY

## Summary
| Metric | Value | Notes |
| --- | --- | --- |
| Bundle Root | logs/frozen/nrr062_fresh_capture_20260514_050245 | frozen capture root |
| order_log Window Start | 2026-05-11T15:10:03.413000+00:00 | earliest frozen order_log event timestamp |
| order_log Window End | 2026-05-14T04:55:09.316000+00:00 | latest frozen order_log event timestamp |
| order_log BOOT Rows | 9 | restart evidence within same cleared window |
| NRR-062 Rows | 227 | canonical reject cohort size |
| Accepted Intent Rows | 0 | frozen order_log non-rejected decision intents |
| Decision Ledger Rows | 416 | frozen shadow telemetry ledger rows |
| Decision Terminal Status Counts | {"EXECUTED_AND_CLOSED": 24, "INVALID_FOR_DATASET": 49, "REJECTED_UPSTREAM": 343} | diagnostics status surface |
| Trade Lifecycle Rows | 279119 | frozen lifecycle rows |
| Regime Audit Rows | 4929 | frozen regime confidence rows |
| Config Snapshot Required Present | 8 / 8 | config-authoritative freeze status |
| Recorder Coverage Sufficient | False | false because ETHUSDT horizon is incomplete |

## Symbols
BNBUSDT, BTCUSDT, ETHUSDT, XRPUSDT, _SYSTEM_

## Strategy IDs
aurora, md_amr

## Capture Integrity
- Active runtime processes observed pre-capture: python -m apps.reference.main, python -m apps.reference.domains.shadow_telemetry.main --config-dir config/aurora --host 127.0.0.1 --port 8443 --log-level INFO, python -m uvicorn apps.reference.api.main:app --host 127.0.0.1 --port 8000
- Source logs hot at capture: logs/aurora_core.log, data/recorder/2026-05-14/1000PEPEUSDT_180.csv, data/recorder/2026-05-14/BNBUSDT_180.csv, data/recorder/2026-05-14/BTCUSDT_180.csv, data/recorder/2026-05-14/DOGEUSDT_180.csv, data/recorder/2026-05-14/ETHUSDT_180.csv, data/recorder/2026-05-14/SOLUSDT_180.csv, data/recorder/2026-05-14/XRPUSDT_180.csv, logs/shadow_telemetry/decision_ledger_v1.jsonl, generated:FREEZE_REPORT.md
- Post-capture bundle remediation: copied logs/shadow_telemetry/decision_ledger_v1.jsonl into frozen bundle, generated FREEZE_REPORT.md at bundle root
