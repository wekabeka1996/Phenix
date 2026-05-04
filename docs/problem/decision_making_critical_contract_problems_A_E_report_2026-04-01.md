# Глубокое доказательное исследование критических незакрытых проблем Decision Making

Date: 2026-04-01

Scope:
- apps/reference/domains/decision_making/inception_filter.py
- apps/reference/domains/decision_making/exit_manager.py
- apps/reference/domains/decision_making/event_handlers.py
- apps/reference/domains/decision_making/flip_orchestration.py
- apps/reference/domains/decision_making/instrument_quantizer.py
- apps/reference/domains/decision_making/aurora_decision.py
- apps/reference/domains/decision_making/decision_making.py
- apps/reference/domains/decision_making/strategy_gateway.py
- apps/reference/domains/decision_making/aurora_config_loader.py
- apps/reference/domains/decision_making/aurora_handler.py
- apps/reference/domains/decision_making/mean_reversion_handler.py
- apps/reference/domains/decision_making/md_amr_handler.py
- apps/reference/config_models.py
- config/aurora/regime.yaml
- config/aurora/domains.yaml
- apps/reference/domains/decision_making/schemas/regime_shift_suspected_v1.json
- targeted tests under tests/domains/decision_making, tests/runtime, tests/integration, tests

Method:
- Full file reads of all five target modules
- Caller-chain inspection through direct runtime consumers
- Repo-wide symbol search for reachability and contract surfaces
- SSOT/config checks against config_models.py and YAML
- Focused validation by py_compile and pytest
- No code edits in this investigation phase

## 1. Executive Summary

- This report is evidence-only. No runtime code was changed while producing it.
- The strongest confirmed issue is not A or C, but D2: flip hysteresis in apps/reference/domains/decision_making/flip_orchestration.py reads payload keys that the current EVT:STRATEGY_SIGNAL_PRODUCED producers do not supply in the expected shape. This is a PROVEN runtime correctness bug.
- Two additional items are PROVEN contract drift rather than active algorithmic breakage:
  - A1: confirm_next_bar exists in config and schema surfaces, but no downstream orchestration exists.
  - C2: arming.require_regime_warmup is wired through DecisionMaking into DMEventHandlers, but the branch in on_regime is behaviorally identical on both sides.
- C1 is also real, but narrower: the proven part is observability loss through silent exception swallowing in best-effort paths, not a proven primary-trade corruption path.
- B1, D1, and E1 remain PARTIAL. Each has a real contract smell or compatibility surface, but the current live blast radius is not fully proven from the inspected runtime chain.

## 2. Problem Matrix

| ID | Hypothesis | Status | Type | Severity | Core Evidence |
| --- | --- | --- | --- | --- | --- |
| A1 | inception_filter / confirm_next_bar | PROVEN | Contract drift | Medium | inception_filter returns a reason token only; caller only acts on micro_size |
| B1 | exit_manager / permissive coercion | PARTIAL | Contract drift with latent runtime risk | Medium | constructor normalizes permissively, but live caller chain is typed |
| C1 | event_handlers / broad exception swallowing | PROVEN for observability, PARTIAL for state risk | Observability gap | Medium | silent pass paths lose forensic truth |
| C2 | event_handlers / dead arming_require_regime_warmup | PROVEN | Contract drift | High | true and false branches compute the same full_ready value |
| D1 | flip_orchestration / direct CMD:CLOSE legacy path | PARTIAL | Compatibility surface | Medium | tested helper exists, but primary runtime path uses handle_flip_orchestration |
| D2 | flip_orchestration / hysteresis payload dependence | PROVEN | Runtime correctness bug | High | consumer expects signal_score, thr_buy, thr_sell in a shape producers do not provide |
| E1 | instrument_quantizer / local InstrumentSpec drift | PARTIAL | Contract drift / maintenance debt | Medium | local DTO duplicates canonical contract subset |

## 3. Deep Findings By File

### A. inception_filter.py / confirm_next_bar

Facts:
- apps/reference/domains/decision_making/inception_filter.py:88 returns InceptionResult(eligible=False, micro_fraction=1.0, why="action_confirm_next_bar") for action confirm_next_bar.
- apps/reference/domains/decision_making/inception_filter.py:55 documents that confirm_next_bar returns a non-eligible token only.
- apps/reference/config_models.py:1027 allows action values none, micro_size, confirm_next_bar.
- apps/reference/domains/decision_making/schemas/regime_shift_suspected_v1.json:14 also advertises confirm_next_bar in action_taken.
- In the direct caller, apps/reference/domains/decision_making/aurora_decision.py:733 computes action_taken from config, but apps/reference/domains/decision_making/aurora_decision.py:747 only applies special handling when inc_res.eligible and action_taken == "micro_size".
- Current YAML in config/aurora/regime.yaml:102, config/aurora/regime.yaml:103, and config/aurora/regime.yaml:104 keeps regime_shift_inception disabled with action none.
- tests/domains/decision_making/test_inception_filter.py covers disabled and micro_size cases, but no confirm_next_bar case was found.

Inference:
- confirm_next_bar is not a hidden delayed-entry mechanism. It is a declared surface that currently terminates as an ineligible reason token without any follow-up scheduling or persistence.

Verdict:
- PROVEN contract drift.

Operational risk:
- Medium. It is currently disabled in YAML, so there is no proven active production break under current config.
- The risk appears when someone enables confirm_next_bar expecting a supported runtime mode.

Recommended safe action:
- Fail closed on confirm_next_bar until a real end-to-end orchestration exists, or remove the advertised action from config/schema surfaces.

### B. exit_manager.py / permissive coercion

Facts:
- apps/reference/domains/decision_making/exit_manager.py:48 through apps/reference/domains/decision_making/exit_manager.py:68 normalize constructor inputs through _safe_danger_zone_action, _safe_float, and _safe_bool.
- apps/reference/domains/decision_making/exit_manager.py:79, apps/reference/domains/decision_making/exit_manager.py:95, and apps/reference/domains/decision_making/exit_manager.py:103 implement permissive conversions.
- apps/reference/domains/decision_making/exit_manager.py:112 uses only normalized private fields for runtime exit logic.
- The inspected app-live constructor path goes through apps/reference/domains/decision_making/aurora_config_loader.py:395 and apps/reference/domains/decision_making/aurora_config_loader.py:416, where a typed ExitManagerConfig is built and then passed to ExitManager.
- apps/reference/config_models.py:2264 defines ExitManagerConfig as a strict Pydantic contract.
- tests/test_exit_manager.py constructs ExitManager through typed config objects and validates priority/behavior on typed inputs.

Inference:
- The coercion layer is real and weakens strict SSOT boundaries if raw values ever reach this constructor.
- However, the current inspected live caller chain does not prove that malformed raw values are actually entering through production wiring.

Verdict:
- PARTIAL.

Operational risk:
- Medium as a contract smell.
- Not yet proven as an active runtime defect under the inspected Aurora path.

Recommended safe action:
- Add a proof test that constructs ExitManager from malformed raw inputs only if such a path is intentionally supported.
- If raw construction is not intended, tighten the constructor boundary and let Pydantic remain the only accepted contract owner.

### C. event_handlers.py / broad exception swallowing and arming_require_regime_warmup

#### C1. Broad exception swallowing

Facts:
- apps/reference/domains/decision_making/event_handlers.py:135 wraps the tick-feature reject WAL write in except Exception: pass.
- apps/reference/domains/decision_making/event_handlers.py:157 suppresses failures while clearing risk_skew_guard on feature refresh.
- apps/reference/domains/decision_making/event_handlers.py:516 suppresses behavior overlay failures in on_regime.
- apps/reference/domains/decision_making/event_handlers.py:245 explicitly documents that ConfigContractError must be re-raised while non-contract failures in alpha scoring are logged and suppressed.
- tests/runtime/test_config_contract_block_normalization.py:95 and tests/domains/decision_making/test_event_export_monitoring_handlers.py:102 prove that ConfigContractError is normalized into EVT:DECISION_BLOCKED.
- apps/reference/domains/decision_making/strategy_gateway.py:515 through apps/reference/domains/decision_making/strategy_gateway.py:530 prove that risk_skew_guard has downstream runtime effect, including auto-clear timeout behavior.

Inference:
- The proven defect is loss of forensic truth in best-effort observability and maintenance side paths.
- A broader state corruption claim is weaker because one important stale-state mechanism, risk_skew_guard, has downstream mitigation through auto-clear.

Verdict:
- PROVEN for observability loss.
- PARTIAL for broader runtime-state skew risk.

Operational risk:
- Medium. The main decision pipeline remains fail-closed on ConfigContractError, but silent suppression makes post-mortem evidence incomplete.

Recommended safe action:
- Replace pure pass sites with at least warning-level trace or metric increments without changing business flow.

#### C2. Dead arming_require_regime_warmup

Facts:
- apps/reference/domains/decision_making/decision_making.py:170 reads dm_cfg.arming.require_regime_warmup.
- apps/reference/domains/decision_making/decision_making.py:250 injects that flag into DMEventHandlers.
- apps/reference/domains/decision_making/event_handlers.py:494 through apps/reference/domains/decision_making/event_handlers.py:497 compute full_ready with the same expression in both the true and false branches.
- config/aurora/domains.yaml:79 sets require_regime_warmup: true.
- tests/integration/test_regime_detector_event_flow.py:101 through tests/integration/test_regime_detector_event_flow.py:109 clearly express an intended behavior difference between true and false, but those tests were skipped in the focused validation run.

Inference:
- The flag is wired through configuration and object construction, but it does not change runtime behavior in the inspected branch.
- The skipped integration test indicates intended semantics, not proven executed semantics.

Verdict:
- PROVEN contract drift.

Operational risk:
- High as a configuration truthfulness issue.
- Current YAML value is true, so the immediate live outcome is not a branch inversion bug; the problem is that false is advertised as meaningful when code does not honor it.

Recommended safe action:
- Either remove or fail-close the false surface until differentiated semantics are implemented and validated.

### D. flip_orchestration.py / direct CMD:CLOSE legacy path and hysteresis payload dependence

#### D1. Direct CMD:CLOSE legacy path

Facts:
- apps/reference/domains/decision_making/flip_orchestration.py:195 defines the canonical handle_flip_orchestration path.
- apps/reference/domains/decision_making/strategy_gateway.py:643 calls dm._handle_flip_orchestration as part of the live gate chain.
- apps/reference/domains/decision_making/decision_making.py:596 is the facade wrapper for handle_flip_orchestration.
- apps/reference/domains/decision_making/flip_orchestration.py:354 defines the separate initiate_flip_close helper that emits direct CMD:CLOSE then deferred retry.
- apps/reference/domains/decision_making/decision_making.py:611 exposes the _initiate_flip_close wrapper.
- tests/domains/decision_making/test_flip_initiate_direct_cmd_close.py directly validates that helper path.
- No internal app runtime caller beyond the facade wrapper was found for _initiate_flip_close in the inspected search scope.

Inference:
- The helper is not dead code because it is tested and still exported through the facade.
- It is also not the primary live runtime path for strategy-signal flip handling.

Verdict:
- PARTIAL.

Operational risk:
- Medium as a compatibility and maintenance surface.
- Not proven as the active path causing current runtime misbehavior.

Recommended safe action:
- Keep it clearly labeled as compatibility-only unless a real runtime caller is found.

#### D2. Hysteresis payload dependence

Facts:
- apps/reference/domains/decision_making/flip_orchestration.py:266 through apps/reference/domains/decision_making/flip_orchestration.py:275 read original_pld.get("signal_score"), original_pld.get("thr_buy"), and original_pld.get("thr_sell") directly from the incoming payload.
- apps/reference/domains/decision_making/strategy_gateway.py:643 forwards the original strategy payload into _handle_flip_orchestration without normalizing these fields.
- Repo-wide search in the inspected strategy-signal producers did not find top-level signal_score emission for EVT:STRATEGY_SIGNAL_PRODUCED.
- In the Aurora signal producer, apps/reference/domains/decision_making/aurora_decision.py:1555 through apps/reference/domains/decision_making/aurora_decision.py:1561 place score and thresholds under the nested scoring block.
- In the mean reversion signal producer, apps/reference/domains/decision_making/mean_reversion_handler.py:1321 through apps/reference/domains/decision_making/mean_reversion_handler.py:1360 emit top-level score and nested scoring.score, but no top-level signal_score or threshold keys were proven.
- In the MD-AMR signal producer, apps/reference/domains/decision_making/md_amr_handler.py:1763 through apps/reference/domains/decision_making/md_amr_handler.py:1784 emit top-level score and nested scoring.score, while threshold evidence is kept elsewhere in trace logic rather than provided in the top-level contract expected by flip hysteresis.
- apps/reference/domains/decision_making/flip_orchestration.py:275 only applies hysteresis when all three values are present.
- No targeted test proving FLIP_HYSTERESIS_BLOCK on a real current producer payload was found.

Inference:
- This is not just a cross-strategy ambiguity. The consumer expects a contract shape that the current producers do not provide in the expected top-level keys.
- Even if some thresholds appear in nested structures, the missing top-level signal_score alone is sufficient to defeat the current hysteresis precondition.

Verdict:
- PROVEN runtime correctness bug.

Operational risk:
- High. Hysteresis can silently fail open even when the feature is nominally enabled, because the payload contract seam is misaligned.

Recommended safe action:
- Fix the consumer, not the entire producer family first. Let flip_orchestration read score from both top-level score and nested scoring.score, and thresholds from top-level or nested scoring, while logging an explicit contract miss when evidence is absent.
- Add one targeted regression test that feeds a real current Aurora-style payload and proves FLIP_HYSTERESIS_BLOCK when configured.

### E. instrument_quantizer.py / local InstrumentSpec drift

Facts:
- apps/reference/domains/decision_making/instrument_quantizer.py:20 defines a local dataclass InstrumentSpec with the subset fields step_size, min_qty, min_notional, tick_size.
- apps/reference/config_models.py:42 defines the canonical Pydantic InstrumentSpec with additional identity and validation semantics.
- The inspected live Aurora quantization path imports the local alias in apps/reference/domains/decision_making/aurora_decision.py:70.
- apps/reference/domains/decision_making/aurora_decision.py:1612 through apps/reference/domains/decision_making/aurora_decision.py:1616 build the local QuantizerSpec from validated precision fields and pass it to quantize_exposure at apps/reference/domains/decision_making/aurora_decision.py:1625.
- apps/reference/domains/decision_making/aurora_handler.py:68 also imports the local QuantizerSpec alias, but no stronger live runtime path was proven there in this investigation.
- Repo search showed compute_risk_adjusted_notional and compute_structural_stop used in tests, especially tests/test_money_management.py and tests/test_instrument_quantizer.py, rather than in the inspected app-live path.

Inference:
- The local DTO duplicates part of the canonical contract and can drift over time.
- In the currently proven live path, the input fields are sourced from validated config precision, so the subset mirror does not yet prove incorrect sizing behavior.

Verdict:
- PARTIAL.

Operational risk:
- Medium as maintenance debt and future drift risk.
- Not proven as a current live-sizing bug under the inspected path.

Recommended safe action:
- Prefer a single canonical spec shape at the boundary or at least add an explicit adapter function with a narrow documented field projection.

## 4. Root Cause Analysis

Primary root causes:
- Producer-consumer contract seams are not pinned tightly enough at EVT:STRATEGY_SIGNAL_PRODUCED, which allowed D2 to persist.
- Config and schema surfaces outlived runtime semantics, which created A1 and C2.
- Best-effort observability paths were allowed to swallow errors silently, which created the proven portion of C1.
- Local defensive adapters and DTO mirrors survived the move to stricter Pydantic SSOT, which explains B1 and E1.

Systemic pattern:
- The repository increasingly prefers fail-closed logic and typed config, but some older compatibility and observability surfaces still advertise more behavior than runtime actually honors.

## 5. Safe Fix Plan

Priority 1: D2
- Make a minimal localized consumer fix in apps/reference/domains/decision_making/flip_orchestration.py.
- Read score from top-level score and nested scoring.score.
- Read thresholds from top-level thr_buy/thr_sell and nested scoring.thr_buy/scoring.thr_sell.
- Emit explicit logging or metrics when hysteresis is enabled but payload evidence is incomplete.
- Add focused tests for real current producer payload shapes.

Priority 2: C1
- Replace silent pass paths with warning or metric emission in apps/reference/domains/decision_making/event_handlers.py.
- Preserve best-effort behavior. Do not promote these paths to hard failures unless the suppressed action is contract-critical.

Priority 3: A1 and C2
- Fail closed on unsupported config surfaces rather than silently honoring dead configuration.
- For A1, reject confirm_next_bar until orchestration exists.
- For C2, either remove the false branch surface or implement real differentiated semantics and validate them through non-skipped integration tests.

Priority 4: B1 and E1
- Tighten boundaries only after proving external callers.
- Avoid broad refactors unless a concrete non-typed caller or DTO drift bug is demonstrated.

## 6. Unproven Or Partially Proven Items And Minimal Proof Tasks

### B1

What remains unproven:
- Whether any live or helper runtime path constructs ExitManager from raw dicts or stringly typed values outside aurora_config_loader.py.

Minimal proof task:
- Repo-wide caller audit for ExitManager construction outside the inspected loader path.
- If such a caller exists, add a focused test demonstrating malformed input acceptance or rejection.

### D1

What remains unproven:
- Whether any real runtime entrypoint still calls _initiate_flip_close in production-like flows rather than only in tests and compatibility wrappers.

Minimal proof task:
- Inspect external scripts, harnesses, and any non-strategy-signal regime flip entrypoints for _initiate_flip_close usage.

### E1

What remains unproven:
- Whether any non-Aurora runtime code relies on the local InstrumentSpec as a de facto canonical type.

Minimal proof task:
- Complete import audit for QuantizerSpec and instrument_quantizer helper use outside the validated Aurora quantization path and tests.

## 7. Validation Evidence

Static and targeted validation completed:
- py_compile passed for:
  - apps/reference/domains/decision_making/inception_filter.py
  - apps/reference/domains/decision_making/exit_manager.py
  - apps/reference/domains/decision_making/event_handlers.py
  - apps/reference/domains/decision_making/flip_orchestration.py
  - apps/reference/domains/decision_making/instrument_quantizer.py
- Focused pytest run completed with 80 passed and 3 skipped.

Focused test set:
- tests/domains/decision_making/test_inception_filter.py
- tests/test_exit_manager.py
- tests/domains/decision_making/test_event_export_monitoring_handlers.py
- tests/runtime/test_config_contract_block_normalization.py
- tests/domains/decision_making/test_flip_orchestration_v1.py
- tests/domains/decision_making/test_flip_initiate_direct_cmd_close.py
- tests/decision_making/test_flip_orchestration_strategy_id.py
- tests/test_instrument_quantizer.py
- tests/test_money_management.py
- tests/integration/test_regime_detector_event_flow.py

Important search outcomes:
- No confirm_next_bar-focused runtime orchestration was found beyond the token-returning branch in inception_filter and the advertised config/schema surfaces.
- No current producer emission of top-level signal_score was found in the inspected EVT:STRATEGY_SIGNAL_PRODUCED producer set.
- No test explicitly proving FLIP_HYSTERESIS_BLOCK on a real current producer payload was found.
- arming_require_regime_warmup was only found in config ingestion, handler injection, the identical branch in on_regime, and tests.

## 8. Final Ranking

1. D2 — flip_orchestration hysteresis payload dependence: PROVEN runtime correctness bug.
2. C2 — dead arming_require_regime_warmup flag: PROVEN contract drift.
3. A1 — confirm_next_bar advertised without runtime support: PROVEN contract drift.
4. C1 — silent exception swallowing in event_handlers: PROVEN observability gap, PARTIAL runtime-state risk.
5. B1 — permissive ExitManager coercion: PARTIAL latent contract problem.
6. E1 — local InstrumentSpec drift: PARTIAL maintenance and future correctness risk.
7. D1 — direct CMD:CLOSE helper path: PARTIAL compatibility surface, not proven primary runtime hazard.

## Final Verdict

- A1 — PROVEN.
- B1 — PARTIAL.
- C1 — PROVEN for observability, PARTIAL for broader runtime-state impact.
- C2 — PROVEN.
- D1 — PARTIAL.
- D2 — PROVEN.
- E1 — PARTIAL.

Most important next action:
- Fix D2 first with a minimal consumer-side contract alignment patch and a regression test built from a real current producer payload.
