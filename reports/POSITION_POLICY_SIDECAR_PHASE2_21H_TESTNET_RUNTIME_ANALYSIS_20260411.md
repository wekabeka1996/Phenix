# REPORT — POSITION POLICY SIDECAR PHASE-2 21H TESTNET RUNTIME ANALYSIS AND CONTEXT HARVEST 2026-04-11

## Executive Verdict

- Overall runtime verdict: `PHASE2_RUNTIME_PATH_NOT_EXERCISED`
- Forensic sufficiency: `PARTIAL_BUT_USABLE`
- Dominant next-work cluster: `insufficient_runtime_exercise`
- The latest post-restart slice available during this analysis is a single append-active runtime window from `1775850999991` to frozen analysis boundary `1775925393942`, equal to `20.664986h` (`20h 39m 54s`).
- Runtime posture is proven as `shadow` with `evaluation_mode=phase1_recommendation_only`, not action-bearing.
- The new Phase-2 request path was not exercised in runtime truth: `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST = 0`, `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE = 0`, sidecar-originated downstream `CMD:CLOSE = 0`, sidecar-originated downstream `DEC:CLOSE = 0`, sidecar-originated `EXECUTION_CLOSE_RECONCILED = 0`.
- The run still produced bounded sidecar activity in shadow: `SCORES = 3045`, `EVALUATED = 3045`, `RECOMMENDED = 5`, `SUPPRESSED = 94375`.
- No system restart, mode switch, enablement, relaunch, or config change was performed in this task.

## Runtime Boundary and Posture Proof

### Artifact Paths Used

- Runtime truth:
  - `logs/trade_lifecycle.jsonl`
  - `logs/aurora_core.log`
  - `logs/order_log_v1.jsonl`
  - `logs/shadow_critical_event_journal_v1.jsonl`
  - `logs/domain_execution_position.log`
  - `logs/domain_decision_making.log`
- Config / contract SSOT:
  - `config/aurora/system.yaml`
  - `config/aurora/trading.yaml`
  - `config/aurora/strategies.yaml`
  - `config/aurora/domains.yaml`
- Frozen governance / package baseline:
  - `position_policy_sidecar_roadmap_v_1.md`
  - `reports/POSITION_POLICY_SIDECAR_PHASE6_REOPENED_ACTION_READINESS_GATE_REVIEW_20260410.md`
  - `reports/POSITION_POLICY_SIDECAR_PHASE2_ACTION_PACKAGE_TESTNET_ONLY_IMPLEMENTATION_20260410.md`

### Boundary Proof

| Item | Evidence | Value |
| --- | --- | --- |
| Slice start | `logs/trade_lifecycle.jsonl` line 1 | `ts_ms=1775850999991` / `2026-04-10T19:56:39.991Z` |
| Slice start marker | `POSITION_POLICY_SIDECAR_MODE_ACTIVE` | `mode=shadow`, `evaluation_mode=phase1_recommendation_only` |
| MODE_ACTIVE count | `logs/trade_lifecycle.jsonl` full-slice count | `1` |
| Frozen analysis end | latest observed `trade_lifecycle` ts during this task | `ts_ms=1775925393942` / `2026-04-11T16:36:33.942Z` |
| Frozen runtime span | `1775925393942 - 1775850999991` | `20.664986h` |
| Slice sufficiency for claimed `~21h` window | runtime duration vs target | `Yes` |

### Freeze Rule

- `logs/trade_lifecycle.jsonl` remained append-active during analysis.
- An earlier read in this task saw `last_ts_ms=1775925174735`; a later read saw `last_ts_ms=1775925393942`.
- This report therefore uses a forensic freeze boundary, not a shutdown boundary.
- Proven statement: the latest available post-restart slice had already reached `20.664986h` at analysis freeze and was sufficient to represent the claimed `~21h` runtime window.

### Trading Mode and Sidecar Posture Proof

- `config/aurora/system.yaml` sets `trading_mode: "hybrid_live_data_testnet_exec"`.
- `config/aurora/trading.yaml` sets `trading.mode: hybrid_live_data_testnet_exec` and explicitly documents live market data with testnet execution.
- The same file fixes `risk_management.data_sources.portfolio_state: testnet` and `market_data: live`.
- `config/aurora/trading.yaml` points the testnet REST surface at `https://testnet.binancefuture.com`.
- `logs/aurora_core.log` shows live runtime requests to `https://testnet.binancefuture.com/fapi/...`, which proves testnet execution surfaces were active at runtime.
- `config/aurora/domains.yaml` sets `position_policy_sidecar.mode: shadow`.
- `logs/trade_lifecycle.jsonl` line 1 proves runtime posture was actually `shadow` with `evaluation_mode=phase1_recommendation_only`.
- Every emitted recommendation row in the slice also carries `mode=shadow` and `evaluation_mode=phase1_recommendation_only`.

## Minimal Context Snapshot

### Active Symbol Universe and Ownership

Current strategy assignment SSOT from `config/aurora/strategies.yaml`:

| Symbol | Strategy owner |
| --- | --- |
| BTCUSDT | `aurora` |
| ETHUSDT | `aurora` |
| SOLUSDT | `aurora` |
| DOGEUSDT | `mean_reversion` |
| XRPUSDT | `md_amr` |
| BNBUSDT | `md_amr` |
| 1000PEPEUSDT | `llm_microstructure` |

Runtime sidecar rows were observed for all seven symbols in the current slice, so the sidecar monitoring surface was broader than the five-symbol recommendation subset.

### Narrow Sidecar Action Scope

Frozen bounded action law from package baseline and current config:

- `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST` and `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE` exist in code and registry.
- Allowed action scope remains narrow and additive only:
  - `soft_close_symbol_current_net_only: true`
  - `partial_reduce: false`
  - `bracket_mutation: false`
  - `exact_targeting: false`
- Contract meaning remains:
  - symbol-scoped only,
  - current live net position only,
  - reduce-only,
  - no partial reduce,
  - no bracket mutation,
  - no exact lifecycle targeting.

### Ownership Boundaries

Frozen sidecar roadmap and Phase-2 package baseline keep these boundaries intact:

- `execution_position` remains lifecycle / execution / reconcile truth owner.
- `ManageFlowFSM` remains local open-position lifecycle SSOT.
- `CloseExecutor` remains close executor.
- `OrderGuardian` remains reconcile / tidy owner.
- `decision_making` remains strategy dispatch and upstream policy flow owner.
- Sidecar remains additive and does not become lifecycle truth owner.

### Runtime Mode Constraints That Materially Affect Interpretation

- The runtime is hybrid: live data ingestion with testnet execution surfaces.
- Sidecar was not running in `enable`; it was running in `shadow`.
- Therefore recommendation evidence is real runtime evidence, but action-path evidence cannot be inferred from recommendation emission alone.
- Because `shadow` was proven at runtime, the absence of request / request-state / reconcile lineage cannot be classified as a request-path failure inside this slice.

## FACTS

- The current slice has exactly one `POSITION_POLICY_SIDECAR_MODE_ACTIVE` row and therefore represents one post-restart sidecar slice, not a mixed multi-restart sample.
- The latest available frozen slice duration is `20.664986h`, not `24h` and not the earlier `27.5h` package-5.2 slice.
- Runtime posture is explicitly `shadow` / `phase1_recommendation_only` in the live log surface.
- Current sidecar event counts in the frozen slice are:
  - `MODE_ACTIVE = 1`
  - `SUPPRESSED = 94375`
  - `SCORES = 3045`
  - `EVALUATED = 3045`
  - `RECOMMENDED = 5`
- Recommendation count by symbol is:
  - `SOLUSDT = 1`
  - `BTCUSDT = 1`
  - `ETHUSDT = 1`
  - `XRPUSDT = 1`
  - `DOGEUSDT = 1`
  - `BNBUSDT = 0`
  - `1000PEPEUSDT = 0`
- Recursive scan over all files under `logs/` found zero occurrences of:
  - `POSITION_POLICY_SIDECAR_CLOSE_REQUEST`
  - `POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE`
  - `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`
  - `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE`
- Recursive scan over all files under `logs/` also found zero sidecar close-lineage markers such as:
  - `"trigger": "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST"`
  - `"policy_source": "position_policy_sidecar"`
  - `"source_event_type": "POSITION_POLICY_SIDECAR_RECOMMENDED"`
  - `"request_id":`
- No `POSITION_POLICY_SIDECAR_ACTION_SKIPPED` rows were present in the slice.
- Suppression reasons observed in the slice were:
  - `features_snapshot_missing_or_stale = 38307`
  - `manage_flow_has_no_active_lifecycle = 26249`
  - `no_manage_flow_for_symbol = 22129`
  - `regime_snapshot_missing_or_stale = 5224`
  - `startup_grace_active = 1373`
  - `post_fill_grace_active = 629`
  - `portfolio_snapshot_missing_or_stale = 322`
  - `recommendation_duplicate_same_state = 141`
  - `recent_terminal_order_state_detected = 1`

## INFERENCES

- The new Phase-2 request surface is present in code and frozen package governance, but it was not exercised in the latest runtime slice because runtime posture stayed in `shadow`.
- The current slice proves recommendation behavior and fail-closed gating under live hybrid/testnet conditions, but it does not prove request intake, request-state transitions, execution submission, execution noop, or reconcile linkage.
- The dominant explanation for zero action-bearing lineage is posture, not a proven request-path bug.
- The shadow forensic surface is good enough to plan the next targeted capture, but not good enough to clear an action-bearing pilot review on runtime truth alone.

## ASSUMPTIONS

- `logs/trade_lifecycle.jsonl` is the authoritative sidecar runtime truth surface for this analysis window.
- The current append-active slice is the latest available post-restart sidecar slice in the workspace.
- The runtime config files inspected are the active config posture for the captured slice.

## UNKNOWNS

- No runtime truth exists in this slice for how `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST` behaves under `enable`.
- No runtime truth exists in this slice for `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE` state progression.
- No runtime truth exists in this slice for sidecar-originated `execution_submitted`, `execution_noop`, or `reconciled` outcomes.
- No runtime truth exists in this slice for sidecar-originated collision behavior once action-bearing requests are admitted.
- Because the slice remained append-active, this report cannot prove the eventual run shutdown timestamp.

## Sidecar Runtime Chain Summary

### Aggregate Chain Counts

| Surface | Count | Runtime status |
| --- | ---: | --- |
| `POSITION_POLICY_SIDECAR_MODE_ACTIVE` | 1 | exercised |
| `POSITION_POLICY_SIDECAR_SCORES` | 3045 | exercised |
| `POSITION_POLICY_SIDECAR_EVALUATED` | 3045 | exercised |
| `POSITION_POLICY_SIDECAR_RECOMMENDED` | 5 | exercised |
| `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST` | 0 | not exercised |
| `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE` total | 0 | not exercised |
| request-state `suppressed` | 0 | not exercised |
| request-state `close_command_emitted` | 0 | not exercised |
| request-state `execution_submitted` | 0 | not exercised |
| request-state `execution_noop` | 0 | not exercised |
| request-state `reconciled` | 0 | not exercised |
| sidecar-originated downstream `CMD:CLOSE` | 0 | not exercised |
| sidecar-originated downstream `DEC:CLOSE` | 0 | not exercised |
| sidecar-originated `EXECUTION_CLOSE_RECONCILED` | 0 | not exercised |

### What Was Actually Exercised

- Shadow recommendation chain was exercised end-to-end through `SUPPRESSED`, `SCORES`, `EVALUATED`, and `RECOMMENDED`.
- The new Phase-2 action/request chain was not exercised at all in runtime truth.
- Therefore the correct classification for this slice is: new plumbing present in code, absent in runtime exercise.

## Request-to-Outcome Lineage Review

### Aggregate Lineage Stats

| Lineage measure | Value |
| --- | ---: |
| Sidecar-originated request count | 0 |
| Request ids observed | 0 |
| Complete request-to-reconcile lineages | 0 |
| Broken request-state chains | 0 |
| Incomplete due to missing runtime request emission | 0 request chains initiated |

### Concrete Symbol-Level Chain Example: Recommendation Without Request Exercise

SOLUSDT recommendation-only shadow chain:

- `logs/trade_lifecycle.jsonl` line `4427`: sidecar suppresses on `regime_snapshot_missing_or_stale` while the position is still `BRACKETS_PENDING` and portfolio is present.
- `logs/trade_lifecycle.jsonl` lines `4428-4430`: same symbol transitions through `SCORES -> EVALUATED -> RECOMMENDED` with `soft_close_pressure = 0.3` under `mode=shadow` and `evaluation_mode=phase1_recommendation_only`.
- `logs/trade_lifecycle.jsonl` line `4449`: follow-up duplicate attempt is converted into `recommendation_duplicate_same_state` suppression, which proves bounded shadow behavior continues after the recommendation.
- Recursive scan over all runtime log files found zero `request_id`, zero `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`, and zero `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE` markers.
- Result: lineage ends at `RECOMMENDED` by proven runtime posture, not by mixed evidence.

### Concrete Symbol-Level Chain Example: Shadow Recommendation on Freshly Filled Lifecycle

BTCUSDT chain:

- `logs/trade_lifecycle.jsonl` line `6049` records a fresh filled lifecycle snapshot for BTCUSDT.
- `logs/trade_lifecycle.jsonl` lines `6051-6053` immediately show `SCORES -> EVALUATED -> RECOMMENDED` for BTCUSDT with portfolio present and `soft_close_pressure = 0.3`.
- No request surface follows anywhere in runtime logs.
- Result: recommendation path is active; request path is absent.

## Suppression / Fail-Closed Review

### Healthy Fail-Closed Behavior

These suppressions are contract-honest and expected from current shadow posture and freshness / lifecycle laws:

- `startup_grace_active = 1373`
  - Expected cold-start protection.
- `post_fill_grace_active = 629`
  - Expected immediate post-fill cooling window.
- `recommendation_duplicate_same_state = 141`
  - Healthy dedup behavior. Example: `logs/trade_lifecycle.jsonl` line `4449` suppresses a same-state duplicate after the SOLUSDT recommendation at line `4430`.
- `recent_terminal_order_state_detected = 1`
  - Healthy incumbent-collision prevention. Example: `logs/trade_lifecycle.jsonl` line `70594` suppresses XRPUSDT with `incumbent_owner = OrderGuardian`.
- `manage_flow_has_no_active_lifecycle = 26249`
  - Healthy fail-closed behavior when local lifecycle is flat or already terminal.
- `no_manage_flow_for_symbol = 22129`
  - Healthy fail-closed behavior for symbols with no local EP lifecycle owner.

### Suspicious Suppression Clusters

No suppression cluster is proven to be dishonest or unsafe, but two clusters dominate the slice and materially reduce actionable coverage:

- `features_snapshot_missing_or_stale = 38307`
  - This is the largest suppressor class.
  - Example: a representative early row shows `manage_state=BRACKETS_PENDING`, portfolio present, but `features_fresh=false`, which blocks evaluation rather than permitting stale action.
  - Interpretation: this is a real runtime gating load, but still contract-honest.
- `regime_snapshot_missing_or_stale = 5224`
  - Example: SOLUSDT line `4427` blocks until regime freshness catches up; once the regime refreshes, the same chain advances to `RECOMMENDED`.
  - Interpretation: stale-regime suppression is functioning as designed, but it further reduces effective action window density.

### Truly Unexplained Behavior

- No truly unexplained sidecar suppression behavior was proven in this slice.
- The single `recent_terminal_order_state_detected` event is explainable from runtime truth and looks protective rather than anomalous.
- `portfolio_snapshot_missing_or_stale = 322` is also explainable. Example: line `29038` shows local `BRACKETS_PENDING` context while the portfolio snapshot is `symbol_absent`, so fail-closed behavior is correct.

## Execution-Bearing Outcome Review

### Counts

| Outcome | Count |
| --- | ---: |
| `execution_submitted` | 0 |
| `execution_noop` | 0 |
| `reconciled` | 0 |

### Assessment

- The 21h slice produced `zero action-bearing requests`.
- There is no runtime evidence of sidecar-originated execution submission.
- There is no runtime evidence of sidecar-originated execution noop.
- There is no runtime evidence of sidecar-originated reconcile completion.
- There is no runtime evidence of duplicate-close ambiguity from the sidecar path, because the sidecar path never entered the action/request seam.

## Forensic Sufficiency Review

### Classification

`PARTIAL_BUT_USABLE`

### Why

- Trace continuity is good inside the shadow surface:
  - freshness suppressions are readable,
  - scores are explicit,
  - evaluated rows are explicit,
  - recommendations are sparse and attributable.
- The slice is also good enough to prove what did not happen:
  - no request command,
  - no request-state rows,
  - no sidecar close lineage.
- But the new Phase-2 forensic additions are not runtime-proven yet:
  - no `request_id` evidence,
  - no request-state progression,
  - no request-to-outcome linkage,
  - no reconcile trace under sidecar origin.
- Therefore the live forensic surface is usable for the next targeted capture decision, but insufficient for action-pilot clearance from this slice alone.

## Dominant Next-Work Cluster

`insufficient_runtime_exercise`

### Evidence-Based Justification

- Runtime posture stayed in `shadow`, not `enable`.
- The slice exercised shadow recommendation behavior but not the newly added request seam.
- Zero counts were observed for the entire Phase-2 request / request-state / close / reconcile chain.
- Because the absent exercise is fully explained by posture, `request_path_bug` is not the dominant proven cluster in this slice.
- Because suppressions remained contract-honest and mostly freshness / lifecycle related, `suppression_logic_issue` is not the dominant proven cluster either.

## Next Exact Step

Prepare one targeted runtime capture prompt for the first human-controlled `enable` slice after restart, with explicit acceptance criteria that require at least one nonzero `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST` and a provable `request_id -> request_state -> close handling -> reconcile` lineage, while preserving operator-only authority over any runtime enablement or pilot decision.
