# Trade Lifecycle Boundary Reconciliation Report

## Problem framing
This report reconciles the contradiction between two prior primary-log reads of `logs/trade_lifecycle.jsonl` about POSITION_POLICY_SIDECAR_MODE_ACTIVE boundaries. The current filesystem snapshot was used as the source of truth.

## FACTS
- The analyzed file is [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl).
- During analysis the file was live and grew while being read.
- The final stable census observed during analysis reported one POSITION_POLICY_SIDECAR_MODE_ACTIVE row, 70061 POSITION_POLICY_SIDECAR_SUPPRESSED rows, 106 POSITION_POLICY_SIDECAR_EVALUATED rows, 106 POSITION_POLICY_SIDECAR_SCORES rows, 0 POSITION_POLICY_SIDECAR_RECOMMENDED rows, and 0 POSITION_POLICY_SIDECAR_ACTION_SKIPPED rows.
- The activation row is a `__DOMAIN__` bootstrap row at line 1 with ts_ms 1777449880830, mode enable, and evaluation_mode bounded_soft_close_policy.
- No rotated or sibling trade_lifecycle log files were found in `logs/` or elsewhere in the workspace search.

## INFERENCES
- The current snapshot supports one activation boundary only.
- The prior report that claimed two activation rows is not supported by the current file snapshot.
- The prior report that claimed one activation row matches the current file snapshot.
- The contradiction is most consistent with snapshot drift or stale counting, not with a second trade_lifecycle file.

## ASSUMPTIONS
- The current file snapshot is authoritative only for the moment of analysis.
- Earlier reports may have used an earlier append state, but that is not proven.

## UNKNOWNS
- The exact snapshot used by the prior report that claimed two activation rows.
- Whether that report used an older append state, a stale extract, or a counting error.
- Whether the file continued to grow after the last census pass.

## Table A — File identity

| item | value |
|---|---|
| absolute path | [C:\Users\user\Music\Phenix\logs\trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl) |
| size_bytes | 184536782 |
| modified_time | 2026-04-29T22:18:07.291149Z |
| line_count | 70704 |
| still_growing? | yes |
| nearby_rotated_files | none found in `logs/`; no other trade_lifecycle*.jsonl/log copies found in workspace search |

## Table B — Sidecar event census

| event_name | exact_count | first_line | first_ts_ms | last_line | last_ts_ms |
|---|---:|---|---:|---|---:|
| POSITION_POLICY_SIDECAR_MODE_ACTIVE | 1 | [1](logs/trade_lifecycle.jsonl#L1) | 1777449880830 | [1](logs/trade_lifecycle.jsonl#L1) | 1777449880830 |
| POSITION_POLICY_SIDECAR_SUPPRESSED | 70061 | [2](logs/trade_lifecycle.jsonl#L2) | 1777449897207 | [70704](logs/trade_lifecycle.jsonl#L70704) | 1777501087290 |
| POSITION_POLICY_SIDECAR_EVALUATED | 106 | [36237](logs/trade_lifecycle.jsonl#L36237) | 1777474505044 | [62629](logs/trade_lifecycle.jsonl#L62629) | 1777494916936 |
| POSITION_POLICY_SIDECAR_SCORES | 106 | [36236](logs/trade_lifecycle.jsonl#L36236) | 1777474505044 | [62628](logs/trade_lifecycle.jsonl#L62628) | 1777494916936 |
| POSITION_POLICY_SIDECAR_RECOMMENDED | 0 | none | none | none | none |
| POSITION_POLICY_SIDECAR_ACTION_SKIPPED | 0 | none | none | none | none |

## Raw activation examples
- [line 1](logs/trade_lifecycle.jsonl#L1): ts_ms 1777449880830, symbol __DOMAIN__, event POSITION_POLICY_SIDECAR_MODE_ACTIVE, highlights: mode enable; evaluation_mode bounded_soft_close_policy; sidecar_config_snapshot present with peak_giveback_close enabled; reason_codes sidecar_initialized.

## Raw event examples
- First POSITION_POLICY_SIDECAR_SUPPRESSED: [line 2](logs/trade_lifecycle.jsonl#L2), ts_ms 1777449897207, symbol BNBUSDT, highlights: trigger_event FEATURES_CALCULATED; suppression_reason startup_grace_active; reason_codes include peak_giveback_not_ready.
- First POSITION_POLICY_SIDECAR_EVALUATED: [line 36237](logs/trade_lifecycle.jsonl#L36237), ts_ms 1777474505044, symbol XRPUSDT, highlights: trigger_event REGIME_DETECTED; manage_state BRACKETS_PENDING; score_snapshot present.
- First POSITION_POLICY_SIDECAR_SCORES: [line 36236](logs/trade_lifecycle.jsonl#L36236), ts_ms 1777474505044, symbol XRPUSDT, highlights: trigger_event REGIME_DETECTED; score_snapshot position_health_score 0.8341289228401074 and exit_pressure_score 0.1658710771598926; reason_codes scores_computed.
- First POSITION_POLICY_SIDECAR_RECOMMENDED: none in the current snapshot.
- Last POSITION_POLICY_SIDECAR_SUPPRESSED: [line 70704](logs/trade_lifecycle.jsonl#L70704), ts_ms 1777501087290, symbol BTCUSDT, highlights: trigger_event PORTFOLIO_STATE_UPDATED; suppression_reason manage_flow_has_no_active_lifecycle; reason_codes include no_active_lifecycle.

## Boundary reality
- Activation count: 1.
- Run #1 boundable from first to second activation: no, because the second activation boundary is absent in the current snapshot.
- Run #2 boundable: no, for the same reason.
- Any prior run-bounding claim that depends on a second activation boundary is invalid under the current snapshot.

## Prior-report audit

| claim | status | evidence | may have been true on earlier snapshot | true now |
|---|---|---|---|---|
| 1. There are two POSITION_POLICY_SIDECAR_MODE_ACTIVE rows in the primary log. | STALE_SNAPSHOT_POSSIBLE | Current census has exactly one activation row at [line 1](logs/trade_lifecycle.jsonl#L1). | yes, if a prior snapshot or extract differed | no |
| 2. There is exactly one POSITION_POLICY_SIDECAR_MODE_ACTIVE row in the primary log. | SUPPORTED | Current census shows one activation row at [line 1](logs/trade_lifecycle.jsonl#L1). | yes | yes |
| 3. Run #1 can be bounded from first to second activation. | STALE_SNAPSHOT_POSSIBLE | Current snapshot has no second activation boundary, so the stated bound cannot be formed here. | possible but unproven | no |
| 4. Run #2 cannot be isolated because there is no second activation boundary. | SUPPORTED | Current snapshot has one activation row only. | yes | yes |
| 5. The file is globally suppression-only. | CONTRADICTED_BY_CURRENT_FILE | Current census has 106 POSITION_POLICY_SIDECAR_EVALUATED rows and 106 POSITION_POLICY_SIDECAR_SCORES rows, with examples at [36236](logs/trade_lifecycle.jsonl#L36236) and [36237](logs/trade_lifecycle.jsonl#L36237). | possibly, on an earlier truncated or older snapshot | no |
| 6. The file contains evaluation/score activity. | SUPPORTED | Current census has 106 evaluated rows and 106 score rows. | yes | yes |
| 7. No recommendation rows exist anywhere in the primary log. | SUPPORTED | Current census has 0 POSITION_POLICY_SIDECAR_RECOMMENDED rows. | yes | yes |

## Reconciliation verdict
FILE_CHANGED_BETWEEN_AUDITS_LIKELY

Why: the current file supports exactly one activation row, no sibling trade_lifecycle log copy was found, and the file visibly advanced during reconciliation. The most likely explanation is a stale snapshot or different append moment, not a second boundary in the current file.

## Final verdict
TRUTH_BASE_RECONCILED_BUT_SNAPSHOT_CHANGED

What is true in the current primary file: one activation row, evaluation and score activity, no recommendation rows.

Which prior claim is invalid now: the two-activation / bounded run #1 claim.

Whether snapshot drift is likely: yes, the file grew during reconciliation and no rotated trade_lifecycle sibling was found.

What should be audited next: the exact earlier snapshot or extract behind report A, plus any archived capture outside logs.
