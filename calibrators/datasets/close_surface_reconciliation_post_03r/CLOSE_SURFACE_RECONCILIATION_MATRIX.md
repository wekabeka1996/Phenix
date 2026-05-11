# CLOSE_SURFACE_RECONCILIATION_MATRIX

Generated at UTC: 2026-05-10T19:33:43.251528+00:00
Audit source kind: artifact_authority_snapshot
Source snapshot manifest: artifacts/calibration_datasets/_post_03k_realized_outcome_03q/source_snapshot/source_snapshot_manifest.json

Total close-expected unmatched rows: 13
Recommended next package: 03T_RUNTIME_POSITION_CLOSED_EMISSION_REPAIR

## Dominant Axes

| axis | rows |
| --- | --- |
| runtime_surface_rows | 10 |
| builder_surface_rows | 0 |
| decision_ledger_surface_rows | 1 |
| inconclusive_rows | 2 |

## Bucket Matrix

| bucket | count | pct_of_13 | example_rids |
| --- | --- | --- | --- |
| ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | 8 | 61.5385 | aurora_BTCUSDT_1778364903981, aurora_BNBUSDT_1778377202278, aurora_BNBUSDT_1778379004957 |
| ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT | 2 | 15.3846 | aurora_BNBUSDT_1778378405537, aurora_XRPUSDT_1778402706854 |
| LIFECYCLE_ID_BRIDGE_AVAILABLE | 0 | 0.0 |  |
| TRADE_ID_BRIDGE_AVAILABLE | 0 | 0.0 |  |
| DECISION_LEDGER_REALIZED_ONLY | 1 | 7.6923 | aurora_BTCUSDT_1778429706498 |
| BUILDER_CANONICALIZATION_GAP | 0 | 0.0 |  |
| RUNTIME_LOGGING_GAP | 0 | 0.0 |  |
| INCONCLUSIVE | 2 | 15.3846 | aurora_ETHUSDT_1778428202947, aurora_XRPUSDT_1778430903673 |

## Recommendation Basis

- runtime-oriented buckets account for 10 / 13 close-expected unmatched rows
- 8 rows already prove closure in trade_lifecycle while canonical POSITION_CLOSED is absent
- 2 rows emit alternative terminal order events instead of canonical close emission
