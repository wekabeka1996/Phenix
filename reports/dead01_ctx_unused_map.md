# DEAD-01-CTX — “Dead code” / duplicate-path audit (static, fact-first)

This is a static + repo-local audit (no runtime tracing). Categories:
- **Suspiciously dead**: no obvious imports/instantiation found with ripgrep.
- **Legacy but still triggered**: confirmed subscriptions or log evidence.
- **Duplicates / overlap**: multiple implementations for the same responsibility (risk of double-trigger / drift).

## Suspiciously dead (no instantiation found)

### OrchestratorFSM module (appears unused)
- Files:
  - `apps/reference/orchestrator/orchestrator_fsm.py`
  - `apps/reference/orchestrator/types.py`
  - `apps/reference/orchestrator/utils_event_bus.py`
- Evidence:
  - No `OrchestratorFSM(` instantiation found under `apps/reference` (`rg "OrchestratorFSM\\(" apps/reference` returned none).
- Risk if removed:
  - Low if truly unused; medium if referenced externally (CLI/scripts) outside `apps/reference`.

## Legacy but still triggered (confirmed)

### Tick → FEATURES → MR data-only reject spam (`tf_sec=0`)
- Trigger:
  - `apps/reference/domains/feature_engineering/feature_engineering.py: _calculate_and_emit_features()` calls `_calculate_and_emit_features_for_tf(..., tf_sec=0, ...)` on every tick after warmup.
- Consumer producing WARN spam:
  - `apps/reference/domains/decision_making/mean_reversion_handler.py: MeanReversionHandler.register()` still listens to `EVT:FEATURES_CALCULATED`.
  - `apps/reference/domains/decision_making/mean_reversion_handler.py: _on_features_calculated()` logs `MR rejecting features ... tf_sec 0 != {timeframe}`.
- Evidence:
  - `reports/mr_chain_probe.jsonl` contains parsed real log lines showing `tf_sec 0 != 180`.
  - `logs/aurora_core.log` (your IDE snippet) shows the same WARN in live run.

### DecisionMaking still subscribes to `EVT:FEATURES_CALCULATED`
- File:
  - `apps/reference/domains/decision_making/decision_making.py` → `self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features)`
- Notes:
  - Current `on_features()` does mostly caching/alpha-telemetry and does not form bar-only decisions, but it still fires on tick-features (`tf_sec=0`) → noisy and mixes contexts unless gated.

## Duplicates / overlap (high-risk drift areas)

### Two different “event bus” semantics for `op` (CMD/EVT)
- `vfoundation/core/fsm_core.py: FSMCore.emit()` always creates `Message(op=\"EVT\", verb=...)` even when emitting `CMD:*`.
- `apps/reference/orchestrator/utils_event_bus.py: LocalBus.emit()` sets `op` from prefix (`CMD/EVT/...`) and `verb` from suffix.
- Risk:
  - Code that inspects `Message.op` can silently misclassify `CMD:*` as `EVT`.
  - WAL/event classification becomes inconsistent (already observed as mixed formats in `ops/wal/*.jsonl`).

### MeanReversion strategy: global BarAggregator vs deprecated local resampler path
- Files:
  - `apps/reference/domains/market_data/bar_aggregator.py` (SSOT bar construction, emits `EVT:BAR_CLOSED`)
  - `apps/reference/domains/feature_engineering/mean_reversion_strategy.py` (contains deprecated local resampler/tick processing blocks)
- Risk:
  - Partial refactors leave “shadow” codepaths that can be reactivated accidentally (e.g., test harnesses, legacy wiring).

## “Orphan verbs/events” (observability-only evidence)

Based on `reports/obs02_ctx_log_inventory.md` (WAL inventory):
- Not observed in WAL at all (count = 0):
  - `BAR_CLOSED` (SSOT bar event missing from WAL)
  - `PROCESS_STRATEGY` / `CMD:PROCESS_STRATEGY` (primary strategy trigger missing from WAL)
- Caveat:
  - Some events may exist only on in-process buses and not be persisted to WAL today; absence in WAL ≠ not occurring.

## Candidates to isolate (not delete yet)

- `apps/reference/orchestrator/*` (move behind feature-flag or remove after confirming no external entrypoint).
- Deprecated MR tick handlers inside `apps/reference/domains/decision_making/mean_reversion_handler.py` (keep but ensure no subscriptions).

