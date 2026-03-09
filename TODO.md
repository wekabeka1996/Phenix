# TODO

## FORENSIC-AUDIT advanced stale cancel follow-up (2026-03-06)
- [ ] Remove Gate 1 fallback path for advanced stale cancel and require per-order `cancelable_regimes` derivation from `allowed_regimes` on every placed LIMIT entry. Goal: no runtime-side namespace fallback, fully order-local invalidation semantics.
- [ ] Sweep legacy DecisionMaking tests that still inject `BULL_TREND/BEAR_TREND` and convert them to canonical `TREND_UP/TREND_DOWN` so test expectations match `EVT:REGIME_DETECTED` SSOT.

## PKG-ABSORPTION-RISK-FULL (2026-03-04) âœ“ CLOSED
- [x] Pydantic schema extended: `absorption_penalty_source`, `absorption_feature_clip_min/max`, `absorption_feature` weight.
- [x] `risk_management.py`: source-routed feature_term + explainability `risk_terms` dict.
- [x] `domains.yaml`: `absorption.mode=full`, `absorption_penalty_source=feature`, `absorption_feature=0.2`.
- [x] Tests: 7 new tests + existing proxy fixture pinned for config independence.
- [x] ConfigLoader validates new keys without extra-field violation.
- [ ] **Follow-up:** Calibrate `max_risk_score` per symbol via live risk_score distribution at `absorption_feature=0.2`.
  Run Nâ‰¥500 events â†’ percentile analysis â†’ adjust per-symbol `max_risk_score` override if tails exceed current 0.96 ceiling.

## PKG-CALIB-APPLY (2026-03-03)
- [x] BTCUSDT re-enabled in Aurora (strategies.yaml: aurora assignment).
- [x] Signal weights calibrated (ridge 70/30) and applied for BTCUSDT + SOLUSDT.
- [x] Regime calibration run for BTC (nogate run: 45/300 valid) and SOL (1/300 valid).
- [x] Regime overlays NOT applied: BTC global config cannot be safely applied per-symbol; SOL test macro_f1 degraded.
- [ ] PKG-CALIB-APPLY follow-up: Expand calibration window to 60+ days to improve regime oracle coverage (current 23 days is too short for stable trend detection).
- [ ] PKG-CALIB-APPLY follow-up: Implement per-symbol regime config section to allow applying SOL/BTC-specific overlays without clobbering global params.
- [ ] PKG-CALIB-APPLY follow-up: Re-evaluate macro_resid/ema_bias sign reversals after calibrating over a trend-rich period.


## PKG-RG-CALIBRATE (2026-03-03)
- [x] Implement regime parameter calibrator tool with walk-forward split and hard-gates.
- [x] BUG-1: Fix metrics.py SyntaxError (literal newline in string) + invalid escape.
- [x] BUG-2: Fix Message(src=,dst=) missing required fields in evaluate_overlay.
- [x] BUG-3: Fix passes_gates coverage loop (pass -> return False). Tests added.
- [x] TEST-LEAKAGE: Fix search.py main() - best selected by score_train, not score_test.
- [ ] PKG-RG-CALIBRATE follow-up: tune default --max-churn-per-1000 threshold (50.0 is tighter than baseline churn ~51; consider 150-200 as a realistic default gate).

## EP-WATCHDOG-POLLING-DEFERRED-BRACKETS-TIMEOUT-ISOLATION follow-up (2026-03-01)
- [ ] Add shared helper fixture for execution_position async tests to disable background loops consistently (`bracket_health_check`, optional orphan monitor).

## EP-H1.1-ALPHA_SEARCH-SYMBOL-PLUMBING follow-up (2026-03-01)
- [ ] Add explicit contract test that distinguishes ensemble skip behavior from non-ensemble fail-closed emission on missing required features.

## EP-INT-FLIP-VERTICAL-QTY-FIXTURE follow-up (2026-03-01)
- [ ] Audit other DM integration monkeypatches of `_propose_trade_intent` to ensure they return non-`None` when simulating successful proposal.

## EP-H2-SAFE-EXIT-DEGRADE follow-up (2026-03-01)
- [ ] Update strategy YAML profiles to explicitly define `execution.exit_order_type`, `execution.exit_tif`, `execution.exit_limit_ttl_ms` where needed.

## EP-H4-WATCHDOG-CONFIG-HARDENING follow-up (2026-03-01)
- [ ] Audit non-test callsites to ensure any future `OrderTimeoutWatchdog(config=...)` usage passes a mapping contract explicitly.

## EP-H1-ALPHA_SEARCH-MANIFEST follow-up (2026-03-01)
- [ ] Optional: evaluate adding `EVT:FEATURE_LINEAGE_BROKEN` for alpha_search feature wiring forensics.

## VF-VERB-REG follow-ups
- VF-VERB-REG-02: periodically review `reports/VF-VERB-REG-02_diff.json` in CI logs and keep registry in sync with runtime.
- VF-VERB-REG-02: switch from warn-only to fail when coverage is ~100% (planned: warn-only ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ shadow-deny ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ hard-deny).
- VF-VERB-REG-03: continue replacing `owner: unknown` with real domain owners; add schemas where there is a confirmed JSON schema.
- VF-VERB-REG-04: use `reports/VF-VERB-REG-04_owner_suggestions.json` to batch-update owners with evidence (no guesses).
- VF-VERB-REG-05: gate now fails only when coverage ÃƒÂ¢Ã¢â‚¬Â°Ã‚Â¥98% and missing>0; keep an eye on the threshold and adjust when registry matures.
- VF-VERB-REG-06: applied all owner suggestions with confidence ÃƒÂ¢Ã¢â‚¬Â°Ã‚Â¥70%; next is to rerun VF-VERB-REG-04 regularly and batch-apply new high-confidence suggestions.
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

**Root cause confirmed:** `add_safety_offset()` result not re-quantized after arithmetic in `_place_brackets()` ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ `stopPrice` violates `tick_size` ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ Binance -1111. Positions left without SL/TP protection.

**Status: CLOSED 2026-02-24** ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â fixes merged, 37/37 tests pass, zero regressions.

**Full context:** `docs/forensics/EP_PRECISION_1111_CONTEXT.md`

Implementation package items:

- [x] **EP-ORDER-PRECISION-1111-FIX-A**: `fsm_manage.py:_place_brackets()` ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â re-quantize `sl_price`/`tp1_price`/`tp2_price` after offset arithmetic (lines 699ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“710). Primary root-cause fix.
- [x] **EP-ORDER-PRECISION-1111-FIX-B**: `fsm.py:_place_deferred_brackets()` ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â defensive re-quantize `sl`/`tp` before adapter calls (lines 4809ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“4813). Guards WAL replay edge cases.
- [x] **EP-ORDER-PRECISION-1111-TEST**: 17 regression tests in `tests/domains/execution_position/test_ep_precision_1111.py` (classes AÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“D); all pass.
- [x] **EP-ORDER-PRECISION-1111-FAIL-CLOSED**: `fsm.py:_place_deferred_brackets()` ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â skip TP if SL failed (lines 4843ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“4851). Fail-closed guard prevents unprotected-position scenario.
- [ ] **EP-ORDER-PRECISION-1111-GUARD** _(optional, defense-in-depth)_: Add precision assertion in `BinanceAdapter.place_stop_market_close_position()` to raise `PrecisionViolationError` before sending to Binance.
- [ ] Verify ETHUSDT is not currently affected (no -1111 in logs) but is theoretically vulnerable; add parametrized test case for ETHUSDT.

## EP-ORDER-MISSING-STOPPRICE-1102 (2026-02-24 forensic: TP stopPrice/triggerPrice missing)

**Root cause confirmed:** `DEC:PLACE_ORDER` for `TAKE_PROFIT_MARKET` executed with `stopPrice=None` (observed as `... @ None/None`), then forwarded to Binance where `stopPrice` (or Algo fallback `triggerPrice`) is mandatory ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ `-1102`.

**Status: CLOSED 2026-02-24** ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â fail-closed preflight + emission guard + adapter P1 guard implemented. 36 regression tests pass, 0 regressions in execution_position suite.

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

**CRITICAL ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Audit required before implementation:**

- [x] **EP-01.3-RISK-AUDIT-FILL-RACE (CRITICAL):** Trace `_async_execute_decision()` ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ DEC:OPEN handler
  path when old entry was FILLED (not cancelled). Confirm ExposureGuard or position guard blocks
  opening a new position when one is already open. This is the double-position risk scenario
  (observed case: BTCUSDT 09:25, order 12515510665 FILLED before cancel timeout).
  File: `fsm.py` DEC:OPEN handler above line 2732.
  Audit doc: `docs/forensics/EP_SUPERSEDE_FILL_RACE_GUARD_AUDIT.md` (verdict: UNGUARDED).

- [ ] **EP-01.3-RISK-AUDIT-CANCEL-LOOP (HIGH):** Map the cancel-failure ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ supersede re-queue loop.
  Verify `IdempotentCancelHelper.max_retries: 2` terminates the cycle. Determine if a perpetually
  failing cancel reaches an escape condition or loops indefinitely.

- [ ] **EP-01.3-RISK-AUDIT-WS-ROUTING (MEDIUM):** Identify what verb/op routes to `_handle_cancel_event()`.
  Verify it is triggered by WS fill/cancel notifications, not only by internal messages.
  Confirm gap for PRE_CHECK_TERMINAL_FILLED case (no REST cancel ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ no cancel event ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ WS path skipped).

**Implementation items (BLOCKED until audits above complete):**

- [ ] **EP-01.3-FIX-OPTION-A:** Add `_process_queued_supersede(symbol)` callback in `_do_cancel()`
  after successful `watchdog.on_order_cancel()` (`fsm.py:1099/1119/1128`). Eliminates 5s delay
  for cancel-success case.

- [ ] **EP-01.3-FIX-FILL-RACE-GUARD:** In DEC:OPEN handler / `_async_execute_decision()`, before
  opening: check if position already open for symbol ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ abort with `EP-01.3: supersede aborted,
  position already open`. Required regardless of fix option chosen.

- [ ] **EP-01.3-SUPERSEDE-FILL-RACE-GUARD-P0:** Implemented in package `EP-01.3-SUPERSEDE-FILL-RACE-GUARD-P0`; close only after merge.

- [ ] **EP-01.3-TESTS:** Add regression tests:
  - Cancel success ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ `_handle_cancel_event()` before timeout (timeout task cancelled)
  - Fill race ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ timeout fires ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ ExposureGuard blocks double open
  - Cancel failure ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ bounded retry loop (no infinite cycle)
  - Duplicate supersede ack (timeout + WS both arrive) ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ idempotent `_process_queued_supersede()`


## EP Brackets After Fill Review Follow-ups (2026-02-25)

- [ ] **EP-BRACKET-RECOVERY-TWO-PHASE-CLEAR (P0):** Do not clear `_pending_brackets`/WAL before confirmed bracket protection state; introduce recover-in-progress semantics and retry-safe consumption.
- [ ] **EP-BRACKET-NAKED-POSITION-POLICY (P0):** Add hard policy for `FILLED_ENTRY_WITHOUT_BRACKETS` with `missing_count=2` (symbol halt and/or emergency close, bounded retries).
- [ ] **EP-BRACKET-DEDUP-SLOT-AWARE (P1):** Extend dedup key to support multi-TP slots (`TP1`/`TP2`) so TP2 is not blocked by TP1.
- [ ] **EP-BRACKET-INFLIGHT-FINALLY (P1):** Guarantee claim release on all failure/cancellation paths (`try/finally`) to avoid stuck dedup inflight keys.
- [ ] **EP-BRACKET-GUARDRAIL-PATH-PARITY (P1):** Emit `FILLED_ENTRY_WITHOUT_BRACKETS` for `PLACE_ORDER` path failures, not only deferred path.
- [ ] **EP-BRACKET-STARTUP-IDEMPOTENCE (P2):** Startup reconcile must detect already-existing SL/TP before placement and avoid duplicate `-4130` attempts.
- [ ] **EP-BRACKET-WS-LATE-CANCEL-RECOVERY (P1):** Make `_handle_cancel_event` fill-aware to avoid dropping deferred brackets on late partial-fill cancel events.
- [ ] **EP-EXEC-ORCH-SSOT-PLAN (P1):** Start phased deduplication/refactor per `docs/reviews/AUDIT_EXECUTION_MANAGER_DUPLICATION.md` (stopPrice, qty policy, bracket coordinator, idempotent cancel semantics).

[2026-03-07 14:03:00 +02:00] | [Objective: UNCERTAIN + LOW_VOLATILITY forensic audit] | [Artifacts: reports/aurora_regime_forensic_uncertain_low_vol_2026-03-07.md; reports/aurora_forensic_report_2026-03-06_2026-03-07.md; reports/aurora_forensic_2026-03-06_2026-03-07_trades.csv; reports/aurora_forensic_2026-03-06_2026-03-07_summary.json] | [Decision: UNCERTAIN hard no-trade = YES; LOW_VOLATILITY = KEEP BUT NARROW SYMBOL SET; next-run NO-GO unless UNCERTAIN enforcement and aurora LOW_VOL narrowing are hard-enforced] | [Open Questions: Why BTC/SOL aurora traded UNCERTAIN despite YAML bans; why ETH aurora traded LOW_VOL with sizing=0.0; why XRP ran mean_reversion and SOL received md_amr intent against strategies registry; whether MR external LOW_VOL should be unified with FLAT_* taxonomy]

[2026-03-07 17:33:20 +02:00] | [Objective: final pre-launch synthesis] | [Artifacts: reports/aurora_final_prelaunch_decision_pack_2026-03-07.md; reports/aurora_forensic_report_2026-03-06_2026-03-07.md; reports/aurora_regime_forensic_uncertain_low_vol_2026-03-07.md; config/aurora/strategies.yaml; config/aurora/strategies/mean_reversion.yaml; config/aurora/strategies/md_amr.yaml] | [Decision: launch state = NOT READY; aurora = enable with restrictions; mean_reversion = enable with restrictions only after 300s revert on DOGE, otherwise shadow only; md_amr = shadow only; UNCERTAIN = disable; LOW_VOLATILITY = BTC-only for aurora] | [Residual Risks: UNCERTAIN runtime enforcement not yet verified; symbol-level mutex/arbitration remains P0; BNBUSDT assigned to md_amr without explicit md_amr asset block or direct md_amr BNB lifecycle evidence; WAL close attribution is still too imprecise]

## FORENSIC-AUDIT mean_reversion / md_amr follow-up (2026-03-07)
- [x] Complete evidence-only live audit for `mean_reversion` and `md_amr` using reports, WAL, logs, and current strategy YAMLs.
- [x] Record next-run containment verdict: `DOGEUSDT -> mean_reversion` = cautious yes; immediate MR move to `5m` = no direct production change from current evidence; `md_amr` = active but blocked.
- [ ] Shadow-validate `mean_reversion` on `300s` bars versus current `180s` using the same symbols/window before any production timeframe switch.
- [ ] Reconcile `strategies.yaml` vs `md_amr.yaml` for `BNBUSDT` ownership/support before allowing `BNBUSDT -> md_amr` in a live launch.
- [ ] Audit why md_amr live-window intents were arbitration-blocked on BTC/ETH/SOL while current registry assignment is `XRPUSDT/BNBUSDT`.
[2026-03-07 23:08:32 UTC] | [Objective: Active trade snapshot audit] | [Artifacts: reports/auto/active_positions_snapshot_latest.md; reports/auto/active_positions_snapshot_20260307_230832.md; reports/auto/active_positions_snapshot_20260307_230832.json; reports/auto/trade_lifecycle_ledger.jsonl; reports/auto/anomalies_register_latest.md] | [Findings: active=3 pending=57 anomalies=63; major=stale pending bracket telemetry and symbol-busy conflicts on active books] | [Open Questions: exchange-open order snapshot unavailable; some lifecycle entry timestamps inferred from account updates]

[2026-03-08 03:06:55 UTC] | [Objective: Active trade snapshot audit] | [Artifacts: reports/auto/active_positions_snapshot_latest.md; reports/auto/active_positions_snapshot_20260308_030655.md; reports/auto/active_positions_snapshot_20260308_030655.json; reports/auto/trade_lifecycle_ledger.jsonl; reports/auto/anomalies_register_latest.md] | [Findings: active=1 pending=0 anomalies=1; SOLUSDT short lifecycle remains open with symbol-busy conflict telemetry] | [Open Questions: WAL has no explicit ORDER_FILLED event for the current SOL lifecycle; entry inferred from PENDING_BRACKETS_CLEARED(reason=filled)+account updates]
[2026-03-08T07:08:12.0882787Z] | [Objective: Active trade snapshot audit] | [Artifacts: reports/auto/active_positions_snapshot_latest.md] | [Findings: validate inferred fill linkage for ENTRY-7c7e117c57a1 and ENTRY-53f78f0d0216] | [Open Questions: should explicit strategy-owner tag be emitted on all lifecycle events?]
[2026-03-08T11:04:59.733386Z] | [Objective: Active trade snapshot audit] | [Artifacts: reports/auto/active_positions_snapshot_latest.md; reports/auto/active_positions_snapshot_20260308_110459.md; reports/auto/active_positions_snapshot_20260308_110459.json; reports/auto/trade_lifecycle_ledger.jsonl; reports/auto/anomalies_register_latest.md] | [Findings: active=0, pending=0, anomalies=0] | [Open Questions: stale symbol-busy persists after flat account updates]
[2026-03-08T11:06:48.245102Z] | [Objective: Active trade snapshot audit] | [Artifacts: reports/auto/active_positions_snapshot_latest.md; reports/auto/active_positions_snapshot_20260308_110648.md; reports/auto/active_positions_snapshot_20260308_110648.json; reports/auto/trade_lifecycle_ledger.jsonl; reports/auto/anomalies_register_latest.md] | [Findings: active=0, pending=0, anomalies=1] | [Open Questions: stale symbol-busy after flat account updates]
[2026-03-08T15:05:10.230486Z] | [Objective: Active trade snapshot audit] | [Artifacts: reports/auto/active_positions_snapshot_latest.md; reports/auto/active_positions_snapshot_20260308_150510.md; reports/auto/active_positions_snapshot_20260308_150510.json; reports/auto/trade_lifecycle_ledger.jsonl; reports/auto/anomalies_register_latest.md] | [Findings: active=3, pending=4, anomalies=2] | [Open Questions: validate runtime-effective mean_reversion enablement for XRPUSDT/BNBUSDT ownership alignment]
[2026-03-08T19:04:18.247000Z] | [Objective: Active trade snapshot audit] | [Artifacts: reports/auto/active_positions_snapshot_latest.md; reports/auto/active_positions_snapshot_20260308_190418.md; reports/auto/active_positions_snapshot_20260308_190418.json; reports/auto/trade_lifecycle_ledger.jsonl; reports/auto/anomalies_register_latest.md] | [Findings: active=5, pending=0, anomalies=4] | [Open Questions: Confirm runtime-effective strategy ownership for md_amr symbols and unresolved bracket close telemetry for legacy aurora lifecycles.]

[2026-03-08T23:05:04.778158Z] | [Objective: Active trade snapshot audit] | [Artifacts: reports/auto/active_positions_snapshot_latest.md; reports/auto/active_positions_snapshot_20260308_230504.md; reports/auto/active_positions_snapshot_20260308_230504.json; reports/auto/trade_lifecycle_ledger.jsonl; reports/auto/anomalies_register_latest.md] | [Findings: active=2 pending=1 anomalies=2; active symbols=ETHUSDT,DOGEUSDT] | [Open Questions: DOGEUSDT fill transition has no explicit ORDER_FILLED event in WAL; open state inferred from market ORDER_PLACED + persistent ACCOUNT_UPDATE_RECEIVED position continuity.; Pending status is inferred from absence of ORDER_CANCELLED/ORDER_TIMEOUT/PENDING_BRACKETS_CLEARED(reason=filled) for the same order_id in current-day WAL.]



[2026-03-09T03:08:10.897271Z] | [Objective: Active trade snapshot audit] | [Artifacts: reports/auto/active_positions_snapshot_latest.md; reports/auto/active_positions_snapshot_20260309_030810.md; reports/auto/active_positions_snapshot_20260309_030810.json; reports/auto/trade_lifecycle_ledger.jsonl; reports/auto/anomalies_register_latest.md] | [Findings: active=1 pending=0 anomalies=0; active symbols=DOGEUSDT] | [Open Questions: DOGEUSDT fill transition has no explicit ORDER_FILLED verb in WAL; active state is inferred from ACCOUNT_UPDATE_RECEIVED continuity after market ORDER_PLACED.; No pending orders remain after applying current-day ORDER_TIMEOUT/ORDER_CANCELLED/PENDING_BRACKETS_CLEARED terminal signals to prior pending continuity.]
[2026-03-09T07:10:37.023843Z] | [Objective: Active trade snapshot audit] | [Artifacts: reports/auto/active_positions_snapshot_latest.md; reports/auto/active_positions_snapshot_20260309_071037.md; reports/auto/active_positions_snapshot_20260309_071037.json; reports/auto/trade_lifecycle_ledger.jsonl; reports/auto/anomalies_register_latest.md] | [Findings: active=1 pending=0 anomalies=0; active symbols=DOGEUSDT] | [Open Questions: Fill transitions still inferred from ORDER_PLACED + ACCOUNT_UPDATE + PENDING_BRACKETS_CLEARED(reason=filled) where explicit ORDER_FILLED is absent.]
[2026-03-09T07:12:07.901500Z] | [Objective: Daily trade postmortem audit] | [Artifacts] reports/auto/closed_positions_postmortem_latest.md; reports/auto/closed_positions_postmortem_20260309.md; reports/auto/closed_positions_postmortem_20260309.csv; reports/auto/postmortem_summary_20260309.json | [Findings] closed=2 categories={'cancel pathology': 1, 'execution issue': 1, 'bad timing': 1, 'unclear': 1} | [Recommended Actions] Add explicit close WAL payload; tune fill-timeout by symbol/regime; review ETH short gating in HIGH_VOLATILITY
