# CALIBRATORS_NRR_PACKAGE_H_POST_G_TESTNET_RUNTIME_VALIDATION_REPORT

## Executive Summary
Package H validates the deployed Package G NRR-062 hybrid/testnet override as an observation-only post-deploy exercise. The active frozen bundle captured exactly one admitted override rid, `aurora_BTCUSDT_1778845805903`, with raw override truth present in order_log and shadow journal, a canonical realized exact-roundtrip close, and positive realized net PnL of `22.6742616` quote.

The boundary audit must be scoped to the post-last-BOOT observation tail rather than the entire frozen multi-day window. Using the last BOOT before the admitted override as the observation boundary (`order_log` line `1734`, `ts_ms=1778842508184`), the post-deploy tail contains exactly one authoritative candidate row and that row is the admitted override. No post-boot leakage was observed into BUY/LONG, dual-failure, geometry-invalid, or SELL non-candidate surfaces.

The current runtime evidence is directionally consistent with the positive Package F replay thesis, but the runtime sample remains `1 / 79 = 0.012658227848101266` of the Package F candidate cohort. This is sufficient for observation-grade validation and insufficient for calibration, threshold tuning, scope expansion, or production promotion.

## Scope Guardrails
- No YAML values were changed.
- No config contracts were changed.
- No Python runtime logic was changed.
- No thresholds were tuned.
- No override conditions were expanded.
- No sidecar authority was promoted or reassigned.
- No production/live promotion was performed.

## Bundle And Evidence
- Bundle root: `logs/frozen/nrr062_fresh_capture_20260515_180927`
- Frozen order_log window: `2026-05-11T15:09:59.999000+00:00` to `2026-05-15T13:59:59.999000+00:00`
- order_log BOOT rows: `11`
- Post-deploy observation boundary: last BOOT before admitted override at `order_log` line `1734` / `ts_ms=1778842508184`
- Override-applied rows in frozen order_log: `1`
- Override-applied rows in frozen shadow journal: `1`
- Override rid cohort: `aurora_BTCUSDT_1778845805903`
- Frozen decision ledger present and readable under `logs/shadow_telemetry/decision_ledger_v1.jsonl`
- Config snapshot required files present: `8 / 8`

The frozen `trade_lifecycle.jsonl` artifact contains `7` malformed fragment lines at `230729`, `429732`, `430100`, `430997`, `430998`, `430999`, and `431004`. These are truncated JSONL fragments unrelated to the admitted rid. They were explicitly documented and skipped during observation processing rather than silently ignored.

## Runtime Outcome
- Override-admitted rid count: `1`
- Realized override rows: `1`
- Exact roundtrip override rows: `1`
- Outcome: `closed_win`
- Gross PnL quote: `24.6`
- Net PnL quote: `22.6742616`
- Fees quote: `1.9257384`
- Symbol distribution: `BTCUSDT=1`
- Side distribution: `short=1`

The authoritative runtime ledger records the following lifecycle for the admitted rid:
- intent timestamp: `1778845806030`
- entry fill timestamp: `1778845868591`
- exit close timestamp: `1778851733971`
- TP close price: `80034.1`
- realized close source: canonical realized dataset plus raw `POSITION_CLOSED`

## Raw Truth Versus Canonical Surfaces
- Raw override truth is preserved on `order_log` and `shadow_critical_event_journal`.
- Canonical objective trade decision rows do not preserve `nrr062_segment_override_applied`.
- The objective dataset row for the admitted rid exists with `authority_mode=shadow` and `dataset_visibility=causal_complete`.
- The decision ledger row for the admitted rid exists with `terminal_status=INVALID_FOR_DATASET` and `dataset_visibility=diagnostics_only`.
- The decision ledger also does not preserve the override token.

This means the override admission proof remains a raw-log truth, not a canonical objective-row truth.

## Sidecar Observation
The admitted rid is present in `trade_lifecycle` sidecar observation rows.

- sidecar observed: `true`
- sidecar row count captured in the ledger slice: `948`
- owner status seen on bracket ownership events: `ambiguous`
- highlighted events include `EXECUTION_BRACKET_DEFERRED_STORED`, `EXECUTION_FILL_INGRESS`, and `EXECUTION_BRACKET_DEFERRED_PLACED`

This is observation of downstream lifecycle involvement only. No evidence in this package supports any claim that sidecar authority was changed, widened, or promoted.

## Safety Boundary Audit
The safety boundary audit is intentionally scoped to the post-last-BOOT observation tail rather than the full frozen historical window. The wider bundle still contains historical pre-boot NRR-062 rows, including `121` pre-boot candidate-contract rows that were rejected before the restart boundary. Those rows are not evidence against the deployed post-boot override behavior.

Post-boot safety facts:
- post-boot NRR-062 surface rows: `1`
- post-boot authoritative candidate-contract rows: `1`
- post-boot candidate-contract rows missing override admission: `0`
- BUY/LONG direction-only rows in post-boot tail: `0`
- dual-failure rows in post-boot tail: `0`
- geometry-invalid rows in post-boot tail: `0`
- SELL direction-only non-candidate rows in post-boot tail: `0`
- override leakage across all observed contrast sets: `0`

Boundary verdict: `PASS`

## Replay Versus Runtime
Package F candidate metrics, taken from the candidate replay metrics section of `CALIBRATORS_NRR_PACKAGE_F_NRR062_MINIMAL_SEGMENT_LOGIC_REPLAY_REPORT.md`, are:

- candidate rows: `79`
- TP / SL / TIMEOUT: `25 / 2 / 52`
- estimated gross PnL quote: `1122.7695276632`
- estimated net PnL quote: `825.2672997047`
- estimated fees quote: `238.0017823673`
- profit factor: `4.92434390438585`
- timeout share: `0.6582278481012658`
- excluded BUY net quote: `-452.7182366138`
- excluded dual-failure net quote: `-194.77884318850002`

Runtime comparison:
- realized override rows: `1`
- wins / losses / unresolved: `1 / 0 / 0`
- runtime net quote: `22.6742616`
- runtime sample fraction of Package F candidate cohort: `0.012658227848101266`
- boundary alignment: `SELL_DIRECTION_ONLY_RAW_SIGNAL`
- economic alignment: `POSITIVE_RUNTIME_OBSERVATION_MATCHES_POSITIVE_REPLAY_DIRECTION`
- calibration readiness: `INSUFFICIENT_RUNTIME_SAMPLE`

Inference: runtime evidence is directionally supportive but statistically too small to replace the offline replay study or justify any tuning or rollout action.

## Rollback Gate
Rollback verdict: `NO_ROLLBACK_SIGNAL_TESTNET_ONLY_CONTINUE_COLLECTION`

Supporting facts:
- override observed in runtime: `true`
- boundary leak detected: `false`
- realized positive: `true`
- sample size sufficient for promotion: `false`
- objective rows preserve override token: `false`
- decision ledger preserves override token: `false`
- sidecar authority changed: `false`
- production scope changed: `false`

Recommended action: keep the Package G override unchanged in `hybrid_live_data_testnet_exec` only, continue runtime collection, do not promote to production, and do not tune thresholds from this sample.

## Focused Validation
Focused pytest validation was run with:

- `tests/domains/decision_making/test_low_vol_cost_floor_gate.py`
- `tests/domains/decision_making/test_low_vol_direction_confidence_contract.py`
- `tests/config/test_decision_making_contracts.py`
- `tests/test_calibrators_import_boundary.py`

Result:
- collected tests: `102`
- passed: `102`
- failed: `0`
- runtime: `22.13s`

This confirms the deployed gate contract, direction-confidence contract, config contract, and import boundary remain intact after the observation pass and artifact generation.

## Generated Artifacts
- `logs/frozen/nrr062_fresh_capture_20260515_180927/FREEZE_REPORT.md`
- `calibrators/datasets/nrr062_testnet_override_runtime/nrr062_override_runtime_ledger.json`
- `calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_RUNTIME_LEDGER.csv`
- `calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_RUNTIME_LEDGER.md`
- `calibrators/datasets/nrr062_testnet_override_runtime/nrr062_override_safety_boundary_audit.json`
- `calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_SAFETY_BOUNDARY_AUDIT.md`
- `calibrators/datasets/nrr062_testnet_override_runtime/nrr062_override_outcome_analysis.json`
- `calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_OUTCOME_ANALYSIS.md`
- `calibrators/datasets/nrr062_testnet_override_runtime/nrr062_override_replay_vs_runtime.json`
- `calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_REPLAY_VS_RUNTIME.md`
- `calibrators/datasets/nrr062_testnet_override_runtime/nrr062_override_rollback_gate.json`
- `calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_ROLLBACK_GATE.md`

## Conclusion
Package H closes as a post-deploy observation-only validation. The deployed override is observed in raw runtime evidence, the admitted trade closed profitably, the post-boot boundary audit shows no leakage, and focused tests remain green. The evidence supports continued hybrid/testnet-only collection and does not support rollback, production promotion, or threshold/config/runtime changes.
