# PKG_REGIME_CONFIDENCE_UPSTREAM_PROOF_8630384019

Date: 2026-04-03

## 1. Scope

Question in scope: for RID `aurora_ETHUSDT_1775105700256` and exchange order `8630384019`, prove the earliest upstream point for `regime_confidence=0.85`, determine whether it came from detector heartbeat or cached regime state, and audit whether any hidden producer or enricher exists between regime detection and `TRADE_INTENT_PROPOSED`.

Evidence rules used in this report:
- local workspace only
- facts separated from inferences
- missing upstream artifact treated as unproven, not assumed
- runtime artifacts take precedence over comments or expectations

FACT: Workspace truth used for this report was local branch `Phenix_v2` at commit `bbda8f7f6021fde0d7d43b281ac033a3b5932acc` with a dirty worktree.

FACT: The referenced protocol files `docs/ai/AGENT_REPORT_SCHEMA.md` and `docs/ai/DONE_CRITERIA.md` were not present at the inspected local paths, so this report follows the existing forensic-report style already present under `reports/`.

## 2. Executive Verdict

FACT: The earliest retained local artifact for the target RID that explicitly carries `regime_confidence=0.85` is [2026-04-02.jsonl#L5774](../ops/wal/2026-04-02.jsonl#L5774), the `EVT:TRADE_INTENT_PROPOSED` record emitted at `1775105700271`.

FACT: The same value is corroborated by [order_log_v1.jsonl#L95](../logs/order_log_v1.jsonl#L95) and later lifecycle records at [trade_lifecycle.jsonl#L13](../logs/trade_lifecycle.jsonl#L13) and [trade_lifecycle.jsonl#L15](../logs/trade_lifecycle.jsonl#L15).

FACT: The last visible ETH transition line before the order open is [domain_regime_detector.log#L60](../logs/domain_regime_detector.log#L60), which shows `UNCERTAIN -> TREND_DOWN` with confidence `0.3302868178681544954828986582`. The next visible ETH transition line is [domain_regime_detector.log#L70](../logs/domain_regime_detector.log#L70), which shows `TREND_DOWN -> LOW_VOLATILITY` with confidence `0.2869937024168590254966161325`.

FACT: Local source code proves that the detector emits `EVT:REGIME_DETECTED` on every basis-bar heartbeat, updates `stable_confidence` on confirmed same-regime heartbeats, and only writes the human-readable transition log when `changed` is true at [regime_detector.py#L705-L801](../apps/reference/domains/regime_detector/regime_detector.py#L705-L801).

FACT: Local source code proves the downstream Aurora path does not synthesize `0.85`. The path is detector event -> Aurora state cache -> shared per-symbol regime cache -> safety-gate read -> intent payload -> lifecycle persistence. Relevant anchors are [aurora_handler.py#L545](../apps/reference/domains/decision_making/aurora_handler.py#L545), [event_handlers.py#L473-L477](../apps/reference/domains/decision_making/event_handlers.py#L473-L477), [safety_gates.py#L132-L140](../apps/reference/domains/decision_making/safety_gates.py#L132-L140), [safety_gates.py#L496-L549](../apps/reference/domains/decision_making/safety_gates.py#L496-L549), [intent_builder.py#L291-L311](../apps/reference/domains/decision_making/intent_builder.py#L291-L311), [intent_builder.py#L418-L426](../apps/reference/domains/decision_making/intent_builder.py#L418-L426), and [trade_lifecycle_logger.py#L269](../apps/reference/telemetry/trade_lifecycle_logger.py#L269).

FACT: The execution-side `ORDER_PLACED` path is non-generative and, in this case, lossy rather than inflationary. `DEC:OPEN` in [2026-04-02.jsonl#L5775](../ops/wal/2026-04-02.jsonl#L5775) does not contain `regime_confidence`, `open_executor` only reads `(decision.pld or {}).get("regime_confidence")` at [open_executor.py#L637](../apps/reference/domains/execution_position/open_executor.py#L637), and the actual execution order log at [order_log_v1.jsonl#L98](../logs/order_log_v1.jsonl#L98) records `regime_confidence: null`.

FACT: No retained `REGIME_DETECTED` artifact for the target ETH 07:55 window was found in `ops/wal/2026-04-02.jsonl`.

INFERENCE: The strongest evidence-bounded explanation is detector heartbeat refresh -> cached regime state -> safety gates -> intent builder.

UNKNOWN: No retained pre-intent detector artifact with ETH `0.85` was found in available local logs or WAL, so the exact upstream event instance remains unproven.

VERDICT: Hidden downstream enrichment is disproven. Semantic corruption is not evidenced. The primary proven issue is an observability gap between detector heartbeat truth and retained artifacts. Exact upstream proof for the `0.85` event remains absent.

## 3. Evidence Table

| Source | Anchor | Proven fact |
| --- | --- | --- |
| Detector config | [regime.yaml#L39-L40](../config/aurora/regime.yaml#L39-L40) | Runtime confidence clamp is configured as `0.15 .. 0.85`. |
| Detector calculation | [regime_detector.py#L247-L282](../apps/reference/domains/regime_detector/regime_detector.py#L247-L282) | `_calculate_confidence()` bounds confidence using configured min and max. |
| Detector heartbeat semantics | [regime_detector.py#L705-L801](../apps/reference/domains/regime_detector/regime_detector.py#L705-L801) | Stable confidence updates on confirmed heartbeats; `EVT:REGIME_DETECTED` emits every basis bar; text log writes only on `changed`. |
| Visible ETH transition before target open | [domain_regime_detector.log#L60](../logs/domain_regime_detector.log#L60) | Last visible ETH pre-open transition shows `0.3302868178681544954828986582`. |
| Visible ETH transition after target open | [domain_regime_detector.log#L70](../logs/domain_regime_detector.log#L70) | Next visible ETH transition shows `0.2869937024168590254966161325`. |
| Decision-side earliest retained `0.85` | [2026-04-02.jsonl#L5774](../ops/wal/2026-04-02.jsonl#L5774) | `TRADE_INTENT_PROPOSED` carries `regime=TREND_DOWN` and `regime_confidence=0.85`. |
| Decision-side corroboration | [order_log_v1.jsonl#L95](../logs/order_log_v1.jsonl#L95) | `ORDER_INTENT` from `DecisionMaking` also carries `regime_confidence=0.85`. |
| Lifecycle corroboration | [trade_lifecycle.jsonl#L13](../logs/trade_lifecycle.jsonl#L13) | Rejected lifecycle record carries `regime_confidence=0.85`. |
| Lifecycle after placement/fill | [trade_lifecycle.jsonl#L15](../logs/trade_lifecycle.jsonl#L15) | Reconciled placed-and-filled record still carries `regime_confidence=0.85`. |
| Runtime open path | [aurora_core.log.20#L6184-L6192](../logs/aurora_core.log.20#L6184-L6192) | At 07:55 ETH had cached structural regime, `TREND_DOWN`, SELL signal, and all gates passed. |
| Cache write in Aurora state | [aurora_handler.py#L545](../apps/reference/domains/decision_making/aurora_handler.py#L545) | `state.regime_confidence` is assigned from event confidence. |
| Shared regime cache write | [event_handlers.py#L473-L477](../apps/reference/domains/decision_making/event_handlers.py#L473-L477) | `_per_symbol_regimes[symbol]["confidence"]` is copied from detector payload. |
| Safety-gate read path | [safety_gates.py#L132-L140](../apps/reference/domains/decision_making/safety_gates.py#L132-L140) | `_extract_regime()` reads confidence from the per-symbol regime cache. |
| Safety-gate max logic | [safety_gates.py#L236-L246](../apps/reference/domains/decision_making/safety_gates.py#L236-L246) | `effective_conf` only affects gate decision logic; it is not written back into payload. |
| Intent payload write | [intent_builder.py#L291-L311](../apps/reference/domains/decision_making/intent_builder.py#L291-L311) | `trade_intent` includes `"regime_confidence": sg.regime_confidence`. |
| Decision order-log write | [intent_builder.py#L418-L426](../apps/reference/domains/decision_making/intent_builder.py#L418-L426) | `ORDER_INTENT` logger writes `sg.regime_confidence` directly. |
| Lifecycle persistence | [trade_lifecycle_logger.py#L269](../apps/reference/telemetry/trade_lifecycle_logger.py#L269) | Lifecycle record stores the confidence passed to it. |
| Execution negative proof | [2026-04-02.jsonl#L5775](../ops/wal/2026-04-02.jsonl#L5775), [open_executor.py#L637](../apps/reference/domains/execution_position/open_executor.py#L637), [order_log_v1.jsonl#L98](../logs/order_log_v1.jsonl#L98) | Execution-side open path does not create `0.85`; in this case it drops the field to `null`. |

## 4. Proven Data-Flow Map

FACT: Detector confidence is computed and bounded in [regime_detector.py#L247-L282](../apps/reference/domains/regime_detector/regime_detector.py#L247-L282).

FACT: Stable regime and stable confidence are maintained in detector hysteresis state and emitted on every basis-bar heartbeat in [regime_detector.py#L717-L792](../apps/reference/domains/regime_detector/regime_detector.py#L717-L792).

FACT: Aurora caches detector confidence in symbol state at [aurora_handler.py#L545](../apps/reference/domains/decision_making/aurora_handler.py#L545).

FACT: DecisionMaking also copies detector confidence into the shared per-symbol regime cache at [event_handlers.py#L473-L477](../apps/reference/domains/decision_making/event_handlers.py#L473-L477).

FACT: Safety gates read that cached confidence back via `_extract_regime()` at [safety_gates.py#L132-L140](../apps/reference/domains/decision_making/safety_gates.py#L132-L140) and store it into `result.regime_confidence` at [safety_gates.py#L496-L549](../apps/reference/domains/decision_making/safety_gates.py#L496-L549).

FACT: IntentBuilder writes `sg.regime_confidence` into the trade-intent DTO and the decision-side order log at [intent_builder.py#L291-L311](../apps/reference/domains/decision_making/intent_builder.py#L291-L311) and [intent_builder.py#L418-L426](../apps/reference/domains/decision_making/intent_builder.py#L418-L426).

FACT: Lifecycle persistence stores the same field at [trade_lifecycle_logger.py#L269](../apps/reference/telemetry/trade_lifecycle_logger.py#L269).

FACT: Execution placement does not regenerate confidence. In the target case, the open path receives a payload that lacks the field and order logging records `null`, as shown by [2026-04-02.jsonl#L5775](../ops/wal/2026-04-02.jsonl#L5775) and [order_log_v1.jsonl#L98](../logs/order_log_v1.jsonl#L98).

## 5. Candidate Path Matrix

| Candidate path | Supporting evidence | Contradicting evidence | Status |
| --- | --- | --- | --- |
| Detector heartbeat refresh -> cached regime state -> intent | Detector emits every basis bar and updates stable confidence on confirmed same-regime heartbeats at [regime_detector.py#L705-L801](../apps/reference/domains/regime_detector/regime_detector.py#L705-L801). Downstream code copies rather than synthesizes confidence. | No retained detector artifact with ETH `0.85` before intent. | Strongest supported path, but upstream event instance remains unproven. |
| Reuse of stale 05:45 ETH transition value | ETH had a visible 05:45 `TREND_DOWN` transition at [domain_regime_detector.log#L60](../logs/domain_regime_detector.log#L60). | That visible value is `0.330286...`, not `0.85`; stale reuse alone does not explain the observed intent value. | Not supported as the primary explanation. |
| Hidden enrichment between cache and intent | No code path found that writes a new higher confidence between cache read and payload creation; intent builder writes `sg.regime_confidence` directly. | None found in inspected local code. | Disproven for inspected path. |
| Execution/open executor synthesis | Execution order log for target case records `regime_confidence: null` at [order_log_v1.jsonl#L98](../logs/order_log_v1.jsonl#L98). | Directly contradicts execution as a source of `0.85`. | Disproven. |
| Semantic corruption/manual override | No local code or artifact proved a manual override or alternate constant-injection path for this RID. | No matching producer found. | Unproven. |

## 6. Operational Risk

FACT: With current retention, an auditor can see detector transition logs showing `0.330286...` at 05:45 and `0.286993...` at 08:45, while the retained decision-side artifacts for the 07:55 order show `0.85`.

INFERENCE: Without the missing detector heartbeat artifact, post-mortem analysis can falsely escalate to semantic corruption or hidden enrichment even when the more likely reality is same-regime detector heartbeat refresh.

FACT: The execution-side order log currently weakens the trail further because the placement row can carry `null` for `regime_confidence` even when the decision-side intent and lifecycle already persisted `0.85`.

## 7. Minimal Fix Direction

1. Persist `EVT:REGIME_DETECTED` heartbeat records to durable truth for every basis bar, not only changed transitions. Minimum fields: `symbol`, `regime`, `confidence`, `changed`, `raw_regime`, `raw_confidence`, `structural_regime_ref`, `last_update_ts_ms`, `hysteresis_confirm_count`.

2. Add an additive upstream regime snapshot reference on `TRADE_INTENT_PROPOSED`, for example detector event timestamp or `structural_regime_ref`, so the exact upstream detector emission can be reconstructed from the intent itself.

3. Make execution logging contract explicit. Either propagate `regime` and `regime_confidence` through `CMD:OPEN` / `DEC:OPEN` into `ORDER_PLACED`, or remove the ambiguous nullable execution copy so the log cannot be misread as evidence of a separate producer.

4. Keep the fix additive-only. Do not add silent fallbacks or hidden constants.

## 8. Classification

CLASSIFICATION: OBSERVABILITY_GAP_WITH_UPSTREAM_ARTIFACT_MISSING

SUBCLASSIFICATIONS:
- hidden downstream enrichment: disproven for inspected path
- semantic corruption: not evidenced
- stale-state reuse: unproven as a direct mechanism, but heartbeat-refreshed cached state remains plausible

FINAL_STATUS: DOWNSTREAM_DISPROVEN_UPSTREAM_UNPROVEN
