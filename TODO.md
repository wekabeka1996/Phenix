# Aurora Refactoring TODO

## ✅ Phase 0: Per-Instrument Config Architecture — COMPLETE
- [x] [P0-01] Add AuroraSideBiasConfig, AuroraExitConfig models — config_models.py
- [x] [P0-02] Add AuroraTakeProfitConfig, AuroraTrailingStopConfig models — config_models.py
- [x] [P0-03] Add AuroraExecutionConfig, AuroraInstrumentConfig models — config_models.py
- [x] [P0-04] Add aurora_instruments field to TradingConfig — config_models.py
- [x] [P0-05] Add self.symbol tracking to ManageFlowFSM — fsm_manage.py
- [x] [P0-06] Add _get_aurora_instr_cfg helper to FSM — fsm_manage.py

## ✅ Track A: Aurora Phase 3+ — COMPLETE

### A1: Per-Asset Core Parameters
- [x] [A1-01] Refactor signal_weights lookup with per-instrument fallback — decision_making.py
- [x] [A1-02] Add _get_side_bias_params helper — decision_making.py
- [x] [A1-03] Add _get_regime_thresholds helper — decision_making.py
- [x] [A1-04] Add _get_regime_sizing helper — decision_making.py
- [x] [A1-05] Add sample aurora_instruments config — trading.yaml

### A2: TP1/TP2 Partial Exit
- [x] [A2-01] Refactor _calculate_bracket_prices to return (sl, tp1, tp2) — fsm_manage.py
- [x] [A2-02] Add _get_take_profit_params helper — fsm_manage.py
- [x] [A2-03] Add _calculate_sl_from_pct, _calculate_tp_from_bps helpers — fsm_manage.py
- [x] [A2-04] Add _quantize_prices helper — fsm_manage.py
- [x] [A2-05] Modify bracket placement for TP1/TP2 partial qty — fsm_manage.py
- [x] [A2-06] Add tp1_order_id, tp2_order_id, tp1_price, tp2_price fields — fsm_manage.py
- [x] [A2-07] Add take_profit config sample — trading.yaml
- [x] [A2-08] Add tests for TP1/TP2 calculation — test_aurora_instrument_config.py

### A3: Trailing Stop
- [x] [A3-01] Add _get_trailing_stop_params helper — fsm_manage.py
- [x] [A3-02] Add peak_price field for high-water mark tracking — fsm_manage.py
- [x] [A3-03] Refactor _check_trailing_stop to use per-instrument config — fsm_manage.py
- [x] [A3-04] Fix _adjust_trailing_stop to use opposite side — fsm_manage.py
- [x] [A3-05] Add trailing_stop config sample — trading.yaml
- [x] [A3-06] Add tests for trailing stop config — test_aurora_instrument_config.py

### A4: Max Hold Time Watchdog
- [x] [A4-01] Add _get_max_hold_sec helper — fsm_manage.py
- [x] [A4-02] Add _check_max_hold_time method — fsm_manage.py
- [x] [A4-03] Integrate max hold check in _check_rules — fsm_manage.py
- [x] [A4-04] Add tests for max hold time — test_aurora_instrument_config.py

## ✅ Configuration: Instruments SSOT Migration — COMPLETE
- [x] [C0-SSOT-01] Wire config/aurora/instruments.yaml → ConfigLoader + Pydantic + fail-fast
- [x] [C0-SSOT-02] Wire DecisionMaking + execution_position to config.instruments SSOT
- [x] [C0-SSOT-03-AUDIT] Audit trading.yaml for SSOT duplicates + add guardrails (CFG-TRADING-YAML-BURN-DOWN-01)
- [x] [C0-SSOT-03-BURNDOWN] Видалити deprecated trading.instruments/domains mirrors після міграції всіх споживачів (CFG-TRADING-YAML-BURN-DOWN-02)

## Configuration: Instrument Parameters (XRPUSDT/DOGEUSDT/SOL/ETH)
- [ ] [C1] Додати XRPUSDT до instruments.yaml з правильними tick_size/step_size
- [ ] [C2] Додати DOGEUSDT до instruments.yaml з правильними tick_size/step_size
- [ ] [C3] Оновити SOLUSDT параметри (tick_size, step_size) згідно з Binance specs
- [ ] [C4] Оновити ETHUSDT параметри (tick_size, step_size) згідно з Binance specs
- [ ] [C5] Додати min_notional для всіх інструментів (перевірити з Binance exchangeInfo)
- [ ] [C6] Додати exchange-specific filters (MAX_POSITION, MAX_NUM_ORDERS тощо)
- [ ] [C7] Валідація інструментів проти Binance exchangeInfo API при старті

## ✅ Tech Debt Cleanup — COMPLETE
- [x] [TD-01] Remove legacy trail_pct/breakeven_after_sec stub fields — fsm_manage.py
- [x] [TD-02] Remove Rule 1 (ADJUST_TRAIL) stub logic — fsm_manage.py
- [x] [TD-03] Remove Rule 2 (ADJUST_BE) stub logic — fsm_manage.py
- [x] [TD-04] Update FSM docstrings to remove stub references — fsm_manage.py
- [x] [TD-05] Update legacy tests to use new BATCH format — test_manage_flow_fsm_sl_side.py, test_manage_flow_fsm_unit.py
- [x] [TD-06] Verify all tests pass after cleanup — 50 tests passed
- [x] [TD-07] Remove duplicate DecisionConfig class — config_models.py
- [x] [TD-08] Remove duplicate exposure field — config_models.py

## ✅ Track B: 1m Mean Reversion — COMPLETE
- [x] [B1-01] Create bar resampler (tick → 1m OHLCV) — bar_resampler.py (25 tests)
- [x] [B2-01] Add Bollinger Bands indicator — indicators.py (26 tests)
- [x] [B3-01] Add FLAT regime mapping — regime_mapping.py (34 tests)
- [x] [B4-01] Create MeanReversion1mStrategy module — mean_reversion_strategy.py (25 tests)
- [x] [B4-02] Add feature_engineering __init__.py exports — all modules exported
- [x] [B4-03] Create 1m MR config — config/aurora/strategies/mean_reversion_1m.yaml
- [x] [B4-04] Clean up config_models.py duplicates — removed DecisionConfig/exposure dups

## ✅ Track B5: MR Integration in DecisionMaking — COMPLETE
- [x] [B5-01] Add MR 1m Pydantic models to config_models.py (MeanReversion1mStrategyConfig, etc.)
- [x] [B5-02] Update ConfigLoader to load strategies/mean_reversion_1m.yaml
- [x] [B5-03] Create MeanReversionHandler in decision_making/ — mean_reversion_handler.py
- [x] [B5-04] Wire MR handler into DecisionMaking.__init__() — decision_making.py
- [x] [B5-05] Add EVT:TICK_RECEIVED listener → on_tick → MRSignal → EVT:TRADE_INTENT_PROPOSED
- [x] [B5-06] Forward regime to MR handler in on_regime() — decision_making.py
- [x] [B5-07] Add config_sizing support to regime_mapping.py (config-driven multipliers)
- [x] [B5-08] Add regime_sizing parameter to MeanReversion1mStrategy — mean_reversion_strategy.py
- [x] [B5-09] Add tests for MR handler — test_mean_reversion_handler.py (16 tests)
- [x] [B5-10] Add tests for config_sizing — test_regime_mapping.py (+7 tests)
- [x] [B5-11] Fix UnboundLocalError in fsm_manage.py (LOG shadowing) — fsm_manage.py

## ✅ Phase C: Config Completion & Validation — COMPLETE

- [x] [C0-SSOT-01] STEP next: підключити execution/DM до config.instruments (забрати tick/step з legacy trading.instruments)
- [x] [C0-SSOT-02] STEP next: підключити execution_position rounding/filters → config.instruments (fsm_open.py, fsm_manage.py)
- [x] [C0-SSOT-03] STEP next: burn-down trading.instruments mirror після міграції всіх споживачів (CFG-TRADING-YAML-BURN-DOWN-02 DONE)

## Phase C: Instrument Coverage Expansion 🔴 IN PROGRESS

**Джерело:** `apps/research/new_alpha/` — R&D документи з Optuna результатами

### C1: Додати XRPUSDT Config (30m) 🔴 HIGH — **+$74/міс**
- [ ] [C1-01] Add instruments.XRPUSDT (step_size, tick_size) — trading.yaml
- [ ] [C1-02] Add XRPUSDT + DOGEUSDT to symbols_to_track — trading.yaml
- [ ] [C1-03] Add aurora_instruments.XRPUSDT (weights, side_bias, TP, trailing!) — trading.yaml

### C2: Додати DOGEUSDT + Enable 1m MR (30m) 🔴 HIGH — **+$88/міс**
- [ ] [C2-01] Add instruments.DOGEUSDT — trading.yaml
- [ ] [C2-02] Set mean_reversion_1m.enabled: true — mean_reversion_1m.yaml
- [ ] [C2-03] Verify DOGEUSDT asset config (bb_window=20, sl=1.97%) — mean_reversion_1m.yaml

### C3: Оновити SOLUSDT до Phase 3 (20m) 🟡 MEDIUM — **+$117/міс**
- [ ] [C3-01] Update weights from best_aurora_SOLUSDT_3m_phase3.json — trading.yaml
- [ ] [C3-02] Update regime_sizing (0.6/2.0/0.7) — trading.yaml
- [ ] [C3-03] Verify side_bias (Phase 3 says 0.0 but RESULTS_PHASE3 says 0.4!) — trading.yaml

### C4: Оновити ETHUSDT Phase 3+ (20m) 🟡 MEDIUM — **+$50/міс**
- [ ] [C4-01] Add TP params (tp_low_ratio=0.4, tp_high_ratio=1.4) — trading.yaml
- [ ] [C4-02] Set trailing_stop.enabled: false — trading.yaml
- [ ] [C4-03] Add execution.cooldown_sec: 15 — trading.yaml

### C5: Валідація Config Loading (15m) 🔴 HIGH
- [ ] [C5-01] Test all aurora_instruments load correctly — test_config_loading.py
- [ ] [C5-02] Test config fallback chain works — test_config_loading.py

### C6: End-to-End Multi-Symbol Test (1-2h) 🔴 HIGH
- [ ] [C6-01] Create multi_symbol_fsm fixture — test_multi_symbol_aurora.py
- [ ] [C6-02] Test bracket prices per symbol — test_multi_symbol_aurora.py
- [ ] [C6-03] Test trailing stop per symbol (XRP=on, ETH=off) — test_multi_symbol_aurora.py
- [ ] [C6-04] Test max_hold per symbol — test_multi_symbol_aurora.py

### C7: Testnet Smoke Test (2-4h) 🟡 MEDIUM
- [ ] [C7-01] Run system with ETHUSDT only — manual
- [ ] [C7-02] Verify order placement (SL/TP1/TP2) — manual
- [ ] [C7-03] Run multi-symbol (ETH/SOL/XRP/DOGE) — manual

---

## ⏳ Optional Phases

### Phase A5: Phase 3+ Risk Weights (2-3h)
- [ ] [A5-01] Add compute_phase3_risk_score() to feature_engineering
- [ ] [A5-02] Add per-asset risk_weights config
- [ ] [A5-03] Integrate with decision_making.py
- [ ] [A5-04] Add tests for risk score

### Phase V: Walk-Forward Validation (10-15h)
- [ ] [V-01] Walk-forward validation on historical data
- [ ] [V-02] Compare backtest vs live metrics
- [ ] [V-03] Production config finalization

---

## 📊 Summary
- **Phase 0:** ✅ Complete (34 tests)
- **Track A (A1-A4):** ✅ Complete (per-asset weights, TP1/TP2, trailing, max hold)
- **Tech Debt:** ✅ Complete (stubs removed, duplicates cleaned)
- **Track B (B1-B5):** ✅ Complete (133 tests: bar_resampler+indicators+regime+strategy+handler)
- **Phase C (Config):** 🔄 In Progress (0/7 sub-phases)
- **Total tests passing:** 189

## 📈 Optuna Results (from new_alpha docs)

### Aurora Phase 3+ (Tick-Based)
| Symbol | PnL | Status |
|--------|-----|--------|
| SOLUSDT | +$318.94 | ⚠️ Partial config |
| ETHUSDT | +$130.50 → $180.84 (P3+) | ⚠️ Missing TP params |
| XRPUSDT | +$45.93 → $74.15 (P3+) | ❌ **MISSING** |
| BTCUSDT | -$1.37 | ❌ Skip |

### 1m Mean Reversion (Bar-Based)
| Symbol | PnL | Status |
|--------|-----|--------|
| DOGEUSDT | +$88.38 🏆 | ❌ **MR DISABLED** |
| BTCUSDT | +$45.27 | ⚠️ Config exists |
| ETHUSDT | +$37.38 | ⚠️ Config exists |
| XRPUSDT | +$31.41 | ⚠️ Config exists |

**Total Expected PnL:** +$532/month (Aurora + 1m MR)
