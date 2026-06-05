# Deep Forensic Research Of Critical Aurora Problem Families

Date: 2026-03-31

## 1. Executive Summary

- This report is investigation-only. No runtime code was changed.
- Family 1 is PROVEN: [apps/reference/domains/decision_making/aurora_holding_period.py#L242](apps/reference/domains/decision_making/aurora_holding_period.py#L242) and [apps/reference/domains/decision_making/aurora_holding_period.py#L244](apps/reference/domains/decision_making/aurora_holding_period.py#L244) synthesize a zero-PnL losing trade on opposite-side fills, while stronger realized-close truth already exists elsewhere in runtime.
- Family 2 is PROVEN: [apps/reference/domains/decision_making/aurora_tpsl.py#L84](apps/reference/domains/decision_making/aurora_tpsl.py#L84) collapses many distinct TP/SL failure modes into one None outcome, and [apps/reference/domains/decision_making/aurora_decision.py#L1695-L1703](apps/reference/domains/decision_making/aurora_decision.py#L1695-L1703) then omits TP/SL fields entirely when that happens.
- Family 3 is PARTIALLY PROVEN: Aurora and MD-AMR TP/SL logic are structurally related, but not identical. Drift is code-proven, while a current live harmful divergence is not yet proven.
- Family 4 is largely WEAKENED: a current import-blocker claim around aurora_scoring_helpers was not reproduced. Fresh validation instead pointed to fixture setup errors in [tests/decision_making/test_regime_tpsl.py](tests/decision_making/test_regime_tpsl.py).
- The strongest current engineering risks are therefore not one shared root bug. They are three different problem classes: synthetic local truth, provenance collapse at a contract boundary, and duplicated strategy logic.

## 2. Scope And Evidence Rules

- Primary files inspected:
- [apps/reference/domains/decision_making/aurora_holding_period.py](apps/reference/domains/decision_making/aurora_holding_period.py)
- [apps/reference/domains/decision_making/dashboard.py](apps/reference/domains/decision_making/dashboard.py)
- [apps/reference/domains/decision_making/aurora_tpsl.py](apps/reference/domains/decision_making/aurora_tpsl.py)
- [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py)
- [apps/reference/domains/decision_making/intent_builder.py](apps/reference/domains/decision_making/intent_builder.py)
- [apps/reference/domains/decision_making/md_amr_handler.py](apps/reference/domains/decision_making/md_amr_handler.py)
- [apps/reference/domains/decision_making/schemas/trade_intent_v1.json](apps/reference/domains/decision_making/schemas/trade_intent_v1.json)
- [apps/reference/domains/position_tracking/position_tracking.py](apps/reference/domains/position_tracking/position_tracking.py)
- [apps/reference/domains/execution_position/event_handlers.py](apps/reference/domains/execution_position/event_handlers.py)
- [apps/reference/domains/objective_engine/snapshot_registry.py](apps/reference/domains/objective_engine/snapshot_registry.py)
- [apps/reference/domains/objective_engine/posttrade_evaluator.py](apps/reference/domains/objective_engine/posttrade_evaluator.py)
- Referenced repo protocol files under docs/ai were not present on disk during this investigation, so conclusions are anchored to inspected code, schemas, tests, search evidence, git archaeology, and fresh runtime validation only.
- Current workspace is not a pristine worktree. There are uncommitted changes around decision_making and tests, so historical claims were checked against current file contents before being treated as live truth.
- Facts and inferences are separated inside each family section. Where live runtime behavior was not directly proven, the report says so explicitly.

## 3. Current Validation State

- Fresh import probing successfully imported aurora_scoring_helpers, aurora_decision, and aurora_handler. No current import failure around aurora_scoring_helpers was reproduced.
- Fresh focused pytest on the Aurora slice collected 60 items and ended with 39 passed, 3 skipped, and 5 errors.
- The visible current errors were fixture-setup errors in [tests/decision_making/test_regime_tpsl.py](tests/decision_making/test_regime_tpsl.py), not import-graph failures.
- A previously cited handler failure is stale relative to the current workspace. The current handler test file now contains the blocked-helper contract test at [tests/domains/decision_making/test_aurora_handler.py#L356-L408](tests/domains/decision_making/test_aurora_handler.py#L356-L408), and the earlier cited failure name is not present in the current file.
- The focused test helper path was unreliable for this slice and returned no-tests-found earlier, so the stronger proof came from direct pytest execution rather than the helper result.

## 4. Family 1: Synthetic Performance Truth Corruption

- Symptom: Aurora local holding-period state records an exit-like dashboard trade on any opposite-side fill, but writes a synthetic zero-PnL loss instead of canonical realized-close truth.
- Proven facts:
- [apps/reference/domains/decision_making/aurora_holding_period.py#L242](apps/reference/domains/decision_making/aurora_holding_period.py#L242) writes pnl_percent as 0.0.
- [apps/reference/domains/decision_making/aurora_holding_period.py#L244](apps/reference/domains/decision_making/aurora_holding_period.py#L244) writes is_win as False.
- [apps/reference/domains/decision_making/dashboard.py#L79-L82](apps/reference/domains/decision_making/dashboard.py#L79-L82) computes win_rate directly from is_win.
- [apps/reference/domains/decision_making/dashboard.py#L88-L97](apps/reference/domains/decision_making/dashboard.py#L88-L97) computes sharpe_ratio_raw from pnl_percent.
- [apps/reference/domains/position_tracking/position_tracking.py#L699-L709](apps/reference/domains/position_tracking/position_tracking.py#L699-L709) computes realized_delta when a trade reduces or offsets an existing position.
- [apps/reference/domains/position_tracking/position_tracking.py#L734](apps/reference/domains/position_tracking/position_tracking.py#L734) explicitly supports cross-through-zero flip semantics.
- [apps/reference/domains/execution_position/event_handlers.py#L215-L221](apps/reference/domains/execution_position/event_handlers.py#L215-L221) prefers realizedPnl from position payloads and falls back to cached fill realized PnL.
- [apps/reference/domains/execution_position/event_handlers.py#L280-L296](apps/reference/domains/execution_position/event_handlers.py#L280-L296) writes POSITION_CLOSED with realized_pnl and realized_pnl_net.
- [apps/reference/domains/execution_position/event_handlers.py#L553-L557](apps/reference/domains/execution_position/event_handlers.py#L553-L557) caches fill realizedPnl by symbol for later close telemetry.
- [apps/reference/domains/objective_engine/snapshot_registry.py#L44-L52](apps/reference/domains/objective_engine/snapshot_registry.py#L44-L52) stores optional stop and target prices from trade intent.
- [apps/reference/domains/objective_engine/posttrade_evaluator.py#L47-L73](apps/reference/domains/objective_engine/posttrade_evaluator.py#L47-L73) reconstructs realized quality from actual entry and exit facts.
- Local mechanism: the local Aurora mixin does not own canonical position truth. It infers a close from an opposite-side fill and emits a dashboard TradeOutcome before execution_position or position_tracking truth is consulted.
- Root cause inference: a local diagnostics helper invented trade outcome truth instead of consuming one of the existing realized-close owners.
- Contributing factors: the mixin intentionally treats opposite fills conservatively as close or flatten events, because it does not reconcile the full execution-side position state itself.
- Masking layer: stronger runtime truth still exists in position_tracking, execution_position, and objective_engine. That can make trading state and realized-close telemetry look correct while dashboard metrics remain corrupted.
- Operational risk: proven for operator diagnostics and any dashboard-derived win-rate or raw-Sharpe interpretation. Not proven as a current direct decision-path input, because no live downstream consumer of these dashboard metrics was proven in the inspected runtime.
- Proof status: PROVEN defect, PARTIALLY PROVEN blast radius.

## 5. Family 2: TP/SL Diagnostic Collapse

- Symptom: many semantically distinct TP/SL outcomes collapse into the same downstream absence state.
- Proven facts:
- [apps/reference/domains/decision_making/aurora_tpsl.py#L84](apps/reference/domains/decision_making/aurora_tpsl.py#L84) is the main regime TP/SL computation entrypoint.
- [apps/reference/domains/decision_making/aurora_tpsl.py#L159](apps/reference/domains/decision_making/aurora_tpsl.py#L159) returns None on unknown mode.
- [apps/reference/domains/decision_making/aurora_tpsl.py#L386](apps/reference/domains/decision_making/aurora_tpsl.py#L386) returns None on invalid side in guardrails.
- [apps/reference/domains/decision_making/aurora_tpsl.py#L393-L401](apps/reference/domains/decision_making/aurora_tpsl.py#L393-L401) returns None on wrong-side SL or TP geometry.
- [apps/reference/domains/decision_making/aurora_tpsl.py#L473-L479](apps/reference/domains/decision_making/aurora_tpsl.py#L473-L479) returns None on min_dist_bps violations.
- [apps/reference/domains/decision_making/aurora_decision.py#L1695-L1703](apps/reference/domains/decision_making/aurora_decision.py#L1695-L1703) attaches stop_price, target_price, and tpsl_ctx only when tpsl_result is not None.
- [apps/reference/domains/decision_making/intent_builder.py#L242-L249](apps/reference/domains/decision_making/intent_builder.py#L242-L249) sanitizes only stop_price and target_price for the trade-intent boundary.
- [apps/reference/domains/decision_making/intent_builder.py#L287-L288](apps/reference/domains/decision_making/intent_builder.py#L287-L288) writes only stop_price and target_price into the trade_intent payload.
- [apps/reference/domains/decision_making/schemas/trade_intent_v1.json#L158](apps/reference/domains/decision_making/schemas/trade_intent_v1.json#L158) and [apps/reference/domains/decision_making/schemas/trade_intent_v1.json#L170](apps/reference/domains/decision_making/schemas/trade_intent_v1.json#L170) allow stop_price and target_price as nullable fields.
- [apps/reference/domains/decision_making/schemas/trade_intent_v1.json#L182](apps/reference/domains/decision_making/schemas/trade_intent_v1.json#L182) includes entry_plan, but the schema has no tpsl_ctx field.
- [apps/reference/domains/objective_engine/snapshot_registry.py#L51-L52](apps/reference/domains/objective_engine/snapshot_registry.py#L51-L52) only persists stop_price and target_price, not TP/SL provenance.
- Local mechanism: TP/SL production uses None as a common sink for disabled config, missing ATR, invalid entry price, invalid side, wrong-side geometry, min-distance failure, and other incompatible states.
- Root cause inference: TP/SL is modeled as optional enrichment instead of a typed outcome family with reason identity.
- Contributing factors: the strategy-signal layer can still carry tpsl_ctx, which makes local producer logs look informative, but the active trade-intent contract removes that provenance.
- Masking layer: downstream code still sees nullable stop and target prices, so absence can look like an intentional no-bracket case even when it was actually a guardrail rejection or data failure.
- Operational risk: high for forensics, policy audit, and supportability. From trade-intent and objective artifacts alone, the system cannot currently distinguish disabled TP/SL from computed-and-rejected TP/SL.
- Proof status: PROVEN contract and observability defect.

## 6. Family 3: Aurora Versus MD-AMR TP/SL Drift

- Symptom: Aurora and MD-AMR present a very similar TP/SL story at the signal layer, but the underlying logic is already divergent.
- Proven facts:
- Aurora attaches TP/SL to the strategy-signal payload only when tpsl_result exists at [apps/reference/domains/decision_making/aurora_decision.py#L1695-L1711](apps/reference/domains/decision_making/aurora_decision.py#L1695-L1711).
- MD-AMR does the same in [apps/reference/domains/decision_making/md_amr_handler.py](apps/reference/domains/decision_making/md_amr_handler.py).
- Aurora pct_mult uses exit.sl_pct and take_profit.tp_low_ratio in [apps/reference/domains/decision_making/aurora_tpsl.py](apps/reference/domains/decision_making/aurora_tpsl.py).
- MD-AMR pct_mult uses exit.sl_pct and exit.tp_rr in [apps/reference/domains/decision_making/md_amr_handler.py](apps/reference/domains/decision_making/md_amr_handler.py).
- Aurora explicitly rejects invalid side and wrong-side geometry at [apps/reference/domains/decision_making/aurora_tpsl.py#L386-L401](apps/reference/domains/decision_making/aurora_tpsl.py#L386-L401).
- MD-AMR has structurally similar guardrails, but its telemetry fields and clamp semantics differ in [apps/reference/domains/decision_making/md_amr_handler.py](apps/reference/domains/decision_making/md_amr_handler.py).
- Aurora surfaces rr_pre and rr_post style telemetry in its why chain and TP/SL context at [apps/reference/domains/decision_making/aurora_decision.py#L1705-L1711](apps/reference/domains/decision_making/aurora_decision.py#L1705-L1711).
- MD-AMR uses tp_rr_base, tp_rr_eff, and guardrail_tp_clamp style telemetry in [apps/reference/domains/decision_making/md_amr_handler.py](apps/reference/domains/decision_making/md_amr_handler.py).
- Local mechanism: the two strategies evolved parallel TP/SL implementations instead of sharing one contract-first helper.
- Root cause inference: conceptual similarity was preserved, but contract unification was not.
- Contributing factors: different strategy configuration shapes, different field names, and different local telemetry needs.
- Masking layer: both strategies emit stop_price, target_price, and tpsl_ctx on the signal boundary, so the surface looks harmonized even when formulas and guardrails already drift underneath.
- Operational risk: moderate. Code drift is proven today. A live harmful behavioral divergence is not yet proven from the inspected runtime and tests.
- Proof status: PROVEN code drift, PARTIALLY PROVEN runtime risk.

## 7. Family 4: aurora_scoring_helpers Validation Blocker Claim

- Symptom: aurora_scoring_helpers was suspected to be the current reason focused Aurora validation could not complete.
- Proven facts:
- Fresh import probing successfully imported aurora_scoring_helpers, aurora_decision, and aurora_handler.
- Fresh focused pytest did not produce an aurora_scoring_helpers import error.
- The current visible focused-test failures were fixture-setup errors in [tests/decision_making/test_regime_tpsl.py](tests/decision_making/test_regime_tpsl.py).
- The current handler file around [tests/domains/decision_making/test_aurora_handler.py#L356-L408](tests/domains/decision_making/test_aurora_handler.py#L356-L408) shows a different local test surface than the stale failure reference cited earlier in the session.
- Local mechanism: stale failure references and an unreliable focused-test helper obscured the distinction between a current import blocker and a current test-fixture blocker.
- Root cause inference: the active blocker is validation-harness drift, not a reproduced runtime import break in aurora_scoring_helpers.
- Contributing factors: dirty worktree, stale references to earlier test names, and helper-tool noise.
- Masking layer: unrelated warnings and old failure references can make the situation look like a current code-import problem when it is not.
- Operational risk: low for current runtime. Medium for engineering feedback quality, because a stale blocker story can easily redirect work toward the wrong module.
- Proof status: UNPROVEN as a current import blocker, PROVEN as a stale or weakened claim.

## 8. Runtime Truth Owners And Contract Boundaries

- Canonical realized-close truth currently lives in [apps/reference/domains/position_tracking/position_tracking.py](apps/reference/domains/position_tracking/position_tracking.py), [apps/reference/domains/execution_position/event_handlers.py](apps/reference/domains/execution_position/event_handlers.py), and [apps/reference/domains/objective_engine/posttrade_evaluator.py](apps/reference/domains/objective_engine/posttrade_evaluator.py), not in [apps/reference/domains/decision_making/dashboard.py](apps/reference/domains/decision_making/dashboard.py).
- One-fill reversal semantics are already supported by [apps/reference/domains/position_tracking/position_tracking.py#L734](apps/reference/domains/position_tracking/position_tracking.py#L734), while the local holding-period mixin still treats opposite-side fills as conservative close detection.
- TP/SL provenance is richer at the strategy-signal layer in [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py) and [apps/reference/domains/decision_making/md_amr_handler.py](apps/reference/domains/decision_making/md_amr_handler.py) than it is at the execution-boundary layer in [apps/reference/domains/decision_making/intent_builder.py](apps/reference/domains/decision_making/intent_builder.py) and [apps/reference/domains/decision_making/schemas/trade_intent_v1.json](apps/reference/domains/decision_making/schemas/trade_intent_v1.json).
- These boundaries explain why Family 1 can corrupt local diagnostics without obviously breaking canonical realized-close accounting, and why Family 2 can look rich upstream but opaque downstream.

## 9. Blast Radius

- Family 1 proven blast radius:
- Dashboard trade history.
- win_rate and sharpe_ratio_raw in [apps/reference/domains/decision_making/dashboard.py#L79-L97](apps/reference/domains/decision_making/dashboard.py#L79-L97).
- Operator interpretation of local Aurora performance.
- Family 1 not yet proven blast radius:
- any current decision gate or execution policy driven from dashboard metrics.
- Family 2 proven blast radius:
- trade-intent artifacts.
- objective-engine snapshot provenance.
- post-mortem classification of TP/SL absence.
- Family 3 proven blast radius:
- maintenance risk.
- cross-strategy behavior drift on edge cases.
- Family 4 proven blast radius:
- engineering proof quality.
- time spent investigating the wrong module.

## 10. Root Cause Separation

- Family 1 is not a TP/SL problem. Its root issue is synthetic local truth being written where canonical realized-close truth already exists elsewhere.
- Family 2 is not a dashboard problem. Its root issue is that many TP/SL failure classes share the same downstream absence representation.
- Family 3 is not primarily a validation blocker. Its root issue is duplicated strategy logic without a shared invariant harness.
- Family 4 is not currently a reproduced runtime module defect. Its root issue is stale evidence and validation-harness mismatch.
- Treating the four families as one bug would lower fix quality, because each family needs a different kind of remediation and a different validation plan.

## 11. Proven, Partial, And Unproven Matrix

- Family 1 local defect: PROVEN.
- Family 1 direct trading-path blast radius: PARTIALLY PROVEN.
- Family 2 TP/SL collapse and provenance loss: PROVEN.
- Family 3 code drift between Aurora and MD-AMR: PROVEN.
- Family 3 current harmful live divergence: PARTIALLY PROVEN.
- Family 4 current aurora_scoring_helpers import blocker: UNPROVEN.
- Family 4 stale or weakened claim status: PROVEN.

## 12. Safe Additive Fix Ranking

- Rank 1: fix validation clarity first.
- Meaning: repair the focused test fixture path in [tests/decision_making/test_regime_tpsl.py](tests/decision_making/test_regime_tpsl.py) and keep the fresh import probe as a control. This is low-risk and immediately improves proof quality.
- Rank 2: add TP/SL outcome identity at the boundary.
- Meaning: keep current stop_price and target_price behavior, but add an additive reason surface for TP/SL omitted, rejected, disabled, or data-missing outcomes before or at the trade-intent boundary.
- Rank 3: stop writing synthetic dashboard close truth when realized PnL is unknown.
- Meaning: either source realized-close values from canonical owners or abstain from recording a TradeOutcome until truth is available.
- Rank 4: add shared Aurora and MD-AMR TP/SL golden tests before deduplication.
- Meaning: prove intended parity or intended divergence case by case before introducing a shared helper.

## 13. Required Validation Before Implementation

- For Family 1:
- prove that realized-close truth is available on the intended path for dashboard consumption.
- run integration or runtime-facing checks, not only unit tests, because the defect sits at a boundary between local decision state and execution truth.
- For Family 2:
- add explicit coverage for disabled config, missing ATR, invalid entry price, invalid side, wrong-side geometry, and min_dist_bps failure.
- validate both the strategy-signal artifact and the trade-intent artifact so provenance loss is measured directly.
- For Family 3:
- add paired Aurora and MD-AMR golden cases with identical market inputs and explicitly different config assumptions.
- validate not only formulas but emitted telemetry and guardrail reason surfaces.
- For Family 4:
- rerun the focused pytest slice after fixing fixture construction.
- keep the import probe as a separate validation step so fixture failures cannot be misreported as module import failures.

## 14. Stale Claims And Corrections

- The current workspace does not support the claim that aurora_scoring_helpers is the active validation blocker. Fresh import probing contradicts that claim.
- The earlier cited handler failure is stale relative to the current local [tests/domains/decision_making/test_aurora_handler.py](tests/domains/decision_making/test_aurora_handler.py).
- Some explanatory comments in the worktree are uncommitted. The conclusions above rely on operative code, direct call chains, schemas, tests, and rerun validation rather than on comments alone.
- The focused test helper path was noisy enough in this workspace that direct pytest results were stronger evidence.

## 15. Final Verdict

- The real current Aurora problem families are not evenly weighted.
- Family 1 and Family 2 are the strongest directly proven defects.
- Family 3 is a real drift risk that should be controlled before refactoring or rollout changes, but it is not yet proven as the current primary failure mode.
- Family 4 should not currently drive implementation work on aurora_scoring_helpers itself. The stronger present action is to fix the validation harness and keep stale evidence out of the problem statement.
- If implementation begins, the safest order is:
- restore validation clarity.
- add TP/SL reason identity at the boundary.
- remove or quarantine synthetic dashboard close truth.
- only then address cross-strategy TP/SL unification.
