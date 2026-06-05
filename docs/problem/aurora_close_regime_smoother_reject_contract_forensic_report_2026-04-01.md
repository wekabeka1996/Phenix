# Aurora Close-Path, Regime-Smoother, And TRADE_INTENT_REJECTED Contract Forensic Report

Date: 2026-04-01
Status: completed, evidence-based, report-only

Scope:
- apps/reference/domains/execution_position/close_executor.py
- apps/reference/domains/execution_position/order_guardian.py
- apps/reference/domains/execution_position/intent_router.py
- apps/reference/domains/execution_position/trade_intent_reject_contracts.py
- apps/reference/domains/decision_making/aurora_decision.py
- apps/reference/domains/decision_making/aurora_handler.py
- apps/reference/domains/decision_making/quadratic_scoring_kernel.py
- apps/reference/domains/decision_making/regime_smoother.py
- apps/reference/domains/decision_making/intent_emitter.py
- apps/reference/domains/decision_making/trade_intent_reject_wal.py
- apps/reference/config_models.py
- apps/reference/dictionaries/verb_registry_v1.yaml
- config/aurora/strategies/aurora.yaml
- config/docs/AURORA_STRATEGY_CONFIG_PASSPORT.md
- schemas/trade_intent_rejected_v1.json
- focused tests under tests/domains/decision_making and tests/domains/execution_position

Method:
- static call-chain tracing across execution_position and decision_making
- targeted runtime probes designed to distinguish real runtime behavior from stale contract surfaces
- focused pytest validation on the exact streams under audit
- no production code edits during the investigation itself

## 1. Executive Summary

- This report covers three priority streams only:
  - execution close-path safety
  - regime_smoother live-wiring truth
  - TRADE_INTENT_REJECTED contract split between decision_making and execution_position
- Stream A is a PROVEN runtime defect. In both partial-close and full-close paths, adapter position-read failure is collapsed into the semantic value "no open position", which clears local bracket tracking and returns before authoritative guardian cleanup/reconcile runs.
- Stream B is not a live scoring bug. It is a PROVEN stale or incomplete migration surface: config and docs expose regime_smoothing, the smoother class exists, aurora_decision passes a nullable hook through, but no runtime construction was found and the quadratic kernel explicitly documents the argument as compatibility-only and ignored.
- Stream C splits into two separate findings:
  - C1 is a PROVEN local contract bug: the decision_making WAL writer can persist a TRADE_INTENT_REJECTED payload whose why field exceeds the registered schema maxLength of 240.
  - C2 is a PROVEN architecture drift or incomplete migration: decision_making owns the verb in the registry, but the stricter canonical normalizer/emitter currently lives in execution_position, while several direct decision_making callsites bypass that canonical boundary entirely.
- Highest runtime urgency is Stream A.
- Safest immediate patch order is:
  - fix Stream A fail-closed behavior
  - fix Stream C1 schema-safe why handling
  - then decide Stream C2 canonical ownership and routing
  - treat Stream B as stale surface cleanup or deliberate feature completion, not as a hot runtime bug

## 2. Evidence Rules And Boundaries

Facts:
- Runtime truth outweighed comments and documentation claims.
- Conclusions are anchored to inspected code, targeted search results, runtime probes, and focused pytest only.
- No broad code changes were made while producing this report.

Facts:
- The docs/ai protocol files referenced by repository instructions were not present on disk during the investigation.

Inference:
- This report had to be anchored to current code and current runtime evidence rather than to absent protocol documents.

Facts:
- The repository already contained other forensic artifacts under docs/problem. This report is scoped only to the three streams above and does not supersede unrelated earlier reports.

## 3. Findings Matrix

| Stream | Core question | Verdict | Classification | Severity |
| --- | --- | --- | --- | --- |
| A | Does DEC:CLOSE treat position-read failure as flat and clear local truth | PROVEN | real runtime bug | High |
| B | Is regime_smoothing live-wired into Aurora scoring | PROVEN no live wiring | stale surface or incomplete migration | Medium |
| C1 | Can decision_making write schema-incompatible TRADE_INTENT_REJECTED payloads | PROVEN | local contract bug | High |
| C2 | Is there one canonical reject payload builder across DM and EP | PROVEN split | architecture drift or incomplete migration | Medium-High |

## 4. Stream A — Execution Close-Path Safety

### FACTS

- In the partial-close branch of apps/reference/domains/execution_position/close_executor.py, the code re-reads positions at line 67.
- If get_open_positions() raises, the branch sets pos = None and continues.
- If pos is None or positionAmt cannot be parsed, amt remains 0.0.
- At line 88, when abs(amt) < 1e-10, the branch logs "No open position to close", clears self._fsm._symbol_brackets for the symbol, and returns immediately.
- The partial-close path only calls order_guardian.reconcile_symbol after a successful reduce-only market close at line 115.
- Therefore, position-read failure in the partial-close branch never reaches guardian reconcile.

- In the full-close branch of apps/reference/domains/execution_position/close_executor.py, the code re-reads positions again at line 193 after tracked bracket cancellation.
- If that second get_open_positions() call raises, the branch again sets pos = None and continues.
- If pos is None or positionAmt cannot be parsed, amt remains 0.0.
- At line 211, when abs(amt) < 1e-10, the branch logs "No open position to close", clears self._fsm._symbol_brackets for the symbol, and returns immediately.
- Authoritative post-close cleanup only occurs later, at lines 286 and 287, where close_executor calls order_guardian.cleanup_orphans() and order_guardian.reconcile_symbol(symbol, rid).
- Therefore, the early return at line 211 bypasses both guardian cleanup and guardian reconcile.

- order_guardian stores bracket truth through register_bracket at apps/reference/domains/execution_position/order_guardian.py:373 and register_brackets at apps/reference/domains/execution_position/order_guardian.py:457.
- cleanup_orphans is the guardian-side cleanup entrypoint at apps/reference/domains/execution_position/order_guardian.py:887.
- On cleanup failure, guardian logs "Orphan cleanup failed" at apps/reference/domains/execution_position/order_guardian.py:1166 instead of translating unknown state into flat.
- reconcile_symbol is the guardian-side authoritative symbol reconcile entrypoint at apps/reference/domains/execution_position/order_guardian.py:1314.
- reconcile_symbol re-reads positions and treats has_position = abs(position_amt) >= 1e-10.
- If a position exists, guardian explicitly skips reconcile and returns.
- If no position exists, guardian calls cleanup_orphans(symbol=symbol, hard=True) at apps/reference/domains/execution_position/order_guardian.py:1351.
- On reconcile failure, guardian logs "Reconcile failed for {symbol}" at apps/reference/domains/execution_position/order_guardian.py:1388.

### RUNTIME PROOF

The focused runtime smoke for this stream returned:

```text
{
  'partial': {
    'steps': [],
    'brackets_after': {},
    'market_close_called': 0,
    'guardian_cleanup_called': 0,
    'guardian_reconcile_called': 0
  },
  'full': {
    'steps': ['cancel:BTCUSDT:sl1', 'cancel:BTCUSDT:tp1'],
    'brackets_after': {},
    'market_close_called': 0,
    'guardian_cleanup_called': 0,
    'guardian_reconcile_called': 0
  }
}
```

This proves:
- partial-close position-read failure can clear local bracket state and return without any market close and without any guardian follow-up
- full-close position-read failure can cancel tracked local brackets, clear local bracket state, and return without any market close and without any guardian follow-up

### INFERENCES

- close_executor currently collapses "position truth unavailable" into the semantic value "flat".
- The stronger fail-closed behavior that exists in guardian code does not protect this path, because close_executor returns before guardian is invoked.
- This is not a harmless idempotent no-op. The local execution_position state changes before authoritative truth is restored.

### ROOT CAUSE

- The close path uses a permissive fallback of pos = None and amt = 0.0 on adapter position-read failure.
- The same zero-amount branch is used for both proven flat state and unknown position state.

### BLAST RADIUS

Facts:
- Local bracket tracking in self._fsm._symbol_brackets can be cleared even though no authoritative flat-state proof was obtained.
- In the full-close path, tracked bracket cancellation can happen before the path returns as if no position existed.
- Guardian cleanup_orphans and guardian reconcile_symbol are skipped on the early-return branch.

Inference:
- The proven blast radius is local execution_position truth corruption and skipped cleanup or reconcile.

Unknown:
- I did not prove that a higher layer immediately marks the symbol globally flat outside execution_position, only that close_executor locally behaves as if flat on lookup failure.

### CLASSIFICATION

- Real runtime bug.
- Best described as fail-open or semantic corruption on the close path.

### SAFE FIX DIRECTION

- Position-read exceptions on the close path should remain fail-closed.
- The close path should not clear local bracket state merely because adapter position truth is unavailable.
- The early-return branch should distinguish proven zero position from unknown position.
- Any repair should preserve guardian as the authoritative cleanup or reconcile owner after uncertainty, rather than clearing local state first.

## 5. Stream B — regime_smoother Live-Wiring Truth

### FACTS

- RegimeSmoothingConfig exists in typed config at apps/reference/config_models.py:1037.
- DecisionConfig includes regime_smoothing at apps/reference/config_models.py:1335.
- Aurora strategy YAML exposes decision.regime_smoothing at config/aurora/strategies/aurora.yaml:190.

- apps/reference/domains/decision_making/regime_smoother.py defines RegimeMultiplierSmoother as a stateful per-symbol helper.
- The class stores internal per-symbol state in four dicts: _last_smoothed, _last_raw, _bars_since_change, and _ramp_start.
- The helper is a passthrough when config is missing or disabled.

- aurora_decision passes a nullable regime_smoother hook through its scoring call chain at apps/reference/domains/decision_making/aurora_decision.py:450 and apps/reference/domains/decision_making/aurora_decision.py:519.
- quadratic_scoring_kernel.compute accepts regime_smoother at apps/reference/domains/decision_making/quadratic_scoring_kernel.py:164.
- The kernel docstring explicitly states at apps/reference/domains/decision_making/quadratic_scoring_kernel.py:182 through apps/reference/domains/decision_making/quadratic_scoring_kernel.py:186 that regime_smoother is a compatibility-only kwarg and is not read by the implementation.

- A repo-wide constructor search over apps/reference/** found no RegimeMultiplierSmoother(...) runtime instantiation.
- A targeted search found no _regime_smoother assignment in apps/reference/domains/decision_making/aurora_handler.py.
- A targeted search found no regime_smoothing or _regime_smoother usage in apps/reference/domains/decision_making/aurora_config_loader.py.

- Existing tests explicitly neutralize the hook by assigning handler._regime_smoother = None in:
  - tests/domains/decision_making/test_aurora_quadratic_logging.py:70
  - tests/domains/decision_making/test_aurora_runtime_readiness_contract.py:824
  - tests/domains/decision_making/test_aurora_runtime_readiness_contract.py:946

- The current config passport still documents decision.regime_smoothing.* as an operator-facing live surface at:
  - config/docs/AURORA_STRATEGY_CONFIG_PASSPORT.md:335
  - config/docs/AURORA_STRATEGY_CONFIG_PASSPORT.md:346
  - config/docs/AURORA_STRATEGY_CONFIG_PASSPORT.md:355
  - config/docs/AURORA_STRATEGY_CONFIG_PASSPORT.md:367

### RUNTIME PROOF

The focused runtime smoke for this stream returned:

```text
{
  'quadratic_kernel_same_with_or_without_smoother': {
    'score_none': '0.36',
    'score_bomb': '0.36',
    'side_none': 'buy',
    'side_bomb': 'buy',
    'equal': True
  }
}
```

This proves that, on the inspected path, supplying a smoother object to the current quadratic kernel does not change the decision output.

### INFERENCES

- The current runtime does not prove any live construction or live use of RegimeMultiplierSmoother.
- The exposed config and passport surface therefore overstate actual runtime capability.
- The smoother class itself is real and unit-testable, but it is not live-wired into the currently inspected Aurora scoring path.

### CLASSIFICATION

- Stale surface or incomplete migration.
- Not a proven live scoring defect in its current unwired state.

### BLAST RADIUS

Facts:
- Operators can set decision.regime_smoothing in YAML and reasonably believe it changes live Aurora scoring.
- The current kernel and runtime path do not prove that belief correct.

Inference:
- The current blast radius is operator confusion, stale documentation, and false confidence in a non-live feature surface.

Unknown:
- I did not prove whether any out-of-scope runtime entrypoint outside the inspected Aurora path constructs and uses the smoother.

### SAFE FIX DIRECTION

- Safest immediate action is to treat regime_smoothing as stale until proven otherwise.
- The two coherent repair options are:
  - wire the feature fully: instantiate the smoother, consume it in the kernel, and add runtime-facing tests
  - or fail closed on the surface: deprecate, remove, or explicitly document it as inactive until implemented

## 6. Stream C — TRADE_INTENT_REJECTED Contract Split

### FACTS

- The verb registry declares decision_making as the owner of TRADE_INTENT_REJECTED at apps/reference/dictionaries/verb_registry_v1.yaml:404.
- The same registry declares execution_position as a co-emitter at apps/reference/dictionaries/verb_registry_v1.yaml:406.
- The registered schema is schemas/trade_intent_rejected_v1.json at apps/reference/dictionaries/verb_registry_v1.yaml:408.

- The schema requires ts_ms, symbol, reason_code, stage, and why at schemas/trade_intent_rejected_v1.json:8.
- The schema caps why at maxLength 240 at schemas/trade_intent_rejected_v1.json:48 through schemas/trade_intent_rejected_v1.json:50.

- decision_making's WAL helper explicitly documents that it does not emit EVT:TRADE_INTENT_REJECTED on the live FSM bus at apps/reference/domains/decision_making/trade_intent_reject_wal.py:5.
- That helper writes payload["why"] = str(why) at apps/reference/domains/decision_making/trade_intent_reject_wal.py:81.
- It appends an event-shaped WAL row at apps/reference/domains/decision_making/trade_intent_reject_wal.py:121 through apps/reference/domains/decision_making/trade_intent_reject_wal.py:126.

- execution_position owns a canonical normalizer in apps/reference/domains/execution_position/trade_intent_reject_contracts.py:102.
- That normalizer clamps why to 240 characters at apps/reference/domains/execution_position/trade_intent_reject_contracts.py:161.
- execution_position owns a canonical live emitter in apps/reference/domains/execution_position/trade_intent_reject_contracts.py:192.
- That canonical emitter emits EVT:TRADE_INTENT_REJECTED through the FSM at apps/reference/domains/execution_position/trade_intent_reject_contracts.py:210 through apps/reference/domains/execution_position/trade_intent_reject_contracts.py:236.

- The decision_making live emitter wrapper exists in apps/reference/domains/decision_making/intent_emitter.py:153.
- intent_emitter writes the reject WAL helper at apps/reference/domains/decision_making/intent_emitter.py:194.
- intent_emitter emits EVT:TRADE_INTENT_REJECTED on the live bus at apps/reference/domains/decision_making/intent_emitter.py:210.

- Several direct decision_making callsites bypass the live emitter and canonicalizer by calling write_trade_intent_rejected directly:
  - apps/reference/domains/decision_making/aurora_decision.py:270
  - apps/reference/domains/decision_making/aurora_decision.py:310
  - apps/reference/domains/decision_making/aurora_handler.py:714
  - apps/reference/domains/decision_making/aurora_handler.py:733
  - apps/reference/domains/decision_making/aurora_handler.py:749
  - apps/reference/domains/decision_making/aurora_handler.py:783

- execution_position intent routing uses the canonical emitter on the boundary at:
  - apps/reference/domains/execution_position/intent_router.py:205
  - apps/reference/domains/execution_position/intent_router.py:233
  - apps/reference/domains/execution_position/intent_router.py:261
  - apps/reference/domains/execution_position/intent_router.py:293
- intent_router also clamps fallback why text through result.why[:240] at:
  - apps/reference/domains/execution_position/intent_router.py:240
  - apps/reference/domains/execution_position/intent_router.py:255
  - apps/reference/domains/execution_position/intent_router.py:501

### RUNTIME PROOF

The focused runtime smoke for this stream returned:

```text
{
  'reject_split': {
    'dm_wal_why_len': 300,
    'ep_normalized_why_len': 240,
    'dm_wal_has_truncation': False,
    'ep_normalizer_truncates': True
  }
}
```

This proves a real runtime split between:
- the decision_making WAL helper, which preserves an overlong why as-is
- the execution_position canonical path, which clamps why to the schema maxLength

### INFERENCES

- A decision_making WAL row that looks event-shaped is not proof of either live bus emission or schema conformance.
- Current runtime behavior depends on which surface emitted the reject:
  - direct DM WAL helper
  - DM intent_emitter
  - EP canonical reject boundary
- The current repo therefore has more than one practical TRADE_INTENT_REJECTED payload contract in motion.

### C1 — LOCAL BUG

Facts:
- The registered schema caps why at 240.
- The direct DM WAL helper writes why without a 240-character clamp.

Verdict:
- PROVEN local contract bug.

Blast radius:
- DM-originated reject truth artifacts can be schema-incompatible.
- Any downstream consumer or audit tool that assumes schema-safe DM reject rows can receive oversize why payloads.

Safe fix direction:
- Clamp or normalize why inside trade_intent_reject_wal.py before persistence.
- Add a focused regression test proving DM-originated WAL rows respect the registered maxLength.

### C2 — CANONICAL OWNERSHIP SPLIT

Facts:
- The registry says decision_making owns the verb.
- The stricter canonical normalizer and canonical boundary emitter currently live in execution_position.
- Direct decision_making callsites bypass both the DM live emitter and the EP canonical normalizer.

Verdict:
- PROVEN architecture drift or incomplete migration.

Blast radius:
- Reject payload semantics differ depending on whether they originated in direct DM helper paths or EP canonical boundary paths.
- Monitoring and audit consumers can observe inconsistent normalization and compatibility handling for the same registered verb.

Safe fix direction:
- Choose one canonical payload builder and one authoritative emit path.
- Then route direct DM callsites through that single canonical surface rather than writing raw reject WAL rows ad hoc.

## 7. Validation Evidence

### Focused Runtime Proofs

Combined runtime proofs established three concrete behaviors:

```text
1. Close path failure collapse:
   partial -> local brackets cleared, no market close, no guardian cleanup, no guardian reconcile
   full    -> tracked brackets cancelled, local brackets cleared, no market close, no guardian cleanup, no guardian reconcile

2. regime_smoother non-effect in current kernel:
   score_none == score_bomb
   side_none  == side_bomb

3. TRADE_INTENT_REJECTED split:
   DM WAL why length 300
   EP canonical normalized why length 240
```

### Focused Pytest Validation

The following focused test slice passed during the investigation:

- tests/domains/decision_making/test_regime_smoother.py
- tests/domains/execution_position/test_reject_contract_and_lifecycle_fix.py
- tests/domains/execution_position/test_execpos_max_hold_close_executes_adapter_v1.py
- tests/domains/execution_position/test_execution_observability_hardening.py

Selected assertions covered:
- regime smoother unit behavior in isolation
- reject schema acceptance and legacy normalization at the execution_position boundary
- canonical reject helper observability and lifecycle closure
- happy-path DEC:CLOSE adapter execution
- tidy-vs-close-reconciled observability semantics

Observed result:

```text
13 selected tests passed, 7 deselected
```

## 8. Assumptions

- I treated the currently loaded repository code and current branch state as the active runtime under audit.
- I treated the focused runtime smokes as representative proofs of the exact branches they exercised, not as broader proofs of every possible deployment topology.

## 9. Unknowns

- I did not prove whether any out-of-scope service or bootstrap path outside the inspected Aurora runtime constructs RegimeMultiplierSmoother and consumes it meaningfully.
- I did not prove whether any out-of-scope consumer normalizes oversize DM reject WAL rows after they are written.
- I did not prove that the close-path local corruption immediately propagates into a broader repository-wide flat-state claim beyond execution_position itself.

## 10. Safe Fix Sequencing

1. Stream A first.

- Fix close_executor so adapter position-read failure remains fail-closed.
- Do not clear local bracket state or return as flat on unknown position truth.
- Preserve or invoke guardian authority after uncertainty instead of bypassing it.

2. Stream C1 second.

- Clamp or normalize DM reject WAL payloads so why always honors the registered schema maxLength.
- Add a regression test at the DM helper boundary.

3. Stream C2 third.

- Decide where the canonical TRADE_INTENT_REJECTED payload builder truly lives.
- After that decision, route all direct DM callsites through the same canonical surface.

4. Stream B last.

- Either implement true regime_smoother runtime wiring with tests and kernel consumption,
- or treat the config and passport surface as stale and remove or deprecate it.

## 11. Final Verdict

- Stream A is a real runtime defect and the most urgent issue in this report.
- Stream B is a stale or incomplete feature surface, not a live scoring regression.
- Stream C contains both a concrete local schema bug and a broader canonical ownership split.
- These streams should not be treated as one bug family. They are different failure classes and should be fixed in different orders.

Condensed disposition:

- A: PROVEN runtime bug
- B: PROVEN stale surface or incomplete migration
- C1: PROVEN local contract bug
- C2: PROVEN architecture drift or incomplete migration
