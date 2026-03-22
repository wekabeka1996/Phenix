# REPORT — OVERNIGHT_RUNTIME_FORENSIC_FOR_TERMINAL_NON_FILL_ORDER_EVENTS

## 1. Objective
Determine whether the fresh overnight live runtime produced natural proof for the terminal non-fill execution seam, with primary focus on `EVT:ORDER_REJECTED` and the terminal non-fill subset of `EVT:ORDER_STATE_CHANGED`, and secondary focus on identity continuity through the early execution admission/open chain.

## 2. Observation window
Analyzed window: `2026-03-22 00:00:00+02:00` through `2026-03-22 12:44:49+02:00`.

Why this window is correct:
- it is the first full post-restart overnight/daytime slice written into [2026-03-22.jsonl](c:/Users/user/Music/Phenix/ops/wal/2026-03-22.jsonl)
- the main live log set for the same day was still active, including [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log), rotated `aurora_core.log.*`, [domain_execution_position.log](c:/Users/user/Music/Phenix/logs/domain_execution_position.log), [order_log_v1.jsonl](c:/Users/user/Music/Phenix/logs/order_log_v1.jsonl), [trade_lifecycle.jsonl](c:/Users/user/Music/Phenix/logs/trade_lifecycle.jsonl), and [shadow_critical_event_journal_v1.jsonl](c:/Users/user/Music/Phenix/logs/shadow_critical_event_journal_v1.jsonl)
- this slice is long enough to include real post-warmup execution activity, not only startup noise

## 3. Evidence base
Inspected runtime artifacts:
- [2026-03-22.jsonl](c:/Users/user/Music/Phenix/ops/wal/2026-03-22.jsonl)
- [shadow_critical_event_journal_v1.jsonl](c:/Users/user/Music/Phenix/logs/shadow_critical_event_journal_v1.jsonl)
- [order_log_v1.jsonl](c:/Users/user/Music/Phenix/logs/order_log_v1.jsonl)
- [domain_execution_position.log](c:/Users/user/Music/Phenix/logs/domain_execution_position.log)
- [trade_lifecycle.jsonl](c:/Users/user/Music/Phenix/logs/trade_lifecycle.jsonl)
- [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log)

Commands used for evidence extraction:
- JSONL machine scans over WAL, shadow journal, and order log for scoped verbs and canonical fields
- `rg` searches for `ORDER_REJECTED`, `ORDER_STATE_CHANGED`, `terminal_state_kind`, `reject_reason_normalized`, `canonical_identity_key`, `identity_quality`, `compatibility_aliases_retained`, `ORDER_INDEX:RESERVE_ENTRY`, `EVT:TRADE_INTENT_PROPOSED`, `CMD:OPEN`, `DEC:OPEN`
- targeted rid correlation for:
  - `mdamr-62575e17395a9984`
  - `mdamr-bb47cf1d2ff4529f`
  - `mdamr-e2ea1134c33f623d`

## 4. Scoped search results
Search targets:
- `EVT:ORDER_REJECTED`
- `EVT:ORDER_STATE_CHANGED`
- `terminal_state_kind`
- `reject_reason_normalized`
- `canonical_identity_key`
- `identity_quality`
- `compatibility_aliases_retained`
- `ORDER_INDEX:RESERVE_ENTRY`
- `EVT:TRADE_INTENT_PROPOSED`
- `CMD:OPEN`
- `DEC:OPEN`

Results:
- WAL overnight contained `3` natural `EVT:ORDER_REJECTED`
- WAL overnight contained `0` `EVT:ORDER_STATE_CHANGED`
- WAL overnight contained canonical reject fields exactly `3` times each:
  - `terminal_state_kind`
  - `reject_reason_normalized`
  - `canonical_identity_key`
  - `identity_quality`
  - `compatibility_aliases_retained`
- shadow overnight contained:
  - `35` `ORDER_INDEX:RESERVE_ENTRY`
  - `21` `EVT:TRADE_INTENT_PROPOSED`
  - `21` `CMD:OPEN`
  - `9` `DEC:OPEN`
  - `0` `EVT:ORDER_REJECTED`
  - `0` `EVT:ORDER_STATE_CHANGED`
- order log overnight contained:
  - `3` execution-side `ORDER_REJECTED` with `source_fsm=ExecPosFSM`
  - `1` `ORDER_CANCELLED`
  - no `ORDER_STATE_CHANGED` event type

## 5. Natural terminal non-fill instances
Natural scoped runtime events did appear overnight, but only for `EVT:ORDER_REJECTED`.

| ts_ms | symbol | rid | lifecycle_id / idempotent_key | orderId / clientOrderId | terminal_state_kind | reject_reason_normalized | source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `1774167303645` | `XRPUSDT` | `mdamr-62575e17395a9984` | no event-level `idempotent_key`; prior open chain lifecycle id `5ee1d314-0f06-4012-9b21-b57248ce96c4` | none | `REJECTED` | `MAKER_ONLY_REJECT` | [2026-03-22.jsonl](c:/Users/user/Music/Phenix/ops/wal/2026-03-22.jsonl) |
| `1774167304096` | `BNBUSDT` | `mdamr-bb47cf1d2ff4529f` | no event-level `idempotent_key`; prior open chain lifecycle id `0a50211b-785d-4606-8832-ff0dd35d9561` | none | `REJECTED` | `MAKER_ONLY_REJECT` | [2026-03-22.jsonl](c:/Users/user/Music/Phenix/ops/wal/2026-03-22.jsonl) |
| `1774169100449` | `XRPUSDT` | `mdamr-e2ea1134c33f623d` | no event-level `idempotent_key`; prior open chain lifecycle id `5515d7a9-0008-4098-b68c-10574898cdad` | none | `REJECTED` | `MAKER_ONLY_REJECT` | [2026-03-22.jsonl](c:/Users/user/Music/Phenix/ops/wal/2026-03-22.jsonl) |

Natural terminal non-fill `EVT:ORDER_STATE_CHANGED` instances found overnight:
- `0`

## 6. Open-chain identity continuity
Observed repeated open-chain pattern across overnight cases:

| rid | symbol | reserve identity basis | downstream proposed/open basis | later natural terminal event basis | continuity assessment |
| --- | --- | --- | --- | --- | --- |
| `mdamr-62575e17395a9984` | `XRPUSDT` | `ORDER_INDEX:RESERVE_ENTRY` used `rid_ref.idempotent_key = rid` | `EVT:TRADE_INTENT_PROPOSED`, `CMD:OPEN`, `DEC:OPEN` used lifecycle id `5ee1d314-0f06-4012-9b21-b57248ce96c4` in payload fragments | `EVT:ORDER_REJECTED` canonical key fell back to `symbol + rid + terminal_state + reject_reason` | split |
| `mdamr-bb47cf1d2ff4529f` | `BNBUSDT` | `rid` basis | lifecycle id `0a50211b-785d-4606-8832-ff0dd35d9561` | reject canonical key used `symbol + rid + terminal_state + reject_reason` | split |
| `mdamr-e2ea1134c33f623d` | `XRPUSDT` | `rid` basis | lifecycle id `5515d7a9-0008-4098-b68c-10574898cdad` | reject canonical key used `symbol + rid + terminal_state + reject_reason` | split |
| `aurora_BTCUSDT_1774131001501` | `BTCUSDT` | `rid` basis | lifecycle id `85abbb0f-c9c6-4143-a25b-9586521ac458` | later reject path previously observed on `rid` basis | split |
| `aurora_ETHUSDT_1774131902549` | `ETHUSDT` | `rid` basis | no completed open chain after emit failure | no natural terminal event | split/aborted |

Observed repeated identity behavior:
- early reserve runs on `rid`
- downstream open-chain payload fragments carry `lifecycle_id` as `idempotent_key`
- natural execution-side reject canonical identity falls back to `rid` because no order-level ids were present
- `partial_identity=true` remained true on the shadow open-chain artifacts

## 7. Terminal chain reconstruction
Scoped terminal chains were reconstructable only for the three natural execution-side `ORDER_REJECTED` cases.

### Case 1 — `mdamr-62575e17395a9984` / `XRPUSDT`
Chain:
1. [shadow_critical_event_journal_v1.jsonl](c:/Users/user/Music/Phenix/logs/shadow_critical_event_journal_v1.jsonl) captured `ORDER_INDEX:RESERVE_ENTRY`
2. shadow captured `EVT:TRADE_INTENT_PROPOSED` with lifecycle id `5ee1d314-0f06-4012-9b21-b57248ce96c4`
3. shadow captured `CMD:OPEN`
4. shadow captured `DEC:OPEN`
5. [domain_execution_position.log](c:/Users/user/Music/Phenix/logs/domain_execution_position.log) captured `LIMIT_SUBMIT_TRACE`
6. WAL emitted natural `EVT:ORDER_REJECTED` with canonical fields
7. [order_log_v1.jsonl](c:/Users/user/Music/Phenix/logs/order_log_v1.jsonl) recorded execution-side `ORDER_REJECTED`
8. [trade_lifecycle.jsonl](c:/Users/user/Music/Phenix/logs/trade_lifecycle.jsonl) later carried orphan/TTL cleanup status, not scoped canonical terminal non-fill event truth

Raw/legacy fields observed on WAL reject:
- `reason`
- `error_code`
- `rid`

Canonical fields observed on WAL reject:
- `terminal_non_fill=true`
- `terminal_state_kind=REJECTED`
- `reject_reason_normalized=MAKER_ONLY_REJECT`
- `reject_reason_source=reason`
- `identity_quality=order_identity_weak`
- `canonical_identity_key=evt:order_rejected:symbol=XRPUSDT:rid=mdamr-62575e17395a9984:terminal_state=REJECTED:reject_reason=MAKER_ONLY_REJECT`
- `compatibility_aliases_retained=true`

Shadow result:
- open-chain visible
- reject event itself missing from shadow

### Case 2 — `mdamr-bb47cf1d2ff4529f` / `BNBUSDT`
Observed same structure as Case 1:
- reserve in shadow on `rid`
- proposed/open chain in shadow on lifecycle id `0a50211b-785d-4606-8832-ff0dd35d9561`
- execution `LIMIT_SUBMIT_TRACE` in [domain_execution_position.log](c:/Users/user/Music/Phenix/logs/domain_execution_position.log)
- canonical `EVT:ORDER_REJECTED` in WAL
- execution-side `ORDER_REJECTED` in order log
- no shadow `EVT:ORDER_REJECTED`

### Case 3 — `mdamr-e2ea1134c33f623d` / `XRPUSDT`
Observed same structure as Case 1:
- reserve in shadow on `rid`
- proposed/open chain in shadow on lifecycle id `5515d7a9-0008-4098-b68c-10574898cdad`
- execution `LIMIT_SUBMIT_TRACE` in [domain_execution_position.log](c:/Users/user/Music/Phenix/logs/domain_execution_position.log)
- canonical `EVT:ORDER_REJECTED` in WAL
- execution-side `ORDER_REJECTED` in order log
- no shadow `EVT:ORDER_REJECTED`

No natural terminal non-fill `EVT:ORDER_STATE_CHANGED` chain could be reconstructed because no such event occurred in the overnight window.

## 8. Facts
- **FACT**: the overnight WAL contains `3` natural `EVT:ORDER_REJECTED` and `0` `EVT:ORDER_STATE_CHANGED`.
- **FACT**: all `3` natural WAL rejects carried canonical contract fields:
  - `terminal_non_fill=true`
  - `terminal_state_kind=REJECTED`
  - `reject_reason_normalized=MAKER_ONLY_REJECT`
  - `identity_quality=order_identity_weak`
  - `canonical_identity_key=...`
  - `compatibility_aliases_retained=true`
- **FACT**: the overnight shadow journal contains `0` `EVT:ORDER_REJECTED` and `0` `EVT:ORDER_STATE_CHANGED`.
- **FACT**: the shadow journal did capture the early open chain for the same reject cases:
  - `ORDER_INDEX:RESERVE_ENTRY`
  - `EVT:TRADE_INTENT_PROPOSED`
  - `CMD:OPEN`
  - `DEC:OPEN`
- **FACT**: for the three natural reject cases, `ORDER_INDEX:RESERVE_ENTRY` used `rid_ref.idempotent_key = rid`.
- **FACT**: for the same three cases, downstream `EVT:TRADE_INTENT_PROPOSED`, `CMD:OPEN`, and `DEC:OPEN` carried lifecycle-id-based `idempotent_key` in payload fragments.
- **FACT**: all observed shadow open-chain records for those cases had `partial_identity=true`.
- **FACT**: [order_log_v1.jsonl](c:/Users/user/Music/Phenix/logs/order_log_v1.jsonl) independently recorded the same three execution-side rejects with `source_fsm=ExecPosFSM`.
- **FACT**: [domain_execution_position.log](c:/Users/user/Music/Phenix/logs/domain_execution_position.log) shows `LIMIT_SUBMIT_TRACE` for the same three reject cases, proving they reached exchange submission attempt.
- **FACT**: one `ORDER_CANCELLED` exists in [order_log_v1.jsonl](c:/Users/user/Music/Phenix/logs/order_log_v1.jsonl), but there was no corresponding overnight `EVT:ORDER_STATE_CHANGED` in WAL or shadow.

Cause / mechanism / effect / operational risk:
- Cause: live overnight traffic naturally produced GTX maker-only rejects.
  Mechanism: execution-side `open_executor` emitted canonical `EVT:ORDER_REJECTED`.
  Effect: runtime proof now exists for the canonical reject contract in WAL.
  Operational risk: lineage remains weak because order-level ids were absent.
- Cause: shadow observability captured reserve/open but not the terminal reject events.
  Mechanism: terminal reject seam is not landing in shadow journal on these natural cases.
  Effect: source-to-shadow truth chain is incomplete for scoped rejects.
  Operational risk: operators can see canonical reject truth in WAL/order log but miss it in the shadow truth plane.
- Cause: early reserve and later open/reject use different identity bases.
  Mechanism: reserve uses `rid`; downstream open chain uses lifecycle id; reject canonical key falls back to `rid`.
  Effect: identity continuity is split across the same lifecycle.
  Operational risk: future replay/correlation remains more fragile than the prior package report implied.

## 9. Inferences
- **INFERENCE**: the terminal non-fill hardening for `EVT:ORDER_REJECTED` is naturally exercised in live runtime and appears broadly correct in WAL.
- **INFERENCE**: the `EVT:ORDER_STATE_CHANGED` terminal non-fill seam was not naturally exercised overnight, so that part of the hardening package remains runtime-unproven.
- **INFERENCE**: `FSMCore.emit()` or its upstream canonicalization seam is being exercised for natural execution-side rejects, because the canonical fields appear in WAL on real live events.
- **INFERENCE**: the missing shadow rejects indicate either a shadow capture gap or a scoped routing/instrumentation gap after canonical emission.
- **INFERENCE**: the repeated `rid` vs lifecycle-id split is not a one-off anomaly; it is a recurring live pattern across multiple symbols and multiple rids.

## 10. Assumptions
- **ASSUMPTION**: if an overnight `EVT:ORDER_STATE_CHANGED` had occurred on the active scoped paths, it would have appeared in at least WAL or shadow artifacts.
- **ASSUMPTION**: the single `ORDER_CANCELLED` row in order log is not sufficient by itself to prove the scoped `EVT:ORDER_STATE_CHANGED` canonical seam, because it is not the scoped verb and lacks canonical-field proof in WAL/shadow.

## 11. Unknowns
- **UNKNOWN**: why the three natural `EVT:ORDER_REJECTED` events were not captured in the shadow journal despite the open chain being captured there.
- **UNKNOWN**: whether natural terminal non-fill `EVT:ORDER_STATE_CHANGED` would carry equally correct canonical fields when it eventually occurs.
- **UNKNOWN**: whether the `rid` vs lifecycle-id split is intentional design or unresolved identity drift.
- **UNKNOWN**: whether a future natural `CANCELED` or `EXPIRED` terminal state would appear on `rid`, lifecycle id, or a third basis.

## 12. FSMCore seam assessment
Assessment: **exercised for natural execution-side rejects, but boundedness is only partially proven**.

What the overnight evidence proves:
- natural live `EVT:ORDER_REJECTED` emitted with canonical fields in WAL
- canonicalization is additive rather than purely decorative, because `reject_reason_normalized`, `terminal_state_kind`, `canonical_identity_key`, `identity_quality`, and `compatibility_aliases_retained` were present on real live rejects

What the overnight evidence does not prove:
- no natural terminal non-fill `EVT:ORDER_STATE_CHANGED` traversed the seam
- no raw pre-normalization producer payload was captured adjacent to the seam for direct before/after diff

Masking risk verdict:
- not enough evidence to claim material masking on the observed reject cases
- enough evidence to say the seam is exercised
- not enough evidence to certify the seam as fully bounded, because shadow missed the resulting rejects and no `ORDER_STATE_CHANGED` instance exercised it

## 13. Semantic separation check
Overnight natural evidence proves only a partial separation result.

Proven:
- natural execution-side `ORDER_REJECTED` remained semantically explicit as:
  - `terminal_non_fill=true`
  - `terminal_state_kind=REJECTED`
  - `reject_reason_normalized=MAKER_ONLY_REJECT`

Not proven overnight:
- `ORDER_REJECTED` versus `CANCELED` on the scoped `EVT:ORDER_STATE_CHANGED` seam
- `ORDER_REJECTED` versus `EXPIRED` on the scoped `EVT:ORDER_STATE_CHANGED` seam
- natural runtime `terminal_state_kind` values for `CANCELED` or `EXPIRED`

Conclusion:
- no evidence of collapse into a vague terminal bucket was found for the observed reject cases
- semantic separation for the full scoped seam remains only partially runtime-proven

## 14. Lineage quality assessment
| case / path | observed overnight? | rid | lifecycle_id | orderId / exchangeOrderId | clientOrderId | canonical_identity_key | partial_identity | lineage quality |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mdamr-62575e17395a9984` reserve/open/reject | yes | yes | yes on open chain | none | none | yes on reject | yes | degraded |
| `mdamr-bb47cf1d2ff4529f` reserve/open/reject | yes | yes | yes on open chain | none | none | yes on reject | yes | degraded |
| `mdamr-e2ea1134c33f623d` reserve/open/reject | yes | yes | yes on open chain | none | none | yes on reject | yes | degraded |
| natural `EVT:ORDER_REJECTED` canonical seam as a class | yes | yes | not on reject event itself | none | none | yes | n/a in WAL, yes upstream in shadow | degraded / weak |
| terminal non-fill `EVT:ORDER_STATE_CHANGED` | no | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| early `ORDER_INDEX:RESERVE_ENTRY` seam as a class | yes | yes | no | none | none | rid-based local idempotent key only | yes | degraded |

Rationale:
- not `exact`, because order-level ids were absent
- not merely `unknown`, because the same cases are traceable across reserve, open, reject, and order-log artifacts by `rid`
- `degraded` is more accurate than `weak` for the three natural reject chains because cross-artifact correlation still worked, but only through partial identity

## 15. Runtime decision
**Decision: C**

`C = Natural scoped terminal non-fill proof is still insufficient and the correct next step is FORCED_EVENT_RUNTIME_PROOF_FOR_TERMINAL_NON_FILL_ORDER_EVENTS.`

Justification:
- overnight natural runtime did provide real proof for execution-side `EVT:ORDER_REJECTED`
- overnight natural runtime still provided `0` terminal non-fill `EVT:ORDER_STATE_CHANGED`
- overnight natural runtime exposed a real repeated identity split across reserve/open/reject
- overnight natural runtime exposed a shadow observability gap: real canonical rejects landed in WAL and order log but not in shadow

Why not `A`:
- full scoped seam is not runtime-confirmed because `EVT:ORDER_STATE_CHANGED` did not occur naturally
- shadow truth-plane coverage is incomplete for the natural reject cases

Why not `B`:
- the overnight window was already long and active enough to produce multiple natural execution rejects
- one more passive observation window is unlikely to resolve the missing `ORDER_STATE_CHANGED` proof efficiently
- the higher-value next step is now bounded forced-event proof, not more waiting

## 16. Residual risks
- natural runtime proof still does not cover terminal non-fill `EVT:ORDER_STATE_CHANGED`
- shadow truth plane missed all three natural execution-side canonical rejects
- reserve/open/reject identity continuity remains split between `rid` and lifecycle id
- natural reject lineage remains degraded because order-level ids are absent
- a single `ORDER_CANCELLED` in order log does not prove the scoped canonical `EVT:ORDER_STATE_CHANGED` seam

## 17. Recommended next step
Run **FORCED_EVENT_RUNTIME_PROOF_FOR_TERMINAL_NON_FILL_ORDER_EVENTS** with a narrow validation goal:
- produce one controlled execution-side `EVT:ORDER_REJECTED` and verify raw source -> canonical WAL -> shadow path
- produce one controlled terminal non-fill `EVT:ORDER_STATE_CHANGED` for `CANCELED` or `EXPIRED`
- capture the same case across:
  - source/producer artifact
  - `FSMCore.emit()` seam
  - WAL
  - shadow journal
  - consumer-visible artifact

Do not broaden beyond that.
