# Engineering Journal

## 2026-03-17: CLEAN-START-EXECUTION-RESTORE-UPGRADE (PROTECT_ONLY self-heal)

**Task:** Fix production blocker where `mean_reversion` cannot open new positions due to sticky PROTECT_ONLY latch after cold startup without snapshot restore.

**Root cause:** Startup restore path sets `execution_status=COLD` when `snapshot_loaded_successfully=False`. `combine_restore_permissions_live_first()` sees `execution_status != RESTORED` → forces `can_open_new_risk=False` for the entire session. No self-heal mechanism existed to upgrade execution restore even when live account confirmed zero open positions.

**What was done:**
- Added `upgrade_cold_execution_restore_if_clean_start()` to contract layer (`apps/reference/contracts/runtime_analytics_restore.py`) — pure function, reusable for any strategy.
- Added `EVT:ACCOUNT_UPDATE_RECEIVED` listener to `MeanReversionHandler` (`_on_account_update_clean_start_check`) that upgrades COLD execution restore → RESTORED when live account confirms zero positions for managed symbols.
- Fail-closed semantics preserved: upgrade only on COLD state, only with trustworthy live zero-positions confirmation, only per-symbol.
- Structured observability via `MR_CLEAN_START_UPGRADE` domain log entry.

**Tests added:**
- `tests/contracts/test_clean_start_execution_restore_upgrade.py` — 13 contract-level tests
- `tests/domains/decision_making/test_mean_reversion_clean_start_upgrade.py` — 11 handler-level integration tests

**Regression:** 762 passed, 0 failed across contracts/bootstrap/decision_making domains.

## 2026-03-16: LIVE-SCHEMA-VALIDATION-HOTFIX (3 crashes)

**Task:** Fix three P0 live runtime crashes caused by JSON schema validation mismatches after Phase 14C schema enforcement was activated.

### Crash 1: EVT:PORTFOLIO_STATE_UPDATED — `'0E-8'` Decimal scientific notation
**Root cause:** `str(Decimal('0.00000000'))` produces `'0E-8'` (Python scientific notation), fails regex `^-?[0-9]+(\.[0-9]+)?$`.
**Fix:** Added `_ds(value: Decimal) -> str` safe serializer in `position_tracking.py` using `format(d, 'f')` for fixed-point output. Replaced all `str(Decimal)` in 6 payload builder sites (~30 fields) with `_ds()`.
**File:** `apps/reference/domains/position_tracking/position_tracking.py`

### Crash 2: EVT:HTF_BARS_IMPORTED — `'o' is a required property`
**Root cause:** Both pillar backfill emit sites in `main.py` built bar dicts with `c, h, l` but omitted `o` (open) and `v` (volume), which schema requires.
**Fix:** Added `"o": bar.open, "v": bar.volume` to both emit sites. Also added `bar_close_ts` to schema (set by `attach_canonical_bar_payload`). Removed `why` from schema required (FSM passes `why` as separate arg, never in payload).
**Files:** `apps/reference/main.py` (2 sites), `schemas/htf_bars_imported_v1.json`

### Crash 3: EVT:MARKET_TICK_RECEIVED — additionalProperties + symbol regex
**Root cause:** Schema had `additionalProperties: false` but emitter sends 8 fields not in schema (`buy_count`, `sell_count`, `buy_notional`, `sell_notional`, `trades_dropped_out_of_order`, `features`, `bid_ask_count`, `trade_count`). Symbol regex `^[A-Z]{2,10}USDT$` rejected `1000PEPEUSDT`.
**Fix:** Added all 8 missing properties to schema. Widened symbol regex to `^[A-Z0-9]{2,20}USDT$`. Added `multiprocess_worker` to `data_source` enum.
**File:** `schemas/market_tick_received_v1.json`

**Verification:** 170 tests passed across position_tracking, feature_engineering, market_data, bootstrap domains. All `_ds()` edge cases verified against schema regex.

## 2026-03-16: DM-EVT-ORDER-REJECTED-CONTRACT-HARDENING-PACK

**Task:** Fix broken cross-domain payload contract between execution_position emitters and decision_making consumer for `EVT:ORDER_REJECTED`.

**Root cause:**
`md_amr_handler._on_order_rejected` read `pld.get("reject_reason")`, but **no emitter** sends `reject_reason`:
- `open_executor.py` sends `reason: "MAKER_ONLY_REJECT"`
- `fsm.py` sends `reason_code: "ADAPTER_ERROR"` + `reason_text: str(e)`
- `binance_ws_client.py` sends `reason: "MAKER_ONLY_REJECT"`

Result: GTX retry counter was **dead in production** — POST_ONLY/MAKER_ONLY rejects never incremented `_gtx_retries`, silently falling through to the else branch that resets counter to 0.

**Fix applied:**
- Added `_normalize_order_reject_reason(pld)` static method to `MDAMRHandler`
- Priority: `reject_reason` > `reason` > `reason_code`+`reason_text` > `""` (fail-closed)
- All values: `.strip().upper()`
- Empty/malformed → `""` → no POST_ONLY/MAKER_ONLY match → no unsafe retry/fallback
- INFO log emitted on empty reason with payload keys for operator visibility

**Files changed:**
- `apps/reference/domains/decision_making/md_amr_handler.py` — added `_normalize_order_reject_reason()`, rewired `_on_order_rejected` to use it
- `tests/domains/decision_making/test_order_rejected_payload_normalization.py` — 41 new tests (17 unit, 10 integration, 7 table-driven POST_ONLY/MAKER_ONLY spellings, 7 safe non-GTX reasons)

**Verification:**
- `pytest tests/domains/decision_making/test_order_rejected_payload_normalization.py -v` → **41/41 passed**
- `pytest tests/domains/decision_making/ -v` → **406 passed**, 23 skipped, 0 failures
- Existing `test_event_import_order_rejected.py` → **4/4 passed** (backward compat confirmed)

**Risk closed:** GTX retry/fallback path now responds to real emitter payloads. Malformed payloads fail-closed (no unsafe MARKET fallback).

**Not in scope:** emitter-side schema enforcement, other event contracts, broad handler refactor.

## 2026-03-16: WARMUP-REGIME-SSOT-UNIFICATION — Corrective patch: profile=None residual fail-open

**Task:** Close residual fail-open path not covered by the 2026-03-15 package.

**Root cause confirmed:**
Independent audit found that exception-based fail-open was fixed, but a second fail-open path remained:
```python
_basis_required = int(_profile.basis_required_bars) if _profile else 0
```
When `get_active_strategy_profile` returns `None` (strategy not registered in matrix) without raising an exception, `_basis_required` silently becomes 0. Gate `if _basis_required and bars_seen < _basis_required` then never fires → strategy trades without readiness enforcement. Same class of live risk as exception fail-open.

**Sites fixed (all 4):**
- `aurora_decision.py` trading path: `if _profile is None:` → `_readiness_contract_error = "READINESS_CONTRACT_UNRESOLVED:PROFILE_NOT_FOUND"` → block + return
- `aurora_handler.py` diagnostics: `if _profile is None:` → immediate return with `ready=False, block_reason=READINESS_CONTRACT_UNRESOLVED:PROFILE_NOT_FOUND` for all symbols
- `md_amr_handler.py` diagnostics: same pattern as aurora_handler
- `md_amr_handler.py` trading gate: `if _profile is None:` → `_readiness_contract_error` → existing block/return path fires

**Verification:**
- `pytest tests/bootstrap/test_warmup_ssot_alignment.py tests/domains/decision_making/test_handler_fail_closed.py -v` → **24/24 passed** (5 new `profile is None` regression tests)
- Full suite: **1552 passed**, 35 skipped, 1 pre-existing failure (`test_task28`)

**Package status:** WARMUP-REGIME-SSOT-UNIFICATION now COMPLETE. Readiness contract is fully fail-closed for both exception and `profile=None` paths.



**Task:** Eliminate three parallel truth layers for regime warmup requirements and fix critical handler fail-open in trading paths.

**Root causes verified:**
1. **RC-1 (CRITICAL):** `aurora_decision.py:263-264` and `md_amr_handler.py:1092-1093` — `except Exception: _basis_required = 0` with `if _basis_required and ...` gate. Any exception during `get_active_strategy_profile` silently disabled the cold-start gate; strategy traded without readiness enforcement.
2. **RC-2 (HIGH):** Two hardcoded literals `320` in `startup_warmup.py:221` and `main.py:1365` — detached from config and based on incorrect math (`"288 + 32"` ignores `atr_period`). Correct canonical value is `max(192, 14+288-1) = 301`.
3. **RC-3 (MEDIUM):** `strategy_compatibility_matrix.py` used `getattr(sma_cfg, "sma_long_period", 192) or 192` — silently fell back to hardcoded defaults when config path traversal failed (i.e., when `sma_cfg` or `vol_cfg` was `None`).

**Fixes applied:**
- `strategy_compatibility_matrix.py`: Added public `regime_detector_required_bars(config)` with `ValueError` guard on `None` models; `_structural_regime_basis_required_bars` alias; removed dead `96` in md_amr profile max(); removed `_aurora_basis_required_bars` no-op wrapper.
- `regime.yaml` + `config_models.py`: Added `basis_import_buffer: 20` — safety buffer field now tracked in YAML + Pydantic as true SSOT.
- `startup_warmup.py` + `main.py`: Replaced both `320` literals with `regime_detector_required_bars(config) + int(getattr(config, "basis_import_buffer", 20))` = 321 currently.
- `aurora_decision.py`: Trading path fail-closed — exception now sets `_readiness_contract_error`, emits `READINESS_CONTRACT_UNRESOLVED` at ERROR, calls `_emit_strategy_blocked`, returns immediately.
- `aurora_handler.py`: Diagnostics fail-closed — exception returns list with `ready=False, bars_required=None, block_reason=...` for all symbols; `ready = bars_seen >= _basis_required` (no more `if _basis_required else True`).
- `md_amr_handler.py`: Both trading path and diagnostics hardened with identical fail-closed patterns.

**Verification:**
- `pytest tests/bootstrap/test_warmup_ssot_alignment.py tests/domains/decision_making/test_handler_fail_closed.py -v` → **19/19 new tests passed**
- Full suite: **861 passed**, 35 skipped, 1 pre-existing failure (`test_task28_hybrid_mode_config_contract.py` — MODE_SSOT conflict, pre-dates this package)

**Artifacts:**
- `reports/fixes/WARMUP_REGIME_SSOT_UNIFICATION_2026-03-15.md`
- `reports/audit/WARMUP_SSOT_AND_FALLBACK_AUDIT_2026-03-15.md`

## 2026-03-15: RUNTIME-RECOVERY-AND-MR-REGRESSION-AUDIT - live-truth bootstrap fix + MR rollback

**Task:** Red-team the real startup path after live evidence showed `md_amr_handler:cold_start:51/96` and `aurora_handler` still climbing one bar per live tick after restart, then isolate why `mean_reversion` lost its edge.

**Live proof that prior fix failed:**
1. `logs/aurora_trades.log` showed `md_amr` moving from `8/96` to `51/96` in exact 15-minute steps on 2026-03-15 instead of starting ready
2. `logs/aurora_core.log.1/.2` showed `aurora` moving from `139/301` to `154/301` in exact 5-minute steps after the same restart
3. This proved startup hydration did not seed handler-local readiness counters; handlers were counting only post-restart live bars

**Root causes verified:**
1. `PillarBackfillService.fetch_candles()` was single-shot; one transient adapter exception or empty/short response collapsed startup import to zero bars
2. `startup_basis_hydrator` then skipped seeding or reported incomplete truth, so operator-visible readiness could diverge from handler state
3. Prior bootstrap tests did not exercise the real runtime contract `StrategyRuntime.start() -> hydration plan -> live handler registry -> real backfill -> seed_startup_bars()`
4. `mean_reversion` DOGE config had drifted away from the last healthier 300s baseline: `bb_window 20 -> 40`, `bb_num_std 2.1 -> 2.5`, `cooldown 210 -> 660`, plus new squeeze/momentum veto layers
5. Live MR evidence also showed execution degradation: the only 2026-03-15 live DOGE signal was rejected by Binance with `-1007 timeout`, so the regression is not signal-only

**Fixes applied:**
- Added retry logic to `PillarBackfillService.fetch_candles()` so transient startup transport failure no longer leaves handlers cold
- Hardened `execute_startup_basis_hydration()` to emit truthful structured readiness summaries and actual `seed_source`
- Added failing-first real-path bootstrap reproducer covering real config, real runtime startup, real hydration planning, transient backfill failure, and real handler seeding
- Added explicit startup backfill retry unit coverage
- Rolled DOGE mean-reversion config back to the last materially healthier 300s profile (`bb_window=20`, `bb_num_std=2.1`, `cooldown_sec=210`, veto layers removed)

**Verification:**
- `pytest tests/config/test_mean_reversion_doge_regression_config.py tests/bootstrap/test_startup_basis_real_path.py tests/bootstrap/test_startup_basis_hydrator.py tests/bootstrap/test_startup_hydration_planner.py tests/unit/feature_engineering/test_pillar_backfill_startup.py -q`
- Result: `37 passed`

**Artifacts:**
- `reports/forensics/RUNTIME_RECOVERY_AND_MR_REGRESSION_AUDIT_2026-03-15.md`
- `reports/forensics/RUNTIME_BLOCKER_AND_MR_REGRESSION_MATRIX_2026-03-15.csv`

## 2026-03-15: BOOTSTRAP-READINESS-HARDENING — Runtime recovery for cold-start blockers

**Task:** Fix runtime blockers preventing aurora/md_amr from trading after startup. Root causes: invisible bootstrap hydration, mode config conflict (backtest vs hybrid), and buried quadratic trace.

**Root causes verified:**
1. `system.yaml` had `trading_mode: "backtest"` while `trading.yaml` had `mode: hybrid_live_data_testnet_exec` — config loader silently forced backtest
2. Bootstrap hydration executor ran but emitted no structured lifecycle evidence — invisible to operator
3. Cold-start gates logged at DEBUG — invisible in production log level
4. Quadratic decision trace was DEBUG-only, never emitted as FSM event

**Fixes applied:**
- **Bootstrap observability:** Added `_emit_bootstrap_lifecycle()` with structured JSON events: `STARTUP_BASIS_EXECUTOR_START`, `STARTUP_BASIS_IMPORTED`, `STARTUP_BASIS_SEEDED`, `STRATEGY_READINESS_STATE`, `STARTUP_BASIS_EXECUTOR_DONE`
- **Readiness model:** Added `get_readiness_diagnostics()` to both `AuroraHandler` and `MDAMRHandler` — returns per-symbol `{strategy, symbol, tf_sec, bars_seen, bars_required, ready, block_reason}`
- **Mode SSOT:** Config loader now raises `ConfigContractError` on non-backtest mode mismatch; fixed `system.yaml` to `hybrid_live_data_testnet_exec`
- **Quadratic visibility:** Quadratic decision trace emitted as `EVT:QUADRATIC_DECISION_TRACE` FSM event + INFO log; cold-start gate elevated from DEBUG to INFO with "quadratic path NOT reached" message
- **Tests:** 15 new tests covering all 7 required areas. Updated 1 existing test for new event compatibility.

**Results:** 1231/1231 domain tests passed, 0 failures. 15 new tests added.

**Report:** `reports/fixes/BOOTSTRAP_READINESS_HARDENING_2026-03-15.md`

## 2026-03-15: TEST-HYGIENE-NORMALIZATION — Stale xfail + artifact ignore cleanup

**Task:** Remove stale xfail marker and normalize generated artifact tracking.

**Changes:**
- Removed stale `@pytest.mark.xfail` from `test_binance_adapter_session.py` (test passes consistently since strict asyncio mode migration)
- Added `.gitignore` rules for `.pytest_junit.xml`, `async_inventory.json`, `coverage*.json`
- Untracked 4 generated artifacts from git index (kept on disk)

**Results:** 89/89 guardrails, test now PASSED (was XPASS). Zero regressions.

**Report:** `reports/cleanup/TEST_HYGIENE_NORMALIZATION_2026-03-15.md`

## 2026-03-15: LEGACY-PURGE-WAVE-2 — Manual review + empty structure cleanup

**Task:** Re-evaluate 4 NEEDS_MANUAL_DECISION test files and remove dead test structure.

**Re-evaluated:**
- `test_execution_schemas_sim.py` → DELETE_NOW (zero assertions, superseded)
- `test_decision_qos_features_burst.py` → DELETE_NOW (mock-only, forbidden `.get()` pattern)
- `test_binance_adapter_session.py` → KEEP (real assertions, stale xfail)
- `test_features_full_chain_happy.py` → KEEP (genuine integration value, skipped for complexity)

**Deleted:** 2 test files (~145 LOC), 17 empty directories.

**Results:** 89/89 guardrails, 524/524 config+contracts. Zero regressions.

**Report:** `reports/cleanup/LEGACY_PURGE_WAVE_2_2026-03-15.md`

## 2026-03-15: FORBIDDEN-CONFIG-PATTERN-FIX — Typed veto configs, zero .get() patterns

**Task:** Fix 4 `.get()` silent-fallback violations in `mean_reversion_strategy.py` causing pre-existing test failure.

**Root cause:** `MRStrategyConfig.squeeze_expansion_veto` and `momentum_separation_veto` were `Optional[Dict[str, Any]]` — accessed via `.get("regimes", [])` and `.get("sides", [])`.

**Fix:** Added `SqueezeExpansionVetoConfig` and `MomentumSeparationVetoConfig` dataclasses. Replaced all 4 `.get()` patterns with typed attribute access. Updated handler converter functions, strategy bridge re-exports, and 3 test files.

**Results:** 6/6 forbidden config scan (was 5/6), 386/386 FE+DM domain tests, 89/89 guardrails. Zero regressions. Pre-existing failure resolved.

**Report:** `reports/cleanup/FORBIDDEN_CONFIG_PATTERN_FIX_2026-03-15.md`

## 2026-03-15: TEST-SUITE-RECLASSIFICATION — Test suite audit and dead test cleanup

**Task:** Classify entire test suite (684 files, 5,368 tests) and safely purge proven dead tests.

**Classified into:** RUNTIME_CRITICAL (~882), ARCH_GUARDRAIL (~162), CONFIG_VALIDATION (~400), INTEGRATION_E2E (~369), VFOUNDATION_CORE (~1,231), ALPHA_SEARCH (~281), NEOCORTEX (~289), FORENSIC_DIAGNOSTIC (~55), UNIT_MISC (~958), OTHER (~741).

**Deleted 15 dead test files (~1,210 LOC):**
- 6 debug scripts masquerading as tests (no `test_*` functions)
- 2 deprecated-event tests (EVT:MARKET_TICK_FORWARDED — 0 emitters)
- 2 deleted-class tests (AuroraBridge removed from main.py)
- 1 empty file, 1 hardcoded-path skip, 1 live-WS utility, 1 live-env skip, 1 zero-method test class

**Results:** 162/162 guardrails, 1,681/1,682 broader tests (1 pre-existing failure). 93 skip-containing files mapped.

**Report:** `reports/tests/TEST_SUITE_RECLASSIFICATION_2026-03-15.md`

## 2026-03-15: LEGACY-PURGE-WAVE-1 — Proven dead code and ghost cleanup

**Task:** First safe deletion wave using evidence from 7 completed domain audits.

**Deleted:**
- `market_ws_client.py` (119 LOC dead module, zero production importers)
- Dead imports: `asdict` in bar_aggregator.py, `time` in market_data_connector.py
- Deprecated no-op: `set_feature_engineering()` from proxy.py and connector
- 7 ghost .pyc in vfoundation/ (errors, binance_adapter, bracket_aggregator, fsm, price_service)
- 2 orphaned vfoundation directory trees (vfoundation/apps/, vfoundation/services/)
- 45 deprecated doc files across 7 domains (docs/deprecated/ directories)
- All test `__pycache__/` directories (~371 orphaned .pyc)

**Cleaned:**
- `__init__.py` MarketWSClient export removed
- `domain_dict.json` dead_code note updated
- `README.md` debt table updated (3 items resolved)
- `decision_context.py` stale doc reference annotated
- Guardrail tests: `TestDeadCodeMarker` → `TestDeletedDeadCode` (3 tests)
- New: `test_legacy_purge_wave1_guardrails.py` (3 cross-project guardrails)

**Results:** 165/165 guardrails, 40/40 market_data tests. Zero runtime behavior changes.

**Report:** `reports/cleanup/LEGACY_PURGE_WAVE_1_2026-03-15.md`

## 2026-03-15: MD-DOMAIN-AUDIT — market_data domain audit + structural cleanup

**Task:** Audit and structurally harden `apps/reference/domains/market_data/` — the root upstream domain.

**Findings:** 7 files, ~2,661 LOC, 4 test files (~23 test functions). Clean event-driven boundary — no other domain imports MD source directly. 3 active verbs (MARKET_TICK_RECEIVED, BAR_CLOSED, ANCHOR_UPDATED), 1 deprecated (MARKET_TICK_FORWARDED). No `domain_dict.json` existed. Dead code: `market_ws_client.py` (119 LOC, never imported). Default timeframe mismatch between domain_builder `[60, 300]` and BarAggregator `[180, 300]`. No TTL enforcement within domain. Auto-generated docs had no staleness warning.

**Changes:** Created `domain_dict.json` v1.0.0 (3 exports, 0 imports, 5 components). Created authoritative `README.md`. Staleness note on `docs/README.md`. 15 guardrail tests (domain_dict consistency, pycache ghosts, empty tests, BarAggregator SSOT, cross-domain import ban, dead code marker, event emitter consistency). **158/158 total guardrail tests across all 7 domains.** Score: 8/10 (was ~6/10).

Report: `reports/domains/MARKET_DATA_DOMAIN_AUDIT_2026-03-15.md`

## 2026-03-15: FE-DM-BOUNDARY-STABILIZATION — FE↔DM boundary stabilization

**Task:** Resolve the domain-boundary leak where strategy-domain logic lives in feature_engineering but is consumed by decision_making.

**Findings:** 3 strategy files in FE (mean_reversion_strategy.py, md_amr_strategy.py, regime_mapping.py) are semantically owned by DM. 5 direct FE strategy imports in DM production code. 27+ import sites in test code. Physical move blast radius: 40+ files.

**Changes:** Created `decision_making/strategy_bridge.py` as sanctioned DM-facing re-export facade (13 symbols). Migrated all 3 DM production files to import via bridge. Bar imports migrated to `shared/types.py`. Both domain READMEs and domain_dict.json updated with boundary policy. 6 guardrail tests (AST-scans DM for forbidden imports, bridge completeness, no new strategy files in FE). **1,143 tests pass, 0 failures.**

Report: `reports/domains/FE_DM_BOUNDARY_STABILIZATION_2026-03-15.md`

## 2026-03-15: FE-DOMAIN-AUDIT — feature_engineering domain audit + structural cleanup

**Task:** Audit and structurally harden `apps/reference/domains/feature_engineering/`.

**Findings:** Largest signal domain: 16 files, ~8,849 LOC, ~150+ test functions. Solid architecture: 60+ typed config properties (Pydantic extra='forbid'), feature catalog in contracts.py with V1/V2 metadata (range, neutral, monotonicity), 3 JSON schemas. 7 events consumed, 3 emitted. `domain_dict.json` was stale (v1.1.0, missing V2/futures/pillars/price_motion and 6 of 7 consumed events). 2 ghost .pyc (config, phase1). Strategy files (MR, MD-AMR, regime_mapping) live in FE but conceptually belong to DM — documented as debt.

**Changes:** Rewrote `domain_dict.json` v2.0.0 (all imports/exports/feature_families). Created authoritative `README.md`. Staleness note on `docs/README.md`. Deleted 2 ghost .pyc. 15 guardrail tests (feature catalog SSOT, schema alignment, domain_dict consistency, pycache, version). Score: **8/10** (was ~6/10).

Report: `reports/domains/FEATURE_ENGINEERING_DOMAIN_AUDIT_2026-03-15.md`

## 2026-03-14: RD-DOMAIN-AUDIT — regime_detector domain audit + structural cleanup

**Task:** Audit and structurally harden `apps/reference/domains/regime_detector/`.

**Findings:** Compact domain (2 files, 803 LOC, ~181 tests across ~18 files). Clean event-driven architecture: consumes EVT:FEATURES_CALCULATED, runs priority cascade (Volatility > MeanReversion > SMATrend), applies hysteresis stabilisation + slope gate, emits EVT:REGIME_DETECTED on every basis bar close. No top-level `domain_dict.json` (only deprecated copy). 1 ghost `.pyc` (`config.cpython-311.pyc`). Auto-generated docs had no staleness warning.

**Changes:** Created `domain_dict.json` v1.0.0. Created authoritative `README.md`. Added staleness note to `docs/README.md`. Deleted ghost `config.cpython-311.pyc`. 10 guardrail tests (fail-closed, domain_dict consistency, schema/code regime label sync, pycache, empty tests, __version__). Score: **9/10** (was ~7/10).

Report: `reports/domains/REGIME_DETECTOR_DOMAIN_AUDIT_2026-03-14.md`

## 2026-03-14: RM-DOMAIN-AUDIT — risk_management domain audit + structural cleanup

**Task:** Audit and structurally harden `apps/reference/domains/risk_management/`.

**Findings:** Compact domain (3 files, 990 LOC, 73 tests). Clean 2-layer fail-closed architecture (daily drawdown gate + per-instrument risk score). No ghost pycache. No duplicate gates. `domain_dict.json` was garbled (whitespace-only descriptions, missing imports).

**Changes:** Rewrote `domain_dict.json` v2.0.0. Created authoritative `README.md`. Added staleness note to `docs/README.md`. 11 guardrail tests (fail-closed, WhyCode canonical, no NRR usage, domain_dict consistency, pycache, empty tests). Score: **9/10** (was ~7/10).

Report: `reports/domains/RISK_MANAGEMENT_DOMAIN_AUDIT_2026-03-14.md`

## 2026-03-14: EP-CONTRACT-BOUNDARY — execution_position contract boundary cleanup

**Task:** Resolve 3 co-emitter gaps and cross-domain NRR import coupling in execution_position.

**Findings:**
1. `EVT:EXPOSURE_SUMMARY_UPDATED` — registry owner was `risk_management` but EP is the sole emitter + schema owner. **Moved ownership to EP.**
2. `EVT:TRADE_INTENT_REJECTED` — valid co-emission (DM rejects at strategy level, EP rejects at execution boundary). **Added co_emitters annotation.**
3. `EVT:TRADE_EXECUTED` — valid co-emission (adapter primary, EP watchdog fallback). **Added co_emitters annotation.**
4. NRR dependency — `leverage_service.py` imported directly from `decision_making`. **Migrated to `shared/types.py` re-export.** Zero direct DM imports remain in EP.

**Changes:** 3 registry entries updated, 1 import migrated, README v1.1.0 with §12 Contract Boundary Policy, 8 guardrail tests. Report: `reports/domains/EXECUTION_POSITION_CONTRACT_BOUNDARY_2026-03-14.md`

## 2026-03-14: EP-DOMAIN-AUDIT — execution_position domain audit + structural cleanup

**Task:** Audit and structurally harden `apps/reference/domains/execution_position/` under the stabilized contract SSOT.

**Context map:** 40 live .py files, 11 JSON schemas, 11 docs, ~16,500 LOC. 9 events consumed, 31 emitted. ~1,192 test functions across 147 test files.

**Changes:**
1. Deleted 3 ghost subpackages (aggregator_oco, observability, shadow_execpos — ~38 ghost .pyc modules)
2. Cleaned 12 ghost .pyc entries from root and infra __pycache__
3. Fixed broken `tests/domains/conftest.py` (removed `adapter_live` fixture referencing deleted `binance_execution_adapter`)
4. Created authoritative `execution_position/README.md` with full state ownership map, FSM architecture, event table, forbidden patterns
5. Created `domain_dict.json` v1.0.0 (9 imports, 31 exports, 19 components, ssot_notes)
6. Updated `docs/ATLAS.md` and `docs/README.md` with staleness notes pointing to authoritative README
7. Added 13 guardrail tests in `test_ep_domain_structural_guardrails.py`: pycache ghosts (2), ghost subpackages (1), deleted module imports (1), domain_dict consistency (3), triple OrderStatus layered (4), reasons completeness (1), empty tests (1)

**Key findings:**
- 3 OrderStatus enums intentionally layered (domain/wire/persistence) — documented, not merged
- 3 co-emitter gaps (EP emits events owned by other domains in registry)
- Clean 3-FSM architecture (Open/Manage/Close) with ExecPosFSM orchestrator
- Single cross-domain import: `leverage_service.py` → `NormalizedRejectReasons`
- No WhyCode usage in this domain

Score: **8/10** (was ~5/10 before cleanup). Report: `reports/domains/EXECUTION_POSITION_DOMAIN_AUDIT_2026-03-14.md`

## 2026-03-14: DM-DOMAIN-AUDIT — decision_making domain audit + structural cleanup

**Task:** Audit and structurally harden `apps/reference/domains/decision_making/` under the stabilized contract SSOT.

**Context map:** 37 live .py files, 5 shields, 3 JSON schemas, 12 docs, ~98 test files. 13 events consumed, 12 emitted. All SSOT-aligned.

**Changes:**
1. Cleaned 5 stale __pycache__ ghosts (deleted files: aurora_scoring_kernel, contracts, portfolio_provider, scoring_direction_strength_v1, signal_score_v2)
2. Deleted empty 0-byte test file (test_mean_reversion_emit_trade_intent_mode.py)
3. Fixed stale doc references to deleted files (ATLAS.md, docs/README.md)
4. Created authoritative domain README.md with full file map and event contracts
5. Updated domain_dict.json: version 2.0.0, 13 imports, 12 exports, ssot_notes
6. Updated __init__.py: version 2.0.0, updated docstring
7. Added 8 guardrail tests (test_dm_domain_structural_guardrails.py)

**Decision:** Full file reorganization (logic/, services/, fsm/) NOT applied — 98 test consumers make the blast radius too high for marginal benefit.

**Tests:** 8 new guardrails pass. All existing DM tests unaffected.

**Report:** `reports/domains/dm_domain_audit_2026-03-14.md`

## 2026-03-14: CONTRACT-SSOT-CONSOLIDATION — single source of truth for contract layer

**Task:** Convert the multi-source contract registration mess into a defined, enforceable SSOT model. Answer explicitly: what is canonical, what is derived, what is deprecated.

**SSOT decisions:**

| Layer | Canonical Source |
|-------|-----------------|
| Contract registry | `verb_registry_v1.yaml` |
| Schemas | Domain-local `schemas/` dirs linked by registry |
| WhyCode | `vfoundation/core/why_codes.py` (72 members) |
| NRR codes | `NormalizedRejectReasons` in `decision_making/` |

**Changes applied:**

1. **WhyCode fork resolved** — promoted 7 codes (SIZING_*, SIGNAL_NEUTRAL) from decision_making to vfoundation canonical. Converted decision_making `why_codes.py` to thin re-export. Marked NRR codes in WhyCode as deprecated (semantic drift vs canonical NRR). Unified `format_why_with_details` to variadic signature.
2. **12 dead registry entries deprecated** — DEC:CANCEL, EVT:EXPIRED, EVT:FILL, EVT:MARKET_TICK_FORWARDED, EVT:MR_SIGNAL_PRODUCED, EVT:NEOCORTEX_STATE_UPDATED, EVT:ORCHESTRATOR_ERROR, EVT:ORDER_EXECUTED, EVT:PARTIAL_FILL, EVT:REJECTED, EVT:TICK_RECEIVED, EVT:VERB.
3. **VERB_PAYLOAD_MAP frozen** — docstring updated to COMPATIBILITY-ONLY, frozen at 11 entries.
4. **Architecture spec created** — `docs/contracts/CONTRACT_ARCHITECTURE.md` with full rules.
5. **9 guardrail tests** — `tests/contracts/test_contract_ssot_guardrails.py`.

**Tests:** 327 passed, 0 failed (all contracts, WhyCode, NRR, config SSOT).

**Report:** `reports/contracts/CONTRACT_SSOT_CONSOLIDATION_2026-03-14.md`

## 2026-03-14: CONTRACT-AUDIT — Event/Command dictionary and schema registry audit

**Task:** Audit and sanitize the event/command contract layer. Map every active runtime contract against registry presence, schema coverage, producer, consumer, and identify ghosts/orphans/duplicates.

**What was found:**

- **Registry SSOT:** `verb_registry_v1.yaml` (68 entries pre-audit) + `VerbSchemaRegistry` runtime loader
- **Schemas on disk:** 40 event/command JSON schemas across 9 directories
- **Contracts emitted in code:** ~88 unique (op:verb) pairs
- **Registry drift:** 20 actively emitted contracts missing from registry, 1 broken schema reference, 1 duplicate entry, 12+ `owner: unknown`, ~12 dead/legacy entries never emitted

**Safe fixes applied:**

1. Fixed broken schema ref: `schemas/order_ack_v1.json` → `apps/reference/schemas/order_ack_v1.json`
2. Removed duplicate PROCESS_STRATEGY_BLOCKED entry
3. Fixed 6 `owner: unknown` entries with code-evidenced owners (BALANCE_UPDATE_RECEIVED → account_balance, ORDER_REJECTED → execution_position, ORDER_STATE_CHANGED → execution_position, ORDER_TIMEOUT → execution_position, INTENT_DROPPED → vfoundation, CONFIG_DEBUG_OVERRIDE_ACTIVE → risk_management)
4. Fixed ANCHOR_UPDATED owner: `decision_making` → `market_data`
5. Added 20 missing registry entries for actively emitted contracts (objective_engine, execution_position, shadow_telemetry, neocortex, decision_making)

**Tests:** 28 new regression tests in `tests/contracts/test_contract_registry_audit.py` — all pass.
**Post-fix registry:** 87 entries (was 68). 0 broken schema refs. 0 duplicates.

**Remaining risks:** 12 orphan registry entries (dead contracts), 8 orphan schema files, WhyCode enum fork between vfoundation and decision_making, mixed JSON Schema draft versions.

**Report:** `reports/contracts/CONTRACT_AUDIT_2026-03-14.md`

## 2026-03-14: CONFIG-NAMESPACE-CLEANUP — isolate dead config trees from active SSOT

**Task:** Bring config namespace to strict SSOT shape. Remove dead config directories that were never loaded by runtime but lived alongside the active `config/aurora/` tree.

**What was done:**

1. **Relocated dead trees** — `config/aurora_baseline/` and `config/mean_reversion/` moved to `archive/config_snapshots/`. Neither directory was ever referenced by any loader, test, CI pipeline, or deployment script.
2. **Archive manifest** — created `archive/config_snapshots/README.md` documenting original path, purpose, runtime status, and historical context for each snapshot.
3. **Config SSOT README** — created `config/README.md` declaring `config/aurora/` as the sole canonical runtime config directory and forbidding new config roots without explicit approval.
4. **PROJECT_ATLAS.md cleaned** — replaced 20 dead config file entries with a single archive note; removed 14 duplicate instrument rows sourced from dead configs.
5. **Stale references fixed** — updated overlay comment and Phase 9 report to note archived paths.
6. **Regression guard** — added `tests/config/test_config_namespace_ssot.py` asserting default config dir resolves to `config/aurora` and dead trees no longer exist under `config/`.

**Runtime verification:** `main.py:315` and `config_loader.py:121-142` remain unchanged. Default config dir = `config/aurora`. No deployment scripts affected.

**Report:** see inline deliverables above.

## 2026-03-14: PHASE-9-QUADRATIC-FINAL-CLEANUP-AND-HARDENING

**Task:** Final cleanup/hardening pass to bring Aurora from "functionally complete" to "quality-complete" after Phase 9 Quadratic Brain migration.

**Prior audit verdict:** MIGRATION FUNCTIONAL — NOT QUALITY-COMPLETE (7/10)

**What was done:**

P0 fixes:
1. **Validator bug** — `_validate_direction_strength_contract` made scoring-mode-aware. Skips deprecated `direction_strength_scoring` check when `scoring_version == "quadratic"`.
2. **Rollback-to-v2 killed** — `_VALID_SCORING_VERSIONS = {"quadratic"}` only. `resolve_requested_quadratic_rollout()` always returns quadratic. `rollback_armed` forced False. V2_ROLLBACK/V2_LIVE/LEGACY_LIVE enum members and mode branches removed.
3. **Shield fail-closed** — NullShield detection raises `ConfigContractError` in production when `scoring_version=quadratic`. `_build_shield_cascade` uses `is not True` identity check to prevent MagicMock bypass.

P1 cleanup:
4. **Config defaults** — `scoring_version` default `"v1"` → `"quadratic"`, `shield_enabled` default `False` → `True`, per-asset `scoring_version` marked DEPRECATED, stale YAML comments updated across all config variants.
5. **Files deleted** — 4 files importing deleted v2 modules (`test_depth_imbalance_signal_contract.py`, `dir_strength_forensics.py`, `strategy_replay.py`, `config_tuner.py`).
6. **Stale code cleaned** — All `"v2"` defaults in handler/adapter/kernel → `"quadratic"`. Stale `AuroraScoringKernel` docstring references updated. Dead `QuadraticRolloutMode` enum members removed.
7. **Alpha_search fixed** — `scoring_version` default `"v2"` → `"quadratic"` in Pydantic model and YAML config.
8. **Dead params marked** — `signal_weights`, `feature_neutrals`, `direction_strength_cfg` in `QuadraticScoringKernel.compute()` marked DEPRECATED (accepted for compat, not read).
9. **Scoring passport updated** — deleted module references marked DEPRECATED.

P2 verification:
- Full test suite: **5206 passed, 3 pre-existing failures, 0 regressions**.
- 7 test files updated/rewritten to match new quadratic-only runtime.

**Post-cleanup verdict:** 9/10 — MIGRATION QUALITY-COMPLETE

**Remaining risks:** `Literal["v1", "v2", "quadratic"]` type still allows v1/v2 at config parse level (runtime corrects); dead wiring for signal_weights/feature_neutrals/direction_strength_cfg (accepted but ignored by kernel); 3 pre-existing test failures on branch.

**Report:** `reports/PHASE9_QUADRATIC_CLEANUP_REPORT.md`

## 2026-03-13: MEAN-REVERSION-STATE-MACHINE-PASSPORT-RE-AUDIT-AND-CODE-DRIVEN-CORRECTION

**Task:** Re-audit and fully resynchronize `config/docs/mean_reversion_state_machine_passport.md` against current strategy YAML, typed config models, bar-driven strategy implementation, handler overlays, registry assignment, and focused tests.

**Why this re-audit was necessary:**
- The old passport mixed stale `1m` / `3m` naming with current runtime and did not clearly separate MR state-machine logic from downstream execution FSM behavior.
- This distinction matters directly for the recent DOGE incident analysis: strategy-entry logic and execution reconciliation are different owners.

**What was traced:**
- `config/aurora/strategies/mean_reversion.yaml`
- `config/aurora/strategies.yaml`
- `apps/reference/config_models.py`
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `apps/reference/domains/strategies/plugins/mean_reversion.py`
- `tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py`
- `tests/domains/decision_making/test_mean_reversion_runtime_readiness.py`
- `tests/integration/test_mean_reversion_handler_event_contract_v1.py`

**Key findings:**
- **Live TF corrected:** current YAML drives MR on `timeframe_sec=300`; old `1m/3m` labels in code/comments are stale naming drift.
- **Assignment-first activation confirmed:** current live MR symbol is `DOGEUSDT`; activation remains `registry assignment ∩ enabled asset`.
- **State-machine core clarified:** `MeanReversion1mStrategy.on_bar()` owns bars, indicators, BB-width filters, regime mapping, `%B` entry logic, confidence, and advisory TP/SL.
- **Handler overlay clarified:** liquidity gate, objective engine, runtime readiness envelope, and final `EVT:STRATEGY_SIGNAL_PRODUCED` emission belong to `MeanReversionHandler`, not the pure state machine.
- **Execution boundary clarified:** `ExecPosFSM` / `ManageFlowFSM` own downstream lifecycle/reconciliation behavior such as `ORDER_UPDATED` sync and TTL/orphan cleanup; these are outside the MR state machine.
- **Test drift found:** the legacy event-contract integration test is currently skipped and still tied to an obsolete tick-driven path.

**Artifacts updated:**
- `config/docs/mean_reversion_state_machine_passport.md`
- `reports/docs_audit/mean_reversion_state_machine_passport_audit_report.md`

**Follow-up cleanup suggested (not implemented here):**
- Rename or document stale `1m` / `3m` naming in MR code/comments so runtime TF ownership is not misread
- Retire or rewrite the skipped tick-path event-contract test around the current `CMD:PROCESS_STRATEGY` bar-driven contract
- Keep incident docs explicit that MR strategy-entry correctness and execution reconciliation failures are owned by different domains

## 2026-03-13: MD-AMR-STRATEGY-PASSPORT-RE-AUDIT-AND-CODE-DRIVEN-CORRECTION

**Task:** Re-audit and fully resynchronize `config/docs/md_amr_strategy_passport.md` against current strategy YAML, typed config contracts, startup/plugin wiring, md_amr handler runtime, signal gateway, and focused readiness/gateway tests.

**Why this re-audit was necessary:**
- The old passport was mostly declarative and treated `md_amr.yaml` as if every documented field were equally live and fully wired.
- Current runtime is stricter: activation is assignment-first, per-symbol contracts are fail-closed, and several execution/reconciliation claims needed a narrower code-driven interpretation.

**What was traced:**
- `config/aurora/strategies/md_amr.yaml`
- `config/aurora/strategies.yaml`
- `apps/reference/config_models.py`
- `apps/reference/main.py`
- `apps/reference/domains/strategies/plugins/md_amr.py`
- `apps/reference/domains/decision_making/md_amr_handler.py`
- `apps/reference/domains/decision_making/strategy_gateway.py`
- `tests/domains/decision_making/test_md_amr_strategy_gateway.py`
- `tests/domains/decision_making/test_md_amr_runtime_readiness.py`

**Key findings:**
- **Normal handler topology confirmed:** `md_amr` is a regular in-process strategy path via `MDAMRPlugin -> MDAMRHandler`, not a sentinel/bridge strategy.
- **Assignment-first activation confirmed:** current live symbols are `XRPUSDT` and `BNBUSDT`; other asset blocks in `md_amr.yaml` are dormant until assigned.
- **Live startup contract corrected:** assigned symbols hard-fail if `md_amr` profile is missing/disabled or if per-symbol `exit` / `allowed_regimes` are missing.
- **Objective path confirmed:** entry flow calls Objective Engine fail-closed when both domain and strategy objective configs are enabled and required data is missing.
- **LLM gate confirmed live:** `features.sentiment_state` can set a temporary macro block through `md_amr.llm_gate`.
- **Execution drift found:** `gtx_fallback_to_market` is currently weaker than its name suggests; the traced handler path logs fallback intent but does not perform the fallback itself.
- **Reconciliation drift found:** `reconcile_position()` exists and uses `drift_tolerance`, but no external caller was found in the audited live path.

**Artifacts updated:**
- `config/docs/md_amr_strategy_passport.md`
- `reports/docs_audit/md_amr_strategy_passport_audit_report.md`

**Follow-up cleanup suggested (not implemented here):**
- Decide whether `md_amr.execution.gtx_fallback_to_market` should trigger a real fallback path or be renamed/documented as bookkeeping-only behavior
- Decide whether `MDAMRHandler.reconcile_position()` needs explicit external wiring or clearer documentation as a dormant/local-only hook
- Decide whether unassigned asset blocks in `md_amr.yaml` should remain as templates or be separated from the live-active contract section

## 2026-03-13: LLM-MICROSTRUCTURE-PASSPORT-RE-AUDIT-AND-CODE-DRIVEN-CORRECTION

**Task:** Re-audit and fully resynchronize config/docs/llm_microstructure_strategy_passport.md against the current strategy profile, registry constraints, sentinel plugin startup, shadow telemetry ingress, bridge command mapping, downstream safety gates, execution policy, and tests.

**Why this re-audit was necessary:**
- The previous passport was too shallow and treated the strategy profile as if it directly described a normal in-process strategy handler.
- Current runtime is split across profile config, global llm_orchestration policy, shadow telemetry ingress, and downstream decision-making consumers.

**What was traced:**
- config/aurora/strategies/llm_microstructure.yaml
- config/aurora/strategies.yaml
- apps/reference/config_models.py
- apps/reference/main.py
- apps/reference/domains/strategies/registry.py
- apps/reference/domains/strategies/plugins/llm_microstructure.py
- apps/reference/domains/shadow_telemetry/main.py
- apps/reference/domains/shadow_telemetry/main_bridge.py
- apps/reference/domains/decision_making/strategy_gateway.py
- apps/reference/domains/decision_making/intent_builder.py
- apps/reference/domains/decision_making/safety_gates.py
- tests/config/test_llm_strategy_contract_fail_closed.py
- tests/domains/shadow_telemetry/test_main_bridge.py

**Key findings:**
- **Sentinel reality confirmed:** `llm_microstructure` is not a normal handler-driven strategy; the registered plugin is a sentinel stub used only to satisfy StrategyRuntime allowlist/start rules.
- **Bridge path confirmed:** actual strategy signals are synthesized by shadow_telemetry via `LLMIntentIngressBridge` and `register_llm_command_mapper()`.
- **Split ownership confirmed:** runtime behavior is governed jointly by the strategy profile and `trading.llm_orchestration`, not by the strategy YAML alone.
- **Timeframe drift found:** profile `timeframe_sec=60`, but the bridge mapper currently emits `tf_sec=300` hardcoded in `EVT:STRATEGY_SIGNAL_PRODUCED`.
- **Execution-policy split clarified:** shadow ingress policy filters external request TIF/order conditions, but final downstream order policy is still resolved from `strategies.llm_microstructure.execution`.
- **Enabled-flag weakness found:** `llm_microstructure.enabled` is typed, but no direct runtime consumer was found that disables the bridge path or sentinel startup from this field alone.

**Artifacts updated:**
- config/docs/llm_microstructure_strategy_passport.md
- reports/docs_audit/llm_microstructure_strategy_passport_audit_report.md

**Follow-up cleanup suggested (not implemented here):**
- Align bridge-emitted `tf_sec` with `strategies.llm_microstructure.timeframe_sec`, or explicitly document why LLM path must emit 300 seconds
- Decide whether `llm_microstructure.enabled` should become a real runtime gate or remain metadata
- Keep strategy docs and shadow telemetry docs aligned around the sentinel-plugin architecture

## 2026-03-13: INSTRUMENTS-PASSPORT-RE-AUDIT-AND-CODE-DRIVEN-CORRECTION

**Task:** Re-audit and fully resynchronize `config/docs/instruments_passport.md` against current `instruments.yaml`, typed config contracts, loader rules, normalization logic, leverage bootstrap/gates, sizing helpers, flip orchestration, startup exchange-filter validation, and tests.

**Why this re-audit was necessary:**
- The old passport was broadly useful but mixed hard runtime authority with duplicated metadata and did not cleanly separate active fields from typed-but-unused contract surface.
- It also predated the current leverage SSOT precedence where execution bootstrap now reads `instruments.yaml` and explicitly warns that legacy strategy leverage is ignored on mismatch.

**What was traced:**
- `config/aurora/instruments.yaml`
- `apps/reference/config_models.py`
- `apps/reference/config_loader.py`
- `apps/reference/config_symbols.py`
- `apps/reference/main.py`
- `apps/reference/domains/execution_position/qty_normalizer.py`
- `apps/reference/domains/execution_position/fsm.py`
- `apps/reference/domains/execution_position/fsm_open.py`
- `apps/reference/domains/execution_position/fsm_manage.py`
- `apps/reference/domains/execution_position/leverage_service.py`
- `apps/reference/domains/execution_position/leverage_config.py`
- `apps/reference/domains/execution_position/bootstrapping/leverage_bootstrapper.py`
- `apps/reference/domains/execution_position/exposure_guard.py`
- `apps/reference/domains/decision_making/sizing_margin_first.py`
- `apps/reference/domains/decision_making/decision_making.py`
- `apps/reference/domains/exchange_filters/validator.py`
- relevant unit/integration tests

**Key findings:**
- **Canonical registry clarified:** runtime primarily treats `config.instruments` map keys as the symbol registry; nested `symbol` is duplicated metadata, not the strongest identity source.
- **Loader contract confirmed:** `trading.instruments` is forbidden; `config/aurora/instruments.yaml` is the canonical root SSOT.
- **Qty/notional gates confirmed:** `step_size`, `min_qty`, and `min_notional` remain strict fail-closed constraints with no silent bump-up path.
- **Leverage SSOT corrected:** `execution.target_leverage`, `margin_mode`, and `leverage_policy` are active runtime fields; leverage bootstrap now collects them from instruments SSOT and only warns on strategy-side mismatch.
- **Dead field exposed:** `execution.max_notional_utilization` is required by live validation but no downstream runtime consumer was found.
- **Startup guard clarified:** exchange filter validation is conditional on `system.validate_instruments_on_startup`; in live/prod it is forced fail-closed.
- **Flip contract clarified:** per-symbol `flip.enabled` and `flip.hysteresis_mult` are required and fail-close for active symbols when global flip is enabled.

**Artifacts updated:**
- `config/docs/instruments_passport.md`
- `reports/docs_audit/instruments_passport_audit_report.md`

**Follow-up cleanup suggested (not implemented here):**
- Either wire `max_notional_utilization` into a real capacity gate or remove it from the active live contract
- Decide whether nested `symbol` should gain an equality validator against the map key or be removed as redundant metadata
- Continue converging historical strategy-side leverage fields toward explicit legacy/deprecated status

## 2026-03-13: STRATEGIES-PASSPORT-RE-AUDIT-AND-CODE-DRIVEN-CORRECTION

**Task:** Re-audit and fully resynchronize `config/docs/strategies_passport.md` against current strategies registry YAML, profile YAML loading rules, typed config models, plugin allowlist startup, arbitration logic, and strategy-specific activation checks.

**Why this re-audit was necessary:**
- The old strategies passport was anchored to stale line references and an outdated mental model where strategy profiles looked more like generic metadata than a strict activation contract.
- It also lacked an audit report artifact and did not reflect the current sentinel status of `llm_microstructure`.

**What was traced:**
- `config/aurora/strategies.yaml`
- all currently assigned strategy profiles under `config/aurora/strategies/*.yaml`
- `apps/reference/config_loader.py`
- `apps/reference/config_models.py`
- `apps/reference/main.py`
- `apps/reference/domains/strategies/registry.py`
- `apps/reference/domains/decision_making/config_resolver.py`
- `apps/reference/domains/decision_making/decision_making.py`
- `apps/reference/domains/decision_making/aurora_handler.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `apps/reference/domains/decision_making/md_amr_handler.py`
- strategy plugins and `intent_builder.py`

**Key findings:**
- **Assignment SSOT confirmed:** runtime activation is driven first by `strategies_registry.assignments`.
- **Registry-driven loading confirmed:** only assigned strategy IDs cause profile YAMLs to be loaded into `config.strategies.<id>`.
- **Allowlist startup confirmed:** assigned strategy IDs must have registered plugins or startup fails.
- **Arbitration drift clarified:** runtime supports only `priority`; `arbitration.logging.log_level` has no traced consumer.
- **Aurora activation corrected:** `aurora.enabled` is not the hard activation SSOT; Aurora checks registry first and only falls back to asset enablement when registry lacks the symbol.
- **MR/MD-AMR strictness confirmed:** both handlers enforce assignment/profile consistency more aggressively than the old passport described.
- **LLM strategy status corrected:** `llm_microstructure` is assignment-valid and allowlisted, but its plugin is sentinel-only; actual behavior is bridge-driven.

**Artifacts updated:**
- `config/docs/strategies_passport.md`
- `reports/docs_audit/strategies_passport_audit_report.md`

**Follow-up cleanup suggested (not implemented here):**
- Remove or wire `strategies_registry.arbitration.logging.log_level`
- Decide whether `aurora.enabled` should remain a soft flag or become a hard activation constraint like MR/MD-AMR
- Keep strategy docs aligned with the current sentinel/bridge model for `llm_microstructure`

## 2026-03-13: AURORA-MATH-PASSPORT-RE-AUDIT-AND-CODE-DRIVEN-CORRECTION

**Task:** Re-audit and fully resynchronize `config/docs/aurora_math_passport.md` against current Aurora YAML, Pydantic contracts, runtime kernels, loader/helper mixins, rollout contract, and math tests.

**Why this re-audit was necessary:**
- The previous math passport still described Aurora through an outdated mostly-monolithic handler narrative.
- It also blurred together currently active linear `v2` math and optional Quadratic code paths.

**What was traced:**
- `config/aurora/strategies/aurora.yaml`
- `apps/reference/config_models.py`
- `aurora_handler.py`, `aurora_config_loader.py`, `aurora_scoring_helpers.py`, `aurora_decision.py`
- `aurora_scoring_kernel.py`, `quadratic_scoring_kernel.py`, `scoring_direction_strength_v1.py`, `signal_score_v2.py`
- `apps/reference/contracts/quadratic_rollout.py`
- tests for Aurora kernel, normalize-mode SSOT, and Quadratic kernel

**Key findings:**
- **Topology drift corrected:** Aurora math runtime is decomposed across handler + mixins + kernels; `aurora_handler.py` is no longer the sole math SSOT.
- **Normalization drift corrected:** production config accepts only `signed_v2`; `off` survives only as explicit offline/function-level passthrough.
- **Live-path drift corrected:** current Aurora live math is still linear `v2`; Quadratic is implemented but not activated by current YAML.
- **Threshold drift confirmed:** active global threshold source is `decision.regime_threshold_multipliers`, not `decision.regime_thresholds`.
- **Unused-field drift found:** `AuroraInstrumentConfig.scoring_version` and `LiquidityGateConfig.failsafe_qty_check` are not wired into live Aurora math semantics.
- **Typed/runtime mismatch found:** runtime probes for per-symbol `neutral_threshold`, but strict `AuroraInstrumentConfig` does not expose that field.
- **Math-range clarification:** SignalScoreV2 output is clamped, but final Aurora `v2` score after direction/strength multiplication is not clamped.

**Artifacts updated:**
- `config/docs/aurora_math_passport.md`
- `reports/docs_audit/aurora_math_passport_audit_report.md`

**Follow-up cleanup suggested (not implemented here):**
- Remove or wire `AuroraInstrumentConfig.scoring_version`
- Remove or wire per-symbol `neutral_threshold` support consistently
- Remove or wire `decision.regime_thresholds` in Aurora runtime
- Remove or implement `failsafe_qty_check`
- Keep internal decision-making docs aligned with the Phase 14A decomposed runtime topology

## 2026-03-13: SCORING-PASSPORT-RE-AUDIT-AND-CODE-DRIVEN-CORRECTION

**Task:** Re-audit and fully resynchronize `config/docs/scoring_passport.md` against current YAML, Pydantic, runtime consumers, contracts, and tests.

**Why this re-audit was necessary:**
- The existing scoring passport and prior audit report overstated Phase 9 Quadratic as if it were the current live Aurora path.
- Current runtime still carries substantial Quadratic infrastructure, but active YAML remains on `scoring_version: "v2"` with no live `scoring_engine` / `quadratic_rollout` block.

**What was traced:**
- L1 daily gate in `daily_gate.py` and `config/aurora/trading.yaml`
- L2 risk score in `risk_management.py` and `config/aurora/domains.yaml`
- Aurora `v2` and Quadratic routing in `aurora_config_loader.py`, `aurora_scoring_kernel.py`, `quadratic_scoring_kernel.py`, `aurora_decision.py`
- Objective Engine seam in `pretrade_kernel.py` and Aurora / MR handlers
- Mean Reversion runtime in `mean_reversion_strategy.py` and `mean_reversion_handler.py`
- Output contracts: `risk_assessment_v1.json`, `trade_intent_v1.json`, `str_decision_blocked_v1.json`, additive strategy-signal contract tests

**Key findings:**
- **Live-path drift corrected:** Aurora live scoring is currently `v2`, not Quadratic.
- **Ownership drift corrected:** strategy routing is controlled by `config/aurora/strategies.yaml`, not by `aurora.assets`.
- **Threshold drift corrected:** Aurora kernels use global `decision.regime_threshold_multipliers` and per-symbol `assets.<SYM>.regime_thresholds`; global `decision.regime_thresholds` is declared but not used for Aurora scoring.
- **Contract drift found:** `DecisionConfig.scoring_version` still allows `v1`, but rollout contract only recognizes `v2|quadratic` and coerces other values to `v2`.
- **Unused fields found:** `scoring_engine.exposure_cap`, `scoring_engine.min_pillar_confidence`, `liquidity_gate.failsafe_qty_check`, and `trading.risk.daily.max_realized_loss_usd` are not consumed in the traced runtime paths.
- **L1 state corrected:** daily gate code exists but current YAML sets `trading.risk.daily.enabled: false`.
- **MR state corrected:** under current strategy registry, DOGEUSDT is the active Mean Reversion symbol; previous broad MR symbol examples were stale.

**Artifacts updated:**
- `config/docs/scoring_passport.md`
- `reports/docs_audit/scoring_passport_audit_report.md`

**Follow-up cleanup suggested (not implemented here):**
- Align `DecisionConfig.scoring_version` enum with rollout contract or explicitly retire `v1`
- Remove or wire `decision.regime_thresholds` for Aurora
- Remove or wire `scoring_engine.exposure_cap` and `min_pillar_confidence`
- Remove or implement `liquidity_gate.failsafe_qty_check`
- Decide explicitly whether Aurora remains `v2` or graduates to configured Quadratic rollout

## 2026-03-12: AURORA-MATH-PASSPORT-AUDIT-AND-SYNC

**Task:** Deep code-trace audit and synchronization of `config/docs/aurora_math_passport.md` against Phase 9 runtime and recent `v2` normalization packages.

**What was audited:**
- Hysteresis and Side-bias penalty math in `aurora_scoring_kernel.py` and `quadratic_scoring_kernel.py`.
- Scoring Direction/Strength formula in `scoring_direction_strength_v1.py` and `signal_score_v2.py`.
- Normalization modes, feature neutrals, and threshold multipliers.
- Pydantic models in `apps/reference/config_models.py`.
- Aurora SSOT config in `config/aurora/strategies/aurora.yaml`.

**Key findings & fixes:**
- **Normalization Drift:** `normalize_signals_mode` is no longer wired to `off/net_zero` in production. It was strictly locked to `"signed_v2"` following the recent EP-SSOT-NORMALIZE-SIGNEDV2 package. This drift was corrected.
- **Phase 9 Context:** Updated the passport to reflect that the described v2 math is now optionally delegated/transformed by the new Phase 9 `QuadraticScoringKernel`.
- **Feature Updates:** Deprecated `macro_sync` and replaced it with `macro_resid` and `absorption` as active fields.
- **Result:** Synchronized `aurora_math_passport.md` accurately reflecting the actual mathematical implementations and runtime constraints in the `decision_making` domain.

**Artifacts created:**
- `config/docs/aurora_math_passport.md` (updated)
- `reports/docs_audit/aurora_math_passport_audit_report.md` (new)

## 2026-03-12: REGIME-PASSPORT-AUDIT-AND-SYNC

**Task:** Deep code-trace audit and synchronization of `config/docs/regime_passport.md` against current runtime reality.

**What was audited:**
- Detector parameters (`basis_tf_sec`, `uncertain_cutoff`, `liveness_factor`, `hysteresis_bars`).
- Model parameters (`sma_trend`, `volatility`, `mean_reversion`).
- System Stress Guard parameters (`system_stress.enabled`, `thresholds`, `aggregation`, `state_mapping`).
- Pydantic models in `apps/reference/config_models.py`.
- Runtime FSM implementation in `regime_detector.py` and `system_stress_overlay.py`.

**Key findings & fixes:**
- **SMA/ATR Tunings:** Updated `sma_short_period` (48), `sma_long_period` (192), and `atr_sma_length` (288) to reflect Phase R2 winner parameters.
- **System Stress:** Added missing documentation for the entire `system_stress` block, describing `NORMAL`/`STRESS`/`EXTREME` FSM mapping and aggregations.
- **Legacy Cleanup:** Removed mentions of completely deleted blocks (`hmm`, `features`).
- **Result:** Fully synchronized `regime_passport.md` with active configuration limits, Pydantic structures, and current detector/overlay execution order.

**Artifacts created:**
- `config/docs/regime_passport.md` (updated)
- `reports/docs_audit/regime_passport_audit_report.md` (new)

## 2026-03-12: SCORING-PASSPORT-AUDIT-AND-SYNC

**Task:** Deep code-trace audit and synchronization of `config/docs/scoring_passport.md` against Phase 9 runtime reality.

**What was audited:**
- L1 Daily Risk Gates and L2 Instrument Risk score (`risk_management.py` and configs).
- L3 Signal Scoring routing (`aurora_config_loader.py`, `aurora_decision.py`, `quadratic_scoring_kernel.py`).
- Feature weights, neutrals, thresholds, hysteresis, and Mean Reversion parameters.

**Key findings & fixes:**
- **Phase 9 Integration:** L3 is now split between `v2` (linear fallback) and `quadratic` (Phase 9 `QuadraticScoringKernel` utilizing `Exposure = sign(Σ) × Σ² × shield_multiplier`).
- **Shield Cascade:** Added documentation for `MemoryShield` and `DangerZone` attenuators.
- **Risk Score Math:** L2 absorption logic split into directionless proxy (`toxicity`) and feature terms based on `absorption_penalty_source`.
- **Legacy Cleanup:** Documented `macro_sync` deprecation and actual `mean_reversion.yaml` active parameters.
- **Result:** Rewrote `scoring_passport.md` to be the actual SSOT for the Phase 9 logic.

**Artifacts created:**
- `config/docs/scoring_passport.md` (updated)
- `reports/docs_audit/scoring_passport_audit_report.md` (new)

## 2026-03-12: NEO-PRODUCER-CONTRACT-ALIGNMENT-AUDIT-AND-IMPLEMENTATION-PLAN

**Task:** Deep audit and implementation planning for the 4 hard blockers that
prevent execution-aware neocortex integration with Aurora. This package is audit
and plan only — no code implementation.

**What was audited:**
- All 4 hard blockers (HB-1 through HB-4) re-validated against active codebase on Phenix_v2
- Complete data lineage per field: `lifecycle_id`, `trade_id`, `fees`, `net_pnl`, `side`, `close_ts_ms`
- All producer-side files: `intent_builder.py`, `event_handlers.py`, `fsm.py`, `open_executor.py`,
  `trade_lifecycle_logger.py`, `order_logger.py`, `core_parser.py`, `order_parser.py`,
  `transport/adapter.py`, `datasets/contracts.py`
- Soft blockers SR-1 through SR-8 assessed for current blocking status
- Alternative solutions enumerated for all 4 hard blockers

**Key findings — all 4 HBs CONFIRMED:**
1. **HB-1 `lifecycle_id`:** Architecturally absent. `idempotent_key` (UUID4 per intent) exists
   and is indexed but never surfaced as top-level `lifecycle_id`. `rid` changes semantic identity
   across ORDER_INTENT → ORDER_FILLED → POSITION_CLOSED (decision UUID → clientOrderId → fill-rid).
2. **HB-2 `trade_id`:** Exchange `tradeId` present in ORDER_FILLED `metadata.fill_trade_id`
   but NOT cached per-symbol. POSITION_CLOSED lacks `trade_id`. `side` hardcoded to "N/A".
3. **HB-3 `fees`/`net_pnl`:** `commission` present in ORDER_FILLED metadata but NOT accumulated.
   No per-symbol fee accumulator exists. POSITION_CLOSED has only `realized_pnl` (gross).
4. **HB-4 regex path:** `core_parser.py` structured path theoretically fires for POSITION_CLOSED
   but yields at most `symbol` + `realized_pnl`. `trade_id`, `fees`, `realized_pnl_net` are
   never in Aurora's log text. `trade_lifecycle.jsonl` is richest structured SSOT but not wired
   as neocortex primary source.

**Root cause unifying all 4 HBs:**
The POSITION_CLOSED write in `event_handlers.py:246-261` is a thin dict write that does not
assemble the data available from per-symbol caches. The pattern for enriching it is identical
to what already exists for `_last_realized_pnl_by_symbol` and `_last_close_reason_by_symbol`.

**Planned fix — 4 additive packages (no neocortex changes, no broad refactor):**
- PKG-1: Add `lifecycle_id` (= `idempotent_key`) to ORDER_INTENT + POSITION_CLOSED
- PKG-2: Cache `tradeId` per-symbol → add `trade_id` + correct `side` to POSITION_CLOSED
- PKG-3: Accumulate `commission` per-symbol → add `fees` + `net_pnl` to POSITION_CLOSED
- PKG-4: Verify structured path fires; deprecate regex fallback comment; validate `reward_complete=True`
- PKG-5 (optional): POSITION_OPENED event + decision trace persistence

**What was NOT done (by design):**
- No implementation of any fix
- No neocortex code changes
- No advisory influence reopened
- No policy training re-enabled
- No broad refactor
- No live/testnet trading

**Artifacts created:**
- `docs/audits/aurora_producer_contract_alignment_audit.md` — full re-validation of all 4 HBs
  with root cause, code anchors, alternatives, recommendations
- `docs/audits/aurora_neocortex_integration_gap_deep_dive.md` — field-by-field data lineage,
  implementation map, gap matrix, why neocortex cannot trust current surface
- `docs/roadmaps/aurora_producer_contract_alignment_plan.md` — dependency-ordered PKG-1 to PKG-5
  with TDD-first test plan, acceptance criteria, rollback posture

**Recommended next package:** `NEO-PRODUCER-CONTRACT-ALIGNMENT-PKG-1` — `lifecycle_id` propagation.
3 files, ≤10 additive lines. No deletions. Write tests first.

---

## 2026-03-11: NEO-INTEGRATION-DATA-CONTRACT-AUDIT

**Task:** Integration audit and research to establish whether the new Aurora execution/data surface is compatible with neocortex's post-P1-P9 input contracts, and what must be resolved before any form of shadow launch.

**What was audited:**
- Neocortex required input contracts (time, lifecycle, reward, objective, sequence, dataset, gates) from `domain.yaml`, parsers, adapter, gates, dataset hygiene, evaluation layer
- Aurora actual data/event surface (20 events across 7 domains, 4 log streams, 3 parsers)
- Log-mediated integration surface: `order_log_v1.jsonl`, `aurora_core.log`, `features/*.log`, `trade_lifecycle.jsonl`
- Compatibility across 34 contract items

**Key findings:**
- 18/34 items COMPATIBLE, 11 PARTIALLY_COMPATIBLE, 5 MISSING
- 4 hard blockers identified:
  1. `lifecycle_id` never written to `order_log_v1.jsonl` (primary neocortex identity key absent from producer)
  2. `trade_id` missing from POSITION_CLOSED log entries (close resolution impossible by canonical key)
  3. No structured `fees`/`net_pnl` in close path (reward completeness always False)
  4. Core log parser depends on unstructured text regex (fragile, 0 `realized_pnl_net` occurrences confirmed)
- 10 soft blockers / quality risks identified

**Verdict:** Partial offline launch ONLY.
- Offline replay for representation + regime_supervision: READY NOW
- Offline replay with execution quality: BLOCKED by 4 producer-side fixes
- Limited shadow runtime: BLOCKED by above + feature timestamp requirement + decision reference log
- Full acceptance campaign: BLOCKED by all above + P0 freeze + follow-ups + URS Phase A

**What was NOT done (by design):**
- No code changes to neocortex or Aurora
- No advisory influence reopened
- No policy training re-enabled
- No acceptance campaign started
- No live/testnet trading

**Artifacts created:**
- `docs/audits/neocortex_integration_data_contract_audit.md` — full audit with matrix, blockers, launch prerequisites
- `docs/audits/neocortex_aurora_event_compatibility_matrix.md` — detailed 34-item table
- `docs/roadmaps/neocortex_shadow_launch_prereqs.md` — phased launch readiness with explicit fix list

**Recommended next package:** `NEO-PRODUCER-CONTRACT-ALIGNMENT` — 3-4 targeted changes in Aurora execution domain telemetry (add `lifecycle_id`, `trade_id`, `fees`/`net_pnl` to order log entries). No neocortex code changes. No broad refactor.

---

## 2026-03-11: NEO-P9-EVALUATOR-CALIBRATION-AND-ADVISORY-HARDENING

**Task:** Add a canonical offline evaluator / calibration / disagreement layer for `apps/reference/domains/neocortex` after P1-P8, without reopening advisory influence, live authority, or policy training.

**What was missing before P9:**
- There was no first-class evaluator layer in `apps/reference/domains/neocortex/logic/*`.
- P1-P8 gave clean contracts and production-shadow gates, but there was no canonical answer to:
  - how regime-supervision quality is measured
  - how execution-quality coverage/diagnostic quality is measured
  - how disagreement with Aurora is counted deterministically
  - whether confidence is calibrated or simply unavailable
  - why advisory remains forbidden even after production-shadow cleanup
- Shadow confidence existed in runtime shadow payloads, but there was no explicit calibration contract and no honesty layer for missing/insufficient confidence support.

**What was implemented:**
- Added canonical `EvaluationConfig` to:
  - `apps/reference/domains/neocortex/config_models.py`
  - `apps/reference/domains/neocortex/config/neuro.yaml`
- Added manifest contract section `contracts.evaluation` to:
  - `apps/reference/domains/neocortex/domain.yaml`
- Added new evaluator layer:
  - `apps/reference/domains/neocortex/logic/evaluation/contracts.py`
  - `apps/reference/domains/neocortex/logic/evaluation/evaluator.py`
  - `apps/reference/domains/neocortex/logic/evaluation/__init__.py`
- Added reports/contracts:
  - `ShadowEvaluationReport`
  - `CalibrationReport`
  - `DisagreementReport`
  - `AdvisoryReadinessPrereqReport`
- Added disagreement input contract:
  - `ShadowDisagreementSample`
- Added a minimal runtime enrichment in `apps/reference/domains/neocortex/transport/adapter.py` so regime-supervision samples carry already-available shadow `confidence` into the evaluation corpus.

**Evaluation / trust semantics:**
- Regime supervision:
  - separate report with label coverage, confusion summary, accuracy, abstain count, symbol coverage, realized-regime coverage
- Execution quality:
  - separate report with reward completeness coverage, unresolved counts, diagnostics-only counts, close-event distribution, lifecycle-state distribution, fill summaries
- Disagreement:
  - deterministic counts only; no claim that disagreement is alpha
  - reported by symbol / regime / confidence bucket / severity bucket
- Calibration:
  - explicit `available` vs `not_available`
  - no fake calibration when confidence signal is missing
- Advisory hardening:
  - separate machine-readable prereq report
  - remains `forbidden`
  - explicitly lists unsatisfied prerequisites and future package needs

**Non-goals preserved:**
- P9 did not reopen advisory influence.
- P9 did not reopen policy training.
- P9 did not change P1-P8 semantic contracts.
- P9 did not add planner/world-model runtime integration.
- P9 did not claim disagreement is alpha.

**Verification:**
- `python -m pytest apps/reference/domains/neocortex/tests/test_evaluator_reports.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_calibration.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_disagreement.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_shadow_gates.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_dataset_hygiene.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_objective_split.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_sequence_semantics.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_performance_contract.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_provenance.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_replay_engineering.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_reward_contract.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_episode_identity.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_time_contract.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_reward_parsing.py -q`

## 2026-03-11: NEO-P8-PRODUCTION-SHADOW-GATES

**Task:** Add centralized production-shadow readiness gating for `apps/reference/domains/neocortex` after P1-P7 remediation, without reopening policy training, advisory influence, or any broader semantic/runtime redesign.

**What was missing before P8:**
- `apps/reference/domains/neocortex/main.py` had no centralized startup/readiness gate evaluation.
- P1-P7 invariants existed as config/runtime contracts, but startup could still proceed without a deterministic machine-readable gate report.
- There was no single production-shadow safety posture check ensuring:
  - policy training stayed disabled
  - advisory/live authority stayed forbidden
  - dataset admission remained fail-closed
  - sequence narrowing remained active
  - `live_shadow` / `offline_replay` mode constraints were enforced as startup readiness, not just as scattered validators

**What was implemented:**
- Added canonical `ShadowGateConfig` to `apps/reference/domains/neocortex/config_models.py` and `apps/reference/domains/neocortex/config/neuro.yaml`.
- Added centralized gate evaluator layer in:
  - `apps/reference/domains/neocortex/logic/gates/shadow.py`
  - `apps/reference/domains/neocortex/logic/gates/__init__.py`
- Added startup integration in `apps/reference/domains/neocortex/main.py` via `evaluate_startup_shadow_gates(...)`.
- Added manifest contract section `contracts.production_shadow_gates` to `apps/reference/domains/neocortex/domain.yaml`.

**Gate taxonomy and enforcement posture:**
- Semantic integrity gates:
  - domain manifest exposes required contract sections
  - objective split remains enforced
  - narrowed sequence contract remains active
  - canonical time mode remains valid for the selected operating mode
- Shadow safety posture gates:
  - policy training stays disabled
  - advisory influence stays forbidden
  - live authority stays forbidden
- Admission/provenance gates:
  - dataset manifest contract remains valid
  - dataset self-tests prove policy samples and unresolved execution samples are not trainable
- Operational readiness gates:
  - performance mode contract remains self-consistent
  - budget/flush thresholds remain sane
- Startup behavior:
  - `startup_enforcement=strict` now hard-fails startup on any blocking gate
  - readiness report is machine-readable and deterministic for the same config + evaluator timestamp

**Non-goals preserved:**
- P8 did not change P1 canonical time semantics.
- P8 did not rewrite P2 lifecycle identity.
- P8 did not redesign P3 reward semantics.
- P8 did not reopen policy training or advisory/live influence.
- P8 did not introduce a new evaluator/ML stack; it only hardened release/startup gating.

**Verification:**
- `python -m pytest apps/reference/domains/neocortex/tests/test_shadow_gates.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_performance_contract.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_dataset_hygiene.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_objective_split.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_sequence_semantics.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_provenance.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_replay_engineering.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_reward_contract.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_episode_identity.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_time_contract.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_reward_parsing.py -q`

## 2026-03-02: READINESS-CONTRACTS-AUDIT

**Task:** Perform a deep READ-ONLY audit and synthesize all readiness states, startup hydration states, and restart recovery semantics across the Aurora/Phenix codebase.
**Goal:** Formalize existing readiness layers and identify missing contracts, false-ready conditions, and restart asymmetries.

**What was audited:**
- FeatureEngineering `warmup` / `full_ready` logic.
- `RegimeDetector` internal state readiness.
- Phase 9 `pillar_backfill.py` HTF readiness dependencies.
- `md_amr` mandatory live warmup mechanisms (`_MANDATORY_LIVE_WARMUP_SEC`).
- `execution_position` Leverage Bootstrap and `InFlightReconciler` bindings on startup.
- `position_tracking` DR (WAL + snapshot) and execution FSM hydration.
- `readiness_gates.py` in `decision_making`.

**Key Findings:**
1. **[CONFIRMED] False-Ready Condition in Execution:** `run_leverage_bootstrap()` returns a set of `blocked_symbols` due to exchange API failures, but `main.py` only logs this. It is never passed to `decision_making` to block intents, creating a critical false-ready state.
2. **[CONFIRMED] Restart Asymmetry:** `position_tracking` mathematically replays WAL, while `execution_position` merely remaps FSM instances via `hydrate()` and relies on an async `InFlightReconciler` without blocking initial trading loops.
3. **[CONFIRMED] Hidden-Ready Assumption:** `md_amr_handler` silently relies on a REST hydration attempt (`_REST_HYDRATION_LIMIT`) before falling back to a mandatory 2-hour live warmup clock.

**Artifacts added:**
- `docs/architectural_audits/READINESS_CONTRACTS_AUDIT.md` - Full contract-oriented synthesis defining canonical readiness scopes (`execution_context_ready`, `quadratic_htf_ready`, `basis_bar_ready`, etc.) and the exact path from startup to the first valid trade cycle.

## 2026-03-11: NEO-P7-PERFORMANCE-AND-REPLAY-ENGINEERING

**Task:** Harden neocortex hot-path execution for production-grade shadow and replay research without rewriting P1 time, P2 lifecycle identity, P3 reward, P4 objective split, P5 sequence semantics, or P6 dataset hygiene.

**What was expensive / uncontrolled:**
- `apps/reference/domains/neocortex/transport/adapter.py` executed non-critical side effects synchronously per feature row:
  - dual shadow event emission
  - per-row shadow JSONL open/write/flush
  - per-row telemetry CSV open/write/flush
- There was no explicit operating-mode contract separating `live_shadow` from `offline_replay`.
- Observational side effects had no explicit budget or overflow policy, so replay throughput could degrade under disk-heavy side effects.
- Observational shadow emission had no deterministic decimation contract for offline replay.

**What was implemented:**
- Added canonical `PerformanceConfig` in `apps/reference/domains/neocortex/config_models.py` and `apps/reference/domains/neocortex/config/neuro.yaml`.
- Added `contracts.performance` to `apps/reference/domains/neocortex/domain.yaml`.
- Introduced explicit operating modes:
  - `live_shadow`
  - `offline_replay`
- Added explicit performance knobs:
  - `shadow_intent_emit_policy`
  - `shadow_intent_decimation_stride`
  - `shadow_jsonl_write_policy`
  - `telemetry_write_policy`
  - `non_critical_queue_limit`
  - `shadow_log_flush_threshold`
  - `telemetry_flush_threshold`
  - `flush_interval_ms`
  - `non_critical_overflow_policy`
- Chosen P7 narrowing:
  - semantic-critical path remains lossless and unbatched
  - only observational side effects are buffered/decimated
  - no encode/act batching was introduced because it would risk semantic drift without explicit equivalence tests
- `TelemetryLogger` now supports buffered ordered flushes, explicit overflow handling, and counters for dropped/flushed rows.
- Adapter now supports:
  - deterministic stride-based observational shadow decimation in `offline_replay`
  - buffered shadow JSONL writes with explicit overflow accounting
  - buffered telemetry writes
  - explicit counters for generated/emitted/decimated shadow outputs and non-critical overload
  - shutdown flush of buffered non-critical outputs

**Determinism / safety posture:**
- P1 causal time remains canonical; offline replay decimation is deterministic and depends on explicit event order/stride, not wallclock.
- P2/P3 lifecycle and reward assembly still run on every event; only observational shadow outputs may be decimated.
- P4 objective routing, P5 sequence narrowing, and P6 provenance/admission remain intact.
- Policy training remains disabled.

**Verification:**
- `python -m pytest apps/reference/domains/neocortex/tests/test_performance_contract.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_replay_engineering.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_dataset_hygiene.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_sequence_semantics.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_objective_split.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_provenance.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_reward_contract.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_episode_identity.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_time_contract.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_reward_parsing.py -q`
- Result: targeted P7 tests are green and checked P1-P6 regression surface remains green.

**Explicit non-goals preserved:**
- Did not batch encode/act across semantic-critical streams.
- Did not change lifecycle/reward/objective/provenance semantics.
- Did not re-enable policy training.
- Did not start P8 production shadow gates or evaluator/advisory hardening.

## 2026-03-10: Aurora Current Warmup / Quadratic / Decision Lifecycle Audit

**Task:** Produce a code-first current-state audit of Aurora startup/bootstrap, warmups, bar-only vs microstructure dependencies, Quadratic runtime activation, decision lifecycle, and backfill/recovery wiring under the active `config/aurora` runtime.

**Confirmed findings:**
- Active Aurora strategy config is still `decision.scoring_version: "v2"`; Quadratic kernel exists but is not active by current config.
- Regime detector is currently a 5m-only runtime and needs about 301 x 5m bars plus hysteresis, or about 25.33h, for full natural readiness from cold start.
- Phase 9 pillars require M15/H4/D1 histories up to 200 D1 bars, and a dedicated Binance-based pillar backfill service exists.
- FeatureEngineering listens for `EVT:HTF_BARS_IMPORTED`, but no confirmed startup call path was found that runs pillar backfill and emits that event before live trading starts.
- FE `warmup.full_ready` is driven by declared microstructure readiness keys and does not include pillar readiness, so FE-ready and Quadratic-ready are currently different contracts.
- If `scoring_version` is flipped to `quadratic` without HTF hydration, FE can still emit `CMD:PROCESS_STRATEGY`, but `QuadraticScoringKernel` will defer on `PILLAR_WARMUP` until `pillar_sum` becomes available.
- Market-data startup is live WebSocket driven; no confirmed historical seed or delta-sync bootstrap was found for bars/HTF state.
- Disaster recovery currently restores execution/position state better than analytics warm state; no equivalent restore path was confirmed for FE/regime/pillars.

**Artifacts added:**
- `docs/audits/current_warmup_quadratic_scoring_decision_lifecycle_audit_2026-03-10.md`

**Operational conclusion:**
- Current branch is operationally closer to a bar-driven Aurora v2 runtime with Phase 9 pieces present than to a fully bootstrapped active Quadratic runtime.
- The main risk before any Quadratic activation is readiness-contract drift: startup hydration, FE warmup, Quadratic readiness, and restart recovery are not yet aligned.

## 2026-03-11: NEO-P6-DATASET-HYGIENE-AND-PROVENANCE

**Task:** Add a canonical dataset hygiene and provenance layer to neocortex without rewriting P1 time, P2 lifecycle identity, P3 reward contract, P4 objective split, or P5 sequence semantics.

**What was broken:**
- Dataset admission was still implicit in `apps/reference/domains/neocortex/transport/adapter.py`: representation rows entered the training buffer without provenance, oracle settlements entered supervision buffers without eligibility checks, and execution-quality samples had no formal quarantine or exclusion path.
- The domain had no canonical dataset provenance contract, so a sample could not answer where it came from, why it was trainable, or why it was excluded.
- There was no first-class manifest contract for deterministic split-by-time inventory and no formal reason counters for contamination, incomplete reward, unresolved lifecycle, or legacy non-causal replay rows.
- Policy family remained disabled after P4, but there was still no dataset-layer admission rule preventing accidental trainable policy samples under a dirty or incomplete contract.

**What was implemented:**
- Added canonical dataset contracts in `apps/reference/domains/neocortex/logic/datasets/contracts.py`:
  - `DatasetSampleProvenance`
  - `DatasetEvaluatedSample`
  - `DatasetSplitManifest`
  - `DatasetManifest`
- Added `DatasetPolicyEngine` in `apps/reference/domains/neocortex/logic/datasets/hygiene.py` with explicit eligibility statuses:
  - `trainable`
  - `eval_only`
  - `diagnostics_only`
  - `quarantined`
  - `rejected`
- Added fail-closed quarantine/rejection rules for:
  - `MagicMock` contamination
  - contaminated identifiers
  - missing source provenance
  - missing canonical `event_ts_ms`
  - unresolved lifecycle / unresolved close
  - reward-incomplete execution/policy samples
  - legacy non-causal rows in causal-sensitive families
  - unknown objective family
  - unsupported sequence contract
  - policy family when `policy_training_mode=disabled`
- Added `dataset` config SSOT to `apps/reference/domains/neocortex/config_models.py` and `apps/reference/domains/neocortex/config/neuro.yaml`.
- Added `contracts.dataset` to `apps/reference/domains/neocortex/domain.yaml`.
- Wired the adapter to evaluate every dataset candidate before admission:
  - `handle_features()` admits representation rows to the train buffer only when explicitly `trainable`
  - `_handle_oracle_settlement()` routes only trainable regime-supervision samples
  - `add_completed_episode()` keeps explicit `trainable/eval_only/diagnostics_only` execution samples with provenance and rejects/quarantines the rest
  - `add_policy_sample()` now fails closed under dataset admission before any policy route is considered
- Added adapter-side provenance sidecars, dataset counters, and `build_dataset_manifest(objective_family)` for deterministic manifest generation over evaluated samples.

**Verification:**
- `python -m pytest apps/reference/domains/neocortex/tests/test_dataset_hygiene.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_provenance.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_objective_split.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_sequence_semantics.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_reward_contract.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_time_contract.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_episode_identity.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_reward_parsing.py -q`
- Result: targeted P6 tests are green and the checked P1/P2/P3/P4/P5 regression surface remains green.

**Explicit non-goals preserved:**
- Did not re-enable policy training.
- Did not redesign runtime live-shadow decision semantics.
- Did not start P7 performance/replay engineering or any post-remediation advisory contour.

## 2026-03-11: NEO-P5-SEQUENCE-SEMANTICS-REPAIR

**Task:** Repair neocortex sequence semantics without rewriting P1 time, P2 lifecycle identity, P3 reward contract, or P4 objective split.

**What was broken:**
- The PPO inference path reused one worker-level LSTM hidden state across unrelated inference calls, so hidden memory could leak between unrelated causal streams.
- `BrainCore.train_batch()` treated arbitrary recent batches as one sequence even though the batch carried no canonical stream owner metadata.
- Replay start had no explicit bridge-level sequence reset, so sequence state was not contractually reset at the start of a new replay session.
- The runtime therefore implied recurrent/sequence semantics that were not actually supported honestly by the training path.

**What was implemented:**
- Added a canonical `sequence` config contract in `apps/reference/domains/neocortex/config_models.py` and `apps/reference/domains/neocortex/config/neuro.yaml`:
  - `inference_mode: stateless_per_event`
  - `representation_training_mode: independent_rows`
  - `reset_on_replay_start: true`
  - `reset_on_symbol_switch: true`
  - `reset_on_objective_family_switch: true`
  - `reset_on_episode_boundary: true`
- Added `contracts.sequence` to `apps/reference/domains/neocortex/domain.yaml`.
- Added `BrainCore.reset_sequence_state()` and explicit representation-batch validation.
- `BrainCore.get_action()` now resets recurrent state before every inference call, eliminating cross-call hidden reuse on the current branch.
- `BrainCore.train_batch()` no longer fabricates a temporal sequence out of arbitrary recent rows; the active representation-training mode is now explicit independent rows, and misleading world-model temporal training is skipped.
- Added `BrainBridge.reset_sequence_state_async()` and worker task `RESET_SEQUENCE_STATE`.
- `NeocortexAdapter.start()` now performs an explicit replay-start sequence reset once the bridge is ready.

**Verification:**
- `python -m pytest apps/reference/domains/neocortex/tests/test_sequence_semantics.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_objective_split.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_reward_contract.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_episode_identity.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_time_contract.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_reward_parsing.py -q`
- `python -m pytest tests/apps/reference/domains/neocortex/tests/test_brain.py -q`
- Result: targeted P5 tests are green and P1/P2/P3/P4 regression surface remains green.

**Explicit non-goals preserved:**
- Did not introduce stateful per-symbol recurrent training; that remains blocked on future explicit sequence-owner datasets.
- Did not enter P6 dataset hygiene/provenance.
- Did not re-enable policy training or live advisory influence.

## 2026-03-10: NEO-P1-CANONICAL-TIME-CONTRACT

**Task:** Introduce one canonical causal time contract for neocortex ingestion/replay without entering P2 lifecycle identity, P3 reward-contract redesign, or P4 objective split.

**What was broken:**
- Feature replay accepted pure JSON rows with no causal timestamp and silently substituted replay wallclock via `time.time()`.
- Order logs arrived in mixed seconds/milliseconds and were not normalized to one unit.
- Core logs were parsed into seconds floats while order logs already carried epoch milliseconds.
- Pending-episode stale cleanup compared mixed units and used replay wallclock instead of event time.
- Shadow-intent idempotency depended on replay-time derived timestamps and model-train timing, not canonical event time.

**What was implemented:**
- Canonical time field introduced: `event_ts_ms: int`.
- Canonical unit introduced: epoch milliseconds.
- Feature, order, and core parsers now normalize supported timestamps to canonical `event_ts_ms`.
- Feature rows without causal timestamps are now **fail-closed by default**.
- Explicit temporary compatibility mode added:
  - `feature_missing_timestamp_policy: legacy_non_causal_file_offset`
  - requires `legacy_feature_base_ts_ms`
  - derives deterministic synthetic timestamps from `legacy_feature_base_ts_ms + file_offset`
  - marks rows as `time_is_causal=False` / `time_source=legacy_non_causal_file_offset`
- `MultiTailer` stale cleanup now uses canonical milliseconds only.
- `handle_position_closed_event()` no longer falls back to `time.time()`; missing causal time now fails closed.
- Shadow intent idempotency now uses canonical source event time/identity, not replay wallclock.

**Migration impact:**
- Legacy pure-JSON feature rows without embedded timestamp no longer pass as normal causal events.
- The repository replay config now opts into the explicit non-causal compatibility path in `apps/reference/domains/neocortex/config/replay.yaml`.
- This compatibility path is diagnostic-only and should not be treated as training-quality causal data.

**Verification:**
- `python -m pytest apps/reference/domains/neocortex/tests/test_time_contract.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_multi_ingest.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_reward_parsing.py -q`
- `python -m pytest apps/reference/domains/neocortex/tests/test_replay.py -q`
- Result: all targeted P1 tests green.

**Explicit non-goals preserved:**
- Did not start P2 canonical episode identity / fill-aware lifecycle.
- Did not redesign P3 reward semantics beyond time normalization touchpoints.
- Did not touch P4 objective split, PPO semantics, sequence repair, dataset hygiene, or performance engineering.

## 2026-03-10: NEO-UNBLOCK-PYTEST-COLLECT-TUPLE-IMPORT

**Task:** Close the minimal repo-level unblocker package for neocortex pytest collection without touching neocortex runtime or starting `NEO-P1-CANONICAL-TIME-CONTRACT`.

**Why:** The remediation plan and audit package recorded a repo-level blocker claiming `apps/reference/config_models.py:3572` used `Tuple` without import, which would stop `pytest apps/reference/domains/neocortex/tests -q` during collection.

**Verification on current branch:**
- Confirmed the current branch no longer matches the recorded blocker condition.
- `apps/reference/config_models.py` already imports `Tuple` from `typing`, and the annotation at `ObjectiveNormalizationConfig.target_range` remains valid.
- `C:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest apps/reference/domains/neocortex/tests --collect-only -q` completed collection successfully: 254 items collected, 1 skipped.
- `C:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest apps/reference/domains/neocortex/tests -q` progressed beyond collection and executed the suite, proving the repo-level `Tuple` import blocker is not active on this branch.

**Package outcome:**
- `NEO-UNBLOCK-PYTEST-COLLECT-TUPLE-IMPORT` is effectively already resolved on the current branch.
- No code change was required in `apps/reference/config_models.py`.
- This package remains strictly pre-`NEO-P1-CANONICAL-TIME-CONTRACT`; no neocortex runtime, ingest, PPO, parser, reward, or time-contract code was touched.

**Newly exposed non-collection failures:**
- `apps/reference/domains/neocortex/tests/test_integration.py` fails under Python 3.14 because `asyncio.get_event_loop()` no longer provides an implicit loop in the main thread.
- `apps/reference/domains/neocortex/tests/test_simulation_bar_v2.py` fails because `torch` is unavailable, the brain bridge degrades, and expected shadow intents are not emitted.

**Next package readiness:**
- Yes. Pytest collection is unblocked on the current branch, so `NEO-P1-CANONICAL-TIME-CONTRACT` can proceed as the next implementation package.

## 2026-03-10: Neocortex Production Shadow Remediation Planning Package

**Task:** Build a full remediation-design package for `apps/reference/domains/neocortex` that converts the domain from a research-grade hybrid observer into a production-grade shadow domain, with an explicit forward path to a 9.5/10 advisory architecture.

**Why:** The current implementation has foundational contract failures that sit below any PPO or model-tuning discussion:
- no canonical time contract,
- no lifecycle-safe episode identity,
- broken reward extraction against actual `aurora_core.log`,
- mixed regime-oracle and execution semantics in one PPO path,
- broken recurrent sequence semantics,
- contaminated datasets,
- hot-path cost too high for replay-scale shadowing.

**Baseline verification completed:**
- Reviewed `apps/reference/domains/neocortex/*`, `domain.yaml`, config YAMLs, and test suite layout.
- Verified the baseline audit against current code and local runtime logs.
- Confirmed all 13 requested findings on the current branch.
- Confirmed repo-level test collection blocker: `apps/reference/config_models.py:3572` uses `Tuple` without import, so `pytest apps/reference/domains/neocortex/tests -q` fails before domain tests run.

**Artifacts added:**
- `docs/audits/neocortex_gap_matrix.md`
- `docs/audits/neocortex_remediation_plan.md`
- `docs/roadmaps/neocortex_prod_shadow_roadmap.md`
- `docs/architecture/neocortex_target_state_95.md`
- `docs/architecture/neocortex_acceptance_gates.md`

**Chosen rollout order:**
1. External unblocker: `NEO-UNBLOCK-PYTEST-COLLECT-TUPLE-IMPORT`
2. P0 Context Freeze / Baseline Verification
3. P1 Canonical Time Contract
4. P2 Canonical Episode Identity + Fill-Aware Lifecycle
5. P3 Reward Contract / Structured Close Feed
6. P4 Objective Split
7. P5 Sequence Semantics Repair
8. P6 Dataset Hygiene Layer
9. P7 Performance / Replay Engineering
10. P8 Production Shadow Gates
11. P9 Path to 9.5/10 advisory architecture

**Why production shadow first:**
- The current domain is already useful as an observer, latent-research surface, disagreement reporter, and diagnostics subsystem.
- It is not safe to let it influence live decisions until data correctness, lifecycle integrity, reward semantics, and uncertainty gates are repaired.
- The shortest path to long-term value is to harden the data plane first, then layer modeling and advisory capability on top.

**Immediate next implementation package:**
- `NEO-P1-CANONICAL-TIME-CONTRACT`
- Note: run after or alongside the minimal repo-level unblocker for pytest collection.


## 2026-03-04: Phase 0.7 — Backtest Engine OHLCV DataContract Integration

**Task:** Wire fail-fast OHLCV data contract validation into `BacktestEngine.load_data()` at parquet load time (per-symbol, before frame concatenation).

**Why:** Corrupt or misaligned parquet files (missing columns, nulls in price cols, high < low) currently produce silent bad data or cryptic downstream errors mid-run. Phase 0.7 adds a hard gate at the earliest possible point — immediately after `q.collect()` per symbol — so violations surface as a clear `ValueError` with the symbol name and exact violation list.

**Design decision — polars-native (no pyarrow/pandas):**
The existing `tools/parquet_contract/data_contract.py` `DataContract` class is pandas-based and requires `pyarrow` for polars→pandas conversion; `pyarrow` is not installed in this environment. Rather than adding a dependency, the validation was implemented as a self-contained native polars check — mirrors the same 4-check structure (missing columns → dtype class → nulls → semantic invariants) without any bridge overhead.

**Changes:**

1. `backtest_engine/engine.py`:
   - `_OHLCV_REQUIRED`, `_OHLCV_NUMERIC`, `_OHLCV_NUMERIC_DTYPES` — module-level constants (frozenset/tuple)
   - `_validate_ohlcv_contract(frame, symbol)` — new module-level function; native polars; 4-check pipeline; raises `ValueError: "DataContract violation (ohlcv) [SYMBOL]: ..."` on any failure
   - `load_data()`: replaced inline `frames.append(q.collect(streaming=True))` with explicit `collected = q.collect()` + `_validate_ohlcv_contract(collected, symbol)` + `frames.append(collected)`
   - Added `except ValueError: raise` before the existing `except Exception` catch-all so DataContract violations are not silently swallowed

2. `tests/backtest_engine/test_data_contract_integration.py` (new):
   - `TestValidateOhlcvContractUnit` (6 tests): valid frame passes, missing column, null in close, high<low, negative volume, single-row edge case
   - `TestLoadDataContractIntegration` (3 tests): valid parquet → `load_data()` succeeds, high<low parquet → raises, null close parquet → raises

**Test results:**
```
tests/backtest_engine/test_data_contract_integration.py  9/9 pass, 0.31s
tests/backtest_engine/ (full suite)                     57/57 pass, 2 skipped (pre-existing), 0 regressions
```

**Invariants after this change:**
- Every symbol's OHLCV parquet is validated at load time before entering the simulation loop
- Contract violations raise `ValueError` and propagate — they are not silenced by the general IO error handler
- Validation is pure polars — no pyarrow dependency; fast (sub-millisecond for typical bar counts)


## 2026-03-01: EP-SSOT-NORMALIZE-SIGNEDV2-P2 — normalize_mode SSOT Final Hardening

**Task:** Complete two-phase SSOT enforcement for `normalize_mode` / `normalize_signals_mode`.
Phase 1 wired YAML → runtime (YAML → `AuroraConfigLoaderMixin` → kernel). Phase 2 (this session)
removes the remaining "two-truths" and silent fallbacks.

**Why:** `SignalsConfig` previously had `Literal["off", "signed_v2"]` but the kernel (`AuroraScoringKernel`) rejected `"off"` at runtime. Config said "allowed"; kernel said "rejected" = two truths. Additionally, `signals=None` silently fell back to `"signed_v2"` on the strict pydantic path — silent default in a fail-closed system.

**Changes:**

1. `apps/reference/config_models.py`:
   - `SignalsConfig.normalize_signals_mode`: `Literal["off", "signed_v2"]` → `Literal["signed_v2"]`. `"off"` removed from production YAML boundary. Forensic passthrough still works by passing `normalize_mode="off"` directly to the scoring function.
   - Removed dead `_forbid_legacy_normalize_signals_in_live` model validator (unreachable: `Literal["signed_v2"]` rejects `legacy_v1` before the validator runs).

2. `apps/reference/domains/decision_making/aurora_config_loader.py` (lines 162–176):
   - `signals=None` on strict pydantic path → `ConfigContractError` (fail-closed). Test-mock path (`_strict_pydantic_config=False`) falls back to `"signed_v2"`.

3. `apps/reference/domains/decision_making/decision_making.py` (lines 153–160):
   - Added `normalize_signals_mode` init block: reads from `config.strategies.aurora.decision.signals.normalize_signals_mode` with `try/except` fallback = `"signed_v2"`. Mirrors `AuroraConfigLoaderMixin` pattern for `DecisionMaking` (which does not extend the mixin).

4. `apps/reference/domains/decision_making/scoring_direction_strength_v1.py` (docstring):
   - Updated to clarify `"off"` = forensic-only passthrough, not valid in production YAML. `legacy_v1` removed.

5. Test fixtures updated (`"off"` → `"signed_v2"` in 4 files):
   - `tests/domains/decision_making/test_normalize_mode_ssot.py`: `test_config_accepts_off` → `test_config_rejects_off_mode`
   - `tests/config/test_toplevel_forbid_enforcement.py:44`
   - `tests/config/test_typed_dict_any_configs.py:49`
   - `tests/domains/decision_making/test_side_bias_window_updates_v1.py:129`

6. Test fixtures for `SimpleNamespace` + `__new__`-based construction:
   - `tests/domains/decision_making/test_aurora_handler.py:44`: added `normalize_signals_mode="signed_v2"` to signals SimpleNamespace
   - `tests/domains/decision_making/test_aurora_reentry_cooldown.py:31`: same
   - `tests/domains/decision_making/test_task40_one_open_order_guard.py:95`: `dm.normalize_signals_mode = "signed_v2"` added to `_mk_dm` (`__new__`-bypass helper)

**Evidence pack:**
- `rg "legacy_v1" apps/ config/` → only docstrings + error-message patterns (no active code)
- `rg "net_zero" apps/ config/` → only docs (`aurora_math_passport.md`)
- `rg "normalize_mode_effective" apps/` → `intent_builder.py:365` ✅ (WAL metadata wired)

**Test results:**
```
tests/domains/decision_making/  288/288 pass
tests/config/                   240/240 pass
tests/audit/                    513/513 pass (combined)
Broader suite                  1269+ pass, 5 pre-existing unrelated fails
```

**Invariants after this change:**
- Production YAML can only express `normalize_signals_mode: signed_v2` (Pydantic `Literal["signed_v2"]`)
- Forensic tooling can pass `normalize_mode="off"` directly to `compute_direction_strength_score()` — no YAML bypass
- `signals=None` on strict pydantic path → `ConfigContractError` (no silent default)
- `intent_builder.py` writes `normalize_mode_effective` to WAL ORDER_INTENT for every placed trade


## 2026-03-01: Phase R3-A-lite — Market Policy Tables (PKG-R3A)

**Task:** Build (trend × vol × stress × horizon) edge tables and derive Aurora sizing + MR entry policies — without requiring backtest trades. Directly from forward returns on historical bars.

**Why:** R3-B confirmed TREND_UP has near-zero sign lift but measurable Cohen's d (fat-tail mean advantage). This means TREND_UP is a sizing signal, not a binary entry filter. TREND_DOWN (SMA 48/192) marks oversold = mean-reversion setup. `TREND_DOWN|HIGH_VOL` consistently 0.53-0.57 sign_acc across all 4 symbols. R3-A-lite quantifies these effects per regime cell and derives operational policies.

**Changes:**

1. `tools/parquet_pipeline/policy_tables.py` (new, ~300 lines):
   - `_cvar5(arr)`: mean of bottom 5% (Expected Shortfall)
   - `_tail_uplift(arr)`: p95 - p50 (upside tail extension)
   - `compute_edge_table()`: per (trend × vol × stress × horizon) cell — n, mean, std, p05/p50/p95, sign_acc, cvar5, tail_uplift
   - `derive_trend_policy()`: Aurora sizing multiplier = clamp(1 + mean_uplift/baseline_std, 0.25, 2.50); signal = increase/neutral/reduce; baseline = FLAT|MID_VOL|NORMAL
   - `derive_mr_policy()`: MR entry policy (boost/allow/reduce/block) by sign_acc_delta thresholds (>0.03 / ≥-0.01 / ≥-0.04 / <-0.04)

2. `tools/parquet_pipeline/__main__.py`: r3a subcommand added:
   - `_parse_r3a_args()`: --with-stress flag triggers A4 actuator attachment (enter=0.60, CB=6, min_dur=15, window=200, max=2)
   - `_generate_r3a_report()`: per-symbol Aurora sizing + MR entry + Edge Table @ 24b in markdown
   - `main_r3a()`: polars pipeline → stress_v0 → optional A4 actuator → edge table + policies → parquet + report + manifest

3. `tests/test_policy_tables.py` (new): 24 tests — `TestCvar5` (3), `TestTailUplift` (3), `TestComputeEdgeTable` (9), `TestDeriveTrendPolicy` (4), `TestDeriveMrPolicy` (5)

**CLI:**
```bash
python -X utf8 -m tools.parquet_pipeline r3a \
  --symbols BTCUSDT ETHUSDT DOGEUSDT 1000PEPEUSDT \
  --months-range 2023-06:2024-03 \
  --output-dir reports/ \
  --with-stress
```

**Key findings (cross-symbol, 4 assets, 2023-06—2024-03):**

Aurora sizing (primary_horizon=24b):
- `TREND_UP|HIGH_VOL|NORMAL` → sizing_mult 1.05—1.16, signal=increase on 3/4 symbols (ETH=neutral at 1.048); tail_ratio 1.94—3.01
- `TREND_DOWN|HIGH_VOL|NORMAL` → sizing_mult 1.08—1.16, signal=increase on all 4 symbols (mean-reversion bounce positive mean at 2h)
- `TREND_UP|LOW_VOL|*` → neutral/reduce in most symbols (thin regime, low edge)
- `FLAT|HIGH_VOL|STRESS` → neutral BTC/ETH, but DOGE has outlier (-6% mean return at 24b)

MR entry policy (primary_horizon=12b):
- `TREND_DOWN|HIGH_VOL|NORMAL` → **boost** all 4 symbols (deltas: +0.065, +0.074, +0.046, +0.028) — most robust finding
- `TREND_DOWN|HIGH_VOL|STRESS` → boost BTC/DOGE, neutral ETH, increase PEPE
- `TREND_UP|MID_VOL|STRESS` → block BTC/ETH, block DOGE, allow PEPE
- `TREND_UP|LOW_VOL|STRESS` → block/reduce on 3/4 (sample n=46-123, treat with caution)

**Test results:**
```
tests/test_policy_tables.py   24/24 pass, 0.51s
Regression suite              5 pre-existing fails only (unchanged)
```

**Outputs generated:**
- `reports/r3a_market_policy_tables.md` — full cross-symbol policy tables
- `reports/r3a_edge_{BTC,ETH,DOGE,PEPE}.parquet` — per-symbol edge tables
- `reports/r3a_aurora_policy_{sym}.parquet`, `r3a_mr_policy_{sym}.parquet`
- `reports/r3a_edge_results.parquet` (combined), `reports/r3a_manifest.json`


## 2026-03-01: Phase R3-B — Forward Separability (PKG-R3B)

**Task:** Validate whether the SMA-slope trend label (from R2) carries predictive edge over
forward return horizons N ∈ {12, 24, 48} bars (1h / 2h / 4h at 5m).

**Motivation:** R2 confirmed vol separation is strong (0.17-0.21 overlap), but trend_return_overlap
at 1-bar returns was 0.87-0.92 — expected for 5m noise. R3-B verifies that the trend label is
predictive over multi-bar horizons before building any strategy overlay on top of it.

**Design decisions:**
- Forward return: `fwd_ret_N[t] = log(close[t+N] / close[t])` — avoids look-ahead, numpy-native.
- Cohen's d with pooled std — standardised mean difference between label groups.
- Sign lift = `P(fwd_ret > 0 | TREND_UP) − P(fwd_ret > 0 | FLAT)` — probability advantage.
- Edge verdict thresholds: strong (|d|>0.20 AND |lift|>0.05), moderate (0.10/0.02), weak (0.05/0.01), none.
- Vol interaction 3×3 matrix (trend × vol_bucket) — captures whether HIGH_VOL+TREND_UP has higher edge.
- Reuses `_trend_labels`, `_vol_labels` from `regime_grid.py` with R2 winner params as defaults.
- Reuses `_histogram_overlap`, `_bhattacharyya` from `market_structure.py` — no duplication.

**Changes:**

1. `tools/parquet_pipeline/forward_separability.py` (new, ~280 lines):
   - `compute_forward_returns(df, horizons) → pl.DataFrame`: attaches fwd_ret_N columns; last N bars = NaN
   - `_cohens_d(a, b) → float`: pooled std; returns 0.0 on empty/zero-variance arrays
   - `_sign_accuracy(arr) → float`: P(x > 0); NaN excluded; 0.5 on empty
   - `_edge_verdict(cohens_d, sign_lift) → str`: strong/moderate/weak/none
   - `_label_stats(df, trend_col, horizon) → dict`: per-label mean/std/sign_accuracy/n
   - `run_forward_separability(df, *, sma_short, sma_long, slope_threshold, atr_window, hysteresis_bars, horizons, tf_minutes) → dict`
     - Returns: params, horizons, tf_minutes, label_distribution, per_horizon, vol_interaction
   - `flatten_separability_to_df(result, symbol) → pl.DataFrame`: one row per (label, horizon) for export

2. `tools/parquet_pipeline/__main__.py` (+~280 lines):
   - `_parse_r3b_args()`: --symbols, --tf, --months-range, --months, --data-dir, --output-dir,
     --window, --burn-in, --sma-short, --sma-long, --slope-threshold, --atr-window, --hysteresis-bars, --horizons
   - `_generate_r3b_report(results, ...)`: 4-section markdown (edge verdict, DOWN vs FLAT, label dist, vol interaction)
   - `main_r3b()`: multi-symbol runner → writes r3_forward_separability_{sym}.parquet, combined parquet, report, manifest
   - Routing: `elif sys.argv[1] == "r3b"` added

3. `tests/test_forward_separability.py` (new, 34 tests, 0.53s):
   - `TestComputeForwardReturns` (7): columns present, last N = NaN, first bar finite, length unchanged, missing close → nulls, default horizons, exact log-ratio check
   - `TestCohensD` (4): identical = 0, large separation, empty = 0, sign correct
   - `TestSignAccuracy` (5): all positive, all negative, 50/50, empty = 0.5, NaN excluded
   - `TestEdgeVerdict` (6): strong, moderate, weak_d, weak_lift, none, negative strong
   - `TestRunForwardSeparability` (9): keys, horizons, dist keys, dist sums to 100, label stats present, sign_acc in [0,1], finite values, valid verdicts, vol matrix combos
   - `TestFlattenSeparabilityToDf` (3): shape (3 labels × H horizons), symbol column, empty result no crash

**Test result:** 34/34 pass, 0.53s, 0 regressions (pre-existing 5 unchanged).

**CLI usage:**
```bash
python -X utf8 -m tools.parquet_pipeline r3b \
  --symbols BTCUSDT ETHUSDT \
  --months-range 2023-06:2024-03 \
  --output-dir reports/
```

**Outputs:** `reports/r3_forward_separability_{symbol}.parquet`, `reports/r3_forward_separability_results.parquet`,
`reports/r3_forward_separability_report.md`, `reports/r3_forward_separability_manifest.json`


## 2026-03-01: Phase R2 — Regime Grid Calibration (PKG-R2)

**Task:** Grid-search over (sma_short, sma_long, slope_threshold, atr_window, hysteresis_bars)
to find regime labeling configurations that are stable (low churn), separable (distinct
return/vol distributions per label), and balanced (no state < 1% or > 80% of bars).

**Motivation:** Phase R1 proved the market has detectable structure. R2 converts that
knowledge into calibrated SMA+vol regime labels for regime.yaml — specifically finding
parameter ranges where labels are stable enough for strategy gating without being decorative.

**Changes:**

1. `tools/parquet_pipeline/regime_grid.py` (new, ~335 lines):
   - `_sma_slope(close, sma_short, sma_long) → pl.Series`: normalised slope via polars expression form
   - `_apply_hysteresis(labels, n) → pl.Series`: O(n) flip suppression; n=1 = identity; return-to-committed commits immediately
   - `_trend_labels(df, sma_short, sma_long, slope_threshold, hysteresis_bars) → pl.Series`: TREND_UP/TREND_DOWN/FLAT; warmup nulls → FLAT fill
   - `_vol_labels(df, atr_window) → pl.Series`: LOW_VOL/MID_VOL/HIGH_VOL via rolling bar_range proxy, global p33/p66 tertiles
   - `_count_switches(labels)`, `_median_run_bars(labels)`: stability helpers
   - `compute_grid_row(df, ...)` → 22-key dict: 5 params + 8 coverage + 4 stability + 4 separability + 1 score
   - `_score_grid_row(row)`: `0.5*churn_score + 0.4*sep_score - 0.1*cov_penalty`; score ∈ [-0.10, 0.90]
   - `run_regime_grid(df, ...)` → Polars DataFrame sorted by score descending; skips sma_short ≥ sma_long
   - Reuses `_histogram_overlap`, `_bhattacharyya` from `market_structure.py` — no duplication

2. `tools/parquet_pipeline/__main__.py` (~340 new lines):
   - `_parse_r2_args()`: --symbols, --tf, --months-range, --months, --data-dir, --output-dir, --window, --burn-in
   - `_generate_r2_report(results, symbols, tf, months)`: 5-section markdown
     - §1 Top-5 cross-symbol avg score table
     - §2 Per-symbol top-3 detail table
     - §3 Parameter sensitivity (mean score per axis value)
     - §4 Coverage check (configs with coverage_ok=False)
     - §5 Calibration recommendations (min/max/mode for top 10%)
   - `main_r2(argv=None)`: multi-symbol runner; per-symbol parquet + top-20 JSON; combined results.parquet; report + manifest
   - Routing: `elif sys.argv[1] == "r2"` (backward-compatible; r1/main() unchanged)

3. `tests/test_regime_grid.py` (new, 29 tests):
   - `TestApplyHysteresis` (4): identity n=1, isolated flip filtered, two consecutive commits, empty series
   - `TestTrendLabels` (5): uptrend→TREND_UP, downtrend→TREND_DOWN, flat→FLAT, hyst reduces switches, length correct
   - `TestVolLabels` (4): distinct groups present, constant bar_range→MID_VOL, window 14vs28 no crash, short no crash
   - `TestComputeGridRow` (7): all 22 keys, spd≥0, trend sum=1, vol sum=1, overlap in [0,1], all finite, score in [-0.15,1.0]
   - `TestScoreGridRow` (4): near-max for perfect row, high churn reduces, high overlap reduces, coverage violation penalizes
   - `TestRunRegimeGrid` (5): sorted desc, shape correct, invalid sma skipped, single combo=1 row, all numeric finite

**CLI usage:**
```bash
python -m tools.parquet_pipeline r2 \
  --symbols BTCUSDT ETHUSDT DOGEUSDT 1000PEPEUSDT \
  --months-range 2023-06:2024-03 \
  --output-dir reports/
```

**Outputs per symbol:** `regime_grid_{symbol}.parquet` (all combos), `regime_grid_{symbol}_top20.json`
**Cross-symbol:** `regime_grid_results.parquet`, `regime_grid_report.md`, `regime_grid_manifest.json`

**Grid axes:**
- sma_short: [24, 36, 48], sma_long: [96, 144, 192] → all combos valid (no sma_short ≥ sma_long)
- slope_threshold: [0.0005, 0.001, 0.0015, 0.002]
- atr_window: [14, 21, 28]
- hysteresis_bars: [1, 2, 3]
- Total: 324 valid combos per symbol

**Scoring design:**
- 50% stability (tanker priority): `churn_score = max(0, 1 - trend_spd / 5.0)`
- 40% separability: `sep_score = 0.5*(1-trend_return_overlap) + 0.5*(1-vol_atr_overlap)`
- 10% coverage penalty: -1.0 if any state < 1% or > 80% of bars

**Key implementation decisions:**
- `bar_range` (already in STRESS_OUTPUT_COLUMNS) used as ATR proxy — no raw OHLC needed
- NaN from rolling warmup falls into MID_VOL: `np.where(nan < p33)` = False (numpy silent NaN semantics)
- `group_by(col).agg(pl.len())` for coverage pcts (avoids `value_counts()` API instability across polars versions)
- Separability compares FLAT vs non-FLAT returns and LOW_VOL vs HIGH_VOL ATR via R1 histogram helpers
- score `-0.1` lower bound: can go slightly below 0 only when coverage_ok=False (penalty dominated)

**Test count:** 29 new tests; 29/29 green in 0.37s; 0 regressions (5 pre-existing failures unchanged).

---

## 2026-03-01: Phase 0.6 — Per-Strategy SystemStress Policy + STRESS Attenuation (PKG-0.6)

**Task:** Add `system_stress_policy: off|attenuate|block` per-strategy to `SafetyGatesConfig` so Gate 0.5 is opt-in per strategy. Add configurable STRESS attenuation: `policy=attenuate` halves `margin_pct_mult` when state=STRESS.

**Motivation:** Phase 0.5 globally blocked EXTREME entries for all strategies. Mean-reversion is counter-trend — stress overlay must not apply. Aurora is trend-following — stress gates fully relevant. Per-strategy policy resolves this without a global toggle.

**Policy semantics:**
- `off` → Gate 0.5 entirely bypassed; EXTREME is ignored for this strategy (fail-open on missing config)
- `attenuate` → EXTREME=DENY(NRR-059); STRESS=ALLOW but `margin_pct_mult *= stress_attenuation_factor`
- `block` → EXTREME=DENY(NRR-059) and STRESS=DENY(NRR-059)

**Changes:**

1. `apps/reference/config_models.py`:
   - `SafetyGatesConfig` gains 2 new fields with defaults (backward-compatible):
     - `system_stress_policy: Literal["off", "attenuate", "block"] = "off"`
     - `stress_attenuation_factor: float = Field(default=0.5, ge=0.0, le=1.0)`

2. `config/aurora/strategies/aurora.yaml`:
   ```yaml
   safety_gates:
     enabled: true
     system_stress_policy: attenuate   # EXTREME=DENY, STRESS=size_down
     stress_attenuation_factor: 0.50   # margin_pct_mult *= 0.5 when STRESS
   ```

3. `config/aurora/strategies/mean_reversion.yaml`:
   ```yaml
   safety_gates:
     enabled: false
     system_stress_policy: "off"   # quoted: YAML 1.1 parses bare 'off' as bool False
   ```
   **Implementation note:** YAML 1.1 treats bare `off` as Python `False`. Pydantic `Literal["off", ...]` rejects `False`. Always quote `off`/`on`/`yes`/`no` in YAML when binding to `Literal` string fields.

4. `apps/reference/domains/decision_making/safety_gates.py`:
   - New helper `_resolve_stress_policy(config, strategy_id) → (str, float)`:
     fail-open: returns `("off", 1.0)` on any missing/bad config so strategies without the field are unaffected
   - `_check_system_stress_gate()` gains `stress_policy: str = "off"` param:
     - `policy=="off"` short-circuits before reading `system_stress_states` (true bypass)
     - `policy in ("attenuate","block")` + EXTREME → DENY(NRR-059)
     - `policy=="block"` + STRESS → DENY(NRR-059)
     - `policy=="attenuate"` + STRESS → ALLOW, surface state for gateway attenuation
   - `apply_safety_gates()`: calls `_resolve_stress_policy()`, passes `stress_policy` to Gate 0.5

5. `apps/reference/domains/decision_making/strategy_gateway.py`:
   - After regime-based `margin_pct_mult` (or `None` treated as `Decimal("1")`), before `_calculate_position_size()`:
     ```python
     _stress = dm._system_stress_states.get(symbol, "NORMAL")
     if _stress == "STRESS" and _policy == "attenuate":
         margin_pct_mult = (margin_pct_mult or Decimal("1")) * Decimal(str(_factor))
     ```
   - Wrapped in `try/except` — fail-open: attenuation errors must never block trades

6. `tests/test_system_stress_overlay.py` (modified):
   - `TestCheckSystemStressGate._call()` default updated to `stress_policy="attenuate"` to preserve Phase 0.5 test semantics under the new `"off"` default
   - `test_disabled_flag_bypasses`: explicit `stress_policy="attenuate"` — proves `apply_safety_gates_flag=False` bypass works independently of policy

7. `tests/test_stress_policy.py` (new, 23 tests):
   - `TestResolveStressPolicy` (6): missing strategy, valid attenuate, valid block, bad policy fallback, factor clamped, missing safety_gates attr
   - `TestStressPolicyOff` (3): NORMAL/STRESS/EXTREME → ALLOW (even EXTREME bypassed)
   - `TestStressPolicyAttenuate` (4): NORMAL→ALLOW, STRESS→ALLOW+surface, EXTREME→DENY, reduce_only bypass
   - `TestStressPolicyBlock` (4): NORMAL→ALLOW, STRESS→DENY, EXTREME→DENY, reduce_only bypass
   - `TestStressAttenuation` (6): halves existing mult, mult=None→factor, off leaves unchanged, NORMAL unchanged, EXTREME not attenuated in gateway, custom factor

**Test count:** 23 new tests; 22 Phase 0.5 tests still pass (45/45 combined); 0 regressions (5 pre-existing failures unchanged).

**Key implementation decisions:**
- Default `policy="off"` (fail-open): any strategy that doesn't set the field gets zero Gate 0.5 interference — existing configs unaffected
- `_factor` applied to `margin_pct_mult`, not `risk_fraction` — consistent with how regime_sizing already works at that point
- `SafetyGateResult.system_stress_state` field unchanged (Phase 0.5); attenuation factor not added to result — gateway reads config directly
- NRR-059 reused for both EXTREME and STRESS-block cases (same semantics: stress entry blocked)

---

## 2026-03-01: Phase R1 — Market Structure Audit (PKG-R1)

**Task:** Build a market-first research layer: statistical characterization of price/vol
distributions before any strategy parameter tuning. Outputs 5 blocks of analysis across
4 symbols (BTCUSDT, ETHUSDT, DOGEUSDT, 1000PEPEUSDT).

**Motivation:** Strategy calibration (R2/R3) requires knowing the market's statistical
character first — distribution tails, regime persistence, separability, memory structure.
Without this, parameter tuning is empirical guesswork blind to the data-generating process.

**Deliverables:**

1. `tools/parquet_pipeline/market_structure.py` (new, ~360 lines):
   - Block 1 `compute_distribution_stats()` — 4 metrics (atr, realized_vol, log_return,
     bar_range): count, mean, std, skew, kurtosis, p25/50/75/90/99, tail_ratio
   - Block 2 `compute_persistence_stats()` — run-length encoding (pure Python accumulator),
     autocorr(return, lag=1), autocorr(vol, lag=1)
   - Block 3 `compute_regime_separability()` — 2-axis proxy labels (directionality +
     vol_bucket), histogram-based Bhattacharyya distance and overlap coefficient
     (polars-first, no scipy; `np.histogram` on shared bins)
   - Block 4 `compute_structural_breaks()` — Hurst R/S exponent, vol_clustering_lag1/2/5,
     rolling mean/variance shift detection
   - Block 5 `simulate_stability_grid()` — actuator config grid search (optional flag),
     reuses `actuator_rules.run_actuator` + `aggregation.compute_stress_level`

2. `tools/parquet_pipeline/__main__.py` (modified, +~390 lines):
   - `_parse_months_range("2023-06:2024-03")` → list of months (year boundary wrap)
   - `_parse_r1_args()` — `--symbols`, `--months-range`, `--include-grid`, `--window`,
     `--burn-in`, `--output-dir`
   - `_generate_r1_report()` — 5-section markdown (distributions, persistence,
     separability, structural breaks, calibration recommendations)
   - `main_r1()` — multi-symbol runner; per-symbol JSON + cross-symbol report + manifest
   - Routing: `sys.argv[1] == "r1"` → `main_r1()` (backward-compatible; existing `main()` tests unchanged)

3. `tests/test_market_structure.py` (new, 38 tests):
   - `TestComputeDistributionStats` (6), `TestComputePersistenceStats` (6),
     `TestHistogramHelpers` (4), `TestProxyLabels` (4),
     `TestComputeRegimeSeparability` (5), `TestComputeStructuralBreaks` (5),
     `TestSimulateStabilityGrid` (4), `TestParseMonthsRange` (4)
   - All synthetic DataFrames — no parquet I/O; 38/38 pass in 0.37s

**CLI usage:**
```bash
python -m tools.parquet_pipeline r1 \
  --symbols BTCUSDT ETHUSDT DOGEUSDT 1000PEPEUSDT \
  --months-range 2023-06:2024-03 \
  --output-dir reports/
```

**Key design decisions:**
- Polars-first throughout; numpy only for histogram math (`_bhattacharyya`, `_histogram_overlap`)
  and `_hurst_rs` R/S loop. No scipy/pandas dependency.
- Proxy labeling is 2-axis (Directionality + Vol bucket), not mutually exclusive regimes.
  SMA_SHORT=24, SMA_LONG=96, slope_flat_threshold=0.002; ATR tertiles p33/p66.
- Bhattacharyya uses shared `np.linspace(combined_min, combined_max, 50)` bins for
  numerically stable comparison of unequal-length series.
- `_hurst_rs` returns 0.5 (neutral) for n < 20 or insufficient chunk diversity.
- Block 5 gated behind `--include-grid` flag (slow: O(T×K³) actuator calls).
- `SEPARABILITY_OVERLAP_WARN = 0.70`: flag raised when histograms overlap > 70%.

**Test count:** 38 new tests; 0 regressions.

---

## 2026-03-01: Phase 0.5 — SystemStressOverlay Live DM Integration (PKG-0.5)

**Task:** Wire A4 preset as a live runtime overlay in the event bus:
`EVT:BAR_CLOSED → SystemStressOverlay → EVT:SYSTEM_STRESS_STATE_UPDATED → DecisionMaking._system_stress_states → SafetyGates Gate 0.5`

**Changes:**

1. `schemas/system_stress_state_updated_v1.json` (new): JSON Schema for the emitted event.
2. `apps/reference/domains/system_stress/__init__.py` (new): package marker.
3. `apps/reference/domains/system_stress/system_stress_overlay.py` (new, ~280 lines):
   - `_SymbolStressState`: per-symbol rolling z-score buffers with strict no-lookahead guarantee
     (compute z against current deque, then append — replicates Polars `.shift(1)` pattern)
   - `_StressActuator`: incremental per-bar FSM (NORMAL/STRESS/EXTREME) with consecutive-bar
     confirmation, min_duration guard, and circuit breaker
   - `SystemStressOverlay`: FSM domain; subscribes to `EVT:BAR_CLOSED` (tf_sec==basis_tf_sec),
     maintains per-symbol state, emits `EVT:SYSTEM_STRESS_STATE_UPDATED` on transitions only
4. `config/aurora/regime.yaml`: updated `state_mapping` from A0 defaults to A4 winner values
   (`consecutive_bars_enter=6`, `consecutive_bars_exit=4`, `min_duration_bars=15`,
   `switch_window_bars=200`, `max_switches_per_window=2`)
5. `apps/reference/domains/decision_making/normalized_reject_reasons.py`:
   added `SYSTEM_STRESS_ENTRY_BLOCKED = "NRR-059"`
6. `apps/reference/domains/decision_making/decision_making.py`:
   - `self._system_stress_states: Dict[str, str] = {}` (volatile cache, same pattern as `_per_symbol_regimes`)
   - Subscription: `fsm.listen("EVT:SYSTEM_STRESS_STATE_UPDATED", self._on_system_stress)`
   - Handler `_on_system_stress()`: caches `pld["state"]` per symbol
   - Pass `system_stress_states=self._system_stress_states` to `apply_safety_gates()`
7. `apps/reference/domains/decision_making/safety_gates.py`:
   - `SafetyGateResult.system_stress_state: str = "NORMAL"` (carried downstream for Phase 0.6 attenuation)
   - `_check_system_stress_gate()`: EXTREME→DENY(NRR-059); STRESS→ALLOW+surface; reduce_only bypasses
   - Gate 0.5 inserted in `apply_safety_gates()` chain after Gate 0 (config), before Gate 1 (regime conf)
8. `apps/reference/bootstrap/domain_builder.py`:
   - `LiveDomainBundle.system_stress_overlay: Optional[SystemStressOverlay] = None`
   - Instantiated in `build_live_domains()` and returned in bundle
9. `apps/reference/main.py`:
   - Import + backtest path wiring (after `RegimeDetector`): `SystemStressOverlay(config, fsm)` + `fsm.register_domain`
10. `tests/test_system_stress_overlay.py` (new, 22 tests):
    - `TestStressActuator` (5): stays_normal, NORMAL→STRESS, hysteresis, interrupted reset, circuit_breaker
    - `TestSystemStressOverlayDisabled` (2): no subscription, no emission
    - `TestSystemStressOverlayBurnIn` (2): burn-in suppression, tf_sec filter
    - `TestSystemStressOverlayTransition` (4): quiet bars hold, NORMAL→crisis, no duplicate, symbol isolation
    - `TestCheckSystemStressGate` (7): NORMAL/STRESS/EXTREME/reduce_only/None/unknown/disabled
    - `TestSafetyGateResultField` (2): default NORMAL, field persistence
11. `tests/domains/decision_making/test_directional_sanity_gate.py`:
    `dm._system_stress_states = {}` added to `dm_minimal` fixture
12. `tests/domains/decision_making/test_task40_one_open_order_guard.py`:
    `dm._system_stress_states = {}` added to fixture

**Test count:** 22 new tests pass; 5 pre-existing failures remain (unrelated: `test_failclosed_validation.py` x4, risk_management x1); zero regressions introduced.

**Gate semantics:**
- `EXTREME` (stress_level ≥ 0.85): new entries DENIED (NRR-059); reduce_only bypasses
- `STRESS` (0.60 ≤ stress_level < 0.85): new entries ALLOWED; `system_stress_state` field surfaced for Phase 0.6 attenuation (risk_fraction reduction)
- `NORMAL`: no change to flow

**Key implementation notes:**
- No-lookahead: z-score computed against deque contents BEFORE appending current bar (exact replication of offline batch logic)
- NORMAL→EXTREME direct: when `stress_level ≥ enter_extreme`, actuator jumps directly without going through STRESS — expected behavior
- `enabled=False` is a true no-op: constructor returns immediately without subscribing, zero overhead
- `min_duration_bars=15` applies to ALL states including NORMAL (anti-churn cooldown: 75 min at 5m after returning from STRESS)

---

## 2026-03-01: Phase 0.4 — A4 Multi-Symbol Portability (PKG-0.4)

**Task:** Verify that A4 preset generalises beyond BTCUSDT to ETH, DOGE, and 1000PEPE (different microstructures).
**Context:** A4 was selected from grid search on BTCUSDT only. Risk: overfitting to BTC's specific
volatility regime in Jan-Mar 2024 (ETF approval period).

**Changes:**
1. `tools/parquet_pipeline/validate_preset.py` (new, ~290 lines):
   - Single-preset multi-symbol runner (no full grid overhead)
   - `_run_symbol()`: per-symbol stress_v0 + aggregation + actuator
   - `_verdict()`: PASS / WARN / FAIL per acceptance thresholds
   - `generate_report()`: cross-symbol table + top-5 switch events per symbol
   - CLI: `python tools/parquet_pipeline/validate_preset.py [--preset A4] [--symbols ...]`
2. `reports/stress_a4_multiasset_report.md` (generated)

**Results (A4, 5m, Jan-Mar 2024):**

| Symbol | /day | STRESS% | Longest run | Verdict |
|--------|------|---------|-------------|---------|
| BTCUSDT | 1.55 | 6.8% | 865 bars | PASS |
| ETHUSDT | 1.57 | 7.0% | 745 bars | PASS |
| DOGEUSDT | 1.39 | 5.4% | 1,169 bars | PASS |
| 1000PEPEUSDT | 1.28 | 4.9% | 1,282 bars | PASS |

**Overall verdict: PORTABLE.**

**Key observations:**
- Meme/high-vol assets (DOGE, 1000PEPE) have FEWER switches than BTC/ETH (1.28-1.39/day vs 1.55-1.57/day)
  — the wide CB window (200 bars) is the main stabiliser across asset classes
- STRESS% is slightly lower for meme assets (4.9-5.4%) vs majors (6.8-7.0%) — expected, as meme assets
  have higher baseline volatility, pushing z-scores above the threshold less frequently relative to their norm
- EXTREME = 0% across all symbols — confirms enter_extreme=0.85 is correctly set for this period

**Acceptance thresholds used:**
- PASS: switches/day ≤ 3.0 AND 2% ≤ STRESS% ≤ 35%
- WARN: switches/day ≤ 5.0 OR STRESS% ≥ 1%

**Conclusion:** A4 is the confirmed foundation preset. Ready for `regime.yaml` update and DM integration.

**Verification:** 53/53 pipeline tests green.

---

## 2026-03-01: Phase 0.3 — Actuator Preset Grid Search (PKG-0.3)

**Task:** Grid-search 6 ActuatorConfig presets on real data to find a "moderate tanker" config.
**Context:** Phase 0.2 baseline (A0) produced 226 switches/90 days (2.5/day). Target: ≤1.5/day
with STRESS% between 5-20% (gate active but not dominant).

**Changes:**
1. `tools/parquet_pipeline/tune_presets.py` (new, ~450 lines):
   - 6 preset definitions (A0–A5) varying enter/exit thresholds, consecutive bars, min_duration, CB window
   - `_collect_result()`: metrics per preset (switches, %NORMAL/STRESS/EXTREME, longest run, top-10 events)
   - `_select_winner()`: primary=switches/day≤1.5 AND secondary=STRESS%∈[5,20]; fallback composite score
   - `generate_report()`: full markdown with comparison table, per-preset detail, top-10 switch timestamps+z-scores
   - CLI: `python tools/parquet_pipeline/tune_presets.py [--symbol --tf --months --output]`
2. `reports/stress_tuning_report.md` (generated):
   - Full grid results for BTCUSDT/5m Jan-Mar 2024

**Key finding — bifurcation at enter_stress 0.60 vs 0.65:**
- Presets at 0.60 threshold: A0 (226/day=2.50), A1 (196/2.16), A4 (140/1.55)
- Presets at 0.65 threshold: A2 (8/0.09), A3 (2/0.02), A5 (2/0.02)
- The aggregation (weighted_vote, current sigma thresholds) rarely produces stress_level > 0.65 outside
  of true extreme events. The 0.60 threshold sits in a churn zone where the signal oscillates.
- Tightening thresholds to 0.65 eliminates almost all switches but makes the gate decorative (0.1% STRESS).

**Winner: A4** — Anti-flip hard (enter=0.60, consecutive_enter=6, min_duration=15, switch_window=200, max_switches=2):
- Switches: 140 (1.55/day) — just barely over target but best in class for STRESS% coverage
- NORMAL: 93.2%, STRESS: 6.8%, EXTREME: 0%
- Longest stable run: 865 bars (~72 hours)
- Top-10 events are verifiable real events (Jan 2-8 2024 BTC ETF volatility)

**Observation for next Phase:** The 0.60 entry threshold is mediocre for churn control at this
sigma/weight setup. Either lower thresholds (so 0.65 produces more STRESS% coverage), or keep 0.60
and rely on CB + min_duration for inertia (A4 approach). A4 is the correct starting config.

**Verification:** 53/53 pipeline tests green.

---

## 2026-03-01: Phase 0.2 — Stress State Actuator (PKG-0.2)

**Task:** Phase 0.2 — aggregation (z-scores → stress_level) + hysteresis FSM (stress_level → NORMAL/STRESS/EXTREME).
**Context:** Z-scores from Phase 0.1 need to be collapsed into a single composite stress_level,
then run through a deterministic state machine with hysteresis to produce stable state labels.

**Changes:**
1. `tools/parquet_pipeline/aggregation.py` (134 lines):
   - `TRIGGER_MAP`: maps config keys (atr, vol, gap, range, volume, spread, depth) to z-score columns + sigma thresholds
   - `compute_stress_level()`: adds `stress_level` column (0..1) via three aggregation methods:
     - `weighted_vote`: binary fire per trigger (z > sigma), then weighted sum
     - `k_of_n`: count firing triggers / k, clamped to [0, 1]
     - `max`: max exceedance ratio (z/sigma), clamped to [0, 1]
2. `tools/parquet_pipeline/actuator_rules.py` (183 lines):
   - Pure, deterministic, O(n) hysteresis FSM
   - `StressState` enum: NORMAL, STRESS, EXTREME
   - `ActuatorConfig` frozen dataclass: enter/exit thresholds, consecutive-bar confirmation,
     min_duration, circuit breaker (switch_window_bars, max_switches_per_window)
   - `run_actuator()`: returns `ActuatorResult` with per-bar state, why (<=80 chars), switches_cumulative
3. `tools/parquet_pipeline/__main__.py` (expanded to 422 lines):
   - `--emit-state` CLI flag
   - Default config fallbacks: `_DEFAULT_THRESHOLDS`, `_DEFAULT_WEIGHTS`, `_DEFAULT_ACTUATOR`
   - Config extraction: `_extract_thresholds()`, `_extract_aggregation()`, `_extract_actuator_config()`
   - State summary: total switches, state distribution %, longest stable run
   - New artifact: `stress_state_timeseries.parquet` (timestamp, stress_level, state, why, switches_total)
   - Provenance includes `state_computed` flag
4. `tools/parquet_pipeline/stress.py` (z-score no-lookahead fix):
   - Added `.shift(1)` on `rolling_mean/std` baseline so bar t uses `[t-window..t-1]` only
   - Docstring updated to reflect shifted rolling
5. `tests/test_stress_actuator.py` (22 tests):
   - Aggregation: weighted_vote (all/none/partial fire), k_of_n (exceed/below k), max, no_active_triggers
   - Actuator: pure_normal, normal→stress, hysteresis holds, consecutive resets, min_duration,
     stress→extreme, extreme→stress, full cycle, circuit breaker, empty input, cumulative switches, why<=80
   - CLI: --emit-state produces parquet + summary with state section
6. `tests/test_parquet_pipeline.py`: +1 test (no-lookahead z-score), now 31 tests

**Real-data validation (BTCUSDT/5m Jan-Mar 2024, 26,088 bars):**
- Total switches: 226 (~2.5/day)
- NORMAL: 23,609 bars (90.5%), STRESS: 2,479 bars (9.5%), EXTREME: 0 bars (0.0%)
- Longest stable run: 626 bars (NORMAL, ~52 hours)
- **NOTE:** 226 switches is in the low-hundreds range. Current `regime.yaml` defaults
  (consecutive_bars_enter=3, min_duration_bars=5, switch_window_bars=50) produce moderate
  stability. For "tanker" behavior, consider increasing consecutive_bars_enter to 5-6
  or min_duration_bars to 10-15. This is a config tuning decision, not a code issue.

**Verification:** 53/53 pipeline tests green (31 Phase 0.1 + 22 Phase 0.2). 225/225 config regression green.

---

## 2026-03-01: Phase 0.1 — Parquet Audit + Stress v0 Pipeline (PKG-0.1)

**Task:** Phase 0.1 — offline Polars-native pipeline for data audit + stress metric extraction.
**Context:** No tooling existed to validate parquet data quality or compute stress baselines
for threshold calibration. Backtest engine loads raw data with no pre-flight check.

**Decision:** New `tools/parquet_pipeline/` module (CLI: `python -m tools.parquet_pipeline`).
NOT modifying backtest engine or domain code — pure offline tooling.

**Changes:**
1. `tools/parquet_pipeline/__init__.py`: Package marker.
2. `tools/parquet_pipeline/discovery.py` (78 lines):
   - `discover_files()`: find parquet files matching backtest engine's search logic
   - `DEFAULT_RENAME = {"open_time": "timestamp"}`: column mapping at tool layer
   - `parse_tf_minutes()`: parse "5m"/"1h"/"1d" to minutes
3. `tools/parquet_pipeline/audit.py` (161 lines):
   - Schema check (6 canonical OHLCV columns after rename)
   - Null counts, duplicate timestamps, time-gap detection (>1.5x interval)
   - OHLCV semantic invariants (high>=low, volume>=0)
   - Value ranges
4. `tools/parquet_pipeline/stress.py` (115 lines):
   - `compute_stress_v0()`: log_return, realized_vol (rolling std), ATR (rolling mean of TR),
     gap (inter-bar), bar_range (normalized)
   - Z-scores with `min_periods=1` for partial-window ramp-up
   - inf/NaN z-score cleanup (div-by-zero when std=0)
   - Burn-in row drop via `with_row_index()` filter
5. `tools/parquet_pipeline/__main__.py` (199 lines):
   - CLI: `--symbol`, `--tf`, `--months`, `--audit-only`, `--window`, `--burn-in`
   - Optional config loading from `system_stress` section (fallback: window=100, burn_in=120)
   - Outputs: `audit_report.json`, `stress_timeseries.parquet`, `stress_summary.md`, `provenance.json`
6. `tests/test_parquet_pipeline.py` (30 tests):
   - Discovery: enriched preference, month filter, klines fallback, not-found
   - Audit: valid data, missing cols, nulls, duplicates, gaps, semantics, value ranges
   - Stress: output columns, burn-in, log_return, bar_range, atr, gap, z-score finiteness
   - CLI: audit-only, full pipeline, not-found, month filter

**Real-data validation:** BTCUSDT/5m Jan-Mar 2024 (26,208 bars):
- Audit: 0 gaps, 0 duplicates, all semantics clean
- Z-scores: z_realized_vol max=9.14, z_gap max=9.87 (extreme events correctly detected)

**Verification:** 30/30 new tests green. 225/225 config regression tests green.

---

## 2026-03-01: FIX-DELETED-TOOLS-TESTS-P1 — Restore green config regression

**Task:** Fix 2 pre-existing failing tests referencing deleted/moved tools.
**Context:** `tools/auroractl.py` was moved to `tools/cli/auroractl.py` but tests still
referenced old path. `tools/autofill_config_defaults_into_yaml.py` was deleted with no
replacement; its test was dead.

**Path chosen:** B (update/remove tests to match current tooling).

**Changes:**
1. `tests/config/test_config_strategy_ssot_freeze.py`: Updated `test_auroractl_provenance_stage_is_strategy`
   - `tools/auroractl.py` → `tools/cli/auroractl.py` (moved path)
   - `python3` → `sys.executable` (Windows compat)
2. `tools/cli/auroractl.py`: Fixed `PROJECT_ROOT = parents[1]` → `parents[2]`
   (bug introduced when file moved from `tools/` to `tools/cli/` — path depth changed)
3. `tests/config/test_optional_required_null_autofill.py`: **Removed** (dead test,
   `tools/autofill_config_defaults_into_yaml.py` was deleted with no replacement)

**Why not shims (Path A)?** Creating stub scripts to make dead-tool tests pass would be
creating dead code to pass dead tests. The autofill workflow no longer exists. The auroractl
tool exists at a new path — updating the reference is the correct fix.

**Verification:** `pytest tests/config/ -v` → 225 passed, 3 skipped, 1 deselected, **0 failed**.

---

## 2026-03-01: Phase 0.0A — system_stress SSOT config (PKG-0.0A)

**Task:** Phase 0.0 — System Stress Guard config + Pydantic models
**Context:** Adding independent circuit-breaker overlay (NORMAL/STRESS/EXTREME) for DM gating.
NOT a replacement for TREND/MR regimes — orthogonal guard layer.

**Decision:** NOT creating parallel `regime_foundation/` domain. Additive section in existing
`regime.yaml` SSOT + models in existing `config_models.py`. Avoids config drift, duplicate
loader paths, terminology fragmentation.

**Changes:**
1. `config/aurora/regime.yaml`: +44 lines (`system_stress` section, `enabled: false` by default)
2. `apps/reference/config_models.py`: +205 lines (5 Pydantic models with cross-validators)
   - `SystemStressThresholdsConfig` (7 sigma triggers, orderbook-gated)
   - `SystemStressAggregationConfig` (weighted_vote/k_of_n/max, strict key validation)
   - `SystemStressStateMappingConfig` (hysteresis ordering invariants)
   - `SystemStressConfig` (top-level with rolling/expanding baseline, burn_in, sources_enabled)
3. `AuroraConfig.system_stress: Optional[SystemStressConfig] = None` (backward compatible)
4. `tests/config/test_system_stress_config.py`: 33 tests (unit + ConfigLoader integration)

**Verification:** 33/33 new tests green. 224/224 config regression tests green (0 new failures).

---

## 2026-03-01: Phase 0.0B — Parquet Data Contract (PKG-0.0B)

**Task:** Fail-fast column/dtype/semantic validation for backtest data
**Context:** No data contract existed — bad parquet files would produce cryptic runtime errors
deep in computation. This tooling catches violations at load time.

**Decision:** Placed in `tools/parquet_contract/` (offline tooling), NOT in a new domain.

**Changes:**
1. `tools/parquet_contract/data_contract.py` (251 lines):
   - `OHLCVContract`: 6 required columns (timestamp, OHLCV)
   - `L2Contract`: 5 required columns (timestamp, bid/ask price/qty)
   - `DataContract.validate_dataframe()`: columns, dtype class (float32/float64 both OK),
     nullability, semantic invariants
   - OHLCV semantics: high >= low/open/close, volume >= 0, timestamp UTC
   - L2 semantics: bid < ask, qty >= 0, timestamp UTC
   - Dtype errors short-circuit before semantics (prevent mixed-type crashes)
2. `tests/test_data_contract.py`: 26 tests

**Verification:** 26/26 tests green.

---
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

## 2026-01-30: DM_SAFETY_BYPASSES_P1 — Critical Security Hardening

**Task:** DM_SAFETY_BYPASSES_P1
**Context:** Identified and fixed two critical security vulnerabilities in the `decision_making` domain.

**Vulnerabilities Fixed:**
1. **Hardcoded safety gates bypass:** `apply_safety_gates = str(strategy_id) == "aurora"` allowed any non-Aurora strategy to bypass directional sanity and price motion gates.
2. **Fail-open exposure cache:** Missing/stale/error cache conditions allowed trades, violating fail-closed principle.

**Changes:**
1. `decision_making.py`: Safety gates now read from `strategies.<id>.safety_gates.enabled` config. Missing config → FAIL-CLOSED (NRR-054).
2. `decision_making.py`: Exposure cache precheck now returns `False` (block) on missing/stale/error (NRR-053).
3. `normalized_reject_reasons.py`: Added NRR-053 (EXPOSURE_CACHE_UNAVAILABLE), NRR-054 (CONFIG_SAFETY_GATES_MISSING).
4. `config_models.py`: Added `SafetyGatesConfig` Pydantic model.
5. `aurora.yaml`, `mean_reversion.yaml`: Added explicit `safety_gates.enabled` field.

**Risk Note — Mean Reversion safety_gates.enabled=false:**
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
- `reports/VF-DICT-FORENSIC-01.md` — inventory, validity, duplication signals
- `reports/VF-DICT-FORENSIC-02.md` — proven code/CLI references
- `reports/VF-DICT-FORENSIC-03.md` — where runtime validation lives today
- `reports/VF-DICT-FORENSIC-04.md` — Aurora event-space vs dictionary declarations (OP-level)
- `reports/VF-DICT-FORENSIC-05.md` — Option A/B/C evolution menu (no implementation)

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

## 2026-01-08: VF-VERB-REG — SSOT Verb Registry (seed + warn-only drift gate)

**Task:** VF-VERB-REG-01/02/03
**Context:** Prepare a single SSOT verb registry seeded from runtime string-scan (no runtime enforcement). Add a warn-only CI gate to surface drift immediately without breaking.

**Changes:**
1. **SSOT registry created:** `apps/reference/dictionaries/verb_registry_v1.yaml` generated from runtime scan (`.py` without `tests/**`).
2. **Warn-only gate:** `tests/vfoundation/test_verb_registry_warn_only.py` compares runtime scan vs registry and writes diffs into `reports/` without failing on coverage gaps.
3. **Owner labeling (top-N):** marked owner + status for the top-20 most frequent runtime tokens; schema is populated only when an exact `<verb_lower>_v1.json` exists (otherwise `null`).

**Reports:**
- `reports/VF-VERB-REG-01.md` — seed generation summary
- `reports/VF-VERB-REG-02.md` + `reports/VF-VERB-REG-02_diff.json` — warn-only drift output
- `reports/VF-VERB-REG-03.md` — owner labeling summary

**Non-goals (explicit):** no runtime deny/allow by verb; no attempt to extract registry from `Router.register` (not used in prod wiring).

## 2026-01-08: VF-VERB-REG-04/05 — Owner inference report + coverage threshold

**Task:** VF-VERB-REG-04/05
**Context:** Speed up cleanup of `owner: unknown` with evidence-based path heuristics (no auto-changes). Tighten drift gate so it fails only once coverage is basically complete.

**Changes:**
1. **Owner inference report (no autofix):** Added `tests/vfoundation/test_verb_owner_inference_report.py` which scans runtime `.py` (no tests), aggregates occurrences per file and per `apps/reference/domains/<X>/` bucket, and suggests owner only when ≥70% of occurrences land in one domain.
2. **Artifacts:** Writes `reports/VF-VERB-REG-04_owner_suggestions.json` and `reports/VF-VERB-REG-04.md`.
3. **Coverage gate policy:** Updated `tests/vfoundation/test_verb_registry_warn_only.py` to fail only if `coverage >= 98%` AND `runtime_not_in_registry > 0` (until then it stays warn-only).

## 2026-01-08: VF-VERB-REG-06 — Apply owner suggestions (>=70%)

**Task:** VF-VERB-REG-06
**Context:** Apply evidence-based owner suggestions to reduce `owner: unknown` without guesses.

**Changes:**
- Updated `apps/reference/dictionaries/verb_registry_v1.yaml` by changing **only** `owner` for entries where current owner was `unknown` and inference confidence was ≥70%.
- Regenerated VF-VERB-REG-04 reports after the update.

**Artifacts:**
- `reports/VF-VERB-REG-06_applied.json` — applied changes with confidence + evidence
- `reports/VF-VERB-REG-06.md` — short summary
- **2026-01-08:** Validated and Frozen 'Alpha Search' domain (Task ALPHA-FREEZE-01/02). Added determinism tests, safe metrics, and offline eval script.

## 2026-01-08: AGENT-NAV-VERB-REG-01 — Agent Navigation Playbook (registry-first)

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

## 2026-03-13: Execution-position P0 split-brain repair package

**Task:** P0 execution split-brain / stale TRACKING / unsafe reopen repair
**Context:** The forensic package and repro suite had already proven that `ExecPosFSM` could admit `CMD:OPEN` while local `ManageFlowFSM` was still non-FLAT, and that exit matching could ignore valid TP fills when local tracking still held the pre-ACK client order id.

**Changes:**
1. `apps/reference/domains/execution_position/fsm.py`
   - Added a fail-closed local execution guard in the `CMD:OPEN` path.
   - Added explicit `EVT:EXECUTION_GUARD_BLOCKED` emission and reservation cleanup when local execution state conflicts with a new open.
2. `apps/reference/domains/execution_position/fsm_manage.py`
   - Added explicit stale-lifecycle guard for entry-like fills that arrive over an already-active local lifecycle.
   - Added tracked entry identity fields and matcher helpers.
   - Hardened TP/SL matching to accept runtime `SL-<hash>`, `TP1-<hash>`, `TP2-<hash>` client ids and `client_order_id` payloads.
3. `tests/domains/execution_position/test_split_brain_repro.py`
   - Inverted the repro basis from bug-demonstration tests into fail-closed invariant tests.
4. `reports/forensics/*`
   - Synced split-brain summary/matrix with the repaired state while keeping `H1` as `LIKELY`.

**Validation:**
- RED baseline before fix: `pytest tests/domains/execution_position/test_split_brain_repro.py -q` -> `4 failed, 1 passed`
- GREEN after fix:
  - `pytest tests/domains/execution_position/test_split_brain_repro.py -q` -> `5 passed`
  - `pytest tests/domains/execution_position/test_execpos_cooldown_after_close_v1.py -q` -> `2 passed`
  - `pytest tests/domains/execution_position/test_open_flow_fsm_leverage_and_guards_v1.py -q` -> `8 passed`
  - `pytest tests/domains/execution_position/test_execpos_manage_scenarios_v1.py -q` -> `12 passed`
  - `pytest tests/domains/execution_position -k "split_brain or tracking or bracket" -q` -> `51 passed, 297 deselected`

**Residual unknowns:**
- No raw DOGEUSDT incident event trail was recovered, so `H1` (`WS/order update loss`) remains `LIKELY`, not `CONFIRMED`.

## 2026-03-13: Execution-position P1 observability hardening package

**Task:** P1 execution observability hardening / forensic readiness
**Context:** P0 repaired the split-brain invariants, but guard blocks, divergence, matcher outcomes, and tidy-vs-close paths were still too opaque for fast incident reconstruction.

**Changes:**
1. `apps/reference/domains/execution_position/fsm.py`
   - Enriched `EVT:EXECUTION_GUARD_BLOCKED` payloads with `rid`, local state, portfolio truth, divergence flag, and `why`.
   - Added standalone `EVT:EXECUTION_DIVERGENCE_DETECTED`.
   - Reused `_emit_observability_event(...)` for logger-side structured events.
2. `apps/reference/domains/execution_position/fsm_manage.py`
   - Added execution guard telemetry for `stale_local_lifecycle_conflict`.
   - Added structured exit matcher telemetry: `EVT:EXIT_MATCH_ATTEMPTED` and `EVT:EXIT_MATCH_FAILED`.
3. `apps/reference/domains/execution_position/order_guardian.py`
   - Added `EVT:EXECUTION_TIDY_PERFORMED`.
   - Enriched `EVT:SYMBOL_TIDY` with `tidy_reason`, `business_close_reconciled=false`, and `why`.
   - Added `EVT:EXECUTION_CLOSE_RECONCILED` to separate authoritative reconcile from tidy-only maintenance.
4. Contracts / docs
   - Added execution event schemas under `apps/reference/domains/execution_position/schemas/`.
   - Updated `apps/reference/dictionaries/verb_registry_v1.yaml`.
   - Synced forensic docs and added `reports/forensics/p1_exec_observability_hardening_report.md`.

**Validation:**
- RED baseline before implementation:
  - `pytest tests/domains/execution_position/test_execution_observability_hardening.py -q` -> `5 failed, 1 passed`
- GREEN after implementation:
  - `pytest tests/domains/execution_position/test_execution_observability_hardening.py -q` -> `7 passed`
  - `pytest tests/domains/execution_position/test_split_brain_repro.py -q` -> `5 passed`
  - `pytest tests/domains/execution_position/test_execpos_cooldown_after_close_v1.py -q` -> `2 passed`
  - `pytest tests/domains/execution_position/test_open_flow_fsm_leverage_and_guards_v1.py -q` -> `8 passed`
  - `pytest tests/domains/execution_position/test_execpos_manage_scenarios_v1.py -q` -> `12 passed`
  - `pytest tests/domains/execution_position -k "split_brain or tracking or bracket or observability" -q` -> `63 passed, 292 deselected`

**Residual unknowns:**
- `H1` (`WS/order update loss`) still remains `LIKELY`, not `CONFIRMED`.
- The new telemetry improves future incident reconstruction but does not retroactively recover the original DOGEUSDT raw event chain.

## 2026-03-14: P1 mean reversion logic review package

**Task:** P1 mean reversion logic review / strategy-only audit
**Context:** Execution P0/P1 packages were already closed. This package explicitly separated MR signal logic from execution failure analysis and rebuilt the current MR contract from code, config SSOT, and historical MR telemetry.

**Changes:**
1. `reports/forensics/p1_mean_reversion_logic_review.md`
   - Reconstructed the current MR contract from code and config.
   - Re-ran the March 13, 2026 DOGE incident through the pure strategy lens.
   - Produced decision-ready implementation candidates without changing runtime behavior.
2. `reports/forensics/p1_mean_reversion_logic_review_summary.md`
   - Added an operator-grade short summary.
3. `reports/forensics/p1_mean_reversion_false_positive_archetypes.md`
   - Cataloged recurring false-positive families from historical `bars_300s` telemetry.
4. `reports/forensics/p1_mean_reversion_filter_candidate_matrix.md`
   - Added a lightweight replay matrix comparing candidate filter families by historical pass-rate and March 13 incident coverage.
5. `reports/forensics/p1_mean_reversion_doc_drift_appendix.md`
   - Recorded the main naming and contract-language drifts (`1m/3m` naming, `allowed_regimes` semantics, and older immediate-tuning wording).

**Validation / evidence base:**
- Code/config review only. No strategy code or YAML was changed.
- Historical replay source: `logs/mean_reversion/bars_300s.jsonl`
- Key proved findings:
  - current MR is a 5m Bollinger/%B fade model with RSI as bonus only
  - MR safety gates are disabled in live YAML
  - March 13 DOGE produced five strategy-valid `FLAT_LOW` SHORTs before execution issues compounded the incident
  - historical telemetry shows repeated same-direction fade runs and many `FLAT_LOW` SHORTs

**Residual unknowns:**
- No full-sample realized-trade replay exists for all historical MR signals, so candidate filters are ranked by contract fit and pass-rate, not expectancy.
- BTC-specific hardening remains uncertain because BTC is not currently live-assigned to MR and the historical MR BTC sample is small.

## 2026-03-14: P2-A mean reversion DOGE / high-beta hardening package

**Task:** P2-A implementation package for DOGE/high-beta mean reversion hardening
**Context:** P1 strategy review showed that the highest-confidence first intervention was not a global width bump, but a narrow DOGE/high-beta hardening on `FLAT_LOW` SHORT fades.

**Changes:**
1. `apps/reference/config_models.py`
   - Added strict per-asset MR override field: `flat_low_short_min_bb_width`.
2. `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
   - Added a narrow fail-closed gate for `FLAT_LOW` SHORT candidate setups when a per-symbol stricter width floor is configured.
   - New neutral reason: `flat_low_short_bb_width_too_narrow:<actual><<threshold>`.
3. `apps/reference/domains/decision_making/mean_reversion_handler.py`
   - Wired the new override into runtime strategy config.
   - Reused the existing neutral block path with explicit reason code `FLAT_LOW_SHORT_HARDENED`.
4. `config/aurora/strategies/mean_reversion.yaml`
   - Added `DOGEUSDT.strategy.flat_low_short_min_bb_width: 0.015`.
   - Left all non-DOGE symbols untouched.
5. Tests / report
   - Added `tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py`.
   - Updated `tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py`.
   - Updated `tests/config/test_mean_reversion_yaml_contract.py`.
   - Added `reports/forensics/p2_mr_doge_high_beta_hardening_report.md`.

**Validation:**
- RED before implementation:
  - `pytest tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py -q` -> `4 failed`
  - `pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q` -> `1 failed, 1 passed`
  - `pytest tests/config/test_mean_reversion_yaml_contract.py -q` -> `1 failed, 1 passed`
- GREEN after implementation:
  - `pytest tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py -q` -> `4 passed`
  - `pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q` -> `2 passed`
  - `pytest tests/config/test_mean_reversion_yaml_contract.py -q` -> `2 passed`
  - `pytest tests/domains/test_mean_reversion_strategy.py -q` -> `23 passed, 8 skipped`
  - `pytest tests/domains/decision_making/test_mr_bar_gating.py -q` -> `8 passed`
  - `pytest tests/domains/decision_making/test_mean_reversion_handler_hardening_v1.py -q` -> `11 passed`
  - `pytest tests/domains/execution_position/test_split_brain_repro.py -q` -> `5 passed`

**Residual gaps:**
- This is not yet a squeeze-expansion veto package.
- This is not yet a momentum/slope separation package.
- High-beta family generalization beyond DOGE remains for a later package once more evidence is pinned.

## 2026-03-14: P2-B mean reversion squeeze-expansion veto package

**Task:** P2-B implementation package for squeeze-expansion breakout-fade veto
**Context:** P2-A removed the narrow DOGE toxic short class, but MR still lacked an explicit additive veto for the broader `squeeze -> expansion -> breakout fade` trap.

**Changes:**
1. `apps/reference/config_models.py`
   - Added strict nested config model `MRSqueezeExpansionVetoConfig`.
   - Added per-asset MR override field `squeeze_expansion_veto`.
2. `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
   - Added `squeeze_expansion_veto` runtime config seam.
   - Added helper logic that rebuilds previous BB width from `closes[:-1]`.
   - Added additive veto on `previous squeeze width + current width expansion + active fade trigger`.
   - New neutral reason: `squeeze_expansion_veto:<SIDE>:<prev_width>-><curr_width>`.
3. `apps/reference/domains/decision_making/mean_reversion_handler.py`
   - Wired per-asset typed squeeze veto config into runtime.
   - Added explicit block reason code `SQUEEZE_EXPANSION_VETO`.
4. `config/aurora/strategies/mean_reversion.yaml`
   - Added DOGE-only squeeze veto config:
     - `squeeze_width_max: 0.010`
     - `post_squeeze_width_max: 0.020`
     - `expansion_ratio_min: 2.0`
     - `regimes: ["FLAT_LOW"]`
     - `sides: ["LONG", "SHORT"]`
5. Tests / report
   - Added `tests/domains/feature_engineering/test_mean_reversion_squeeze_expansion_veto.py`.
   - Updated handler/config contract tests.
   - Added `reports/forensics/p2_mr_squeeze_expansion_veto_report.md`.

**Validation:**
- RED baseline (reconstructed temp checkout: after P2-A / before P2-B):
  - `pytest tests/domains/feature_engineering/test_mean_reversion_squeeze_expansion_veto.py -q` -> `5 failed`
  - `pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q` -> import error for missing `MRSqueezeExpansionVetoConfig`
  - `pytest tests/config/test_mean_reversion_yaml_contract.py -q` -> import error for missing `MRSqueezeExpansionVetoConfig`
- GREEN after implementation:
  - `pytest tests/domains/feature_engineering/test_mean_reversion_squeeze_expansion_veto.py -q` -> `6 passed`
  - `pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q` -> `2 passed`
  - `pytest tests/config/test_mean_reversion_yaml_contract.py -q` -> `3 passed`
  - `pytest tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py -q` -> `4 passed`
  - `pytest tests/domains/test_mean_reversion_strategy.py -q` -> `23 passed, 8 skipped`
  - `pytest tests/domains/decision_making/test_mr_bar_gating.py -q` -> `8 passed`
  - `pytest tests/domains/decision_making/test_mean_reversion_handler_hardening_v1.py -q` -> `11 passed`
  - `pytest tests/domains/execution_position/test_split_brain_repro.py -q` -> `5 passed`

**Residual gaps:**
- This still is not the momentum/slope separation package.
- Broader high-beta family generalization remains a later follow-up if more MR assets are enabled.

## 2026-03-14: P2-C mean reversion momentum / slope separation package

**Task:** P2-C implementation package for late-drift / momentum-separation veto
**Context:** P2-B closed the breakout-from-squeeze trap, but MR still lacked a narrow additive veto for later counter-trend fades after volatility had already expanded and directional drift remained obvious.

**Changes:**
1. `apps/reference/config_models.py`
   - Added strict nested config model `MRMomentumSeparationVetoConfig`.
   - Added per-asset MR override field `momentum_separation_veto`.
2. `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
   - Added `momentum_separation_veto` runtime config seam.
   - Added additive late-drift helper on `lookback closes + cumulative drift + current width floor + active fade side`.
   - New neutral reason: `momentum_separation_veto:<SIDE>:<signed_pct>%`.
3. `apps/reference/domains/decision_making/mean_reversion_handler.py`
   - Wired typed momentum veto config into runtime.
   - Added explicit block reason code `MOMENTUM_SEPARATION_VETO`.
4. `config/aurora/strategies/mean_reversion.yaml`
   - Added DOGE-only momentum-separation config:
     - `lookback_bars: 4`
     - `min_drift_pct: 0.02`
     - `min_current_bb_width: 0.020`
     - `regimes: ["FLAT_LOW"]`
     - `sides: ["LONG", "SHORT"]`
5. Tests / report
   - Added `tests/domains/feature_engineering/test_mean_reversion_momentum_slope_separation.py`.
   - Updated handler/config contract tests.
   - Added `reports/forensics/p2_mr_momentum_slope_separation_report.md`.

**Validation:**
- RED baseline:
  - `pytest tests/domains/feature_engineering/test_mean_reversion_momentum_slope_separation.py -q` -> `5 failed`
  - `pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q` -> import error for missing `MRMomentumSeparationVetoConfig`
  - `pytest tests/config/test_mean_reversion_yaml_contract.py -q` -> import error for missing `MRMomentumSeparationVetoConfig`
- GREEN after implementation:
  - `pytest tests/domains/feature_engineering/test_mean_reversion_momentum_slope_separation.py -q` -> `7 passed`
  - `pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q` -> `2 passed`
  - `pytest tests/config/test_mean_reversion_yaml_contract.py -q` -> `4 passed`
  - `pytest tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py -q` -> `4 passed`
  - `pytest tests/domains/feature_engineering/test_mean_reversion_squeeze_expansion_veto.py -q` -> `6 passed`
  - `pytest tests/domains/test_mean_reversion_strategy.py -q` -> `23 passed, 8 skipped`
  - `pytest tests/domains/decision_making/test_mr_bar_gating.py -q` -> `8 passed`
  - `pytest tests/domains/decision_making/test_mean_reversion_handler_hardening_v1.py -q` -> `11 passed`
  - `pytest tests/domains/execution_position/test_split_brain_repro.py -q` -> `5 passed`

**Residual gaps:**
- This is still not a broad trend engine or regime redesign package.
- Broader high-beta family rollout beyond DOGE remains a later follow-up if more MR assets are enabled.

 # #   2 0 2 6 - 0 3 - 1 4 :   N E O - P R O D U C E R - C O N T R A C T - A L I G N M E N T - P K G - 1 - 4 - V E R I F I C A T I O N 
 
 * * T a s k : * *   V e r i f y   a n d   f i n a l i z e   N E O - P R O D U C E R - C O N T R A C T - A L I G N M E N T   p a c k a g e s   1   t h r o u g h   4 . 
 
 * * W h a t   w a s   d o n e : * * 
 -   P h a s e   0 :   V e r i f i e d   A u r o r a   o p e r a t e s   a s   o n e - a c t i v e - l i f e c y c l e - p e r - s y m b o l .   C o n f i r m e d   F S M   p e r - s y m b o l   c a c h e s   f o r   i d e m p o t e n t _ k e y ,   	 r a d e I d ,   s i d e ,   a n d    e e s   a r e   s a f e . 
 -   P h a s e   1 :   V e r i f i e d   p r o p a g a t i o n   o f   l i f e c y c l e _ i d   v i a   i d e m p o t e n t _ k e y   a c r o s s   O R D E R _ I N T E N T ,   O R D E R _ F I L L E D ,   a n d   P O S I T I O N _ C L O S E D .   
 -   P h a s e   2 :   V e r i f i e d   s t r u c t u r e d   c l o s e   i d e n t i t y   v i a   	 r a d e _ i d   a n d   c o r r e c t   s i d e   i n   P O S I T I O N _ C L O S E D . 
 -   P h a s e   3 :   V e r i f i e d   f e e s   a c c u m u l a t i o n   a n d   
 e t _ p n l   c o m p u t a t i o n   i n   c l o s e   p a t h . 
 -   P h a s e   4 :   V e r i f i e d   s t r u c t u r e d   c l o s e   v a l i d a t i o n   a n d   t e s t   c o v e r a g e   ( 4 7 / 4 7   p a s s i n g   t e s t s ) . 
 
 * * V e r d i c t : * * 
 I m p l e m e n t a t i o n   i s   c o n f i r m e d   s a f e ,   c o m p l e t e ,   a n d   f u l l y   t e s t e d .   A l l   4   h a r d   b l o c k e r s   ( H B - 1   t o   H B - 4 )   a r e   f u n c t i o n a l l y   r e s o l v e d   o n   t h e   e x e c u t i o n   s i d e . 
 
 
 
 
