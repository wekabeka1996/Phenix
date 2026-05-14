# R7S-B Extended Fee-Aware Observation Freeze Report

- Bundle root: frozen/r7s_b_extended_fee_aware_observation_20260513T233631Z
- Bundle created UTC: 2026-05-13T23:36:31Z
- Manifest path: MANIFEST.json

## Primary Artifacts

| Frozen path | Exists | Size bytes | Raw lines | SHA256 |
| --- | --- | ---: | ---: | --- |
| logs/trade_lifecycle.jsonl | True | 2427423798 | 253098 | 21db138b86824868283bd86a422e04565f678f0db92739453c00169330a149b5 |
| logs/order_log_v1.jsonl | True | 2740827 | 812 | 7775b1251251529023c63d4636456e0001030f6a0214859415b8ce712b44ade6 |
| logs/shadow_critical_event_journal_v1.jsonl | True | 104875735 | 82660 | d3f4fda6d33d9a8b9c9de2992dade106900b57e1ad6b0875d83f79afed004521 |
| logs/execution_lifecycle_stats_v1.jsonl | True | 23827762 | 24308 | c0f92c2484d75e5b695b3631baa7b2c1001dc6932f8cca68527fd3da19a71c98 |
| logs/aurora_events.jsonl | True | 94397 | 279 | 6a6cd1f652162222a22aff4edc19d4688195994502154591d762e9c7f133b178 |
| logs/event_chain.log | True | 7285320 | 39344 | 278493991e618809207449267079f67a2eea50d91bd2e7778b57278cba008fc8 |

## Supporting Log Sets

| Pattern | File count | Total size bytes | First matched file | Last matched file |
| --- | ---: | ---: | --- | --- |
| logs/domain_execution_position.log* | 5 | 21599298 | logs/domain_execution_position.log | logs/domain_execution_position.log.4 |
| logs/order_guardian.log* | 1 | 14768469 | logs/order_guardian.log | logs/order_guardian.log |

Freeze identity is confirmed only if MANIFEST.json and FREEZE_REPORT.md both exist and the primary artifact rows above are populated.
