# R7D Peak-Giveback Runtime Observation Report

## Problem Framing

R7D audits the first fresh runtime slice after R7C and answers a bounded question: did runtime now emit the new peak-giveback observability surfaces, or is the Sidecar peak-giveback path still not provable from production-style artifacts?

This package does not retune thresholds, does not modify code, and does not reinterpret R7A or R7C at code level. It only evaluates fresh runtime evidence.

## Observation Window

- Freshest Sidecar restart anchor in trade lifecycle: 2026-04-25T23:00:46.264Z
- Observation window start: 2026-04-25T23:00:46.264Z
- Observation window end: 2026-04-26T09:27:22.675Z
- Trade lifecycle artifact: logs/trade_lifecycle.jsonl, last write 2026-04-26 09:27:40 UTC
- Order log artifact: logs/order_log_v1.jsonl, last write 2026-04-26 09:20:00 UTC
- Shadow journal artifact: logs/shadow_critical_event_journal_v1.jsonl, last write 2026-04-26 09:27:40 UTC
- Execution domain logs inspected: logs/domain_execution_position.log and logs/domain_execution_position.log.1

## FACTS

- The required read-first docs under docs/ai are still absent on disk. This remains a repo-policy gap, not runtime evidence.
- The latest `POSITION_POLICY_SIDECAR_MODE_ACTIVE` row is trace_id `pps:__DOMAIN__:1777158046264:1` at 2026-04-25T23:00:46.264Z.
- That latest mode-active row does not contain `sidecar_config_snapshot`.
- Across the entire trade lifecycle file, zero Sidecar rows contain `sidecar_config_snapshot`.
- Across the entire trade lifecycle file, zero Sidecar rows contain `peak_giveback_snapshot`.
- Across the entire trade lifecycle file, zero Sidecar rows contain `peak_giveback_detail`.
- Across the latest observation window, Sidecar emitted:
  - 1 `POSITION_POLICY_SIDECAR_MODE_ACTIVE`
  - 48,770 `POSITION_POLICY_SIDECAR_SUPPRESSED`
  - 296 `POSITION_POLICY_SIDECAR_SCORES`
  - 296 `POSITION_POLICY_SIDECAR_EVALUATED`
  - 0 `POSITION_POLICY_SIDECAR_RECOMMENDED`
  - 0 `POSITION_POLICY_SIDECAR_CLOSE_REQUESTED`
- Across the latest observation window, 49,362 non-mode Sidecar rows are missing `peak_giveback_snapshot`.
- Across the latest observation window, no Sidecar row carries `policy_source`.
- The first evaluated row in the latest window is `pps:BNBUSDT:1777158302057:76580` at 2026-04-25T23:05:02.057Z for rid `aurora_BNBUSDT_1777136102246`.
- That evaluated row contains legacy lifecycle context (`side=SELL`, `position_qty=0.1`, `entry_price=629.58`, `portfolio_snapshot_status=present`) but `mark_price`, `unrealized_pnl_usdt`, and `unrealized_pnl_pct` are all null.
- All 296 evaluated rows in the latest window belong to rid `aurora_BNBUSDT_1777136102246`.
- All 296 evaluated rows in the latest window have zero populated position economics for `mark_price` and `unrealized_pnl_usdt`.
- No evaluated row in the latest window emits explicit `null_reasons` because `peak_giveback_snapshot` is absent entirely.
- Suppression distribution in the latest window is:
  - `no_manage_flow_for_symbol`: 42,054
  - `manage_flow_has_no_active_lifecycle`: 2,792
  - `features_snapshot_missing_or_stale`: 3,462
  - `regime_snapshot_missing_or_stale`: 462
- Reason-code distribution in the latest window is dominated by:
  - `no_active_lifecycle`: 44,846
  - `features_stale`: 3,462
  - `regime_stale`: 462
- There are no malformed Sidecar payload suppressions in the latest window.
- There are no `manage_flow_close_in_progress` suppressions in the latest window.
- Targeted search across logs/order_log_v1.jsonl, logs/shadow_critical_event_journal_v1.jsonl, logs/domain_execution_position.log, and logs/domain_execution_position.log.1 returned no matches for:
  - `peak_giveback`
  - `position_policy_sidecar`
  - `POSITION_POLICY_SIDECAR_CLOSE_REQUESTED`
  - `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`
  - `policy_source`
- The current SSOT config in config/aurora/domains.yaml still declares:
  - `position_policy_sidecar.mode = enable`
  - `peak_giveback_close.enabled = true`
  - `edge_arm_usd = 25.0`
  - `giveback_trigger_pct = 50.0`
  - freshness limits `15000 / 15000 / 30000 / 15000`
- The runtime window does not echo those values back in any startup or policy row.
- Existing validator cross-check on the latest slice reports one fill-ingress symbol, one fresh portfolio-present candidate, and zero post-fill evaluated rows for that fill-ingress path.
- The validator identifies BNBUSDT post-fill as `became_candidate_but_never_evaluated`, with first blocker `manage_flow_has_no_active_lifecycle` after fill ingress at 2026-04-26T05:17:12.496Z.

## INFERENCES

- The fresh runtime slice is still emitting a pre-R7C payload shape, or an equivalent deployment or serialization path that strips the R7C additive fields before they land in runtime artifacts.
- Q1 fails: post-R7C runtime did not emit the new observability fields in the inspected artifacts.
- Q2 fails: runtime does not prove the loaded `peak_giveback_close` config, even though SSOT config still says 25.0 and 50.0.
- Q3 fails: peak-giveback states cannot be reconstructed from runtime because the required state carrier `peak_giveback_snapshot` never appears.
- Q4 fails: runtime does not prove any armed lifecycle because there is no `peak_giveback_snapshot`, no `peak_giveback_armed` marker, and no usable economic surface on evaluated rows.
- Q5 fails on proof, not on market behavior: there is no threshold-met runtime evidence, but the absence of trigger rows cannot be classified as quiet-by-market because the required observability fields are missing.
- Q6 is only partially answerable. The trigger path did not fire at all, so there is no evidence of duplicate trigger storms, no evidence of direct exchange action from Sidecar, and no evidence of bracket mutation from Sidecar provenance. But this is absence of trigger activity, not proof of a clean exercised trigger path.
- The BNB post-fill transition gap is adjacent evidence that runtime lifecycle continuity is not clean enough to strengthen the peak-giveback case. After fill ingress, the candidate became suppress-only and never re-entered evaluated.

## ASSUMPTIONS

- The latest `POSITION_POLICY_SIDECAR_MODE_ACTIVE` row is the correct anchor for the freshest post-R7C runtime slice.
- logs/trade_lifecycle.jsonl remains the authoritative artifact for serialized Sidecar payload shape.
- The targeted searches over order log, shadow journal, and execution-domain logs would have surfaced downstream Sidecar routing if it existed in those artifacts.

## UNKNOWNS

- Whether the runtime host actually restarted on an R7C-capable build.
- Whether a downstream serializer or transport path dropped the R7C additive fields even if in-memory runtime had them.
- Whether any armed or threshold-met peak-giveback case occurred in memory but was not serialized to the inspected artifacts.
- Whether a different artifact outside the requested runtime surfaces captured R7C fields.

## Config Snapshot Proof

Expected by SSOT config:

- `peak_giveback_close.enabled = true`
- `edge_arm_usd = 25.0`
- `giveback_trigger_pct = 50.0`
- freshness limits: `portfolio=15000`, `features=15000`, `regime=30000`, `order_state=15000`

Runtime proof status:

- Not proven.
- No inspected mode-active row contains `sidecar_config_snapshot`.
- No inspected sidecar-specific text log surfaced the config fields by name.

## New Field Presence Proof

Latest mode-active row example:

- Timestamp: 2026-04-25T23:00:46.264Z
- Trace: `pps:__DOMAIN__:1777158046264:1`
- `sidecar_config_snapshot`: absent

Latest-window evaluated row example:

- Timestamp: 2026-04-25T23:05:02.057Z
- Trace: `pps:BNBUSDT:1777158302057:76580`
- Rid: `aurora_BNBUSDT_1777136102246`
- `peak_giveback_snapshot`: absent
- `policy_source`: absent
- Legacy economics still null:
  - `position_snapshot.mark_price = null`
  - `position_snapshot.unrealized_pnl_usdt = null`
  - `position_snapshot.unrealized_pnl_pct = null`

Conclusion:

- R7C runtime field presence is not observed.
- Missing fields are not replaced by explicit null-reason semantics.

## Peak-Giveback State Distribution

Proven runtime counts by named R7C peak-giveback state:

- `peak_giveback_disabled`: 0
- `peak_giveback_not_armed_below_edge`: 0
- `peak_giveback_armed`: 0
- `peak_giveback_below_trigger`: 0
- `peak_giveback_threshold_met`: 0
- `peak_giveback_suppressed_close_in_progress`: 0
- `peak_giveback_suppressed_stale_inputs`: 0
- `peak_giveback_unavailable_economics_missing`: 0
- `peak_giveback_not_ready`: 0
- `unknown or malformed because snapshot missing`: 49,362 non-mode rows

This is not a quiet-state distribution. It is an observability failure distribution.

## Lifecycle Case Split

- CASE A — Observable but never armed: 0 proven
- CASE B — Armed but below trigger: 0 proven
- CASE C — Threshold met and recommendation/request emitted: 0
- CASE D — Threshold met but no recommendation/request: 0 proven
- CASE E — Suppressed safely: generic Sidecar suppressions observed at high volume, mainly `no_manage_flow_for_symbol`, `manage_flow_has_no_active_lifecycle`, and stale snapshots
- CASE F — Still unobservable: yes, globally. Latest mode-active row is missing `sidecar_config_snapshot`; all non-mode rows are missing `peak_giveback_snapshot`; evaluated rows lack usable economics and have no explicit null-reason block
- CASE G — Anomalous or unsafe: no exercised trigger-path anomaly observed because the trigger path never fired; one adjacent lifecycle continuity anomaly exists on BNBUSDT post-fill, where the candidate never re-entered evaluated

## Trigger, Routing, And Safety Analysis

- Recommendation count: 0
- Close-request count: 0
- Downstream sidecar close routing observed: 0
- Duplicate trigger storm observed: 0
- Sidecar firing without open lifecycle observed: 0 trigger-path cases
- Sidecar firing under close-in-progress observed: 0 trigger-path cases
- Sidecar firing under stale or missing inputs observed: 0 trigger-path cases
- Bracket mutation evidence from Sidecar provenance: none found
- Direct exchange action from Sidecar provenance: none found
- Malformed sidecar payloads: none found

Interpretation:

- Safety stayed fail-closed at the coarse Sidecar level.
- The peak-giveback trigger path itself was not exercised or serialized, so trigger-path cleanliness is not runtime-proven.

## First Bounded Economic Signal

Classification: mixed / insufficient sample.

Reason:

- There is one evaluated lifecycle rid in the latest window.
- That lifecycle never exposes the required economic fields in runtime artifacts.
- No arm state, giveback percentage, threshold-crossing state, recommendation provenance, or close-request provenance is visible.

## Final Verdict

The fresh runtime slice is not quiet-but-observable. It is still not observable in the R7C sense.

R7C payload additions are absent from the latest runtime artifacts, so peak-giveback state cannot be reconstructed and no arm or threshold conclusion can be made safely from runtime.

Verdict: `PEAK_GIVEBACK_RUNTIME_NOT_PROVEN`
