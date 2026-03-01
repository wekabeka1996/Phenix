# TODO

## EP-H2-SAFE-EXIT-DEGRADE follow-up (2026-03-01)
- [ ] Update strategy YAML profiles to explicitly define `execution.exit_order_type`, `execution.exit_tif`, `execution.exit_limit_ttl_ms` where needed.

## VF-VERB-REG follow-ups
- VF-VERB-REG-02: periodically review `reports/VF-VERB-REG-02_diff.json` in CI logs and keep registry in sync with runtime.
- VF-VERB-REG-02: switch from warn-only to fail when coverage is ~100% (planned: warn-only Ã¢â€ â€™ shadow-deny Ã¢â€ â€™ hard-deny).
- VF-VERB-REG-03: continue replacing `owner: unknown` with real domain owners; add schemas where there is a confirmed JSON schema.
- VF-VERB-REG-04: use `reports/VF-VERB-REG-04_owner_suggestions.json` to batch-update owners with evidence (no guesses).
- VF-VERB-REG-05: gate now fails only when coverage Ã¢â€°Â¥98% and missing>0; keep an eye on the threshold and adjust when registry matures.
- VF-VERB-REG-06: applied all owner suggestions with confidence Ã¢â€°Â¥70%; next is to rerun VF-VERB-REG-04 regularly and batch-apply new high-confidence suggestions.
- VF-VERB-REG: decide SSOT policy for wildcards (keep default false; `UPD` currently allowed by policy).

## SOLUSDT / Aurora follow-ups (2026-02-13 forensic)
- Decide: disable FLIP for `SOLUSDT` vs restrict regimes (`UNCERTAIN`/`HIGH_VOLATILITY`) for entries.
- Adjust SOL exit RR guardrails: `take_profit.tp_low_ratio` and/or `exit.regime_tpsl.min_tp_rr`; re-run a short live-sim/backtest.
- Fix `NRR-046` flip CLOSE rejects: audit `execution_position.pending_entry_ttl` expectations for tf_sec=0/None and pick a safe TTL policy.
- Reduce `MAKER_ONLY_REJECT` frequency: tune `aurora.assets.SOLUSDT.volatility_entry_logic.regime_multipliers` and/or revisit `aurora.execution.entry_tif`.
- Add a grep/script to surface bracket fill/close events (SL/TP) for postmortems (WAL currently shows closure via ACCOUNT_UPDATE only).

## SOL follow-ups after TASK-SOL-REGIME-BLOCK-01 / TASK-SOL-SL-TIGHTEN-01 (2026-02-13)
- Regime gate is now strict for SOL (`UNCERTAIN` removed). Monitor live WAL for drop in `SOLUSDT` intents during `UNCERTAIN`.
- Keep `sl_pct=0.0135` for 1-2 sessions and compare stop-hit rate vs prior baseline (`0.01512`).
- Sizing verdict recorded: `REGIME-AWARE SIZING = YES` in DecisionMaking via `regime_sizing -> margin_pct_mult`.
- Decide if to add explicit `SOLUSDT.regime_sizing.DEFAULT` and/or `UNCERTAIN: 0.0` (or keep only allowlist gating).
- Optional next package (separate commit): additive `notional_mult_by_regime` schema/model/tests if we want deterministic per-regime size policy.

## EP-ORDER-PRECISION-1111 (2026-02-24 forensic: bracket stopPrice precision violation)

**Root cause confirmed:** `add_safety_offset()` result not re-quantized after arithmetic in `_place_brackets()` Ã¢â€ â€™ `stopPrice` violates `tick_size` Ã¢â€ â€™ Binance -1111. Positions left without SL/TP protection.

**Status: CLOSED 2026-02-24** Ã¢â‚¬â€ fixes merged, 37/37 tests pass, zero regressions.

**Full context:** `docs/forensics/EP_PRECISION_1111_CONTEXT.md`

Implementation package items:

- [x] **EP-ORDER-PRECISION-1111-FIX-A**: `fsm_manage.py:_place_brackets()` Ã¢â‚¬â€ re-quantize `sl_price`/`tp1_price`/`tp2_price` after offset arithmetic (lines 699Ã¢â‚¬â€œ710). Primary root-cause fix.
- [x] **EP-ORDER-PRECISION-1111-FIX-B**: `fsm.py:_place_deferred_brackets()` Ã¢â‚¬â€ defensive re-quantize `sl`/`tp` before adapter calls (lines 4809Ã¢â‚¬â€œ4813). Guards WAL replay edge cases.
- [x] **EP-ORDER-PRECISION-1111-TEST**: 17 regression tests in `tests/domains/execution_position/test_ep_precision_1111.py` (classes AÃ¢â‚¬â€œD); all pass.
- [x] **EP-ORDER-PRECISION-1111-FAIL-CLOSED**: `fsm.py:_place_deferred_brackets()` Ã¢â‚¬â€ skip TP if SL failed (lines 4843Ã¢â‚¬â€œ4851). Fail-closed guard prevents unprotected-position scenario.
- [ ] **EP-ORDER-PRECISION-1111-GUARD** _(optional, defense-in-depth)_: Add precision assertion in `BinanceAdapter.place_stop_market_close_position()` to raise `PrecisionViolationError` before sending to Binance.
- [ ] Verify ETHUSDT is not currently affected (no -1111 in logs) but is theoretically vulnerable; add parametrized test case for ETHUSDT.

## EP-ORDER-MISSING-STOPPRICE-1102 (2026-02-24 forensic: TP stopPrice/triggerPrice missing)

**Root cause confirmed:** `DEC:PLACE_ORDER` for `TAKE_PROFIT_MARKET` executed with `stopPrice=None` (observed as `... @ None/None`), then forwarded to Binance where `stopPrice` (or Algo fallback `triggerPrice`) is mandatory Ã¢â€ â€™ `-1102`.

**Status: CLOSED 2026-02-24** Ã¢â‚¬â€ fail-closed preflight + emission guard + adapter P1 guard implemented. 36 regression tests pass, 0 regressions in execution_position suite.

**Full context:** `docs/forensics/EP_MISSING_STOPPRICE_1102_CONTEXT.md`

- [x] **EP-ORDER-MISSING-STOPPRICE-1102**: Fail-closed preflight + emission guard + adapter P1 guard implemented. 36 regression tests added. **CLOSED 2026-02-24**.

## EP-IDEMPOTENT-CANCEL-2011 (2026-02-24)

- [ ] **EP-IDEMPOTENT-CANCEL-2011**: P0 implemented (absorb `-2011/-2013` exception-path + truthful `_do_cancel` logging/watchdog gating), close after merge.
- [ ] **EP-IDEMPOTENT-CANCEL-2011-P1**: optional in-flight cancel dedup (`_pending_cancel_tasks`) in separate package.

## EP-01.3 Supersede Cancel Timeout (2026-02-24 forensic)

**Status: PARTIALLY AUDITED - fill-race audit complete (UNGUARDED); remaining audits pending**
**Full context:** `docs/forensics/EP_SUPERSEDE_CANCEL_TIMEOUT_CONTEXT.md`

**Root cause confirmed:** `_do_cancel()` closure (`fsm.py:1084`) never calls `_process_queued_supersede()`.
WS-event path (`_handle_cancel_event`, `fsm.py:4410`) exists but silently aborts when watchdog not
fully cleared. 5s timeout (`supersede_cancel_timeout_sec`) is the only reliable execution path.

**CRITICAL Ã¢â‚¬â€ Audit required before implementation:**

- [x] **EP-01.3-RISK-AUDIT-FILL-RACE (CRITICAL):** Trace `_async_execute_decision()` Ã¢â€ â€™ DEC:OPEN handler
  path when old entry was FILLED (not cancelled). Confirm ExposureGuard or position guard blocks
  opening a new position when one is already open. This is the double-position risk scenario
  (observed case: BTCUSDT 09:25, order 12515510665 FILLED before cancel timeout).
  File: `fsm.py` DEC:OPEN handler above line 2732.
  Audit doc: `docs/forensics/EP_SUPERSEDE_FILL_RACE_GUARD_AUDIT.md` (verdict: UNGUARDED).

- [ ] **EP-01.3-RISK-AUDIT-CANCEL-LOOP (HIGH):** Map the cancel-failure Ã¢â€ â€™ supersede re-queue loop.
  Verify `IdempotentCancelHelper.max_retries: 2` terminates the cycle. Determine if a perpetually
  failing cancel reaches an escape condition or loops indefinitely.

- [ ] **EP-01.3-RISK-AUDIT-WS-ROUTING (MEDIUM):** Identify what verb/op routes to `_handle_cancel_event()`.
  Verify it is triggered by WS fill/cancel notifications, not only by internal messages.
  Confirm gap for PRE_CHECK_TERMINAL_FILLED case (no REST cancel Ã¢â€ â€™ no cancel event Ã¢â€ â€™ WS path skipped).

**Implementation items (BLOCKED until audits above complete):**

- [ ] **EP-01.3-FIX-OPTION-A:** Add `_process_queued_supersede(symbol)` callback in `_do_cancel()`
  after successful `watchdog.on_order_cancel()` (`fsm.py:1099/1119/1128`). Eliminates 5s delay
  for cancel-success case.

- [ ] **EP-01.3-FIX-FILL-RACE-GUARD:** In DEC:OPEN handler / `_async_execute_decision()`, before
  opening: check if position already open for symbol Ã¢â€ â€™ abort with `EP-01.3: supersede aborted,
  position already open`. Required regardless of fix option chosen.

- [ ] **EP-01.3-SUPERSEDE-FILL-RACE-GUARD-P0:** Implemented in package `EP-01.3-SUPERSEDE-FILL-RACE-GUARD-P0`; close only after merge.

- [ ] **EP-01.3-TESTS:** Add regression tests:
  - Cancel success Ã¢â€ â€™ `_handle_cancel_event()` before timeout (timeout task cancelled)
  - Fill race Ã¢â€ â€™ timeout fires Ã¢â€ â€™ ExposureGuard blocks double open
  - Cancel failure Ã¢â€ â€™ bounded retry loop (no infinite cycle)
  - Duplicate supersede ack (timeout + WS both arrive) Ã¢â€ â€™ idempotent `_process_queued_supersede()`


## EP Brackets After Fill Review Follow-ups (2026-02-25)

- [ ] **EP-BRACKET-RECOVERY-TWO-PHASE-CLEAR (P0):** Do not clear `_pending_brackets`/WAL before confirmed bracket protection state; introduce recover-in-progress semantics and retry-safe consumption.
- [ ] **EP-BRACKET-NAKED-POSITION-POLICY (P0):** Add hard policy for `FILLED_ENTRY_WITHOUT_BRACKETS` with `missing_count=2` (symbol halt and/or emergency close, bounded retries).
- [ ] **EP-BRACKET-DEDUP-SLOT-AWARE (P1):** Extend dedup key to support multi-TP slots (`TP1`/`TP2`) so TP2 is not blocked by TP1.
- [ ] **EP-BRACKET-INFLIGHT-FINALLY (P1):** Guarantee claim release on all failure/cancellation paths (`try/finally`) to avoid stuck dedup inflight keys.
- [ ] **EP-BRACKET-GUARDRAIL-PATH-PARITY (P1):** Emit `FILLED_ENTRY_WITHOUT_BRACKETS` for `PLACE_ORDER` path failures, not only deferred path.
- [ ] **EP-BRACKET-STARTUP-IDEMPOTENCE (P2):** Startup reconcile must detect already-existing SL/TP before placement and avoid duplicate `-4130` attempts.
- [ ] **EP-BRACKET-WS-LATE-CANCEL-RECOVERY (P1):** Make `_handle_cancel_event` fill-aware to avoid dropping deferred brackets on late partial-fill cancel events.
- [ ] **EP-EXEC-ORCH-SSOT-PLAN (P1):** Start phased deduplication/refactor per `docs/reviews/AUDIT_EXECUTION_MANAGER_DUPLICATION.md` (stopPrice, qty policy, bracket coordinator, idempotent cancel semantics).
