# CLOSE_SURFACE_RECONCILIATION_MATRIX

Generated at UTC: 2026-05-13T19:24:51.108866+00:00
Audit source kind: artifact_authority_snapshot
Source snapshot manifest: artifacts/calibration_datasets/_post_03t_multiday_realized_outcome/source_snapshot/source_snapshot_manifest.json

Total close-expected unmatched rows: 24
Recommended next package: 03T_RUNTIME_POSITION_CLOSED_EMISSION_REPAIR

## Dominant Axes

| axis | rows |
| --- | --- |
| runtime_surface_rows | 23 |
| builder_surface_rows | 0 |
| decision_ledger_surface_rows | 1 |
| inconclusive_rows | 0 |

## Bucket Matrix

| bucket | count | pct_of_13 | example_rids |
| --- | --- | --- | --- |
| ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | 16 | 66.6667 | aurora_ETHUSDT_1778512203285, aurora_BTCUSDT_1778512203705, aurora_BNBUSDT_1778512805536 |
| ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT | 7 | 29.1667 | aurora_XRPUSDT_1778512506317, aurora_XRPUSDT_1778513105442, aurora_BTCUSDT_1778552105915 |
| LIFECYCLE_ID_BRIDGE_AVAILABLE | 0 | 0.0 |  |
| TRADE_ID_BRIDGE_AVAILABLE | 0 | 0.0 |  |
| DECISION_LEDGER_REALIZED_ONLY | 1 | 4.1667 | aurora_BNBUSDT_1778682001038 |
| BUILDER_CANONICALIZATION_GAP | 0 | 0.0 |  |
| RUNTIME_LOGGING_GAP | 0 | 0.0 |  |
| INCONCLUSIVE | 0 | 0.0 |  |

## Recommendation Basis

- runtime-oriented buckets account for 23 / 24 close-expected unmatched rows
- 16 rows already prove closure in trade_lifecycle while canonical POSITION_CLOSED is absent
- 7 rows emit alternative terminal order events instead of canonical close emission
