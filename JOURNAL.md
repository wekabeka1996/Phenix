# Engineering Journal

## 2026-03-01: EP-H4-WATCHDOG-CONFIG-HARDENING complete

**Mode:** TDD implementation.  
**Scope:** watchdog config contract hardening (test-integrity + fail-fast).

**Changes (additive-only):**
1. `OrderTimeoutWatchdog` now validates `config` contract at init:
   - `config=None` -> `{}` default
   - non-mapping -> `RuntimeError("CRITICAL: watchdog config must be mapping")`
2. `rps_limit` is strictly validated as `int`:
   - non-int -> `RuntimeError("CRITICAL: rps_limit must be int")`
3. Added watchdog contract tests for MagicMock rejection, strict `rps_limit`, and `None` defaults.
4. Updated one legacy test callsite to pass mapping config explicitly.

**Validation:**
- `pytest -q tests/domains/execution_position/test_watchdog_config_hardening.py`
- `pytest -q tests/domains/execution_position/test_bracket_health_check.py -k watchdog`
- `pytest -q tests/domains/execution_position -k "watchdog"` (timed out in unrelated async loop test suite)

## 2026-03-01: EP-H2-SAFE-EXIT-DEGRADE complete

**Mode:** TDD implementation.  
**Scope:** reduce-only close fail-safe on missing tf/TTL, exit policy split from entry policy.

**Changes (additive-only):**
1. Added strategy execution fields for exit policy: `exit_order_type`, `exit_tif`, `exit_limit_ttl_ms`.
2. In `DecisionMaking._propose_trade_intent`, reduce-only closes now use `execution.exit_*` with fail-safe default `MARKET`.
3. LIMIT reduce-only exit without `exit_limit_ttl_ms` now degrades to MARKET (no NRR-046 reject path).
4. Added `EVT:TRADE_INTENT_DEGRADED` with schema + registry entry.
5. `_emit_reduce_only_close` now returns success only when intent creation succeeds.
6. Added coverage for both flip paths: `_handle_flip_orchestration` and `_handle_regime_flip`.

**Validation:**
- `pytest -q tests/domains/decision_making/test_flip_orchestration_v1.py`
- `pytest -q tests/domains/decision_making/test_regime_flip_close.py`
- `pytest -q tests/ops/test_verb_registry_contracts.py -k "trade_intent"`

## 2026-02-24: EP-01.3 P0 - queued supersede guarded by live position check + dispatch fix

**Mode:** TDD implementation.
**Scope:** `apps/reference/domains/execution_position/fsm.py`, `tests/domains/execution_position/test_supersede_fill_race_guard.py`

**Changes (additive-only, P0):**
1. `_process_queued_supersede()` converted to async drain path with fail-closed live position check via `adapter.get_open_positions(symbol)`.
2. If live position exists (`positionAmt`/`position_amount`/`net_position` non-zero), queued supersede OPEN is dropped with explicit abort log.
3. If live position query is unavailable/raises (or payload parse fails), queued supersede OPEN is dropped fail-closed.
4. Dispatch defect fixed by using existing `_execute_decision()` instead of missing `_async_execute_decision`.
5. Supersede drain callsites updated:
   - timeout path now `await`s `_process_queued_supersede()`
   - cancel-event path schedules `_process_queued_supersede()` via `_submit_async`.

**Tests added:**
- `tests/domains/execution_position/test_supersede_fill_race_guard.py`
  - `test_supersede_timeout_blocks_open_when_live_position_exists`
  - `test_supersede_timeout_blocks_open_when_position_query_unavailable_fail_closed`
  - `test_supersede_timeout_allows_open_when_no_live_position`
  - `test_process_queued_supersede_does_not_reference_missing_async_method`

**Validation:**
- `pytest -q tests/domains/execution_position/test_supersede_fill_race_guard.py` -> 4 passed
- `pytest -q tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py -k cancel` -> 7 passed
- `pytest -q tests/domains/execution_position/test_fsm_cancel_logging.py` -> 2 passed

---

## 2026-02-24: EP-01.3 Fill-Race Guard Audit - Coverage Verdict

**Mode:** Forensic only. No implementation.
**Scope:** `apps/reference/domains/execution_position/fsm.py`, `apps/reference/domains/execution_position/exposure_guard.py`, `apps/reference/adapters/binance_adapter.py`
**Doc:** `docs/forensics/EP_SUPERSEDE_FILL_RACE_GUARD_AUDIT.md`

**Verdict:** `UNGUARDED (unsafe)` for scenario "old entry FILLED, queued supersede open executes after timeout".

**Key evidence:**
- Queued supersede path does not run a live position guard before entry placement.
- ExposureGuard fail-closed logic exists for CMD:OPEN, but is not re-applied in queued DEC supersede execution.
- Pending-order watchdog checks only track open entry orders; they do not block when a position is already open after fill.
- Additional defect observed: `_process_queued_supersede()` calls missing `_async_execute_decision`.

**No code changes. Context/audit only.**

---
## 2026-02-24: EP-01.3 Supersede Cancel Timeout â€” Forensic Investigation Complete

**Mode:** Forensic only. No implementation.
**Scope:** `apps/reference/domains/execution_position/fsm.py`, `config/aurora/domains.yaml`
**Doc:** `docs/forensics/EP_SUPERSEDE_CANCEL_TIMEOUT_CONTEXT.md`

**Finding:**
Log message `EP-01.3: supersede cancel timeout, proceeding with queued open` observed 3Ã— in
`logs/domain_execution_position.log` (SOLUSDT 09:05, BTCUSDT 09:25, SOLUSDT 09:30).
In all cases the old order was confirmed dead (cancelled or FILLED) in < 1s, yet the 5-second
timeout fired anyway.

**Root cause confirmed:** `_do_cancel()` fire-and-forget closure (`fsm.py:1084-1130`) does NOT
call `_process_queued_supersede()` after successful cancel. A WS-event path *does* exist in
`_handle_cancel_event()` (`fsm.py:4410`), but it silently aborts when `watchdog.pending_orders +
watchdog.acked_orders` still contains any entry for that symbol â€” a timing-dependent condition.
Result: the 5-second timeout (`config/aurora/domains.yaml:416`, `supersede_cancel_timeout_sec: 5.0`)
is the **only reliable execution path** for queued DEC:OPEN in all 3 observed cases.

**Risk flags (UNAUDITED â€” block implementation):**
- Fill-race case (BTCUSDT): order FILLED before cancel, timeout fires â†’ new DEC:OPEN runs â†’
  ExposureGuard behavior not verified â†’ potential **double-position risk**
- Cancel-failure loop: if cancel fails â†’ supersede re-queues â†’ new timeout â†’ infinite 5s cycle
- See forensic doc Section 5 + Section 7 for full risk matrix and open TODOs

**No code changed. No tests added. Investigation only.**

---

## 2026-02-24: EP-IDEMPOTENT-CANCEL-2011 â€” Exception-path absorption + truthful cancel logging

**Mode:** TDD implementation.
**Scope:** `apps/reference/domains/execution_position/idempotent_cancel.py`, `apps/reference/domains/execution_position/fsm.py`

**Changes (additive-only):**
1. `IdempotentCancelHelper.cancel_order_idempotent()` now absorbs `BinanceAPIError` exception-path `-2011/-2013` as idempotent success without retry:
   - reasons: `IDEMPOTENT_-2011_ABSORBED_EXC`, `IDEMPOTENT_-2013_ABSORBED_EXC`
   - `success=True`, `is_idempotent_success=True`, `order_status_after="UNKNOWN"`
2. `_cancel_pending_entries_for_symbol()` inner `_do_cancel` now uses truth-aligned gating:
   - success log + `watchdog.on_order_cancel(oid)` + `ORDER_CANCELLED` audit only when
     `res.success` or `res.is_idempotent_success`
   - failed result logs `Cancel FAILED` and leaves watchdog state untouched.
3. P1 in-flight dedup intentionally deferred to separate package.

**Tests added:**
- `tests/unit/test_idempotent_cancel_logic.py`
  - `test_cancel_2011_exception_absorbed_as_success`
  - `test_cancel_2013_exception_absorbed_as_success`
- `tests/domains/execution_position/test_fsm_cancel_logging.py`
  - `test_do_cancel_logs_warning_on_failed_result`
  - `test_do_cancel_logs_success_on_success_result`

**Validation:** targeted cancel suites pass (8 + 2 + 17 + 7 selected).


## 2026-02-24: EP-1102 fail-closed preflight + emission guard

**Mode:** TDD implementation.
**Scope:** `apps/reference/domains/execution_position/fsm.py`, `apps/reference/domains/execution_position/fsm_manage.py`, `apps/reference/adapters/binance_adapter.py`

**Problem:** `DEC:PLACE_ORDER` for `TAKE_PROFIT_MARKET` was executed with `stopPrice=None` (`... @ None/None`), forwarded to Binance as `stopPrice="None"` â†’ `-1102`.

**Changes (fail-closed, additive-only):**
1. **fsm.py** â€” module-level `_CONDITIONAL_ORDER_TYPES` + `_is_valid_stop_price()` helper. Preflight in `_execute_decision()` PLACE_ORDER handler blocks conditional orders with missing/invalid `stopPrice` before any adapter call. Logs `âŒ EP-1102 missing stopPrice {symbol} {order_type}` (â‰¤80 chars).
2. **fsm_manage.py** â€” `_emit_place_order()` raises `ValueError(EP-1102 â€¦)` when called for a conditional order type with an invalid price, preventing bad messages from entering the bus.
3. **binance_adapter.py** â€” `_assert_valid_stop_price()` helper called at the top of `place_stop_market_close_position` and `place_take_profit_market_close_position`; raises `ValueError` before any HTTP call.

**Tests:** `tests/domains/execution_position/test_ep_missing_stopprice_1102.py` â€” 36 tests (classes Aâ€“D); all pass. 88/88 in targeted regression suite, 0 regressions.

**Context doc:** `docs/forensics/EP_MISSING_STOPPRICE_1102_CONTEXT.md`

### Closed
- [x] **EP-ORDER-MISSING-STOPPRICE-1102**: Implemented and tested.



## 2026-02-24: EP-ORDER-CLIENTORDERID-4015 â€” Forensic Investigation Complete

**Task:** EP-ORDER-CLIENTORDERID-4015 (investigation only; no code changes)
**Scope:** `apps/reference/domains/execution_position/` â€” clientOrderId generation, `apps/reference/adapters/binance_adapter.py`
**Evidence source:** `logs/domain_execution_position.log.1` (4 confirmed -4015 occurrences)

### Root Cause â€” CONFIRMED

**Classification:** `CLIENTORDERID_OVERFLOW` â€” raw `idem_base` string was used directly as clientOrderId component without hashing, producing IDs of 42â€“64 chars.

In `fsm_manage.py:_place_brackets()`:
```python
idem_base = f"{msg.rid}_{int(self.position_open_ts)}"
# Example: "aurora_BTCUSDT_1771850701848_1771850735" = 39 chars
# Pre-fix cid: "SL-aurora_BTCUSDT_1771850701848_1771850735" = 42 chars  â† -4015
```

Binance constraint: `len(newClientOrderId) < 36` (max 35 chars). All 4 occurrences were bracket SL/TP from the ManageFlowFSM DEC:BATCH path.

### Evidence

| # | Timestamp | Lines | Symbol | Type | Pre-fix cid len |
|---|---|---|---|---|---|
| 1 | 14:45:36,278 | 5672 | BTCUSDT | STOP_MARKET | **42** |
| 2 | 14:45:36,326 | 5676 | BTCUSDT | TAKE_PROFIT_MARKET | **42** |
| 3 | 21:26:04,501 | 14967 | SOLUSDT | STOP_MARKET | **43** |
| 4 | 21:26:04,502 | 14968 | SOLUSDT | TAKE_PROFIT_MARKET | **43** |

In the same log sessions, deferred bracket paths succeeded with 15-char MD5 IDs (`SL-d760e404fcdc`), confirming the -4015 was specific to the ManageFlowFSM DEC:BATCH path at the time.

### Current State

`generate_client_order_id()` (`utils.py:159`) now applies an MD5 hash (`hexdigest()[:12]`), producing IDs of 15-18 chars across all 3 branches. The `max_len=32` guard provides an additional truncation safety net. All 12 callsites in `fsm.py` + `fsm_manage.py` route through this function.

Existing regression tests: `tests/domains/execution_position/test_fsm_manage_bracket_fixes.py::TestClientOrderIdLength` â€” 4 parametrized tests with UUID and long-rid inputs.

### Open Actions

- [ ] **EP-ORDER-CLIENTORDERID-4015-TEST**: Extend regression tests with all prefix types, charset assertion, and adapter-level length guard.
- [ ] **EP-ORDER-CLIENTORDERID-4015-GUARD** (optional): Length assertion in `BinanceAdapter._post_order_with_algo_fallback()` as defense-in-depth.

**Full forensic document:** `docs/forensics/EP_CLIENTORDERID_4015_CONTEXT.md`

---

## 2026-02-24: EP-IDEMPOTENT-CANCEL-2011 â€” Forensic Investigation Complete

**Task:** EP-IDEMPOTENT-CANCEL-2011 (investigation only; no code changes)
**Scope:** `apps/reference/domains/execution_position/fsm.py`, `idempotent_cancel.py`, `apps/reference/adapters/binance_adapter.py`
**Evidence source:** `logs/domain_execution_position.log` â€” 2 confirmed -2011 occurrences (lines 3709, 3732)

### Root Causes â€” CONFIRMED (two bugs + one structural race)

**Classification:** `CONCURRENT_DUPLICATE_CANCEL + EXCEPTION_ABSORPTION_GAP`

**Bug #1 (P0): Exception-path -2011 absorption gap**
`IdempotentCancelHelper.cancel_order_idempotent()` absorbs `-2011` only from the API response **dict** (`result.get("code") == -2011`). Since `BinanceAdapter.cancel_order()` always **raises** `BinanceAPIError(code=-2011)` (never returns a dict), the absorption path is unreachable. The exception handler treats -2011 as a transient error, retries, and returns `success=False`.

Fix: add `code = getattr(e, "code", None); if code in (-2011, -2013): return absorbed_success` at the top of the exception handler in `cancel_order_idempotent()`.

**Bug #2 (P0): `_do_cancel()` logs "âœ… Cancelled" unconditionally**
After `await self._cancel_order()`, the FSM logs success regardless of `res.success`. A FAILED `IdempotentCancelResult` is silently discarded and "âœ…" is emitted â€” misleading all log readers.

Fix: check `res.success` before logging "âœ…"; log WARNING on failure.

**Structural race (P1): two concurrent cancels for the same order_id**
When a regime change and a supersede intent arrive within ~281 ms, both call `_cancel_pending_entries_for_symbol()` for the same pending order. Two concurrent async `_do_cancel()` tasks are submitted without deduplication. The pre-check for the second cancel sees `NEW` (first cancel not done yet), proceeds, then gets -2011 when order is already gone.

Fix (dedup guard): track in-flight cancel task IDs in a `_pending_cancel_tasks: set[str]`; skip scheduling if already in-flight.

### Evidence Summary

| Timestamp | order_id | symbol | Trigger | before â†’ after | Result |
|---|---|---|---|---|---|
| 09:05:05,082 | 1726744894 | BTCUSDT | CANCEL_SUPERSEDED attempt 1 | NEW â†’ None | FAILED (-2011 exception) |
| 09:05:05,547 | 1726744894 | BTCUSDT | CANCEL_SUPERSEDED attempt 2 | NEW â†’ None | FAILED (-2011 exception) |

Concurrent CANCEL_STALE_REGIME for the same order succeeded at 09:05:04,841 (673ms RTT). The SUPERSEDED cancel pre-check ran at ~09:05:04,750 â€” before stale regime cancel completed â€” so it saw `NEW` and proceeded.

**Behavioral impact: NONE** â€” order was correctly removed from Binance and from watchdog tracking. The failure is diagnostic only.

**PRE_CHECK_TERMINAL_FILLED** path verified correct: 4 cases in `log` + `log.1` where FILLED orders trigger the short-circuit correctly. No -2011 in those cases.

### Recommended Policy

**Option A (recommended):** Treat -2011 from exceptions as idempotent success ALWAYS in cancel context.
`cancel is idempotent by nature â†’ -2011 means order gone â†’ desired postcondition achieved`.

### Open Actions

- [ ] **EP-IDEMPOTENT-CANCEL-2011-FIX-A**: `idempotent_cancel.py` â€” add BinanceAPIError(-2011/-2013) absorption in exception handler (no retry).
- [ ] **EP-IDEMPOTENT-CANCEL-2011-FIX-B**: `fsm.py:_do_cancel()` â€” check `res.success`; log WARNING on FAILED, "âœ…" only on success.
- [ ] **EP-IDEMPOTENT-CANCEL-2011-FIX-C**: `fsm.py:_cancel_pending_entries_for_symbol()` â€” add `_pending_cancel_tasks` dedup guard.
- [ ] **EP-IDEMPOTENT-CANCEL-2011-TEST**: Implement Class Aâ€“D tests per `docs/forensics/EP_IDEMPOTENT_CANCEL_2011_CONTEXT.md`.

**Full forensic document:** `docs/forensics/EP_IDEMPOTENT_CANCEL_2011_CONTEXT.md`

---

## 2026-02-18: Forensic Audit â€” H1/H2/H3 Config Hypotheses Verification

**Mode:** Read-only. No code/config changes.
**Scope:** `apps/reference/domains/regime_detector/regime_detector.py`, `apps/reference/config_models.py`, `config/aurora/regime.yaml`

### What was checked
1. **H1** â€” Directionality of `uncertain_cutoff` on UNCERTAIN demotions.
2. **H2** â€” Directionality of `sma_trend.confidence_multiplier` on computed confidence.
3. **H3** â€” Existence of Grok-proposed YAML keys in Pydantic schemas + `extra='forbid'` enforcement.

### What was confirmed

**H1 â€” VERIFIED (TRUE):**
- `regime_detector.py:539`: `if regime != "UNCERTAIN" and float(confidence) < self._uncertain_cutoff: â†’ regime = "UNCERTAIN"`
- Operator is `<`. Raising cutoff from 0.60 â†’ 0.67 **expands** the demote zone â†’ more UNCERTAIN. Confirmed.

**H2 â€” VERIFIED (TRUE with nuance):**
- `regime_detector.py:182-195`: formula = `abs(spread_ratio * confidence_multiplier)` clamped to `[conf_min, conf_max]`.
- Lowering multiplier (e.g. 30 â†’ 16) lowers raw confidence. Floor is `conf_min` (cannot go below it), but if result falls below `uncertain_cutoff` while above `conf_min`, the regime is demoted to UNCERTAIN by H1 gate. Net effect: more UNCERTAIN or flat at floor.

**H3 â€” MOSTLY SAFE; ONE TRAP:**
- `volatility_entry_logic` â€” EXISTS at `AuroraInstrumentConfig:2791`.
- `regime_multipliers` â€” EXISTS **only inside** `VolatilityEntryConfig:2657`. As a top-level key under `AuroraInstrumentConfig` it does NOT exist â†’ would crash under `extra='forbid'`.
  Correct path: `aurora.assets.<SYMBOL>.volatility_entry_logic.regime_multipliers`.
- `position_mode` â€” EXISTS at `AuroraInstrumentConfig:2724`.
- `leverage` â€” EXISTS at `AuroraInstrumentConfig:2729`.
- `holding_period.min_duration_sec` â€” EXISTS at `HoldingPeriodConfig:606`.
- `aurora.decision.gates.anti_fomo_sigma` â€” EXISTS via `DecisionConfig.gates` (`VolAdjGatesConfig:633`).
- `motion_window_sec`, `anti_flat_sigma` â€” EXISTS in `VolAdjGatesConfig:627,639`.

### Next action items (TODO â€” no code changes yet)
- [ ] **TODO-H3-TRAP**: Audit any Grok-generated config snippets that place `regime_multipliers` at the top level of an asset block. Must be nested under `volatility_entry_logic`.
- [ ] **TODO-H2-IMPACT**: If `sma_trend.confidence_multiplier` is lowered to 16, verify `conf_min` (floor) in `config/aurora/regime.yaml` models.sma_trend. If `conf_min > uncertain_cutoff`, then lowering multiplier has no visible effect (floor dominates). If `conf_min < uncertain_cutoff`, more UNCERTAIN events will appear.
- [ ] **TODO-H1-VALIDATE**: Run `tools/bars_regime_analysis.py` in dry mode with `uncertain_cutoff=0.62` vs `0.60` to quantify the UNCERTAIN rate delta before applying to live.

---

## 2026-02-13: SOLUSDT last filled order (loss) + FLIP audit

**Scope:** Forensics from `ops/wal/2026-02-13.jsonl`, `logs/*`, YAML SSOT under `config/aurora/`.

**Last filled SOLUSDT order (PnL-impacting):**
- rid: `aurora_SOLUSDT_1770973502430`
- side/qty: `SELL 5` (short)
- entry: `79.64` (LIMIT GTX, filled)
- SL/TP: `80.85 / 79.20` (strategy-provided, tick-rounded)
- regime at entry: `UNCERTAIN` (confidence=0.5 per regime detector)
- close: SOL position disappears at `2026-02-13T14:35:23.029Z`, wallet delta `-8.9628 USDT`

**why (facts / evidence pointers):**
- why: flip entry buy->sell (WAL `ops/wal/2026-02-13.jsonl:9746`)
- why: RR=0.36 (TP 0.544% vs SL 1.512%) (WAL `ops/wal/2026-02-13.jsonl:9746`)
- why: closed as mark>SL stop; TP orphan cleaned (WAL `ops/wal/2026-02-13.jsonl:14649`, `logs/aurora_core.log.1:35126`)

**FLIP operational issues observed:**
- why: flip CLOSE intents rejected (NRR-046: LIMIT needs tf_sec) (`ops/wal/2026-02-13.jsonl:14489`)
- why: flip OPEN attempts can be maker-only rejected (GTX post-only) (`ops/wal/2026-02-13.jsonl:14791`)

**Config candidates (YAML-only, not applied):**
- Block `UNCERTAIN` for `SOLUSDT` (or raise thresholds) to avoid low-quality flips.
- Raise SOL TP/RR guardrails (`take_profit.tp_low_ratio`, `exit.regime_tpsl.min_tp_rr`) to avoid RR=0.36.
- Unblock flip CLOSE TTL derivation (review `execution_position.pending_entry_ttl.*` behavior for tf_sec=0/None).
- Reduce maker-only rejects (tune `volatility_entry_logic` multipliers for SOL or revisit `aurora.execution.entry_tif`).

## 2026-01-30: DM QoS P2-Lite Purge and Wiring Audit

**Task:** DM_QOS_P2_LITE_PURGE_AND_WIRING_AUDIT
**Context:** Audited DecisionMaking QoS logic to reduce cognitive load and verify "Exposure Block" feature status without full refactor.

**Findings:**
1. **Dead Code Confirmed:** `_check_qos_rules` was strictly unreachable (0 callsites).
2. **Missing Wiring:** `_handle_exposure_block` is UNWIRED (no event listener calls it). It also contains a SPLIT-BRAIN BUG (writes to flat key, read by partitioned query). "Global Exposure Block" logic is effectively non-existent despite config presence.
3. **P2-Lite Action:**
    - **DELETED** `_check_qos_rules`.
    - **ANNOTATED** `_handle_exposure_block` with failure warning/TODO.
    - **VERIFIED** QoS tests pass.

## 2026-01-30: DM_SAFETY_BYPASSES_P1 â€” Critical Security Hardening

**Task:** DM_SAFETY_BYPASSES_P1
**Context:** Identified and fixed two critical security vulnerabilities in the `decision_making` domain.

**Vulnerabilities Fixed:**
1. **Hardcoded safety gates bypass:** `apply_safety_gates = str(strategy_id) == "aurora"` allowed any non-Aurora strategy to bypass directional sanity and price motion gates.
2. **Fail-open exposure cache:** Missing/stale/error cache conditions allowed trades, violating fail-closed principle.

**Changes:**
1. `decision_making.py`: Safety gates now read from `strategies.<id>.safety_gates.enabled` config. Missing config â†’ FAIL-CLOSED (NRR-054).
2. `decision_making.py`: Exposure cache precheck now returns `False` (block) on missing/stale/error (NRR-053).
3. `normalized_reject_reasons.py`: Added NRR-053 (EXPOSURE_CACHE_UNAVAILABLE), NRR-054 (CONFIG_SAFETY_GATES_MISSING).
4. `config_models.py`: Added `SafetyGatesConfig` Pydantic model.
5. `aurora.yaml`, `mean_reversion.yaml`: Added explicit `safety_gates.enabled` field.

**Risk Note â€” Mean Reversion safety_gates.enabled=false:**
MR intentionally trades against trend (counter-trend), so directional sanity and price motion gates are DISABLED.
**Alternative guards protecting MR:**
- Regime gating: MR only trades in FLAT regimes (`allowed_regimes`).
- Bollinger Band boundaries: BB upper/lower provide entry structure.
- ATR-based stops: `sl_atr_mult` prevents runaway losses.
- Per-asset `max_risk_score` filtering in Phase 3+.

**P2 TODO:** Consider `safety_gates.profile: "counter_trend"` to formalize MR-specific gate logic (e.g., require oversold/overbought RSI instead of trend confirmation).

**Verification:**
- NRR-053/054 uniqueness confirmed.
- All strategy YAMLs updated.
- 22/22 tests passed.


## 2026-01-08: VF-DICT Forensics (Global/Domain Dictionaries)

**Task:** VF-DICT-FORENSIC (01..05)
**Context:** Investigate vFoundation Global/Domain Dictionaries as governance SSOT (op/verb/TTL/security/routing) and prove how/if they are used by runtime vs tooling.

**Outcome (facts):**
1. **Inventory:** Dictionary artifacts exist in three layers: global dictionaries (`global_v2_2*.yaml`), domain dictionaries (`vfoundation/dictionaries/domains/domain_*.yaml`), and app domain metadata (`apps/reference/domains/**/domain_dict.json`).
2. **Runtime usage:** vFoundation runtime does not parse these dictionary YAML files; enforcement currently lives in code (Message op allowlist, TTL range + expiry, signature required for DEC/CMD, NO_ROUTE for unknown handlers).
3. **CLI usage:** `vfound dict --global` only checks dictionary file existence (no content parsing).
4. **Data quality:** `vfoundation/dictionaries/global_v2_2_framework.yaml` contains a markdown code-fence and is not valid YAML for parsing; this is currently harmless because it's not parsed.

**Reports:**
- `reports/VF-DICT-FORENSIC-01.md` â€” inventory, validity, duplication signals
- `reports/VF-DICT-FORENSIC-02.md` â€” proven code/CLI references
- `reports/VF-DICT-FORENSIC-03.md` â€” where runtime validation lives today
- `reports/VF-DICT-FORENSIC-04.md` â€” Aurora event-space vs dictionary declarations (OP-level)
- `reports/VF-DICT-FORENSIC-05.md` â€” Option A/B/C evolution menu (no implementation)

## 2026-01-08: Config Contract Ghost Rejections Eliminated

**Task:** TASK-CFG-REJECT-INTEGRATE-01
**Context:** Previous forensic analysis revealed that `ConfigContractError` exceptions (raised when strictly typed config is missing or invalid) were being caught and logged but did not emit standard rejection events. This created "ghost" failures where the system would silently stop trading on a symbol without a trace in the event bus or order logs.

**Changes:**
1.  **NRR Integration:** Added `NRR-CFG-001` (MISSING) and `NRR-CFG-002` (INVALID) to `NormalizedRejectReasons`.
2.  **Strategy Gateway:** Modified `_on_strategy_signal_gateway` in `DecisionMaking` to emit `EVT:TRADE_INTENT_REJECTED` when a config contract violation occurs.
3.  **Feature Engine:** Modified `on_features` to emit `EVT:DECISION_BLOCKED` (new health event) when config errors prevent feature calculation.
4.  **Verification:** Updated `test_config_contract_block_normalization.py` to verify event emission.

**Outcome:**
All configuration-related trading blocks are now observable in the event stream. The "Ghost" class of errors has been eliminated.
- **2026-01-08:** Synced `EVT:DECISION_BLOCKED` to new SSOT `docs/FSM_EVENT_MAP.md` and added `decision_blocked_total` metric.
- **2026-01-08:** Deleted dead legacy spot `AccountObserver` domain (reachability=0 for Futures, unwired from main.py).
- **2026-01-08:** Fixed test env: FastAPI missing (installed in .venv but pytest not using it?).

## 2026-01-08: VF-VERB-REG â€” SSOT Verb Registry (seed + warn-only drift gate)

**Task:** VF-VERB-REG-01/02/03
**Context:** Prepare a single SSOT verb registry seeded from runtime string-scan (no runtime enforcement). Add a warn-only CI gate to surface drift immediately without breaking.

**Changes:**
1. **SSOT registry created:** `apps/reference/dictionaries/verb_registry_v1.yaml` generated from runtime scan (`.py` without `tests/**`).
2. **Warn-only gate:** `tests/vfoundation/test_verb_registry_warn_only.py` compares runtime scan vs registry and writes diffs into `reports/` without failing on coverage gaps.
3. **Owner labeling (top-N):** marked owner + status for the top-20 most frequent runtime tokens; schema is populated only when an exact `<verb_lower>_v1.json` exists (otherwise `null`).

**Reports:**
- `reports/VF-VERB-REG-01.md` â€” seed generation summary
- `reports/VF-VERB-REG-02.md` + `reports/VF-VERB-REG-02_diff.json` â€” warn-only drift output
- `reports/VF-VERB-REG-03.md` â€” owner labeling summary

**Non-goals (explicit):** no runtime deny/allow by verb; no attempt to extract registry from `Router.register` (not used in prod wiring).

## 2026-01-08: VF-VERB-REG-04/05 â€” Owner inference report + coverage threshold

**Task:** VF-VERB-REG-04/05
**Context:** Speed up cleanup of `owner: unknown` with evidence-based path heuristics (no auto-changes). Tighten drift gate so it fails only once coverage is basically complete.

**Changes:**
1. **Owner inference report (no autofix):** Added `tests/vfoundation/test_verb_owner_inference_report.py` which scans runtime `.py` (no tests), aggregates occurrences per file and per `apps/reference/domains/<X>/` bucket, and suggests owner only when â‰¥70% of occurrences land in one domain.
2. **Artifacts:** Writes `reports/VF-VERB-REG-04_owner_suggestions.json` and `reports/VF-VERB-REG-04.md`.
3. **Coverage gate policy:** Updated `tests/vfoundation/test_verb_registry_warn_only.py` to fail only if `coverage >= 98%` AND `runtime_not_in_registry > 0` (until then it stays warn-only).

## 2026-01-08: VF-VERB-REG-06 â€” Apply owner suggestions (>=70%)

**Task:** VF-VERB-REG-06
**Context:** Apply evidence-based owner suggestions to reduce `owner: unknown` without guesses.

**Changes:**
- Updated `apps/reference/dictionaries/verb_registry_v1.yaml` by changing **only** `owner` for entries where current owner was `unknown` and inference confidence was â‰¥70%.
- Regenerated VF-VERB-REG-04 reports after the update.

**Artifacts:**
- `reports/VF-VERB-REG-06_applied.json` â€” applied changes with confidence + evidence
- `reports/VF-VERB-REG-06.md` â€” short summary
- **2026-01-08:** Validated and Frozen 'Alpha Search' domain (Task ALPHA-FREEZE-01/02). Added determinism tests, safe metrics, and offline eval script.

## 2026-01-08: AGENT-NAV-VERB-REG-01 â€” Agent Navigation Playbook (registry-first)

**Task:** AGENT-NAV-VERB-REG-01
**Context:** After establishing SSOT for system language (Verb Registry) and governance dictionaries, we need an explicit, contract-first navigation instruction for Copilot/LLM agents.

**Changes:**
- Added a strict navigation playbook in `docs/AGENT_NAVIGATION_PLAYBOOK.md`.
- Rules are registry-first (`apps/reference/dictionaries/verb_registry_v1.yaml`), owner-boundary (`apps/reference/domains/<owner>/`), and policy-aware (global/domain governance YAML).

**Outcome:**
Copilot/agents now have a single official procedure that forbids guessing verbs/owners and forbids repo-wide wandering without a contract.

## 2026-01-08: Exchange Filters Startup Guard Integration

**Task:** TASK-EXF-IMPLEMENTATION (07..12)
**Context:** Implemented a critical startup guard that validates `config/aurora/instruments.yaml` against real-time exchange constraints (`/fapi/v1/exchangeInfo`). This prevents runtime rejections due to precision mismatches (LOT_SIZE, PRICE_FILTER) or missing filters.

**Changes:**
1.  **Validator Implementation (`validator.py`):**
    *   Added logic to fetch and parse exchange filters (`LOT_SIZE`, `PRICE_FILTER`, `MIN_NOTIONAL`).
    *   Implemented batch fetching (1 request for all symbols) to optimize startup time (~N -> 1 request).
    *   Removed unsafe defaults (e.g., `min_notional=5`) to ensure fail-closed behavior on missing data.
2.  **Configuration (`system.yaml`/`config_models.py`):**
    *   Added `validate_instruments_on_startup` (default: True).
    *   Added `warn_only_filters` (default: False) for Dev/Shadow environments.
3.  **Wiring (`main.py`):**
    *   Integrated validation logic immediately after config loading.
    *   Implemented blocking behavior on CRITICAL mismatches (SystemExit 1).
4.  **Testing:**
    *   Added `tests/contracts/test_exchange_filters_validation.py` (Unit).
    *   Added `tests/integration/test_startup_filters_wiring.py` (E2E Integration).

**Policies:**
*   **Fail-Closed:** In LIVE/TESTNET, any critical filter mismatch blocks startup.
*   **Warn-Only:** Available via config for non-critical environments.

**Artifacts:**
*   `docs/STARTUP_GUARDS.md`: Official documentation of the new guard.

## 2026-01-08: Execution Management (Zombie) Removal

**Task:** EM-ZOMBIE-01
**Context:** Domain `execution_management` was identified as a non-functional stub (not wired, no logic, tests only checking logs). It was creating confusion vs `execution_position` (the real execution domain).

**Changes:**
1.  **Removed:** `apps/reference/domains/execution_management/` and `tests/test_execution_management.py`.
2.  **Refactored:** `apps/reference/main.py` - Renamed log file `domain_execution_management.log` to `domain_execution_position.log` (as it was actually containing ExecPos logs).
3.  **Docs:** Added tombstone in `docs/deprecations/`.

**Validation:**
*   Confirmed 0 functional references in code/config.
*   Verified `main.py` wiring logic remains intact (integration tests passed).

## 2026-02-13: SOL hardening (UNCERTAIN gate off + tighter SL)

**Tasks:** TASK-SOL-REGIME-BLOCK-01, TASK-SOL-SL-TIGHTEN-01, TASK-SOL-GATE-TESTS-01, TASK-SIZING-FORENSIC-01

**Changes:**
1. `config/aurora/strategies/aurora.yaml`
   - `aurora.assets.SOLUSDT.allowed_regimes`: removed `UNCERTAIN`.
   - `aurora.assets.SOLUSDT.exit.sl_pct`: `0.01512 -> 0.0135`.
2. Added test `tests/domains/decision_making/test_sol_uncertain_gate.py::test_sol_uncertain_blocked`
   - Verifies `SOLUSDT` in `UNCERTAIN` emits `EVT:STRATEGY_DECISION_BLOCKED` with `REGIME_NOT_ALLOWLISTED` and no `EVT:STRATEGY_SIGNAL_PRODUCED`.
3. Updated and extended `tests/domains/test_tpsl_config_production.py`
   - Updated SOL assertions to `sl_pct=0.0135`.
   - Added `test_sol_sl_pct_applied` (SELL path, tick-quantized SL check).

**Forensic note (RID):**
- `rid=aurora_SOLUSDT_1770973502430` found in `ops/wal/2026-02-13.jsonl` with:
  - `TRADE_INTENT_PROPOSED` payload `order.qty="5"` and `order.price="79.6401785714285714300"`.
  - Followed by `DEC OPEN` with `qty="5"` and rounded entry `price="79.64"`.

**Sizing verdict:**
- Regime-aware sizing in DecisionMaking is present (`YES`) via `margin_pct_mult` from `aurora.assets.<symbol>.regime_sizing[regime]` in `_on_strategy_signal_gateway`.
- For `UNCERTAIN`, SOL has no regime multiplier key/default, so sizing falls back to base `instruments.SOLUSDT.sizing.margin_pct`.

**Validation run:**
- Targeted: `python -m pytest -q tests/domains/decision_making/test_sol_uncertain_gate.py::test_sol_uncertain_blocked tests/domains/test_tpsl_config_production.py::TestAuroraConfigLoading::test_solusdt_exit_config_loaded tests/domains/test_tpsl_config_production.py::TestBracketPriceCalculation::test_solusdt_sl_calculation tests/domains/test_tpsl_config_production.py::TestBracketPriceCalculation::test_sol_sl_pct_applied tests/domains/test_tpsl_config_production.py::TestEndToEndBracketCalculation::test_solusdt_full_bracket_path_uses_aurora_config tests/contracts/test_regime_allowlist.py -q` -> **102 passed**.
- Full suite: `python -m pytest -q` currently blocked by environment issues (`polars` missing and pytest marker `timeout` not registered).

## 2026-02-24: EP-ORDER-PRECISION-1111 â€” Forensic Investigation Complete

**Task:** EP-ORDER-PRECISION-1111 (investigation only; no code changes)
**Scope:** `apps/reference/domains/execution_position/` â€” bracket order placement, `config/aurora/instruments.yaml`
**Evidence source:** `logs/domain_execution_position.log` + `logs/domain_execution_position.log.1` (8 confirmed -1111 occurrences)

### Root Cause â€” CONFIRMED

**Classification:** `NORMALIZER_BYPASS` â€” post-offset re-quantization missing

In `fsm_manage.py:_place_brackets()`:
1. `_quantize_prices()` correctly aligns `sl` and `tp` to `tick_size` âœ“
2. `TPSLValidationRules.add_safety_offset(sl, tick_size, offset_bps=5)` returns `max(tick_size, sl * 5/10000)`. The percentage branch is **not a tick_size multiple** âœ—
3. `sl = sl - sl_offset` â†’ tick alignment destroyed âœ—
4. `str(sl)` passed to adapter â†’ Binance rejects with `-1111`

Identical bug in `fsm.py:_place_deferred_brackets()` (LIMIT-DEFERRED fill path) â€” unquantized values survive into `bracket_data` WAL and replay on fill/restart.

### Mathematical Proof

| Symbol | Quantized SL | Offset | Raw stopPrice (log) | tick_size | Excess dp |
|--------|-------------|--------|--------------------|-----------|----|
| BTCUSDT | 62890.9 | 31.44545 | **62859.45455** | 0.1 | +4 |
| SOLUSDT | 76.07 | 0.038035 | **76.031965** | 0.01 | +4 |
| DOGEUSDT | 0.09048 | 0.00004524 | **0.09043476** | 0.00001 | +3 |
| XRPUSDT | 1.3402 | 0.00067010 | **1.3395299** | 0.0001 | +3 |

All 4 symbols: `raw = quantized - offset` reproduces log values exactly.

### Impact

- 8 confirmed -1111 occurrences across 4 symbols (BTCUSDT, SOLUSDT, DOGEUSDT, XRPUSDT).
- After -1111, SL/TP placement fails silently (`except Exception` absorbs error). Position is left **without brackets** â€” no stop-loss protection.
- SOLUSDT `76.031965` appears in both log files â†’ confirms unquantized value stored in WAL and replayed.

### Next Actions

- [ ] **EP-ORDER-PRECISION-1111-FIX-A**: `fsm_manage.py:_place_brackets()` â€” add `quantize_stop_price(sl, tick_size, side=sl_side)` after offset subtraction.
- [ ] **EP-ORDER-PRECISION-1111-FIX-B**: WAL/bracket_data storage point â€” ensure quantized prices written before deferred path reads them.
- [ ] **EP-ORDER-PRECISION-1111-TEST**: Implement 5 regression tests per `docs/forensics/EP_PRECISION_1111_CONTEXT.md`.
- [ ] **EP-ORDER-PRECISION-1111-GUARD** (optional): Precision assertion in `BinanceAdapter.place_stop_market_close_position()` as defense-in-depth.

**Full forensic document:** `docs/forensics/EP_PRECISION_1111_CONTEXT.md`

## 2026-02-24: EP-ORDER-PRECISION-1111 â€” Fix Implemented (TDD)

**Status: CLOSED**

### Changes

| File | Lines | Change |
|------|-------|--------|
| `apps/reference/domains/execution_position/fsm_manage.py` | 699â€“710 | Re-quantize `sl_price`, `tp1_price`, `tp2_price` after offset arithmetic before emitting BATCH |
| `apps/reference/domains/execution_position/fsm.py` | 4809â€“4813 | Defensive re-quantize `sl`/`tp` in `_place_deferred_brackets()` before adapter calls |
| `apps/reference/domains/execution_position/fsm.py` | 4843â€“4851 | Fail-closed guard: skip TP if SL placement failed (unprotected position prevention) |
| `tests/domains/execution_position/test_ep_precision_1111.py` | new | 17 regression tests (Aâ€“D), all pass |

### Fix Summary

**Path A (`fsm_manage.py:_place_brackets`):**
After `add_safety_offset()` arithmetic, re-quantize using `quantize_stop_price(float(price), float(tick_size), side=bracket_side)` â†’ wraps back to `Decimal`. This restores tick alignment before `str(price)` is emitted to the adapter.

**Path B (`fsm.py:_place_deferred_brackets`):**
Defensive re-quantize of `sl`/`tp` from `bracket_data` using already-known `sl_side`/`tp_side`. A no-op for clean values from WAL, guards against any edge-case unquantized replay.

**Fail-closed (`fsm.py:_place_deferred_brackets`):**
If `sl_resp is None` after SL placement attempt, skip TP placement and log CRITICAL. Prevents a TP-only position with no stop-loss protection.

### Test Gate

```
tests/domains/execution_position/test_ep_precision_1111.py  17 passed
tests/domains/execution_position/test_fsm_manage_bracket_fixes.py  20 passed
```

Pre-fix: 5 FAILED (class B: precision violation proved, class C: unquantized replay proved)
Post-fix: 37/37 passed, zero regressions.

## 2026-02-25: Forensic Review Completed (EP Brackets After Fill + Execution Orchestration Duplication)

Review artifacts created:
- `docs/reviews/REVIEW_EP_BRACKETS_AFTER_FILL.md`
- `docs/reviews/AUDIT_EXECUTION_MANAGER_DUPLICATION.md`

Key findings:
- Verdict for delivered EP brackets fix: **FAIL** (safety gaps remain).
- Critical follow-ups: pending state is cleared before bracket placement success, no hard policy for `missing_count=2` naked positions, and dedup key is not slot-aware for multi-TP.
- Duplication audit verdict: **HIGH** risk (execution-manager responsibilities are split across execution_position, decision_making, order_guardian service, and orchestrator).

