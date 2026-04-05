# POSITION POLICY SIDECAR V1 — DEEP AUDIT AND PHASE-CLOSURE VERDICT

**Date**: 2026-04-04
**Auditor**: Claude Opus 4.6 (automated deep audit)
**Branch**: Phenix_v2
**Scope**: Phase-state audit and closure audit for Sidecar v1, Packages 1–4

---

## 1. Executive Verdict

The Position Policy Sidecar v1 is at **implementation-complete, runtime-unproven** status for the shadow evaluation phase. Four sequentially discovered blockers — lifecycle activation, portfolio field mismatch, postfill reservation crash, and bracket OrderIndex registration — have each been fixed in code with deterministic test proof. However, **zero runtime instances of `SCORES`, `EVALUATED`, `RECOMMENDED`, or `ACTION_SKIPPED`** have ever been observed in any live session. All 6,424 sidecar policy rows in the most recent validation summary are either `MODE_ACTIVE` (1) or `SUPPRESSED` (6,423). The compound effect of all four fixes applied simultaneously has never been validated against a live exchange session. The current codebase is ready for a live restart audit that would either close the phase or surface a fifth layer blocker.

**Primary Verdict**: `IMPLEMENTATION_PHASE_CLOSED_RUNTIME_PHASE_OPEN`

---

## 2. Current Sidecar Phase Map

The roadmap defines 11 phases (R0–R10). The current work corresponds to **R3: Observability First (No Live Actions)** — specifically the shadow validation gate within R3 that requires evidence the sidecar *actually evaluates* before declaring shadow mode operational.

### Sub-Area Classification

| # | Sub-Area | Status | Evidence |
|---|----------|--------|----------|
| 1 | Sidecar bootstrap / activation | `PROVEN_RUNTIME_OK` | 1 `MODE_ACTIVE` row in trade_lifecycle.jsonl; confirmed in validation summary; emitted on real restart |
| 2 | Live ingress reception | `PROVEN_RUNTIME_OK` | 6,423 SUPPRESSED rows from 5 distinct trigger events (PORTFOLIO_STATE_UPDATED=3229, FEATURES_CALCULATED=1785, REGIME_DETECTED=1389, TRADE_EXECUTED=20, ORDER_STATE_CHANGED=~0); all 7 symbols represented |
| 3 | Lifecycle activation on live fill path | `IMPLEMENTED_TESTED_RUNTIME_UNPROVEN` | Post-fix restart audit (Report F) showed `manage_state=BRACKETS_PENDING` for SOL/BTC on real fills. BUT: this was the state *before* the portfolio snapshot fix and postfill exp_ts fix were applied. No runtime evidence exists with ALL fixes combined |
| 4 | Portfolio snapshot semantics | `IMPLEMENTED_TESTED_RUNTIME_UNPROVEN` | Code now normalizes `net_position`→`positionAmt`, `avg_entry_price`→`entryPrice` via `_first_present_value()`. Absent symbols get explicit `symbol_absent` status, not zero. 19 deterministic tests pass. No live evidence of correct non-zero `positionAmt` in sidecar rows |
| 5 | Portfolio freshness propagation | `IMPLEMENTED_TESTED_RUNTIME_UNPROVEN` | `positions_last_ts_ms` now retained on per-symbol snapshots via `_normalize_portfolio_position_snapshot()`. Postfill crash seam (`exp_ts` KeyError) fixed by routing through canonical `record_postfill_hold()`. 22 deterministic tests pass for the fix. No live evidence the sidecar's portfolio freshness advances past fill → portfolio event boundary |
| 6 | Sidecar evaluation progression | `STILL_BROKEN` (at runtime level) | Zero SCORES, EVALUATED, RECOMMENDED, ACTION_SKIPPED rows in any runtime session. The suppression chain terminates evaluation before scoring in every observed case. Code-level: full chain (SCORES→EVALUATED→RECOMMENDED→ACTION_SKIPPED) is exercised in 1 unit test with synthetic inputs |
| 7 | Bracket ownership / provenance | `IMPLEMENTED_TESTED_RUNTIME_UNPROVEN` | `register_bracket_child()` in `OrderIndex` called from `BracketManager` for both SL and TP. 22 tests pass. Guardian fallback removed in favor of canonical registration. Post-fix restart showed coherent ownership (`strategy_id=aurora`, `owner_status=resolved`). No live proof after bracket child OrderIndex fix deployed |
| 8 | Terminal WS close truth restoration | `IMPLEMENTED_TESTED_RUNTIME_UNPROVEN` | Full deterministic replay chain from raw WS `ORDER_TRADE_UPDATE` through guardian correlation to ManageFlowFSM flatten to PositionTracking zeroing to disappearance attribution. 15 tests pass. No live exchange proof post-deployment |
| 9 | Disappearance attribution correctness | `IMPLEMENTED_TESTED_RUNTIME_UNPROVEN` | Proven bracket close → `proven_exchange_bracket_close` attribution. Unknown → `unknown_disappearance` (fail-closed, no false `manual` label). 2 targeted tests pass. No live runtime proof |
| 10 | Runtime observability sufficiency | `PARTIALLY_FIXED` | 6 sidecar event schemas exist (MODE_ACTIVE, SUPPRESSED, SCORES, EVALUATED, RECOMMENDED, ACTION_SKIPPED). Trade lifecycle JSONL records sidecar rows. Forensic tooling (`position_policy_sidecar_validation.py`) can scan WAL + lifecycle + order_log. BUT: only SUPPRESSED observability works in practice since evaluation never fires at runtime |

---

## 3. FACTS (Evidence-Backed Only)

### F1: Sidecar runtime row counts (most recent validation summary)

```
policy_rows.total        = 6,424
  MODE_ACTIVE            = 1
  SUPPRESSED             = 6,423
  SCORES                 = 0
  EVALUATED              = 0
  RECOMMENDED            = 0
  ACTION_SKIPPED         = 0
```

**Source**: `PKG_POSITION_POLICY_SIDECAR_POST_FIX_RESTART_RUNTIME_AUDIT_REPORT.md` and package4 validation tooling report.

### F2: Runtime suppression distribution

```
startup_grace_active                     = 2,412
no_manage_flow_for_symbol                = 3,796
post_fill_grace_active                   =    20
manage_flow_has_no_active_lifecycle      =    25
portfolio_snapshot_missing_or_stale      =   170
```

### F3: Post-fix lifecycle activation confirmed for one runtime window

SOL post-restart chain: fill at `1775250755101` → ManageFlowFSM `FLAT→BRACKETS_PENDING` at `1775250755141` → sidecar saw `manage_state=BRACKETS_PENDING` → subsequently suppressed on `post_fill_grace_active`, then `portfolio_snapshot_missing_or_stale`.

**Source**: `PKG_POSITION_POLICY_SIDECAR_POST_FIX_RESTART_RUNTIME_AUDIT_REPORT.md`, SOL chain proof.

### F4: Portfolio snapshot contract fix verified in code

`_normalize_portfolio_position_snapshot()` (position_policy_sidecar.py:124-154) now resolves `positionAmt` from `("net_position", "positionAmt")` and `entryPrice` from `("avg_entry_price", "entryPrice", "avgEntryPrice")` via `_first_present_value()`. Missing symbols get explicit `symbol_absent` status without zero overwrite.

### F5: Postfill reservation canonical writer fix verified in code

`EPEventHandlers.on_order_fill()` (event_handlers.py:~760) now calls `self._fsm.exposure_guard.record_postfill_hold()` which writes canonical shape with `exp_ts` field, preventing the `KeyError('exp_ts')` crash in `expire_stale()`.

### F6: Bracket child OrderIndex registration verified in code

`BracketManager._register_bracket_results()` (bracket_manager.py:212-243) calls `order_index.register_bracket_child()` for both SL and TP bracket children, at both the primary market path and the deferred limit path (lines 420-441). `register_bracket_child()` (order_index.py:160+) validates `clientOrderId`, `exchangeOrderId`, and `order_kind` before registering in all three index maps.

### F7: Test coverage for sidecar chain

- 1 test exercises full SCORES→EVALUATED→RECOMMENDED→ACTION_SKIPPED chain (unit-level, synthetic inputs)
- 14 total sidecar-specific tests (portfolio normalization, suppression taxonomy, config validation)
- 19 portfolio snapshot contract fix tests
- 22 postfill exp_ts fix tests
- 22 bracket child OrderIndex registration tests
- 2 disappearance attribution tests
- 53+ effective test variants across all sidecar-related files

### F8: All fixes applied after the most recent runtime audit

The most recent runtime audit (`PKG_POSITION_POLICY_SIDECAR_POST_FIX_RESTART_RUNTIME_AUDIT_REPORT.md`) showed the lifecycle fix working, but was conducted **before** the portfolio snapshot contract fix and the postfill reservation exp_ts fix were deployed. The bracket child OrderIndex fix was also applied after this audit. Therefore, the compound effect of all four fixes has never been tested at runtime.

---

## 4. Blocker Ledger

### Blocker 1: ManageFlowFSM lifecycle activation on live fill path

| Attribute | Value |
|-----------|-------|
| **Original problem** | `ManageFlowFSM` stayed `FLAT` after live fills because the bus listener path (`_on_trade_executed`) did not call `manage_flow.handle(msg)` |
| **Cause** | Live WS fill listener called `_evt_handlers.on_trade_executed()` and `sidecar.on_order_fill()` but not `manage_flow.handle()` |
| **Fix package** | `_handle_canonical_fill_ingress()` — unified fill handler at fsm.py:1767 that routes all fill events through `manage_flow.handle()` |
| **Current proof level** | Code fix: YES. Deterministic tests: YES (2 tests in `test_canonical_fill_ingress_activation.py`). Runtime: PARTIAL — one runtime window showed `BRACKETS_PENDING` for SOL/BTC post-restart |
| **Residual risk** | LOW — the single runtime observation aligns with code expectation. But compound interaction with subsequent fixes is untested |
| **Status** | `RESOLVED_WITH_DETERMINISTIC_PROOF_ONLY` (runtime evidence partial, predates compound fix) |

### Blocker 2: Semantically empty portfolio snapshot seam

| Attribute | Value |
|-----------|-------|
| **Original problem** | Sidecar read `positionAmt`/`entryPrice` field names but PositionTracking emitted `net_position`/`avg_entry_price`. Missing symbols were silently overwritten with zero. `positions_last_ts_ms` was lost |
| **Cause** | Three-part contract mismatch between PositionTracking emission format and sidecar ingress parser |
| **Fix package** | `_normalize_portfolio_position_snapshot()` + `_missing_portfolio_position_snapshot()` + `_portfolio_snapshot_is_usable()` refactor |
| **Current proof level** | Code fix: YES. Deterministic tests: YES (19 tests). Runtime: NONE — fix was applied after the most recent runtime audit |
| **Residual risk** | MEDIUM — the normalization logic is straightforward, but the runtime interaction with actual Binance positions array has never been verified |
| **Status** | `IMPLEMENTED_BUT_NOT_PROVEN_IN_RUNTIME` |

### Blocker 3: Partial-update / `exp_ts` crash-before-sidecar-refresh seam

| Attribute | Value |
|-----------|-------|
| **Original problem** | `EPEventHandlers.on_order_fill()` wrote postfill reservation without `exp_ts`. On next portfolio event, `expire_stale()` raised `KeyError('exp_ts')`, crashing before sidecar portfolio refresh |
| **Cause** | `on_order_fill()` was a non-canonical writer that bypassed `ExposureGuard.record_postfill_hold()` |
| **Fix package** | Routed `on_order_fill()` through `ExposureGuard.record_postfill_hold()` as the SSOT writer |
| **Current proof level** | Code fix: YES. Deterministic tests: YES (22 tests with trace pipeline assertion). Runtime: NONE — fix was applied after the most recent runtime audit |
| **Residual risk** | LOW — the fix consolidates writers to a single canonical path. The trace pipeline test confirms both the crash path (before fix) and repair path (after fix) |
| **Status** | `IMPLEMENTED_BUT_NOT_PROVEN_IN_RUNTIME` |

### Blocker 4: Terminal WS bracket close truth / disappearance attribution

| Attribute | Value |
|-----------|-------|
| **Original problem** | Bracket child SL/TP orders were not registered in `OrderIndex`. When Binance sent `ORDER_TRADE_UPDATE FILLED` for SL, `binance_ws_client` dropped it as uncorrelated. `ManageFlowFSM` stayed stale. `PositionTracking` labeled the position disappearance as "manual intervention" |
| **Cause** | `BracketManager._register_bracket_results()` wrote to `correlation_store`, `order_guardian`, and `_symbol_brackets` but NOT to `OrderIndex`. WS ingress only read `OrderIndex` |
| **Fix package** | Two packages: (a) Guardian fallback recovery initially, then (b) root-cause write-side registration via `register_bracket_child()` in `OrderIndex` |
| **Current proof level** | Code fix: YES. Deterministic tests: YES (22 new + 5 updated + full ETH replay chain). Runtime: NONE — fix applied after most recent runtime audit |
| **Residual risk** | MEDIUM — `OrderIndex` is in-memory only; restart loses bracket registrations (pre-existing limitation for all order types). Out-of-order WS delivery before registration is mitigated by REST-synchronous placement boundary but not proven |
| **Status** | `IMPLEMENTED_BUT_NOT_PROVEN_IN_RUNTIME` |

### Blocker 5: False manual/external disappearance attribution seam

| Attribute | Value |
|-----------|-------|
| **Original problem** | `PositionTracking.on_account_update()` used set-difference disappearance detection with no ability to distinguish proven exchange bracket close from manual/external |
| **Cause** | No close-truth provenance was propagated from `ExecPosFSM` to `PositionTracking` |
| **Fix package** | `get_recent_terminal_close_proof()` on `ExecPosFSM` + attribution taxonomy in `PositionTracking` (`proven_exchange_bracket_close` vs `unknown_disappearance`) + downstream `_resolve_position_close_reason()` precedence |
| **Current proof level** | Code fix: YES. Deterministic tests: YES (2 targeted + 17 downstream close reason tests). Runtime: NONE |
| **Residual risk** | LOW — fail-closed design: unknown disappearances do NOT get `manual` label, they get `unknown_disappearance` |
| **Status** | `IMPLEMENTED_BUT_NOT_PROVEN_IN_RUNTIME` |

### Blocker 6: Sidecar suppression-only evaluation

| Attribute | Value |
|-----------|-------|
| **Original problem** | The sidecar has never reached the scoring/evaluation path at runtime. Every trigger event terminates at a suppression gate |
| **Cause** | Compound of blockers 1–3: lifecycle not active on fill → portfolio snapshot empty/wrong → portfolio stale. After grace expires, `portfolio_snapshot_missing_or_stale` blocks. After lifecycle fix, `portfolio_snapshot_missing_or_stale` remains dominant |
| **Fix package** | Compound of all fixes above. No single additional fix needed — the theory is that fixes 1–3 together remove the suppression chain |
| **Current proof level** | Code fix: YES (compound). Deterministic tests: YES (1 unit test exercises full chain with synthetic inputs). Runtime: **ZERO** SCORES/EVALUATED/RECOMMENDED/ACTION_SKIPPED rows have ever been written |
| **Residual risk** | HIGH — this is the remaining dominant gap. The compound fix has never been validated at runtime |
| **Status** | `UNRESOLVED` (at runtime level) |

---

## 5. What Is Genuinely Fixed

These are fixed at the code level with deterministic proof:

1. **Canonical fill ingress unification**: `_handle_canonical_fill_ingress()` routes all fill events through unified lifecycle activation (ManageFlowFSM, EPEventHandlers, sidecar). Confirmed working in one partial runtime window.

2. **Portfolio snapshot normalization**: Field aliasing (`net_position`→`positionAmt`), absent-symbol fail-closed (no zero overwrite), `positions_last_ts_ms` retention. 19 tests.

3. **Postfill reservation writer canonicalization**: Single SSOT writer `record_postfill_hold()` eliminates the `exp_ts` crash seam. 22 tests.

4. **Bracket child OrderIndex registration**: Write-side root cause closure. SL/TP bracket children registered in all three OrderIndex maps at placement time. 22 tests.

5. **Terminal close truth restoration**: Guardian-backed WS correlation + ManageFlowFSM flatten + close proof caching. Full ETH-shaped replay chain.

6. **Disappearance attribution taxonomy**: `proven_exchange_bracket_close` vs `unknown_disappearance` (fail-closed, no false `manual` label).

7. **Downstream close provenance**: `_resolve_position_close_reason()` preserves proven bracket close truth through POSITION_CLOSED and trade_lifecycle.on_close() writes.

8. **Sidecar contracts, config, logging**: 6 event schemas, strict Pydantic config, Phase-1 action scope guard, verb registry, domain_dict exports, forensic tooling.

---

## 6. What Is Only Test-Proven

Everything in Section 5 except item 1 (which has partial runtime evidence) is **test-proven only**. The critical distinction:

| Fix | Test Proof | Runtime Proof |
|-----|-----------|--------------|
| Canonical fill ingress | 2 tests | PARTIAL (1 runtime window, pre-compound) |
| Portfolio snapshot normalization | 19 tests | NONE |
| Postfill exp_ts writer fix | 22 tests | NONE |
| Bracket child OrderIndex registration | 22 tests | NONE |
| Terminal WS close truth restoration | 15 tests | NONE |
| Disappearance attribution | 2 tests | NONE |
| Downstream close provenance | 17 tests | NONE |
| Full sidecar SCORES→EVALUATED chain | 1 unit test (synthetic) | NONE |

---

## 7. What Is Still Open or Unproven

### 7.1 Critical: Sidecar has never reached SCORES at runtime

**This is the central unresolved gap.** After all fixes:
- 0 SCORES rows
- 0 EVALUATED rows
- 0 RECOMMENDED rows
- 0 ACTION_SKIPPED rows

The suppression chain theory is that blockers 1–3 (lifecycle + portfolio normalization + postfill crash) *together* prevented evaluation, and fixing all three should unblock. But this is an inference, not a fact. A fifth-layer blocker may exist.

### 7.2 Compound fix interaction untested at runtime

All four major fixes were applied incrementally. No runtime session has ever run with ALL fixes simultaneously. The only runtime audit with any fix was before the portfolio and postfill fixes.

### 7.3 OrderIndex restart hydration gap

`OrderIndex` is in-memory only. Bracket children registered before restart are lost. This means:
- If a restart occurs while a position has open brackets, the bracket child registrations are gone
- WS terminal events for those brackets will hit `OrderIndex` miss → fail-closed (ERROR log, no correlation)
- This is a pre-existing limitation for all order types, not introduced by the sidecar work

### 7.4 TradeLifecycleLogger durability gap

The lifecycle logger only flushes on terminal events. Intent, order, and fill data is memory-only. A restart between fill and close loses lifecycle rows. This is independent of the sidecar but affects operational forensics.

### 7.5 Timing window between fill and portfolio update

Even with all fixes, there is a structural timing window:
1. Fill arrives → ManageFlowFSM activates → `post_fill_grace_active` suppresses (expected)
2. Grace expires → sidecar checks portfolio → portfolio may still reflect pre-fill state if Binance is slow
3. If portfolio never updates with non-zero position during the lifecycle, evaluation never fires

This is not a bug but a structural constraint of the event-driven architecture. The sidecar cannot evaluate without a non-zero portfolio snapshot. If the position is opened and closed before the portfolio snapshot catches up, the sidecar will never evaluate that position.

---

## 8. Current Dominant Blocker

**The current dominant blocker is: No runtime evidence that the compound of all fixes produces sidecar SCORES.**

This is not a code bug. The code looks correct. The deterministic tests pass. But the phase-closure evidence gate requires runtime proof, not just code proof.

Specifically, the minimal evidence needed to close this gap is:

> One live restart session where at least one symbol produces at least one `POSITION_POLICY_SIDECAR_SCORES` row in `trade_lifecycle.jsonl`, demonstrating that:
> 1. Fill activates ManageFlowFSM (lifecycle gate passes)
> 2. Portfolio snapshot has non-zero `positionAmt` from normalized `net_position` (portfolio gate passes)
> 3. Portfolio freshness advances past the postfill crash seam (freshness gate passes)
> 4. Features and regime envelopes are fresh enough (feature/regime gates pass)
> 5. The suppression chain returns None → scoring fires → SCORES emitted

---

## 9. Phase-Closure Verdict

### Primary Verdict: `IMPLEMENTATION_PHASE_CLOSED_RUNTIME_PHASE_OPEN`

**Justification**:

The implementation work for Packages 1–4 is substantively complete:
- Package 1 (Contract/Config): DONE, production config loads correctly
- Package 2 (Shadow Sidecar Core): DONE, all suppression/evaluation logic implemented
- Package 3 (Forensic Logging): DONE, 6 event schemas, JSONL records, forensic tooling
- Package 4 (Shadow Validation): DONE for tooling, **BLOCKED** for evidence gate

The 4 sequentially discovered blockers (lifecycle activation, portfolio normalization, postfill crash, bracket OrderIndex) are all fixed in code with comprehensive deterministic proof (total: 100+ tests).

BUT: **Phase R3 ("Observability First") requires that the sidecar actually observes something beyond suppression**. The minimum R3 closure criterion is that the sidecar reaches evaluation (SCORES) for at least one live position. This has not happened.

Therefore:
- **Implementation phase**: CLOSED
- **Runtime evidence phase**: OPEN
- **R3 roadmap phase**: NOT YET CLOSABLE

### Secondary Note

The gap between implementation-closed and runtime-closed is narrow. All four identified blockers are fixed. The code path from fill→lifecycle→portfolio→evaluation is correct in deterministic testing. A single live restart session with the compound fix deployed is the only remaining gate. The probability that a fifth-layer blocker exists is non-zero but low, given the exhaustive blocker investigation chain.

---

## 10. Next Exact Step

**Deploy the current codebase with all four fixes to a live testnet session and collect one complete sidecar evaluation cycle.**

Success criteria for phase closure:
1. At least 1 `POSITION_POLICY_SIDECAR_SCORES` row in `trade_lifecycle.jsonl`
2. At least 1 `POSITION_POLICY_SIDECAR_EVALUATED` row
3. The validation tooling (`position_policy_sidecar_validation.py`) shows non-zero SCORES count
4. The suppression distribution shifts: `portfolio_snapshot_missing_or_stale` drops below 100% of non-grace suppression

Failure criteria (indicating fifth-layer blocker):
1. All rows remain SUPPRESSED after multiple fill→lifecycle cycles
2. New suppression reason appears that was not seen in prior audits
3. Portfolio snapshot normalization does not produce usable `positionAmt` from live Binance data

On success: Phase R3 can be honestly declared complete. Work transitions to R4 (Data Truth and Path Statistics Hardening).

On failure: The specific new suppression reason identifies the fifth-layer blocker for targeted fix.

---

## Appendix A: Validation Evidence Index

| Evidence | Location | Type |
|----------|----------|------|
| Roadmap SSOT | `ROI_GATED_POSITION_LIFECYCLE_POLICY_ROADMAP_v1.md` | Governance |
| Package 1 report | `artifacts/position_policy_sidecar/package1_contract_and_config_report.md` | Implementation |
| Package 2 report | `artifacts/position_policy_sidecar/package2_shadow_sidecar_core_report.md` | Implementation |
| Package 3 report | `artifacts/position_policy_sidecar/package3_forensic_logging_report.md` | Implementation |
| Package 4 tooling report | `artifacts/position_policy_sidecar/package4_validation_tooling_report.md` | Implementation |
| Package 4 validation JSON | `artifacts/position_policy_sidecar/package4_validation_summary.json` | Runtime evidence |
| Portfolio snapshot fix | `reports/PKG_POSITION_POLICY_SIDECAR_PORTFOLIO_SNAPSHOT_CONTRACT_FIX_REPORT.md` | Implementation |
| Post-fill portfolio gate audit | `reports/PKG_POSITION_POLICY_SIDECAR_POST_FILL_PORTFOLIO_GATE_AUDIT.md` | Runtime forensic |
| Post-fix restart audit | `reports/PKG_POSITION_POLICY_SIDECAR_POST_FIX_RESTART_RUNTIME_AUDIT_REPORT.md` | Runtime evidence |
| Post-restart runtime audit | `reports/PKG_POSITION_POLICY_SIDECAR_POST_RESTART_RUNTIME_AUDIT_REPORT.md` | Runtime evidence |
| Temporal lifecycle chokepoint | `reports/PKG_POSITION_POLICY_SIDECAR_TEMPORAL_LIFECYCLE_CHOKEPOINT_AUDIT.md` | Code forensic |
| Partial-update proof package | `reports/PKG_PORTFOLIO_EVENT_PARTIAL_UPDATE_SIDECAR_REFRESH_PROOF_PACKAGE.md` | Deterministic proof |
| Postfill exp_ts fix | `reports/PKG_POSTFILL_RESERVATION_EXP_TS_AND_SIDECAR_REFRESH_FIX.md` | Implementation |
| Terminal WS close truth | `reports/PKG_EXECUTION_POSITION_TERMINAL_WS_CORRELATION_AND_CLOSE_TRUTH_RESTORATION_FIX.md` | Implementation |
| ETH terminal forensic | `reports/PKG_ETH_TERMINAL_MECHANISM_FORENSIC_BY_BRACKET_IDS_AND_EXCHANGE_SIDE_PATH.md` | Runtime forensic |
| SOL/ETH close cause forensic | `reports/PKG_POST_RESTART_SOL_ETH_CLOSE_CAUSE_FORENSIC.md` | Runtime forensic |
| Bracket child OrderIndex fix | `reports/PKG_BRACKET_CHILD_ORDERINDEX_CANONICAL_REGISTRATION_REPORT.md` | Implementation |
| Close correlation hardening | `reports/BRACKET_CLOSE_CORRELATION_HARDENING_FOR_FALSE_MANUAL_CLOSE_ELIMINATION.md` | Implementation |
| Sidecar core implementation | `apps/reference/domains/execution_position/position_policy_sidecar.py` | Code |
| FSM fill ingress | `apps/reference/domains/execution_position/fsm.py:1767` (`_handle_canonical_fill_ingress`) | Code |
| Event handlers postfill | `apps/reference/domains/execution_position/event_handlers.py:760` (`record_postfill_hold`) | Code |
| Bracket manager registration | `apps/reference/domains/execution_position/bracket_manager.py:212-243` | Code |
| OrderIndex bracket child | `apps/reference/domains/execution_position/order_index.py:160` | Code |
| Exposure guard canonical writer | `apps/reference/domains/execution_position/exposure_guard.py` (`record_postfill_hold`) | Code |
| Sidecar unit tests | `tests/domains/execution_position/test_position_policy_sidecar.py` (14 tests) | Test |
| Portfolio partial-update tests | `tests/domains/execution_position/test_portfolio_event_partial_update_sidecar_trace.py` (2 tests) | Test |
| Terminal WS tests | `tests/domains/execution_position/test_terminal_ws_close_truth_*.py` (2 tests) | Test |
| Fill ingress tests | `tests/domains/execution_position/test_canonical_fill_ingress_activation.py` (2 tests) | Test |
| Sidecar contract tests | `tests/contracts/test_position_policy_sidecar_contracts.py` (2 tests) | Test |
| Config contract tests | `tests/config/test_position_policy_sidecar_config_contract.py` (6 tests) | Test |
| Validation tooling tests | `tests/tools/test_position_policy_sidecar_validation.py` (3 tests) | Test |
| Disappearance attribution tests | `tests/domains/position_tracking/test_terminal_close_disappearance_attribution.py` (2 tests) | Test |

## Appendix B: Proof Level Definitions Used

| Level | Meaning |
|-------|---------|
| **Code fix** | The code change exists on the current branch |
| **Deterministic proof** | Pytest with constructed inputs exercises the fixed path and asserts correct behavior |
| **Runtime evidence** | Live exchange session produced observable artifacts (JSONL rows, log entries, shadow journal records) confirming the fix works in production |
| **Phase-closure evidence** | Runtime evidence that satisfies the roadmap phase's exit criteria |

---

*End of audit.*
