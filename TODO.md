# TODO

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
