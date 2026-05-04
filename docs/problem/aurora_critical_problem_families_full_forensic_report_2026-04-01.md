# Deep Forensic Research Of Critical Aurora Problem Families

Date: 2026-04-01

Scope:
- apps/reference/domains/decision_making/aurora_holding_period.py
- apps/reference/domains/decision_making/dashboard.py
- apps/reference/domains/decision_making/aurora_tpsl.py
- apps/reference/domains/decision_making/aurora_decision.py
- apps/reference/domains/decision_making/aurora_handler.py
- apps/reference/domains/decision_making/aurora_scoring_helpers.py
- apps/reference/domains/decision_making/intent_builder.py
- apps/reference/domains/decision_making/md_amr_handler.py
- apps/reference/domains/decision_making/schemas/trade_intent_v1.json
- schemas/strategy_signal_produced_v1.json
- apps/reference/domains/position_tracking/schemas/trade_executed_v1.json
- apps/reference/domains/position_tracking/position_tracking.py
- apps/reference/domains/execution_position/event_handlers.py
- apps/reference/domains/objective_engine/snapshot_registry.py
- apps/reference/domains/objective_engine/posttrade_evaluator.py
- apps/reference/config_models.py
- tests/domains/decision_making/test_aurora_handler.py
- tests/domains/decision_making/test_aurora_tpsl.py
- tests/decision_making/test_regime_tpsl.py
- tests/units/test_aurora_position_sync.py

Method:
- file-by-file runtime tracing of producers, consumers, schemas, and adjacent truth owners
- schema and contract inspection across strategy signal, trade intent, and trade executed boundaries
- targeted search for downstream consumers of dashboard metrics and TP/SL provenance
- git archaeology already performed earlier in this investigation and incorporated where still consistent with current workspace truth
- fresh import probing and fresh focused pytest reruns
- no code edits to runtime modules while producing this report

## 1. Executive Summary

- This report is evidence-first and investigation-only. No runtime fix was applied.
- Family 1 is PROVEN: Aurora local holding-period logic synthesizes a zero-PnL losing trade on opposite-side fills in `aurora_holding_period.py`, while stronger realized-close truth already exists in `position_tracking`, `execution_position`, and `objective_engine`.
- Family 2 is PROVEN: Aurora TP/SL computation collapses many semantically distinct failures into a single `None` result, and the active trade-intent boundary drops TP/SL provenance entirely even when the strategy-signal layer had it.
- Family 3 is PARTIALLY PROVEN: Aurora and MD-AMR TP/SL logic are clearly related but already drifted in formulas, telemetry, and guardrail semantics. Harmful live divergence is plausible but not yet fully proven from the inspected runtime slice.
- Family 4 is not a current proven import blocker: fresh imports of `aurora_scoring_helpers`, `aurora_decision`, and `aurora_handler` all succeeded. The currently reproduced validation blocker is in test-fixture setup for `test_regime_tpsl`, not in the aurora_scoring_helpers import graph.
- The four families are not one root-cause cluster. They separate into three different classes of failure: synthetic local truth, contract-boundary provenance collapse, and duplicated strategy logic. The suspected import blocker belongs to stale or weakened evidence, not to the strongest current defect set.

## 2. Evidence Boundaries

Facts in this report are limited to:
- code and schema content directly inspected in the current workspace
- search results gathered during this investigation
- current file contents after reconciling stale references
- fresh runtime validation that was actually rerun

The report does not assume:
- undocumented runtime behavior
- hidden downstream consumers of the local dashboard unless found by search
- that earlier failures still apply if the current file or current rerun contradicts them

Important context:
- referenced AI protocol files under `docs/ai` were missing on disk when this investigation began
- the worktree is not pristine, so current-file truth was checked before trusting older failure references

## 3. Repository Surfaces Actually Traced

Primary Aurora surfaces:
- `apps/reference/domains/decision_making/aurora_holding_period.py`
- `apps/reference/domains/decision_making/dashboard.py`
- `apps/reference/domains/decision_making/aurora_tpsl.py`
- `apps/reference/domains/decision_making/aurora_decision.py`
- `apps/reference/domains/decision_making/aurora_handler.py`
- `apps/reference/domains/decision_making/aurora_scoring_helpers.py`

Boundary and contract surfaces:
- `apps/reference/domains/decision_making/intent_builder.py`
- `apps/reference/domains/decision_making/schemas/trade_intent_v1.json`
- `schemas/strategy_signal_produced_v1.json`
- `apps/reference/domains/position_tracking/schemas/trade_executed_v1.json`
- `apps/reference/dictionaries/verb_registry_v1.yaml`
- `apps/reference/config_models.py`

Canonical realized-truth owners:
- `apps/reference/domains/position_tracking/position_tracking.py`
- `apps/reference/domains/execution_position/event_handlers.py`
- `apps/reference/domains/objective_engine/snapshot_registry.py`
- `apps/reference/domains/objective_engine/posttrade_evaluator.py`

Cross-strategy comparison surface:
- `apps/reference/domains/decision_making/md_amr_handler.py`

Validation surfaces:
- `tests/domains/decision_making/test_aurora_handler.py`
- `tests/domains/decision_making/test_aurora_tpsl.py`
- `tests/decision_making/test_regime_tpsl.py`
- `tests/units/test_aurora_position_sync.py`

## 4. Current Runtime Validation

Fresh runtime validation during this investigation established:
- direct import probing succeeded for `apps.reference.domains.decision_making.aurora_scoring_helpers`
- direct import probing succeeded for `apps.reference.domains.decision_making.aurora_decision`
- direct import probing succeeded for `apps.reference.domains.decision_making.aurora_handler`
- the previously suspected narrow import-blocker claim around aurora_scoring_helpers was not reproduced on the current path

Fresh focused pytest established:
- 60 items collected in the focused Aurora slice
- 39 passed
- 3 skipped
- 5 errors

The visible current errors were all fixture-setup failures in `tests/decision_making/test_regime_tpsl.py` caused by `MagicMock operational_mode` not satisfying the typed `OperationalMode` contract during AuroraHandler initialization.

That means:
- the current reproduced blocker is test-harness incompatibility
- the current reproduced blocker is not an import failure in `aurora_scoring_helpers`

Additional current-truth correction:
- an earlier handler-failure reference is stale relative to the current local `tests/domains/decision_making/test_aurora_handler.py`
- the current file now contains the blocked-helper contract test, not the earlier cited test name

## 5. Family 1: Synthetic Performance Truth Corruption

### Symptom

Aurora local holding-period state records an exit-like dashboard trade on opposite-side fills, but writes a synthetic zero-PnL losing trade rather than canonical realized-close truth.

### Proven Facts

- `apps/reference/domains/decision_making/aurora_holding_period.py` writes `pnl_percent=0.0` on the opposite-side branch.
- `apps/reference/domains/decision_making/aurora_holding_period.py` writes `is_win=False` on the same branch.
- `apps/reference/domains/decision_making/aurora_holding_period.py` then logs exit detection and clears local state.
- `apps/reference/domains/decision_making/dashboard.py` computes `win_rate` from `is_win`.
- `apps/reference/domains/decision_making/dashboard.py` computes `sharpe_ratio_raw` from `pnl_percent`.
- No reconciliation or correction layer was found between this local dashboard write and the dashboard metrics computation.

### Stronger Truth Owners Found Elsewhere

- `apps/reference/domains/position_tracking/position_tracking.py` calculates realized delta when a fill reduces or offsets an existing position.
- `apps/reference/domains/position_tracking/position_tracking.py` explicitly supports crossing through zero and treats the new residual side as a flip with a new average price.
- `apps/reference/domains/execution_position/event_handlers.py` prefers `realizedPnl` from position payloads when logging closes.
- `apps/reference/domains/execution_position/event_handlers.py` falls back to cached fill-level realized PnL when the portfolio payload has no `realizedPnl`.
- `apps/reference/domains/execution_position/event_handlers.py` writes `POSITION_CLOSED` with `realized_pnl` and `realized_pnl_net`.
- `apps/reference/domains/execution_position/event_handlers.py` caches `realizedPnl` from fills for later close telemetry.
- `apps/reference/domains/objective_engine/posttrade_evaluator.py` reconstructs realized quality from actual entry and exit facts rather than from local dashboard placeholders.

### Local Mechanism

The local holding-period mixin does not own canonical portfolio truth. On an opposite-side execution, it conservatively infers a close or flatten event and records a dashboard `TradeOutcome` before execution-side or objective-side realized-close truth is consulted.

### Root Cause

The local diagnostics path invented a trade-outcome truth model instead of consuming an existing realized-close owner.

### Contributing Factors

- the mixin is intentionally local and does not reconcile full execution-side state
- opposite-side fill handling was simplified into a conservative close interpretation
- local dashboard metrics are in-memory only and therefore easy to treat as “just diagnostics,” even though they still produce operator-facing numbers

### Masking Layer

The rest of the runtime can still look correct:
- position tracking realized PnL can be correct
- execution close telemetry can be correct
- objective realized evaluation can be correct

This masks the defect because canonical truth and local dashboard truth can diverge without an obvious crash.

### Operational Risk

Proven risk:
- corrupted operator diagnostics
- corrupted local win-rate interpretation
- corrupted raw Sharpe-style interpretation for Aurora local dashboard metrics

Not yet proven:
- any current decision gate that consumes these dashboard metrics in the inspected runtime slice

### Proof Status

- local defect: PROVEN
- direct trading-path blast radius: PARTIALLY PROVEN

## 6. Family 2: TP/SL Diagnostic Collapse

### Symptom

Many semantically different TP/SL outcomes collapse into one shared downstream absence state.

### Proven Facts

- `apps/reference/domains/decision_making/aurora_tpsl.py` returns `None` when instrument config is missing.
- it returns `None` when exit config is missing.
- it returns `None` when regime TP/SL config is missing or disabled.
- it returns `None` when symbol state is unknown.
- it returns `None` when entry price is invalid.
- it returns `None` when TP/SL mode is unknown.
- it returns `None` when ATR is missing or unusable in ATR mode.
- it returns `None` when side is invalid in guardrails.
- it returns `None` when SL is on the wrong side.
- it returns `None` when TP is on the wrong side.
- it returns `None` when post-guardrail distance violates `min_dist_bps`.

### Consumer Behavior

- `apps/reference/domains/decision_making/aurora_decision.py` attaches `stop_price`, `target_price`, and `tpsl_ctx` only when `tpsl_result is not None`.
- when `tpsl_result is None`, signal emission can continue without TP/SL fields.
- `apps/reference/domains/decision_making/intent_builder.py` only sanitizes and forwards `stop_price` and `target_price`.
- the active trade-intent schema allows nullable `stop_price` and `target_price` but has no `tpsl_ctx` field.
- objective snapshot registration stores stop and target prices only when present and does not persist TP/SL provenance.

### Provenance Collapse Point

The strategy-signal layer can still carry TP/SL context, but the active execution-boundary contract removes it.

That means three different realities become hard to distinguish downstream:
- TP/SL intentionally disabled
- TP/SL unavailable because prerequisites were missing
- TP/SL computed and then rejected by guardrails

### Root Cause

TP/SL is currently modeled as optional enrichment rather than as a typed outcome family with identity.

### Contributing Factors

- `None` is used as the common sink for many unrelated failure conditions
- strategy-signal payloads look rich enough that local logs remain informative
- the boundary contract preserves prices but not outcome reasons

### Masking Layer

Because nullable prices are schema-valid, downstream consumers cannot tell whether absence was expected or pathological without out-of-band log correlation.

### Operational Risk

High risk for:
- post-mortem analysis
- boundary-level debugging
- objective/quality forensics
- future contract evolution, because business semantics are already hidden behind one shared null path

### Proof Status

- contract-level collapse: PROVEN
- provenance loss at the trade-intent boundary: PROVEN

## 7. Family 3: Cross-Strategy Drift Between Aurora And MD-AMR

### Symptom

Aurora and MD-AMR expose superficially similar TP/SL surfaces at strategy-signal time, but their actual implementations are already divergent.

### Proven Similarities

- both compute regime-aware TP/SL only for entry-style signals
- both attach stop price and target price to the strategy-signal payload when TP/SL exists
- both use a `tpsl_ctx` telemetry object at that layer
- both apply post-compute guardrails before emission

### Proven Differences

- Aurora pct-mult logic uses `take_profit.tp_low_ratio`.
- MD-AMR pct-mult logic uses `exit.tp_rr`.
- Aurora emits richer telemetry around `rr_pre`, `rr_post`, and effective ratios.
- MD-AMR emits a different telemetry shape centered around `tp_rr_base`, `tp_rr_eff`, and `guardrail_tp_clamp`.
- Aurora explicitly rejects invalid side in guardrails.
- MD-AMR is structurally similar but not telemetry-identical and not formula-identical.
- Aurora and MD-AMR use different config field names for conceptually similar behavior.

### Root Cause

Parallel strategy-specific TP/SL implementations evolved without a shared invariant harness or a shared contract-first helper.

### Contributing Factors

- different strategy configuration trees
- different earlier business vocabularies
- a boundary layer that normalizes output shape just enough to hide implementation drift

### What Is Proven Versus Not Proven

Proven:
- code drift exists today
- telemetry drift exists today
- formula drift exists today

Not yet proven:
- that current drift produces a harmful live inconsistency on the same market case under intended configs

### Operational Risk

Moderate now, higher if future changes are applied to one strategy path and assumed to cover the other.

### Proof Status

- drift in implementation: PROVEN
- current harmful runtime divergence: PARTIALLY PROVEN

## 8. Family 4: aurora_scoring_helpers As Validation Blocker

### Investigated Claim

The suspected claim was that `aurora_scoring_helpers.py` was the current reason Aurora-focused validation could not complete.

### Fresh Evidence

- fresh imports of `aurora_scoring_helpers`, `aurora_decision`, and `aurora_handler` all succeeded
- fresh focused pytest did not show an aurora_scoring_helpers import failure
- current visible errors came from fixture setup in `tests/decision_making/test_regime_tpsl.py`

### Current Root Cause Of Validation Failure

The currently reproduced validation blocker is test-fixture incompatibility around `operational_mode`, not an import-graph break in aurora_scoring_helpers.

### Stale-Evidence Correction

- an earlier handler-failure reference is stale relative to the current workspace
- the current local `tests/domains/decision_making/test_aurora_handler.py` no longer matches that earlier failure reference
- helper-tool noise earlier in the investigation also obscured the current truth by producing unreliable no-tests-found results

### Operational Risk

Low for runtime, but medium for engineering decision quality. A stale blocker theory can send implementation effort into the wrong module.

### Proof Status

- current aurora_scoring_helpers import blocker: UNPROVEN
- stale or weakened claim status: PROVEN

## 9. Producer And Consumer Chain Findings

### Dashboard Outcome Flow

Only one live producer for the problematic synthetic trade outcome was found in the inspected Aurora path:
- opposite-side execution handling in `aurora_holding_period.py`

Dashboard consumer logic is direct and local:
- `DashboardMetrics.record_trade()` appends the trade
- `DashboardMetrics.get_metrics()` computes win rate and Sharpe-like output from those stored values

No stronger downstream consumer of these dashboard metrics was proven in the inspected codebase slice.

### TP/SL Producer And Consumer Chain

Producer side:
- Aurora computes TP/SL in `aurora_tpsl.py`
- Aurora decides whether to attach TP/SL in `aurora_decision.py`
- MD-AMR computes and attaches a parallel TP/SL surface in `md_amr_handler.py`

Boundary side:
- `intent_builder.py` preserves only stop and target prices
- `trade_intent_v1.json` preserves only stop and target prices plus optional entry-plan trace
- TP/SL provenance is dropped at this boundary

Objective side:
- snapshot registry stores only optional stop and target prices
- posttrade evaluator uses those prices only if present for efficiency calculations

This chain is why Family 2 is not just a local logging issue. It is a real contract-boundary collapse.

## 10. Schema And Ownership Findings

Relevant active contract facts:
- strategy-signal payloads can carry richer TP/SL context upstream
- trade-intent payloads allow null stop and target prices downstream
- trade-intent payloads do not carry `tpsl_ctx`
- trade-executed and execution-position flows already have a place for realized-close truth through `realizedPnl`

Interpretation:
- price-level TP/SL data crosses the execution boundary
- TP/SL reason identity does not
- realized-close truth already has a stronger canonical owner than the local dashboard path

## 11. Git Archaeology Findings Already Established Earlier In This Investigation

Earlier git archaeology within this same investigation established two useful historical facts:
- the operative synthetic dashboard emission lines in `aurora_holding_period.py` were not a brand-new local comment artifact; they trace back to an existing earlier commit
- the `None`-sink and guardrail structure in `aurora_tpsl.py` mostly predates the current uncommitted explanatory comments, with some newer hardening lines added later

Those findings strengthen the conclusion that both Family 1 and Family 2 are real inherited behavior surfaces, not temporary workspace noise.

## 12. Proof Matrix

- Family 1 local defect: PROVEN
- Family 1 direct decision-path reuse of corrupted dashboard metrics: PARTIALLY PROVEN
- Family 2 TP/SL branch collapse: PROVEN
- Family 2 trade-intent provenance loss: PROVEN
- Family 3 Aurora vs MD-AMR implementation drift: PROVEN
- Family 3 harmful same-case live divergence: PARTIALLY PROVEN
- Family 4 current import blocker in aurora_scoring_helpers: UNPROVEN
- Family 4 stale-claim correction: PROVEN

## 13. Safe Additive Fix Ranking

### Rank 1: repair validation clarity first

Target:
- `tests/decision_making/test_regime_tpsl.py`

Reason:
- current proof quality is still being distorted by fixture incompatibility
- this is the cheapest and lowest-risk path to cleaner evidence

### Rank 2: add TP/SL outcome identity at the boundary

Target:
- boundary between `aurora_decision.py` and `intent_builder.py`
- possibly the trade-intent schema if additive fields are allowed

Reason:
- Family 2 is a proven contract defect
- additive reason identity would fix a real observability gap without changing pricing geometry

### Rank 3: stop writing synthetic dashboard close truth when realized truth is unknown

Target:
- `aurora_holding_period.py`

Reason:
- Family 1 is a proven local defect
- safest fix is to consume canonical close truth or abstain from recording a TradeOutcome until it exists

### Rank 4: add shared Aurora/MD-AMR TP/SL golden tests before unification

Target:
- paired tests around Aurora and MD-AMR TP/SL behavior

Reason:
- drift is proven
- shared helper work before invariant coverage would be risky

## 14. Required Validation Before Implementation

For Family 1:
- prove where realized-close truth becomes available on the intended Aurora local-diagnostics path
- validate with integration or runtime-facing checks, not only with local unit tests

For Family 2:
- add explicit coverage for each distinct TP/SL omission reason
- validate the strategy-signal artifact and the trade-intent artifact together

For Family 3:
- add golden cases that run Aurora and MD-AMR on explicitly controlled comparable setups
- validate formulas, emitted telemetry, and final guardrail outputs

For Family 4:
- fix the `operational_mode` fixture setup in `tests/decision_making/test_regime_tpsl.py`
- rerun the same focused pytest slice
- keep import probing as a separate control so fixture failures cannot masquerade as import failures

## 15. Final Verdict

- The strongest current Aurora forensic findings are Family 1 and Family 2.
- Family 1 is a real synthetic-truth defect in local diagnostics.
- Family 2 is a real contract-boundary provenance defect around TP/SL omission semantics.
- Family 3 is a real drift problem that should be controlled before any unification or rollout assumptions are made.
- Family 4 should not currently be treated as the primary code blocker in aurora_scoring_helpers itself.

Safest implementation order if work begins:
- restore validation clarity
- add TP/SL reason identity at the boundary
- remove or quarantine synthetic dashboard close truth
- only then decide whether Aurora and MD-AMR TP/SL should converge or remain intentionally distinct
