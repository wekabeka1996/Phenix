# Sidecar Feature Freshness Capture Freeze Report

- Bundle root: frozen/sidecar_feature_freshness_capture_20260513T191500Z
- Bundle created UTC: 2026-05-13T19:24:15Z
- Manifest path: MANIFEST.json
- Primary artifacts present: 8 / 8

## Primary Artifacts

| Frozen path | Exists | Size bytes | Raw lines | SHA256 |
| --- | --- | ---: | ---: | --- |
| logs/trade_lifecycle.jsonl | True | 2219970914 | 232708 | 4903a2c08eac0ae06f25e0b3958296427007019ec4d76579e4099e13d5757fa6 |
| logs/order_log_v1.jsonl | True | 2302757 | 761 | 21ffae4edd2da1b78a132d357cd9156c007f4466beadf6e312d74a8529eb0e54 |
| logs/shadow_critical_event_journal_v1.jsonl | True | 97268639 | 76279 | 9fc7a7a51f65117d923f7f627c9e0de457fd4d243bd5c84d71a4c5b81400edcd |
| logs/execution_lifecycle_stats_v1.jsonl | True | 23826933 | 24307 | 49317b09dde7951c41b50a2003cea677dca17b1dedd29a9955e893578f6c4822 |
| logs/regime_confidence_audit_v1.jsonl | True | 5088016 | 4030 | a98f597663b3f94cb7646024a231470329ac47807f08f18ccd04b1497a2f16fa |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | True | 1650874 | 334 | 6533a2b4f938f14eb4b290158c875d6cd381f3c8bb9ada6d2a66e8646a82b1b6 |
| logs/aurora_events.jsonl | True | 94397 | 279 | 6a6cd1f652162222a22aff4edc19d4688195994502154591d762e9c7f133b178 |
| logs/event_chain.log | True | 6872715 | 37118 | a206ba82a6c20ee92278f892194abcd414b6db0e70b4c35e8f9e64f0124e4c2c |

## Supporting Log Sets

| Pattern | File count | Total size bytes | First matched file | Last matched file |
| --- | ---: | ---: | --- | --- |
| logs/aurora_core.log* | 51 | 528367882 | logs/aurora_core.log | logs/aurora_core.log.9 |
| logs/domain_execution_position.log* | 4 | 20312175 | logs/domain_execution_position.log | logs/domain_execution_position.log.3 |
| logs/order_guardian.log* | 1 | 13594142 | logs/order_guardian.log | logs/order_guardian.log |
| logs/aurora_trades.log* | 1 | 51167 | logs/aurora_trades.log | logs/aurora_trades.log |
| logs/domain_feature_engineering.log* | 31 | 157693546 | logs/domain_feature_engineering.log | logs/domain_feature_engineering.log.9 |
| logs/domain_decision_making.log* | 3 | 11730346 | logs/domain_decision_making.log | logs/domain_decision_making.log.30 |
| logs/domain_regime_detector.log* | 1 | 2075423 | logs/domain_regime_detector.log | logs/domain_regime_detector.log |

## Directory Summaries

| Frozen path | Exists | File count | Total size bytes | First top-level entry | Last top-level entry |
| --- | --- | ---: | ---: | --- | --- |
| data/recorder | True | 1839 | 342566350 | 2026-02-08 | 2026-05-13 |
| logs/features | True | 7 | 297291100 | 1000PEPEUSDT.log | XRPUSDT.log |
| logs/ta_features | True | 9 | 71213616 | 1000PEPEUSDT.jsonl | XRPUSDT.jsonl.1 |
| data/shadow_telemetry/snapshots | True | 2465 | 1572221639 | 1000PEPEUSDT | XRPUSDT |
| generated_reports | True | 14 | 464481 | FEATURE_REGIME_INPUT_INTEGRITY_DEEP_RESEARCH_REPORT.md | SIDECAR_ENABLE_GOVERNANCE_AUDIT_REPORT.md |
| config_snapshot | True | 12 | 119353 | apps | config |

Freeze identity is confirmed only if MANIFEST.json and FREEZE_REPORT.md both exist and the primary artifact rows above are populated.
