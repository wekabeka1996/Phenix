# TODO

## Runtime recovery + MR regression follow-ups (added 2026-03-15)

### P1: Post-deploy live verification
- [ ] Restart runtime and verify `STARTUP_BASIS_IMPORTED`, `STARTUP_BASIS_SEEDED`, and `STRATEGY_READINESS_STATE` appear for every warmup-sensitive symbol
- [ ] Confirm `md_amr` jumps to `>=96/96` and `aurora` jumps to `>=301/301` immediately after startup instead of climbing one live bar at a time
- [ ] Capture the first post-restart 30 minutes of `aurora_core.log`, `aurora_trades.log`, and lifecycle logs as evidence that readiness is now real

### P1: Mean reversion regression closure
- [ ] Investigate Binance `-1007` timeout path for MR order intents and determine whether execution retry/state reconciliation is missing
- [ ] Replay current 300s DOGE config versus rolled-back 300s DOGE config on the same historical window to measure whether the rollback restores edge
- [ ] Decide explicitly whether historical 180s MR pipeline should be restored or the 300s line should remain the production contract

### P2: Bootstrap contract hardening
- [ ] Add a deployment-grade check that fails loudly when hydration plan exists but imports/seeds resolve to zero for warmup-sensitive handlers
- [ ] Add operator-facing alerting when `STRATEGY_READINESS_STATE.ready=false` persists beyond the first startup warmup window

## Bootstrap readiness — residual debt (added 2026-03-15)

### P1: Hydration data-path verification
- [ ] Verify `PillarBackfillService.fetch_candles()` actually returns sufficient bars for all enabled symbols in production
- [ ] Verify `started_strategy_handlers` dict is populated before `execute_startup_basis_hydration()` runs (timing dependency)
- [ ] Add integration test that runs full bootstrap → hydration → seed → readiness check path end-to-end

### P1: Quadratic trace sink routing
- [ ] Verify `EVT:QUADRATIC_DECISION_TRACE` is picked up by the operator-visible decision sink (not just FSM bus)
- [ ] Consider adding JSONL file sink for quadratic traces (`logs/aurora/quadratic_trace.jsonl`)

### P2: Readiness dashboard
- [ ] Wire `get_readiness_diagnostics()` to a periodic health check emitter (e.g. every 60s after startup)
- [ ] Consider adding `/readiness` HTTP endpoint for operator tooling

## Test suite follow-ups (added 2026-03-15)

### P1: Manual review candidates (RESOLVED 2026-03-15)
- [x] ~~`tests/test_execution_schemas_sim.py`~~ — deleted in LEGACY-PURGE-WAVE-2 (zero assertions, superseded)
- [x] ~~`tests/integration/test_decision_qos_features_burst.py`~~ — deleted in LEGACY-PURGE-WAVE-2 (mock-only, forbidden .get())
- [x] `tests/units/test_binance_adapter_session.py` — KEEP (xfail removed in TEST-HYGIENE-NORMALIZATION)
- [x] `tests/integration/test_features_full_chain_happy.py` — KEEP (integration value, modernize later)

### P2: Test location consolidation
- [ ] Resolve `tests/units/` vs `tests/unit/` dual naming
- [ ] Consolidate `tests/execution_position/` → `tests/domains/execution_position/`
- [ ] Consolidate `tests/decision_making/` → `tests/domains/decision_making/`
- [ ] Relocate root-level test orphans to appropriate subdirectories

### P2: Empty directory cleanup (RESOLVED 2026-03-15)
- [x] ~~Remove 14 empty directories under tests/~~ — removed 17 in LEGACY-PURGE-WAVE-2

### P3: Pre-existing test failure (RESOLVED 2026-03-15)
- [x] ~~Fix 4 `.get()` patterns in `mean_reversion_strategy.py`~~ — done in FORBIDDEN-CONFIG-PATTERN-FIX

## Legacy Purge Wave 2 candidates (added 2026-03-15)

### P2: Skipped deprecated event tests
- [x] ~~Delete `tests/integration/test_market_tick_forwarded_emitted.py`~~ — done in TEST-SUITE-RECLASSIFICATION
- [x] ~~Delete `tests/integration/test_mr_receives_forwarded_tick_smoke.py`~~ — done in TEST-SUITE-RECLASSIFICATION
- [ ] Review `scripts/diagnostics/mr_restore_002_probe.py` MARKET_TICK_FORWARDED ref

### P2: Default timeframe mismatch
- [ ] Unify `domain_builder.py` fallback `[60, 300]` and `BarAggregator.__init__` default `[180, 300]`

### P2: Absorption stub
- [ ] `websocket_aggregator.py:335` hardcodes `"absorption": "0.0"` — implement or document as intentional

### P2: Memory leak risk
- [ ] `seen_trade_ids` set in WebSocketAggregator has no size limit — add eviction

### P3: WS URL duplication
- [ ] Extract hardcoded Binance WS URLs from 2 files (connector, worker) into config

## Legacy Purge Wave 1 (completed 2026-03-15)
- [x] Deleted `market_ws_client.py` (119 LOC dead module)
- [x] Cleaned `__init__.py` MarketWSClient export
- [x] Deleted dead imports: `asdict` (bar_aggregator), `time` (connector)
- [x] Deleted `set_feature_engineering()` no-op from proxy + connector
- [x] Deleted 7 ghost .pyc in vfoundation/ (5 unique stems)
- [x] Deleted 2 orphaned vfoundation directories (apps/, services/)
- [x] Purged 45 deprecated doc files across 7 domains (docs/deprecated/)
- [x] Purged all test `__pycache__/` directories
- [x] Updated guardrail tests (3 anti-reintroduction + 3 cross-project)
- [x] Report: `reports/cleanup/LEGACY_PURGE_WAVE_1_2026-03-15.md`

## Market data domain audit (completed 2026-03-15)
- [x] Phase A: Context map — 7 files, ~2,661 LOC, 3 active verbs, 1 deprecated
- [x] Phase B: Created domain_dict.json v1.0.0, staleness note on docs/README.md
- [x] Phase C: Created authoritative README.md
- [x] Phase D: 15 guardrail tests in `test_md_domain_structural_guardrails.py`
- [x] Phase E: Report `reports/domains/MARKET_DATA_DOMAIN_AUDIT_2026-03-15.md`

## FE-DM boundary stabilization follow-ups (added 2026-03-15)

### P2: Physical strategy file migration
- [ ] Move `mean_reversion_strategy.py`, `md_amr_strategy.py`, `regime_mapping.py` from FE to DM
- [ ] Convert `strategy_bridge.py` into backward-compat shim in FE
- [ ] Update ~17 test files to import from bridge or DM paths

## FE-DM boundary stabilization (completed 2026-03-15)
- [x] Classified 5 disputed files (3 WRAP_BEHIND_DM_FACADE, 2 KEEP_IN_FE)
- [x] Created `decision_making/strategy_bridge.py` (13 symbols)
- [x] Migrated 3 DM production files (5 import sites)
- [x] Updated both domain README.md and domain_dict.json
- [x] 6 guardrail tests in `test_fe_dm_boundary_guardrails.py`
- [x] Report `reports/domains/FE_DM_BOUNDARY_STABILIZATION_2026-03-15.md`

## FE domain audit follow-ups (added 2026-03-15)

### P3: Config-drive strategy constants
- [ ] Make BB/RSI/ATR defaults in MR/MD-AMR config-overridable (currently hardcoded)

### P3: Unify duplicate compute_sma
- [ ] Consider unifying `indicators.compute_sma()` (list-based) and `pillar_indicators.compute_sma()` (deque-based) with adapter pattern

### P3: Purge deprecated FE docs
- [ ] Purge or refresh stale docs in `apps/reference/domains/feature_engineering/docs/deprecated/` (7 files)

### P3: Fix FE skipped/xfail tests
- [ ] Fix `test_features_full_chain_happy.py` (skipped: complex async domain integration chain)
- [ ] Fix P1-1, P1-2 xfail tests in `test_task24_feature_engineering_correctness.py`

### P4: Ghost test .pyc cleanup (cross-project)
- [ ] Clean ~15 ghost .pyc across test __pycache__ directories (not FE-specific)

## FE domain audit (completed 2026-03-15)
- [x] Phase A: Context map — 16 files, ~8,849 LOC, 7 consumed / 3 emitted events, ~150+ tests
- [x] Phase B: Deleted 2 ghost .pyc (config, feature_engineering_phase1), rewrote domain_dict.json v2.0.0, staleness note
- [x] Phase C: Created authoritative README.md
- [x] Phase D: 15 guardrail tests in `test_fe_domain_structural_guardrails.py`
- [x] Phase E: Report `reports/domains/FEATURE_ENGINEERING_DOMAIN_AUDIT_2026-03-15.md`

## RD domain audit follow-ups (added 2026-03-14)

### P3: Purge/refresh deprecated RD docs
- [ ] Purge or refresh stale docs in `apps/reference/domains/regime_detector/docs/deprecated/` (6 files)

### P3: Fix skipped integration test
- [ ] Fix `tests/integration/test_regime_detector_event_flow.py` (unconditionally skipped — needs BAR-ONLY mock payload)

### P3: Create shared RegimeLabel Enum
- [ ] Consider extracting regime label strings to a shared Enum class (currently raw strings, schema-only enforcement)

### P4: Add RegimeDetector re-export to __init__.py
- [ ] Add `from .regime_detector import RegimeDetector` to `__init__.py` (currently only exports `__version__`)

### P4: Replace silent bar_ttl_ms default
- [ ] Replace `getattr(sys_md, "bar_ttl_ms", 10000)` with explicit config contract (minor config opacity)

## RD domain audit (completed 2026-03-14)
- [x] Phase A: Context map — 2 files, 803 LOC, ~181 test functions, clean event-driven, priority cascade
- [x] Phase B: Cleanup — deleted ghost config.cpython-311.pyc, created domain_dict.json, staleness note
- [x] Phase C: Created authoritative README.md
- [x] Phase D: 10 guardrail tests in `test_rd_domain_structural_guardrails.py`
- [x] Phase E: Report `reports/domains/REGIME_DETECTOR_DOMAIN_AUDIT_2026-03-14.md`

## RM domain audit follow-ups (added 2026-03-14)

### P3: Purge/refresh auto-generated RM docs
- [ ] Purge or refresh stale auto-generated docs in `apps/reference/domains/risk_management/docs/` subdirectory

### P3: Delete broken test_risk_strategy_fsm.py
- [ ] Delete `tests/domains/test_risk_strategy_fsm.py` (references non-existent `risk_strategy` domain, unconditionally skipped)

## RM domain audit (completed 2026-03-14)
- [x] Phase A: Context map — 3 files, 990 LOC, 73 test functions, clean 2-layer fail-closed
- [x] Phase B-F: Rewrote garbled domain_dict.json v2.0.0, created README, staleness note, 11 guardrail tests
- [x] Phase G: Report `reports/domains/RISK_MANAGEMENT_DOMAIN_AUDIT_2026-03-14.md`

## EP contract boundary follow-ups (added 2026-03-14)

### P3: Update CONTRACT_ARCHITECTURE.md with co_emitters policy
- [ ] Add co_emitters annotation pattern to `docs/contracts/CONTRACT_ARCHITECTURE.md`

## EP domain audit follow-ups (added 2026-03-14)

### P3: Consolidate triple OrderStatus enum
- [ ] Extract adapter mapping functions instead of merging the 3 OrderStatus enums (contracts.py, idempotent_cancel.py, infra/order_ledger.py)

### P3: Add missing EP event schemas
- [ ] Add schemas for ~20 EP-emitted events with `schema: null` in registry

### P3: Purge/refresh auto-generated EP docs
- [ ] Purge or refresh stale auto-generated docs in `apps/reference/domains/execution_position/docs/` subdirectory

### P4: Evaluate fsm.py split
- [ ] Evaluate splitting fsm.py (2,056 LOC) into smaller orchestration units (very low priority)

## EP contract boundary (completed 2026-03-14)
- [x] EXPOSURE_SUMMARY_UPDATED owner moved from risk_management to execution_position
- [x] co_emitters annotations added to TRADE_INTENT_REJECTED and TRADE_EXECUTED
- [x] NRR import migrated from direct DM import to shared/types.py re-export
- [x] 8 guardrail tests in `test_ep_contract_boundary_guardrails.py`

## EP domain audit (completed 2026-03-14)
- [x] Phase A: Context map — 40 live files, ~16,500 LOC, 9 consumed + 31 emitted events, ~1,192 test functions
- [x] Phase B: Cleanup — 3 ghost subpackages, 12 ghost .pyc, broken conftest import fixed
- [x] Phase C: Lifecycle hygiene — triple OrderStatus documented (not merged)
- [x] Phase D+E: Authoritative README.md, domain_dict.json v1.0.0, staleness notes on docs/
- [x] Phase F: 13 guardrail tests in `test_ep_domain_structural_guardrails.py`
- [x] Phase G: Report `reports/domains/EXECUTION_POSITION_DOMAIN_AUDIT_2026-03-14.md`

## DM domain audit follow-ups (added 2026-03-14)

### P3: Consolidate schemas.py + schemas_decision_blocked.py
- [ ] Merge into single `models.py` or consolidate, to avoid confusion with JSON `schemas/` dir

### P3: Migrate all DM WhyCode imports
- [ ] Migrate all `from .why_codes import` to `from vfoundation.core.why_codes import` (currently backward-compatible via re-export shim)

### P3: Purge/refresh auto-generated docs
- [ ] Purge or refresh 12 auto-generated docs in `apps/reference/domains/decision_making/docs/` subdirectory

### P4: Rename shields/ to safety/
- [ ] Consider `shields/` → `safety/` rename for clarity (very low priority)

## DM domain audit (completed 2026-03-14)
- [x] Phase A: Context map — 37 live files, ~98 test files, 13 consumed + 12 emitted events
- [x] Phase B: Cleanup — 5 pycache ghosts, 1 empty test, stale docs fixed
- [x] Phase C: Authoritative README.md, domain_dict.json v2.0.0, __init__.py v2.0.0
- [x] Phase D: 8 guardrail tests in `test_dm_domain_structural_guardrails.py`
- [x] Phase E: Report `reports/domains/dm_domain_audit_2026-03-14.md`

## Contract SSOT consolidation follow-ups (added 2026-03-14)

### P2: NRR ad-hoc code migration
- [ ] Normalize `NRR-LEV-REDUCE`, `NRR-LEV-BRACKET`, `NRR-MARGIN-ORDERS`, `NRR-MARGIN-POSITION`, `NRR-CANCEL-STRICT`, `NRR-INSTRUMENT-CONFIG-MISSING` to `NRR-\d{3}` format in canonical NormalizedRejectReasons

### P2: Schema coverage push
- [ ] Add schemas for high-traffic active contracts with `schema: null` (ORDER_REJECTED, ORDER_STATE_CHANGED, ACCOUNT_UPDATE_RECEIVED, ORDER_PLACED, BALANCE_UPDATE_RECEIVED)

### P3: WhyCode import migration
- [ ] Migrate all `from decision_making.why_codes` imports to `from vfoundation.core.why_codes` (currently backward-compatible via re-export shim)

### P3: NRR WhyCode removal
- [ ] Remove 9 deprecated NRR members from `vfoundation/core/why_codes.py` WhyCode enum (after verifying no production consumers)

### P3: VERB_PAYLOAD_MAP decision
- [ ] Either promote to active Pydantic migration or remove entirely

### P3: vfoundation event registration policy
- [ ] Decide whether internal meta-FSM/routing events (STATE_TRANSITION, DOMAIN_STATUS, INIT, ENTROPY_SPIKE, etc.) should be registered in verb_registry or remain internal

### Schema cleanup
- [ ] Remove duplicate `schemas/portfolio_state_v1.json` (keep `apps/reference/domains/position_tracking/schemas/portfolio_state_v1.json` which is registry-referenced)
- [ ] Decide whether orphan sub-schemas (`bracket_order_v1.json`, `bracket_error_v1.json`, `features_price_motion_v1.json`, `order_clipped_event_v1.json`, `order_rejected_event_v1.json`) should be registered or remain internal
- [ ] Decide whether `message_v1.json` and `order_logger_v1.json` should be registered or documented as internal

## Contract SSOT consolidation (completed 2026-03-14)
- [x] WhyCode fork resolved — 7 codes promoted to vfoundation, decision_making converted to re-export
- [x] 12 dead registry entries marked deprecated
- [x] VERB_PAYLOAD_MAP frozen as COMPATIBILITY-ONLY
- [x] Architecture spec: `docs/contracts/CONTRACT_ARCHITECTURE.md`
- [x] 9 guardrail tests: `tests/contracts/test_contract_ssot_guardrails.py`

## Contract audit (completed 2026-03-14)
- [x] 20 missing contracts added to registry
- [x] Broken schema ref fixed, duplicate removed, 7 owner fixes
- [x] 28 regression tests in `tests/contracts/test_contract_registry_audit.py`

## Config namespace cleanup (completed 2026-03-14)
- [x] Relocate `config/aurora_baseline/` and `config/mean_reversion/` to `archive/config_snapshots/`
- [x] Create archive manifest `archive/config_snapshots/README.md`
- [x] Create config SSOT contract `config/README.md`
- [x] Clean `PROJECT_ATLAS.md` dead config entries
- [x] Add regression guard `tests/config/test_config_namespace_ssot.py`
- [x] Update JOURNAL.md and JOURNAL_мій.md

## Execution-position P0 split-brain repair package (updated 2026-03-13)

### Implemented in this package
- [x] Add a fail-closed local execution guard so `CMD:OPEN` is rejected whenever local execution still owns an active lifecycle
- [x] Add an explicit divergence gate so `REST=FLAT` + local `FSM=TRACKING` blocks reopen until reconciliation completes
- [x] Repair stale-lifecycle handling so an unexpected new entry fill cannot stay on the old `TRACKING` path with old bracket ids
- [x] Normalize exit matching so pre-ACK client ids and exchange order ids both reconcile valid TP/SL fills
- [x] Keep `OrderGuardian.cleanup_orphans()` / `EVT:SYMBOL_TIDY` as maintenance only; do not treat tidy/cleanup as a substitute for business close reconciliation
- [x] Convert `tests/domains/execution_position/test_split_brain_repro.py` from bug-demonstration evidence into fail-closed invariant tests

### Follow-up still open
- [ ] Recover raw runtime evidence to upgrade or disprove `H1` (`WS/order update loss`) beyond `LIKELY`
- [ ] Capture live/testnet event traces for the original DOGEUSDT incident window so the primary trigger can be classified without inference

## Mean reversion state machine passport follow-ups (added 2026-03-13)

### Runtime / contract cleanup exposed by MR state-machine re-audit
- [ ] Rename or clearly annotate stale `1m` / `3m` MR names and comments so they do not contradict live `timeframe_sec=300`
- [ ] Replace or unskip `tests/integration/test_mean_reversion_handler_event_contract_v1.py`; it still targets an obsolete tick-driven path instead of current `CMD:PROCESS_STRATEGY` bar-driven runtime
- [ ] Keep incident and strategy docs explicit that `MeanReversion1mStrategy` stops at signal formation, while `ExecPosFSM` / `ManageFlowFSM` own downstream lifecycle and reconciliation failures

## MD-AMR strategy passport follow-ups (added 2026-03-13)

### Runtime / contract cleanup exposed by md_amr re-audit
- [ ] Decide whether `strategies.md_amr.execution.gtx_fallback_to_market` should trigger a real fallback path after GTX reject exhaustion or be renamed/documented as logging-only bookkeeping
- [ ] Decide whether `MDAMRHandler.reconcile_position()` needs explicit end-to-end wiring from exchange/account sync or should be documented as a local dormant hook
- [ ] Decide whether unassigned asset blocks in `config/aurora/strategies/md_amr.yaml` should remain mixed into the live profile or be separated from the active contract surface

## LLM microstructure passport follow-ups (added 2026-03-13)

### Runtime / contract cleanup exposed by llm microstructure re-audit
- [ ] Align bridge-emitted `EVT:STRATEGY_SIGNAL_PRODUCED.tf_sec` with `strategies.llm_microstructure.timeframe_sec`, or explicitly codify why the bridge must emit `300` while the profile declares `60`
- [ ] Decide whether `strategies.llm_microstructure.enabled` should become a real runtime gate for ingress / bridge wiring or remain typed metadata only
- [ ] Keep `shadow_telemetry` docs and strategy docs aligned on the sentinel-plugin architecture so llm_microstructure is not described as a normal in-process handler

## Instruments passport follow-ups (added 2026-03-13)

### Runtime / contract cleanup exposed by instruments re-audit
- [ ] Either wire `instruments.<SYM>.execution.max_notional_utilization` into a real runtime capacity/exposure gate or remove it from the active live execution contract
- [ ] Decide whether `instruments.<SYM>.symbol` should be validated against the map key or removed as duplicated metadata
- [ ] Continue deprecating or clearly marking legacy strategy-side leverage fields that are now ignored when they disagree with instruments SSOT

## Strategies passport follow-ups (added 2026-03-13)

### Runtime / contract cleanup exposed by strategies re-audit
- [ ] Remove or wire `strategies_registry.arbitration.logging.log_level`; no runtime arbitration consumer was found
- [ ] Decide whether `aurora.enabled` should become a hard activation constraint or remain a soft/profile metadata flag beside assignment SSOT
- [ ] Document `llm_microstructure` consistently as sentinel plugin + bridge-driven runtime across internal strategy docs
- [ ] Review whether any unassigned strategy profiles should still be prevalidated at startup or remain load-on-assignment only

## Aurora math passport follow-ups (added 2026-03-13)

### Runtime / contract cleanup exposed by aurora math re-audit
- [x] Remove or wire `AuroraInstrumentConfig.scoring_version`; current Aurora loader routes only through global `DecisionConfig.scoring_version`
  - **DONE (Phase 9 cleanup 2026-03-14):** Per-asset `scoring_version` marked DEPRECATED with `default=None`, non-operational. Global `DecisionConfig.scoring_version` defaults to `"quadratic"`.
- [ ] Decide whether per-symbol `neutral_threshold` should exist in strict `AuroraInstrumentConfig` or be removed from Aurora runtime probing
- [ ] Keep decision-making internal docs aligned with the Phase 14A decomposed runtime topology instead of treating `aurora_handler.py` as the sole math owner
- [ ] Review whether deprecated `side_bias_min_score` should remain in `DecisionConfig` now that no Aurora math consumer was found

## Scoring passport follow-ups (added 2026-03-13)

### Runtime / contract cleanup exposed by scoring re-audit
- [ ] Align `DecisionConfig.scoring_version` with rollout contract: either retire `v1` from Pydantic or make rollout contract accept it explicitly
- [ ] Remove or wire `strategies.aurora.decision.regime_thresholds`; current Aurora kernels ignore the global block and use `regime_threshold_multipliers`
- [ ] Remove or wire `ScoringEngineConfig.exposure_cap` in Aurora live runtime / quantization path
- [ ] Remove or wire `ScoringEngineConfig.min_pillar_confidence` in Quadratic runtime path
- [ ] Remove or implement `LiquidityGateConfig.failsafe_qty_check`; current runtime only echoes it in diagnostics
- [x] Decide explicitly whether Aurora remains on configured `v2` or moves to explicit `quadratic` rollout in `config/aurora/strategies/aurora.yaml`
  - **DONE (Phase 9 cleanup 2026-03-14):** Aurora is now quadratic-only. `scoring_version: "quadratic"` is the sole active path. v2 runtime deleted.
- [x] If Quadratic remains planned, add explicit live YAML blocks for `scoring_engine` and `quadratic_rollout` instead of relying on repo-level code presence
  - **DONE (Phase 9 cleanup 2026-03-14):** `scoring_engine` and `quadratic_rollout` are now explicit in aurora.yaml with fail-closed defaults.
- [ ] Decide whether `trading.risk.daily.max_realized_loss_usd` should be wired into `DailyRiskState.can_open()` or removed from the active L1 contract

## Aurora runtime audit follow-ups (added 2026-03-10)

### Must-fix before next live/testnet run with Quadratic ambitions
- [ ] Wire startup HTF pillar backfill into live bootstrap and emit `EVT:HTF_BARS_IMPORTED` before Aurora signal generation
- [ ] Add explicit Quadratic readiness gate so FE/DM readiness cannot be `true` while `pillar_sum` is still absent
- [x] Make runtime intent explicit: keep Aurora on `v2` or switch to `quadratic`; do not leave activation implicit in repo state
  - **DONE (Phase 9 cleanup 2026-03-14):** `scoring_version: quadratic` is now the global default, v2 runtime fully deleted, rollback infrastructure non-operational.
- [ ] Add startup/restart policy for regime and pillar state: historical seed, snapshot restore, or explicit cold-start deny window
- [ ] Add one end-to-end integration test from runtime startup to first Quadratic-ready `CMD:PROCESS_STRATEGY`
- [ ] Reconcile `market_data_connector.py` runtime behavior with its REST/klines docstring, or remove the stale contract claim
- [ ] Decide whether current 5m regime cold-start requirement must be satisfied by startup history load instead of natural live accumulation
- [x] Evaluate explicitly setting `scoring_version: "quadratic"` in `config/aurora/strategies/aurora.yaml` when Phase 9 pillars are globally ready.
  - **DONE (Phase 9 cleanup 2026-03-14):** All config variants now set `scoring_version: "quadratic"`. Default in schema is `"quadratic"`.
- [ ] Periodically sync `regime_passport.md` with upcoming Phase R3-A Grid calibrations, specifically monitoring shifts in `sma_short_period`, `sma_long_period`, and `atr_sma_length`.
- [ ] Ensure `aurora_math_passport.md` is updated if Phase 9 introduces new quadratic bounds on signal strengths or significantly alters the hysteresis formula.

## Neocortex production-shadow remediation (planned 2026-03-10)

### External unblocker
- [x] `NEO-UNBLOCK-PYTEST-COLLECT-TUPLE-IMPORT`: verified on current branch as already resolved; `apps/reference/config_models.py` already imports `Tuple`, and `pytest apps/reference/domains/neocortex/tests --collect-only -q` collects successfully

### Newly exposed non-collection follow-ups
- [ ] Python 3.14 asyncio compatibility: replace legacy `asyncio.get_event_loop()` test helper usage in `apps/reference/domains/neocortex/tests/test_integration.py`
- [ ] Shadow-learning dependency/runtime follow-up: `apps/reference/domains/neocortex/tests/test_simulation_bar_v2.py` expects neural path activity, but current environment lacks `torch` and the brain bridge degrades

### P0 Context Freeze / Baseline Verification
- [ ] Freeze current neocortex baseline against `reports/neocortex_deep_domain_audit_2026-03-10.md`
- [ ] Add baseline replay fixtures for features, order logs, and core close logs under `apps/reference/domains/neocortex/tests/fixtures/`
- [ ] Add contract-manifest consistency test for `apps/reference/domains/neocortex/domain.yaml`
- [ ] Document and test path-resolution behavior for replay config paths

### P1 Canonical Time Contract
- [x] Add canonical `event_ts_ms` contract to neocortex ingest path
- [x] Remove replay wallclock from causal ordering / idempotency logic
- [x] Normalize feature, order, and core log timestamps to one unit
- [x] Update stale cleanup and replay ordering to use canonical ms only
- [x] Add `test_time_contract.py` and extend ingest / replay tests
- [x] Make missing feature timestamp policy explicit and fail-closed by default
- [ ] P1 follow-up: remove `legacy_non_causal_file_offset` compatibility once feature producers emit real causal timestamps
- [ ] P1 follow-up: decide whether aurora text-log timestamp parsing needs an explicit timezone contract for cross-host replay portability

### P2 Canonical Episode Identity + Fill-Aware Lifecycle
- [x] Add lifecycle identity contract: `lifecycle_id`, `trade_id`, `order_id`, `client_order_id`
- [x] Move episode entry anchor from `ORDER_PLACED` to `ORDER_FILLED` or canonical open event
- [x] Support partial fills and overlapping same-symbol lifecycles
- [x] Fail closed on ambiguous close mapping
- [x] Add lifecycle-focused episode identity tests
- [ ] P2 follow-up: retire the temporary `legacy_rid` fill-resolution bridge after canonical fill IDs are emitted upstream

### P3 Reward Contract / Structured Close Feed
- [x] Define canonical close / reward payload with completeness status
- [x] Prefer structured close feed; keep parser only as transitional shim
- [x] Add reward completeness and coverage tests
- [x] Extend `test_reward_parsing.py` and add close-feed fixtures
- [x] P3 follow-up: producer-side close plane must emit canonical `close_price` / `fees` / `trade_id` consistently
      — RESOLVED by `AURORA-PRODUCER-CONTRACT-ALIGNMENT-IMPLEMENTATION` (2026-03-12):
        `lifecycle_id` (Phase 1), `trade_id` + real `side` (Phase 2), `fees` + `realized_pnl_net`
        (Phase 3) now emitted as top-level keys in `ORDER_INTENT`, `ORDER_FILLED`, and
        `POSITION_CLOSED` writes. 57 TDD tests + 19 contract tests + 1140 regression tests pass.
- [ ] P3 follow-up: retire the transitional parser shim once authoritative structured close events exist

### P4 Objective Split
- [x] Split representation, regime supervision, execution-quality prediction, and policy learning buffers
- [x] Remove regime-oracle / execution semantic mixing from one PPO head
- [x] Disable polluted policy training by default until a clean `PolicySample` producer exists
- [x] Add `test_objective_split.py`
- [ ] P4 follow-up: wire `ppo.state_dim` to an explicit policy-state contract or remove it
- [ ] P4 follow-up: add `test_state_vector_contract.py`

### P5 Sequence Semantics Repair
- [x] Add explicit sequence contract: `stateless_per_event` inference + `independent_rows` representation training
- [x] Eliminate global hidden reuse by resetting recurrent state before every inference call
- [x] Add deterministic replay-start sequence reset through BrainBridge
- [x] Reject sequence-shaped representation batches fail-closed under the narrowed contract
- [x] Add `test_sequence_semantics.py`
- [ ] P5 follow-up: add canonical sequence-owner metadata before any future per-stream stateful mode is enabled
- [ ] P5 follow-up: re-enable temporal world-model training only after explicit sequence dataset assembly exists
- [ ] P5 follow-up: if policy training is ever re-enabled, require the same sequence-owner contract in policy samples

### P6 Dataset Hygiene Layer
- [x] Add contamination quarantine for `MagicMock` and malformed identity rows
- [x] Build canonical dataset manifests with provenance and hash
- [x] Enforce time-based train / validation / test splits
- [x] Add `test_dataset_hygiene.py`
- [x] Add `test_provenance.py`
- [ ] P6 follow-up: persist dataset manifests to an explicit artifact path when offline dataset builds become a first-class workflow
- [ ] P6 follow-up: extend provenance source inventory from adapter-local refs to canonical upstream source identifiers where available
- [ ] P6 follow-up: keep policy dataset admission blocked until a future post-remediation policy contour is explicitly re-opened

### P7 Performance / Replay Engineering
- [x] Split live-shadow mode from offline-replay mode
- [x] Buffer non-critical shadow/telemetry writes and remove per-row synchronous flush from hot path
- [x] Add deterministic decimation policy for shadow-intent observational outputs
- [x] Define queue/flush/overflow budgets for non-critical side effects
- [x] Add `test_performance_contract.py`
- [x] Add `test_replay_engineering.py`
- [ ] P7 follow-up: add explicit throughput/CPU/disk benchmark test (`test_shadow_hot_path_budget.py`)
- [ ] P7 follow-up: consider any encode/act batching only after semantic-equivalence fixtures exist for replay determinism and objective/provenance preservation

### P8 Production Shadow Gates
- [x] Add gate runner for production shadow acceptance criteria
- [x] Block production-shadow startup on hard gate failures
- [x] Block any production-shadow label until gates are green
- [ ] P8 follow-up: persist startup gate reports as first-class artifacts when release packaging/evaluator harness is added
- [ ] P8 follow-up: add explicit acceptance-gate suite for deterministic replay equality and manifest consistency as release artifacts, not only startup config gating

### P9 Path to 9.5/10 advisory architecture
- [x] Add uncertainty estimation and calibration reporting
- [ ] Add OOD / drift detector contracts
- [ ] Add agent-state-aware inputs
- [x] Add offline evaluator with calibration, disagreement, and reward-coverage metrics
- [x] Keep advisory read-only until dedicated advisory gates are green
- [ ] P9 follow-up: build canonical shadow-vs-Aurora comparison corpus from persisted artifacts instead of synthetic comparator inputs
- [ ] P9 follow-up: harden confidence-source lineage beyond `sample.confidence` and define confidence provenance per report
- [ ] P9 follow-up: add OOD/drift evaluator package before any advisory-only gate discussion
- [ ] P9 follow-up: add agent-state-aware evaluator inputs before any usefulness claim on contextual execution advice

### Acceptance gate checklist
- [ ] 100% canonical timestamp normalization on valid inputs
- [ ] 0 mixed-unit time defects on fixtures
- [ ] 0 hidden-state leakage across symbols
- [x] 0 contaminated rows in canonical train dataset
- [ ] Reward extraction coverage meets target threshold on valid close fixtures
- [ ] Deterministic replay equality with fixed seed
- [ ] Contract-manifest consistency green
- [ ] Throughput and memory stay within configured budgets
- [ ] Ambiguous lifecycle mapping fails closed

### Next recommended package
- [x] `NEO-P1-CANONICAL-TIME-CONTRACT`
- [x] Prerequisite note: repo-level pytest collection blocker is cleared on the current branch
- [x] `NEO-P2-CANONICAL-EPISODE-IDENTITY-FILL-AWARE-LIFECYCLE`
- [x] `NEO-P3-REWARD-CONTRACT-STRUCTURED-CLOSE-FEED`
- [x] `NEO-P4-OBJECTIVE-SPLIT`
- [x] `NEO-P5-SEQUENCE-SEMANTICS-REPAIR`
- [x] `NEO-P6-DATASET-HYGIENE-AND-PROVENANCE`
- [x] `NEO-P7-PERFORMANCE-AND-REPLAY-ENGINEERING`
- [x] `NEO-P8-PRODUCTION-SHADOW-GATES`
- [x] `NEO-P9-EVALUATOR-CALIBRATION-AND-ADVISORY-HARDENING`
- [x] `NEO-INTEGRATION-DATA-CONTRACT-AUDIT` (audit/research only, no code changes)
- [x] `NEO-PRODUCER-CONTRACT-ALIGNMENT-AUDIT-AND-IMPLEMENTATION-PLAN` (audit only, 2026-03-12)
- [x] Post-remediation milestone: `NEO-PRODUCER-CONTRACT-ALIGNMENT-PKG-1` (lifecycle_id propagation)
      — DONE 2026-03-12: intent_builder, fsm, event_handlers. 19 TDD tests green.
- [x] Post-remediation milestone: `NEO-PRODUCER-CONTRACT-ALIGNMENT-PKG-2` (trade_id + side)
      — DONE 2026-03-12: real side + tradeId cached+emitted in POSITION_CLOSED. 16 TDD tests green.
- [x] Post-remediation milestone: `NEO-PRODUCER-CONTRACT-ALIGNMENT-PKG-3` (fees + net_pnl)
      — DONE 2026-03-12: fee accumulation per lifecycle, realized_pnl_net computed at close. 22 TDD tests green.
- [x] Post-remediation milestone: `NEO-PRODUCER-CONTRACT-ALIGNMENT-PKG-4` (structured close validation)
      — DONE 2026-03-12: 19 contract tests + dead-code annotation. All 1140 regression tests pass.
- [ ] Post-remediation milestone: `NEO-ACCEPTANCE-CAMPAIGN-SHADOW-ANALYTICS`

## EP-SSOT-NORMALIZE-SIGNEDV2 — normalize_mode SSOT Enforcement (completed 2026-03-01)
- [x] P1: Wire `normalize_signals_mode` YAML → `AuroraConfigLoaderMixin` → `AuroraScoringKernel` (block non-`signed_v2` in kernel)
- [x] P1: `intent_builder.py` — pass `normalize_mode` + write `normalize_mode_effective` to WAL ORDER_INTENT metadata
- [x] P1: `decision_making.py` — pass `normalize_mode` to `build_and_emit_trade_intent`
- [x] P1: `test_normalize_mode_ssot.py` — 15 TDD tests
- [x] P2: `config_models.py` — `SignalsConfig.normalize_signals_mode: Literal["signed_v2"]` (removed `"off"`)
- [x] P2: `config_models.py` — removed dead `_forbid_legacy_normalize_signals_in_live` validator
- [x] P2: `aurora_config_loader.py` — `ConfigContractError` on `signals=None` (strict pydantic path)
- [x] P2: `decision_making.py` — `normalize_signals_mode` init block (mirrors AuroraConfigLoaderMixin)
- [x] P2: Fix test fixtures (`"off"` → `"signed_v2"` in 4 test files; `SimpleNamespace` + `__new__`-bypass fixtures in 3 test files)
- [x] P2: Evidence pack clean (no active `legacy_v1`/`net_zero` in apps/; WAL metadata wired)
- 513/513 tests pass (decision_making + config + audit combined); 5 pre-existing unrelated fails untouched

## Phase 0.0 — Regime Foundation (completed 2026-03-01)
- [x] Phase 0.0A: system_stress SSOT config in `regime.yaml` + Pydantic models (33 tests)
- [x] Phase 0.0B: Parquet data contract `tools/parquet_contract/` (26 tests)
- [x] FIX-DELETED-TOOLS-TESTS-P1: config regression restored to green (225 pass, 0 fail)

## Phase 0.1 — Parquet Audit + Stress v0 (completed 2026-03-01)
- [x] Phase 0.1: `tools/parquet_pipeline/` — Polars-native audit + stress extract CLI (30 tests)

## Phase 0.2 — Stress State Actuator (completed 2026-03-01)
- [x] Phase 0.2: aggregation (z-scores → stress_level) + hysteresis FSM (53 tests total)
- [x] Z-score no-lookahead fix (`.shift(1)` on rolling baseline)
- [x] Real-data validation: 226 switches / 26,088 bars, 90.5% NORMAL, 9.5% STRESS, 0% EXTREME
- **Tuning note:** 226 switches (~2.5/day) is borderline. Config tuning (consecutive_bars_enter, min_duration_bars) may reduce to "tanker" profile.

## Phase 0.3 — Actuator Preset Grid Search (completed 2026-03-01)
- [x] Phase 0.3: `tools/parquet_pipeline/tune_presets.py` — 6-preset grid, winner selection, `reports/stress_tuning_report.md`
- [x] Winner: **A4** (enter=0.60, consecutive_enter=6, min_duration=15, switch_window=200, max_per_window=2)
  - 140 switches (1.55/day), NORMAL=93.2%, STRESS=6.8%, longest_run=865 bars
- **Key finding:** bifurcation at enter_stress 0.60 vs 0.65 — 0.65 is decorative on this data (0.1% STRESS), 0.60 with CB+inertia (A4) is the correct approach.

## Phase 0.4 — A4 Multi-Symbol Portability (completed 2026-03-01)
- [x] Phase 0.4: `tools/parquet_pipeline/validate_preset.py` + `reports/stress_a4_multiasset_report.md`
- [x] A4 PORTABLE: BTCUSDT(1.55/6.8%), ETHUSDT(1.57/7.0%), DOGEUSDT(1.39/5.4%), 1000PEPEUSDT(1.28/4.9%)
- A4 is the **confirmed foundation preset** — ready for `regime.yaml` update + DM integration

## Phase 0.5 — SystemStressOverlay Live DM Integration (completed 2026-03-01)
- [x] `apps/reference/domains/system_stress/system_stress_overlay.py` (new domain)
- [x] `schemas/system_stress_state_updated_v1.json` (event schema)
- [x] `config/aurora/regime.yaml` state_mapping updated to A4 values
- [x] `normalized_reject_reasons.py`: `SYSTEM_STRESS_ENTRY_BLOCKED = "NRR-059"`
- [x] `decision_making.py`: `_system_stress_states` cache + `_on_system_stress` handler
- [x] `safety_gates.py`: Gate 0.5 (`EXTREME→DENY`, `STRESS→ALLOW+surface`), `system_stress_state` field
- [x] `domain_builder.py` + `main.py`: both live and backtest paths wired
- [x] 22 tests green; 0 regressions introduced
- **Gate semantics:** EXTREME=DENY(NRR-059), STRESS=ALLOW+surface for Phase 0.6 attenuation

## Phase 0.6 — Per-Strategy SystemStress Policy + STRESS Attenuation (completed 2026-03-01)
- [x] `config_models.py`: `SafetyGatesConfig` + `system_stress_policy: Literal["off","attenuate","block"]` + `stress_attenuation_factor: float`
- [x] `aurora.yaml`: `system_stress_policy: attenuate`, `stress_attenuation_factor: 0.50`
- [x] `mean_reversion.yaml`: `system_stress_policy: "off"` (quoted — YAML 1.1 bare `off` = bool `False`)
- [x] `safety_gates.py`: `_resolve_stress_policy()` helper (fail-open), `_check_system_stress_gate()` updated, `apply_safety_gates()` wired
- [x] `strategy_gateway.py`: STRESS attenuation block (`margin_pct_mult *= factor` when STRESS+attenuate), wrapped in `try/except` (fail-open)
- [x] `tests/test_stress_policy.py`: 23 new tests (5 classes: ResolveStressPolicy, Off, Attenuate, Block, Attenuation)
- [x] `tests/test_system_stress_overlay.py`: `_call()` default updated to `stress_policy="attenuate"` (backward compat)
- [x] 45/45 stress tests green; 0 regressions (5 pre-existing failures unchanged)

## Phase R1 — Market Structure Audit (completed 2026-03-01)
- [x] `tools/parquet_pipeline/market_structure.py` (new): 5 analysis blocks — distribution stats, persistence, regime separability, structural breaks, stability grid
- [x] `tools/parquet_pipeline/__main__.py`: `r1` subcommand, `_parse_months_range()`, `_generate_r1_report()`, `main_r1()`, manifest output
- [x] `tests/test_market_structure.py` (new): 38 tests, 0 regressions, 0.37s
- [x] Design: polars-first, no scipy, histogram Bhattacharyya, 2-axis proxy labels, Hurst R/S, `--include-grid` optional
- **Next:** Phase R2 — regime grid calibration (confidence vs. outcome heatmaps per regime)

## Phase R2 — Regime Grid Calibration (completed 2026-03-01)
- [x] `tools/parquet_pipeline/regime_grid.py` (new): 5 label/scoring/grid functions
- [x] `tools/parquet_pipeline/__main__.py`: `r2` subcommand, `_parse_r2_args`, `_generate_r2_report`, `main_r2`
- [x] `tests/test_regime_grid.py` (new): 29 tests, 0 regressions, 0.37s
- Grid axes: sma_short [24,36,48], sma_long [96,144,192], slope_threshold [0.0005–0.002], atr_window [14,21,28], hyst [1,2,3] = 324 valid combos
- Scoring: 50% stability + 40% separability − 10% coverage penalty; score ∈ [-0.10, 0.90]
- **Next:** Phase R3 — Strategy overlay (expectancy curves per regime, TP/SL grid analysis)

## Phase R3-B — Forward Separability (completed 2026-03-01)
- [x] `tools/parquet_pipeline/forward_separability.py` (new): fwd_ret_N, Cohen's d, sign lift, edge verdict, vol interaction matrix
- [x] `tools/parquet_pipeline/__main__.py`: `r3b` subcommand, `_parse_r3b_args`, `_generate_r3b_report`, `main_r3b`
- [x] `tests/test_forward_separability.py` (new): 34 tests, 0 regressions, 0.53s
- Edge verdict thresholds: strong (|d|>0.20 AND |lift|>0.05), moderate (0.10/0.02), weak (0.05/0.01), none
- CLI finding: TREND_UP sign lift ≈ 0 (NOT a binary entry filter); Cohen's d > 0 (fat-tail mean) → sizing signal; TREND_DOWN = oversold marker for MR

## Phase R3-A-lite — Market Policy Tables (completed 2026-03-01)
- [x] `tools/parquet_pipeline/policy_tables.py` (new): `compute_edge_table`, `derive_trend_policy`, `derive_mr_policy`; CVaR-5%, tail_uplift, Kelly-like sizing_mult
- [x] `tools/parquet_pipeline/__main__.py`: `r3a` subcommand; `--with-stress` A4 actuator integration; per-symbol parquet + markdown report + manifest
- [x] `tests/test_policy_tables.py` (new): 24 tests, 0 regressions, 0.51s
- CLI run: 4 symbols × 9 months with `--with-stress` (BTC 482 sw, ETH 472 sw, DOGE 434 sw, PEPE 412 sw)
- **Aurora sizing cross-symbol consensus:** `TREND_UP|HIGH_VOL` → increase (3/4), `TREND_DOWN|HIGH_VOL` → increase (4/4); `sizing_mult ≈ 1.08–1.16`
- **MR entry cross-symbol consensus:** `TREND_DOWN|HIGH_VOL|NORMAL` → boost all 4; `TREND_UP|MID_VOL|STRESS` → block/reduce 3/4
- **Next:** Phase R3-A full — backtest trade join + expectancy per regime (TP/SL heatmaps, confidence curves, after backtest re-run with preliminary weights)

## Phase 0.7 — Backtest Engine DataContract Integration (completed 2026-03-04)
- [x] `backtest_engine/engine.py`: `_validate_ohlcv_contract()` — native polars, 4-check pipeline (columns/dtype/nulls/semantics)
- [x] `backtest_engine/engine.py`: `load_data()` — `except ValueError: raise` guard so contract violations are fatal
- [x] `tests/backtest_engine/test_data_contract_integration.py` (new): 9 tests (6 unit + 3 integration), 0 regressions
- Design note: pandas-based `DataContract` skipped — no `pyarrow`; polars-native impl used directly

## Phase 0.x — Next steps
- [ ] Phase 0.8: L2 orderbook integration (spread/depth triggers, require_l2_if_enabled fail-fast)
- [ ] Phase 0.9: Visualization tooling — stress overlay on price charts for research
- [ ] Phase R3-A full: Backtest trade join + expectancy per regime, TP/SL heatmaps, confidence curves per (trend×vol×stress) cell

## VF-VERB-REG follow-ups
- VF-VERB-REG-02: periodically review `reports/VF-VERB-REG-02_diff.json` in CI logs and keep registry in sync with runtime.
- VF-VERB-REG-02: switch from warn-only to fail when coverage is ~100% (planned: warn-only → shadow-deny → hard-deny).
- VF-VERB-REG-03: continue replacing `owner: unknown` with real domain owners; add schemas where there is a confirmed JSON schema.
- VF-VERB-REG-04: use `reports/VF-VERB-REG-04_owner_suggestions.json` to batch-update owners with evidence (no guesses).
- VF-VERB-REG-05: gate now fails only when coverage ≥98% and missing>0; keep an eye on the threshold and adjust when registry matures.
- VF-VERB-REG-06: applied all owner suggestions with confidence ≥70%; next is to rerun VF-VERB-REG-04 regularly and batch-apply new high-confidence suggestions.
- VF-VERB-REG: decide SSOT policy for wildcards (keep default false; `UPD` currently allowed by policy).

## Execution observability follow-up
- [x] P1 execution observability hardening package
  - Added structured execution guard/divergence/matcher/tidy/reconcile telemetry.
  - Added execution event schemas and registry entries.
  - Kept P0 split-brain invariants green while improving forensic readability.
- [ ] Recover raw WS / adapter payload evidence for the DOGEUSDT incident path so `H1` can be upgraded or disproven with direct proof.

## Mean reversion research follow-up
- [x] P1 mean reversion logic review package
  - Rebuilt the current MR contract from code/config/log evidence.
  - Separated strategy weakness from already-closed execution failures.
  - Produced false-positive archetypes and a candidate filter matrix.
- [x] P2-A MR DOGE / high-beta hardening package
  - Added per-asset `flat_low_short_min_bb_width` contract and DOGE-only `FLAT_LOW` short hardening.
  - Blocked the narrow-band toxic DOGE short class without globally bumping `min_bb_width`.
- [x] P2-B MR squeeze-expansion veto package
  - Added per-asset squeeze-expansion veto on `previous width + expansion ratio + active fade trigger`.
  - Scoped the live YAML rollout to DOGE `FLAT_LOW` for minimal blast radius.
- [x] P2-C MR momentum-separation package
  - Added a per-asset `momentum_separation_veto` on cumulative drift plus current-width floor.
  - Scoped the live YAML rollout to DOGE `FLAT_LOW` and kept P2-B ownership of squeeze traps.
- [ ] P2 MR broader high-beta family package
  - Decide whether squeeze/hardening contracts should be generalized beyond DOGE when more MR assets are enabled.
- [ ] P2 MR broader regime redesign package
  - Keep broader trend/regime separation out of the narrow P2-C blast radius unless new evidence justifies it.
- [ ] P2 MR contract cleanup / doc-sync package
  - Normalize 5m terminology and clarify `allowed_regimes`, RSI, and filter ownership semantics.

## Phase 9 Quadratic cleanup — remaining follow-ups (added 2026-03-14)

### Completed in this cleanup pass
- [x] Fix validator bug: `_validate_direction_strength_contract` made scoring-mode-aware
- [x] Kill rollback-to-v2 runtime: `_VALID_SCORING_VERSIONS = {"quadratic"}`, gate always active
- [x] Shield fail-closed: NullShield guard + `is not True` identity check
- [x] Config defaults: `scoring_version → "quadratic"`, `shield_enabled → True`
- [x] Stale enum cleanup: `LEGACY_LIVE`, `V2_LIVE`, `V2_ROLLBACK` removed from `QuadraticRolloutMode`
- [x] Broken files deleted: 4 files importing deleted v2 modules
- [x] Alpha_search config: `scoring_version → "quadratic"` in YAML and Pydantic model
- [x] Stale docstrings: `AuroraScoringKernel` references updated in handler, adapter, kernel
- [x] Config variant annotations: mean_reversion and baseline YAML annotated with DEPRECATED
- [x] Scoring passport: deleted module references marked DEPRECATED

### Still open (low-risk / deferred)
- [ ] Remove `Literal["v1", "v2"]` from `DecisionConfig.scoring_version` type — requires config migration for existing YAML files
- [ ] Remove dead wiring: `signal_weights` / `feature_neutrals` / `direction_strength_cfg` kwargs passed to `QuadraticScoringKernel.compute()` (accepted but ignored)
- [ ] Remove dead helpers: `_get_signal_weights()`, `_get_feature_neutrals()` in `aurora_scoring_helpers.py`
- [ ] Remove dead direction_strength_scoring parsing in `aurora_config_loader.py:170-177`
- [ ] Clean alpha_search `scenario_matrix.yaml` signal_weight overrides (tuning dead knobs)
- [ ] Clean alpha_search `override_allowlist.py` deprecated config paths
- [ ] Update `DOMAIN_DOCUMENTATION_DECISION_MAKING.md` to reference QuadraticScoringKernel
- [ ] Review `tools/calibration/calibrate_aurora_signal_weights.py` — operates on dead config surfaces

### Pre-existing test failures (not caused by this cleanup)
- [ ] `test_no_forbidden_config_get_patterns` — `.get()` patterns in `mean_reversion_strategy.py`
- [ ] `test_stale_features_do_not_update_buffers` — regime detector stale_features assertion
- [ ] `test_emit_failure_logged_not_swallowed` — order guardian log message mismatch
