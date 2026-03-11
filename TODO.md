# TODO

## Aurora runtime audit follow-ups (added 2026-03-10)

### Must-fix before next live/testnet run with Quadratic ambitions
- [ ] Wire startup HTF pillar backfill into live bootstrap and emit `EVT:HTF_BARS_IMPORTED` before Aurora signal generation
- [ ] Add explicit Quadratic readiness gate so FE/DM readiness cannot be `true` while `pillar_sum` is still absent
- [ ] Make runtime intent explicit: keep Aurora on `v2` or switch to `quadratic`; do not leave activation implicit in repo state
- [ ] Add startup/restart policy for regime and pillar state: historical seed, snapshot restore, or explicit cold-start deny window
- [ ] Add one end-to-end integration test from runtime startup to first Quadratic-ready `CMD:PROCESS_STRATEGY`
- [ ] Reconcile `market_data_connector.py` runtime behavior with its REST/klines docstring, or remove the stale contract claim
- [ ] Decide whether current 5m regime cold-start requirement must be satisfied by startup history load instead of natural live accumulation

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
- [ ] P3 follow-up: producer-side close plane must emit canonical `close_price` / `fees` / `trade_id` consistently
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
- [ ] Post-remediation milestone: `NEO-PRODUCER-CONTRACT-ALIGNMENT` (4 hard blockers to fix)
- [ ] Post-remediation milestone: `NEO-ACCEPTANCE-CAMPAIGN-SHADOW-ANALYTICS`

## NEO-PRODUCER-CONTRACT-ALIGNMENT — Aurora-side telemetry fixes for neocortex integration (identified 2026-03-11)

### Hard blockers (must fix before execution quality family works)
- [ ] HB-1: Add `lifecycle_id` to ORDER_INTENT, ORDER_FILLED, POSITION_CLOSED in `order_log_v1.jsonl` — `intent_builder.py:357-364`, `event_handlers.py:403-420`, `event_handlers.py:236-250`
- [ ] HB-2: Add `trade_id` to POSITION_CLOSED log entries — `event_handlers.py:236-250` (cache from last fill `tradeId`)
- [ ] HB-3: Emit structured `fees` and `realized_pnl_net` in POSITION_CLOSED — `event_handlers.py:236-250` (accumulate `commission` per lifecycle)
- [ ] HB-4: Replace core log regex parser dependency — either (a) structured JSON close events in `aurora_core.log`, or (b) new `lifecycle_parser.py` for `trade_lifecycle.jsonl`

### Soft prerequisites (for live shadow)
- [ ] SP-1: Feature engineering must embed `event_ts_ms` in every feature log line (required for `fail_closed` timestamp policy)
- [ ] SP-2: Persist Aurora decision reference for disagreement analysis (minimal JSONL with strategy_id, symbol, side, score, regime, ts_ms)
- [ ] SP-3: Add restart-gap detection in neocortex ingest (quarantine samples during cold-start window)

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
