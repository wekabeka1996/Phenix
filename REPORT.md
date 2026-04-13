# TRACK_A_21H_RUNTIME_CONTEXT_COLLECTION_AND_NEXT_WORK_BASELINE

## 1. Executive Summary

- FACT: Retained runtime evidence window is 2026-04-10 19:56:39 UTC to 2026-04-11 16:33:05 UTC (20.61h, near-21h).
- FACT: One close-bearing WS miss was observed: `EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS` for BTCUSDT, followed by one `unknown_disappearance` attribution.
- FACT: Bracket-health `-4130` spam remains active at high frequency (6,641 lines in `aurora_core.log*`; 13,252 raw `-4130` hits across all retained logs).
- FACT: Runtime shows continued heavy classic `/openOrders` polling and repeated algo re-placement attempts via `/fapi/v1/algoOrder` with `400 [-4130]`.
- FACT: Sidecar remains predominantly suppressive in this window; suppressions are explainable from upstream lifecycle/freshness states.
- INFERENCE: Dominant operational burden in this exact window is `BRACKET_HEALTH_ALGO_ENDPOINT_SPLIT_FIX_A_THEN_B` (high-frequency API waste + noise + incident masking risk), while post-start OrderIndex miss family remains open but low-count in this window.
- UNKNOWN: Restart-carried recovery-gap family was not directly exercised in this retained window; closure cannot be claimed from silence.

## 2. 21h Evidence Window Definition (TASK C1)

- FACT: `logs/trade_lifecycle.jsonl` first ts_ms `1775850999991` -> 2026-04-10 19:56:39 UTC.
- FACT: `logs/trade_lifecycle.jsonl` last ts_ms `1775925185067` -> 2026-04-11 16:33:05 UTC.
- FACT: `logs/shadow_critical_event_journal_v1.jsonl` first ts_ms `1775850999747`, last ts_ms `1775925180736` (same window envelope).
- FACT: Duration from lifecycle anchor is `(1775925185067-1775850999991)/3600000 = 20.61h`.
- FACT: This is slightly below nominal 21h; coverage is still within requested post-restart forensic scope.
- FACT: Log rotation boundaries are present (`aurora_core.log.21`..`.1` + current, `domain_execution_position.log.1` + current) and timestamps are continuous within retained span.
- FACT: Large logs cannot be line-read via editor sync (>50MB); extraction used terminal streaming and targeted grep/search.
- INFERENCE: Evidence confidence is HIGH for observed families in retained window.
- UNKNOWN: True process BOOT marker line for this run is not retained as explicit `BOOT` token; earliest retained runtime anchor is lifecycle/sidecar start row.

### Window Table

| item | value |
|---|---|
| restart/runtime anchor used | `trade_lifecycle` first retained row (`POSITION_POLICY_SIDECAR_MODE_ACTIVE`) |
| anchor ts | `1775850999991` (2026-04-10 19:56:39 UTC) |
| window end ts | `1775925185067` (2026-04-11 16:33:05 UTC) |
| effective retained length | `20.61h` |
| confidence | HIGH |
| coverage risk | LOW-MEDIUM (explicit BOOT token not retained; inferred from first retained runtime row) |

## 3. Runtime Contour Inventory (TASK C2)

### Runtime Contour Matrix (Deliverable 2)

| contour id | contour name | symbols | observed? | primary evidence | owner domain | severity | verdict |
|---|---|---|---|---|---|---|---|
| C01 | startup truth / startup suppression | BTC, ETH, SOL, DOGE, XRP, BNB, 1000PEPE | YES | `trade_lifecycle` first rows: sidecar `startup_grace_active`; `STARTUP` pattern count=1373 | execution_position + sidecar | M | PARTIAL (startup surface visible, explicit BOOT token not retained) |
| C02 | carried position recovery contour | N/A (not explicitly carried in retained rows) | NOT OBSERVED | no direct carried-position reconstruction event in retained 20.61h | execution_position | H if present | NOT OBSERVED |
| C03 | new post-restart placement contour | BTC, BNB, XRP, DOGE (active BRACKETS_PENDING states) | YES | lifecycle rows around 67240+ show active post-start lifecycles and later transitions | execution_position | H | OBSERVED |
| C04 | terminal close contour (healthy + degraded mix) | multiple | YES | `terminal_correlation_source=order_index_canonical` count=18; `POSITION_DISAPPEARANCE_ATTRIBUTED` count=10 | execution_position + ws adapter | H | MIXED |
| C05 | OrderIndex miss contour | BTCUSDT | YES | `EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS` count=1; ws contract breach line | execution_position + binance_ws_client | H | OPEN |
| C06 | unknown_disappearance contour | BTCUSDT | YES | `unknown_disappearance` count=1 (same chain as C05) | execution_position | H | OPEN |
| C07 | bracket-health `-4130` contour | BNB, XRP, BTC, ETH, SOL | YES | `-4130` counts: 6641 in core logs; 13252 raw all logs; GET openOrders + POST algoOrder 400 cycles | execution_position + adapter | H | PROVEN |
| C08 | sidecar runtime contour | all assigned symbols | YES | `POSITION_POLICY_SIDECAR_SUPPRESSED` count=94354, reason breakdown present | execution_position sidecar | M | OBSERVED (detector-like, mostly suppressive) |
| C09 | artifact hygiene / contamination contour | report-level | YES | `strategies_passport.md` claims DOGE unassigned; runtime/config show DOGE assigned | docs/config boundary | M | DOC-RUNTIME CONFLICT PRESENT |

## 4. Startup / Carried-Truth Baseline (TASK C3)

- FACT: Earliest retained lifecycle row is sidecar mode activation (`ts_ms=1775850999991`).
- FACT: Immediate startup rows show sidecar suppressions with `suppression_reason=startup_grace_active` and empty/null position snapshots for symbols.
- FACT: No direct retained evidence in this 20.61h window proves a carried-from-pre-restart position being reconstructed into OrderIndex.
- FACT: By mid-window, BTC/DOGE/XRP/BNB states are active (`manage_state=BRACKETS_PENDING`) with `position_open_ts` values after anchor time, indicating post-start lifecycle activity.
- INFERENCE: This retained window primarily captures post-start lifecycle behavior rather than explicit carried-recovery exercise.

### Startup/Carried Table

| symbol | carried position? | carried bracket truth persisted? | startup openOrders visible? | reconstructed into OrderIndex? | status |
|---|---|---|---|---|---|
| BTCUSDT | unknown | unknown | unknown | unknown | post-start active lifecycle observed; no direct carried proof in retained window |
| ETHUSDT | unknown | unknown | unknown | unknown | startup suppressive rows then no-active-lifecycle states observed |
| SOLUSDT | unknown | unknown | unknown | unknown | startup suppressive rows then no-active-lifecycle states observed |
| DOGEUSDT | unknown | unknown | unknown | unknown | startup suppressive rows; later BRACKETS_PENDING observed |
| XRPUSDT | unknown | unknown | unknown | unknown | startup suppressive rows; later BRACKETS_PENDING observed |
| BNBUSDT | unknown | unknown | unknown | unknown | startup suppressive rows; later BRACKETS_PENDING observed |
| 1000PEPEUSDT | no active lifecycle observed | n/a | unknown | n/a | consistently `no_manage_flow_for_symbol` suppressions |

## 5. Healthy Post-Restart Placement Baseline (TASK C4)

- FACT: `terminal_correlation_source="order_index_canonical"` appears 18 times in retained lifecycle.
- FACT: `attribution="proven_exchange_bracket_close"` appears 9 times; total disappearance-attributed events are 10.
- FACT: This proves healthy correlated terminal close chains coexist with degraded chain.
- INFERENCE: Post-start path is partially healthy; failures are specific, not global collapse.

## 6. Miss / unknown_disappearance Casebook (TASK C5)

### FACT chain for retained miss case

1. WS terminal update observed for BTCUSDT child order:
   - `client_order_id=web_9BQIEGGSIaHBeYDvVYTU`, `exchange_order_id=13028503639`, status `FILLED`.
2. WS adapter logs explicit fail-closed correlation breach:
   - `CONTRACT BREACH: close-bearing terminal update ... has no canonical OrderIndex record; fail-closed drop`.
3. Lifecycle emits:
   - `EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS` at `ts_ms=1775899115386`.
4. Later lifecycle emits:
   - `POSITION_DISAPPEARANCE_ATTRIBUTED` with `attribution=unknown_disappearance` at `ts_ms=1775899117109`.
5. Context rows around miss show BTC in active post-start state (`BRACKETS_PENDING`, `position_open_ts=1775853608...`, after window anchor), so this is not a carried-startup case.

### Miss Case Matrix (Deliverable 3)

| case id | symbol | carried or post-start | ids observed | guardian/ledger truth present? | reconstructed into OrderIndex? | miss type | disappearance attribution | verdict |
|---|---|---|---|---|---|---|---|---|
| M01 | BTCUSDT | POST-START | `client_order_id=web_9BQIEGGSIaHBeYDvVYTU`, `exchange_order_id=13028503639` | UNKNOWN in retained proof | NO (runtime contract breach says canonical record missing) | `POST_START_IDENTITY_OR_REGISTRATION_GAP` | `unknown_disappearance` | OPEN |

### Required classification status

- RESTART_CARRIED_RECOVERY_GAP: NOT OBSERVED in this retained window.
- POST_START_IDENTITY_OR_REGISTRATION_GAP: PROVEN (M01).
- BRACKET_HEALTH_FALSE_NEGATIVE_RELATED: SEPARATE contour; no direct proof M01 is caused by `-4130` loop.
- ARTIFACT / FALSE LEAD: not indicated for M01.
- UNKNOWN FAMILY: not required for M01 (classified as post-start gap).

## 7. Bracket-Health `-4130` Contour Audit (TASK C6)

- FACT: `-4130` appears massively in retained logs.
  - 6,641 lines in `aurora_core.log*`.
  - 13,252 raw `-4130` matches across retained logs.
- FACT: Symbol spread in core logs:
  - BNBUSDT 2336, XRPUSDT 2209, BTCUSDT 1752, ETHUSDT 272, SOLUSDT 72.
- FACT: Runtime sequence repeatedly shows:
  - `GET /fapi/v1/openOrders?...` (200), then
  - `POST /fapi/v1/algoOrder?...` (400), then
  - warning `[BRACKET-HEALTH] ... [-4130] ...`.
- FACT (code): adapter uses classic open-orders path and algo placement path:
  - `_get_open_orders_cached()` -> `GET /fapi/v1/openOrders`.
  - conditional fallback placement -> `POST /fapi/v1/algoOrder`.
- INFERENCE: This is consistent with endpoint-split false-negative loop family (classic detection vs algo-side existing trigger order).

### Bounded verdict

- Verdict: PROVEN.
- Operational effect:
  - safety: MEDIUM (fail-closed behavior preserved, but repeated recovery churn);
  - observability noise: HIGH;
  - API waste: HIGH;
  - masking risk: HIGH (high-volume warnings can hide unrelated incidents).

## 8. Sidecar Contextual Audit (TASK C7)

- FACT: Sidecar suppressive mode is dominant (`POSITION_POLICY_SIDECAR_SUPPRESSED` count=94,354).
- FACT: suppression reason counts in retained lifecycle:
  - `startup_grace_active`: 1,373
  - `features_snapshot_missing_or_stale`: 38,299
  - `manage_flow_has_no_active_lifecycle`: 26,245
  - `no_manage_flow_for_symbol`: 22,127
- FACT (code): suppression reasons are explicit in sidecar logic (`startup_grace_active`, `no_manage_flow_for_symbol`, `manage_flow_has_no_active_lifecycle`, `features_snapshot_missing_or_stale`).
- INFERENCE: Sidecar is acting as detector/reflector of upstream lifecycle/freshness conditions, not as the primary source of OrderIndex miss.

### Bounded verdict

- sidecar as detector: YES
- sidecar as masking layer: PARTIAL (high suppression volume can obscure signal, but does not create miss root cause)
- sidecar as unrelated: NO
- unknown: LOW

## 9. SSOT / Authority Context Map (TASK C8, Deliverable 4)

### FACT/INFERENCE split

- FACT: `Copilot_Master_Roadmap.md` defines SSOT role and verb-registry anchor.
- FACT: `apps/reference/dictionaries/verb_registry_v1.yaml` marks key ownership:
  - `CMD:CLOSE`, `CMD:OPEN`, `DEC:CLOSE`, `DEC:OPEN` owner=`execution_position`.
  - `EVT:DECISION_BLOCKED` owner=`decision_making`.
  - `CMD:PROCESS_STRATEGY` exists with strategy/feature boundary role.
- FACT: `config/aurora/strategies.yaml` currently assigns:
  - BTC/ETH/SOL -> aurora
  - DOGE -> mean_reversion
  - XRP/BNB -> md_amr
  - 1000PEPE -> llm_microstructure
- FACT: `config/docs/strategies_passport.md` currently claims DOGE is unassigned (doc drift vs runtime config).
- INFERENCE: Runtime/config truth must outrank stale passport claims for current assignment context.

| surface | owner | authority class | runtime status | document anchor | notes |
|---|---|---|---|---|---|
| execution lifecycle truth (open/close/order tracking) | execution_position | authoritative | ACTIVE | `verb_registry_v1.yaml` + runtime logs | primary owner of close-bearing correlation and OrderIndex contract |
| OrderIndex mapping | execution_position | authoritative local runtime SSOT | ACTIVE with one proven miss | ws contract-breach + miss event | fail-closed drop confirms strict dependency |
| decision policy/gating | decision_making | authoritative for policy, not execution truth | ACTIVE | domains/strategies passports + verb registry | boundary respected in observed logs |
| feature production + strategy processing command | feature_engineering + strategies boundary | authoritative upstream input | ACTIVE | `CMD:PROCESS_STRATEGY` verb ownership | does not own terminal close correlation |
| bracket-health detection loop | execution_position + adapter | authoritative implementation plane | DEGRADED (high spam) | runtime GET openOrders + POST algoOrder + `-4130` | dominant operational defect contour |
| startup truth artifact / restore envelope | execution_position | derivative artifact (evidence, not sole truth) | ACTIVE periodic writes | restore events in core logs | useful for observability, not closure proof alone |
| sidecar | execution_position sidecar | derivative contextual surface | ACTIVE suppressive | lifecycle records + sidecar code | reflective layer; not root owner of miss |
| strategy assignment map | config SSOT (`strategies.yaml`) | authoritative config | ACTIVE | `config/aurora/strategies.yaml` | doc drift exists in `strategies_passport.md` |

## 10. Exact Next-Package Decision (TASK C9)

### Candidate ranking from this 20.61h runtime

1. `BRACKET_HEALTH_ALGO_ENDPOINT_SPLIT_FIX_A_THEN_B`
2. `POST_START_ORDERINDEX_MISS_FAMILY_FORENSIC_AND_CLOSURE`
3. `ZERO_OPEN_ORDER_STARTUP_RECOVERY_CLOSURE`
4. `ARTIFACT_HYGIENE_FINISHING_PACKAGE`

### Selected dominant next package

- Dominant next package: `BRACKET_HEALTH_ALGO_ENDPOINT_SPLIT_FIX_A_THEN_B`.

### Justification

- FACT: `-4130` contour is high-frequency and cross-symbol (thousands of warnings in 20.61h).
- FACT: repeated classic `/openOrders` detection + algo `/algoOrder` recovery attempts are directly visible in runtime.
- FACT: post-start miss family is still open but observed as one retained case in this window.
- INFERENCE: Immediate risk to operations (noise/API churn/masking) is dominated by bracket-health loop volume; fixing this first improves observability and reduces incident-collision risk before deeper miss-family closure.

### What remains unproven

- UNKNOWN: restart-carried zero-open-order recovery gap behavior in this exact retained window.
- UNKNOWN: whether M01 miss shares root cause with prior carried-recovery family (not proven here).

### Risk if not done next

- continued alert fatigue and API waste;
- increased chance of missing lower-frequency but high-severity defects;
- continued false-negative health loop can interfere with clean attribution for future lifecycle incidents.

## 11. Remaining Unknowns

- UNKNOWN: explicit BOOT marker for this retained run (not present as retained token).
- UNKNOWN: carried-restart recovery gap exercise in this retained window (not directly observed).
- UNKNOWN: guardian/ledger presence for M01 specific child identity (not proven in retained artifacts).
- UNKNOWN: exact percentage of `-4130` attempts that are pure false negatives vs mixed race windows.

## 12. Final Verdict

- 21h evidence window established: DONE
- runtime contour inventory completed: DONE
- startup / carried baseline reconstructed: DONE
- healthy placement baseline reconstructed: DONE
- miss families classified: DONE
- bracket-health contour audited: DONE
- sidecar context audited: DONE
- SSOT context map produced: DONE
- exact next package selected: DONE

Then:

- Current Track A runtime state: DEGRADED_PARTIAL
- Dominant next package: BRACKET_HEALTH_ALGO_ENDPOINT_SPLIT_FIX_A_THEN_B
- Confidence in next-package choice: MEDIUM

---

## Appendix A: Mandatory Defect Family Separation Check

- carried restart recovery gap: NOT OBSERVED in retained 20.61h window (no closure claim).
- post-start OrderIndex miss family: OBSERVED (M01 BTC case).
- guardian write-path behavior: PARTIALLY PROVEN in this window (healthy canonical terminal correlations exist; no broad closure claim).
- bracket-health algo split / `-4130`: PROVEN and high-frequency.
- startup artifact / startup observability: OBSERVED (startup suppressions + periodic restore writes).
- artifact contamination / mixed-stream reading risk: PRESENT (doc-runtime drift in strategies passport).
- sidecar runtime behavior: OBSERVED (mostly suppressive, reflective of upstream state).

## Appendix B: Fact / Inference / Assumption / Unknown Summary

- FACT:
  - window bounds and duration;
  - one miss + one unknown disappearance;
  - high-volume `-4130` contour and endpoint sequence;
  - sidecar suppression breakdown;
  - config/runtime strategy assignments include DOGE -> mean_reversion.
- INFERENCE:
  - bracket-health split is dominant operational next package;
  - sidecar is reflective detector, not primary miss generator.
- ASSUMPTION:
  - retained window is representative for immediate next-package prioritization.
- UNKNOWN:
  - carried restart recovery exercise in this retained window;
  - full root-cause linkage between M01 and historical carried-family defects.
