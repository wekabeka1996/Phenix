# Copilot Instructions — Phenix Aurora Trading System

**Language:** Respond in Ukrainian. Generate code/configs in English.  
**Mode:** ADDITIVE-ONLY. Never delete working code without explicit approval.

---

## 1. Project Context

**System:** Aurora tick-based trading + 1m Mean Reversion strategies on Binance Futures.  
**Goal:** Migrate Optuna R&D results to production via per-instrument config layer.

**Source of Truth:**
- `NEW_ALPHA_OPTUNA_PROD_ROADMAP.md` — implementation phases & priorities
- `NEW_ALPHA_OPTUNA_TECHNICAL_APPENDIX.md` — code skeletons & patches
- `config/aurora_optimal_full_v1.yaml` — Phase 3+ Optuna params

**Key Domains:**
- `apps/reference/domains/decision_making/` — signal generation
- `apps/reference/domains/execution_position/` — FSM, brackets, trailing
- `apps/reference/domains/feature_engineering/` — indicators
- `apps/reference/config_models.py` — Pydantic schemas

---

## 2. Implementation Order (STRICT)

```
Phase 0 (BLOCKING) → Track A (Aurora) → Track B (1m MR) → Validation
```

### Phase 0: Per-Instrument Config Architecture
1. Add `AuroraInstrumentConfig` to `config_models.py`
2. Add `aurora_instruments` section to `TradingConfig`
3. Implement `_get_aurora_instrument_cfg(symbol)` helper
4. Add `self.symbol = None` to `ManageFlowFSM.__init__`

### Track A: Aurora Phase 3+
- A1: Per-asset weights, side_bias, regime_thresholds, regime_sizing
- A2: TP1/TP2 partial exit (70/30 split)
- A3: Trailing stop (CANCEL+NEW flow)
- A4: Max hold time watchdog
- A5: Phase 3+ risk weights

### Track B: 1m Mean Reversion
- B1: Bar resampler (tick → 1m OHLCV)
- B2: Bollinger Bands indicator
- B3: FLAT regime mapping
- B4: MeanReversion1mStrategy module

---

## 3. Mandatory Workflow

### Before ANY code change:
```
1. Read relevant section in TECHNICAL_APPENDIX.md
2. Update TODO.md with task
3. Run existing tests: pytest -q
```

### After EACH code change:
```
1. Run tests: pytest -q
2. Check errors: get_errors tool
3. Update JOURNAL.md with entry
4. Mark TODO.md task complete
```

### TODO.md Format:
```markdown
- [ ] [PHASE-ID] Task description — file.py
- [x] [A1-01] Add _get_aurora_instrument_cfg helper — decision_making.py #PR123
```

### JOURNAL.md Format:
```markdown
## YYYY-MM-DD

### [PHASE-ID] Short description
- **Files:** `path/to/file.py`
- **Changes:** What was added/modified
- **Tests:** pytest result or "pending"
- **Next:** What follows
```

---

## 4. Code Patterns (MUST USE)

### Per-Instrument Config Lookup (fallback chain):
```python
def _get_param(self, symbol: str, param: str, default: Any) -> Any:
    # 1. Try aurora_instruments.<SYMBOL>.<param>
    instr_cfg = self._get_aurora_instrument_cfg(symbol)
    if instr_cfg and getattr(instr_cfg, param, None) is not None:
        return getattr(instr_cfg, param)
    # 2. Fallback to global
    return self._safe_config_get("trading", "decision", param, default=default)
```

### FSM Bracket Calculation (with fallback):
```python
# Per-asset sl_pct → fallback to bps
if sl_pct is not None:
    sl_price = entry * (1 - Decimal(str(sl_pct)))
else:
    sl_price = self._calculate_sl_from_bps(entry)  # existing logic
```

### Trailing Stop Update:
```python
# In _check_rules():
self._update_trailing(msg)
if self._pending_sl_update:
    return self._apply_trailing_sl_update(msg)  # CANCEL + NEW
```

---

## 5. Testing Requirements

| Scope | Command | Coverage |
|-------|---------|----------|
| Unit | `pytest tests/domains/` | ≥80% |
| Integration | `pytest tests/integration/` | Key flows |
| Specific file | `pytest tests/domains/test_X.py -v` | Full |

**Critical Test Files:**
- `test_fsm_manage_brackets.py` — TP1/TP2, trailing
- `test_per_instrument_overrides.py` — config fallbacks
- `test_aurora_instrument_config.py` — Pydantic validation

---

## 6. Config Paths (Reference)

| Param | Global Path | Per-Asset Path |
|-------|-------------|----------------|
| signal_weights | `trading.decision.signal_weights` | `trading.aurora_instruments.<SYM>.weights` |
| side_bias | `trading.decision.side_bias_*` | `trading.aurora_instruments.<SYM>.side_bias.*` |
| sl | `trading.execution.manage.brackets.sl.fixed_bps` | `trading.aurora_instruments.<SYM>.exit.sl_pct` |
| regime_thresholds | `trading.decision.regime_threshold_multipliers` | `trading.aurora_instruments.<SYM>.regime_thresholds` |

---

## 7. Constraints

- **No breaking changes** to existing FSM states
- **Backward compatible** — missing per-asset config = use global
- **One PR per phase** — atomic, testable units
- **Quantize prices** to `tick_size` from `instruments` config
- **Rate limit** trailing stop modifications (max 1 per 5s)

---

## 8. Quick Reference

```bash
# Activate env (Linux)
source .venv/bin/activate

# Run all tests
pytest -q

# Run specific domain tests
pytest tests/domains/test_manage_flow_fsm.py -v

# Check for errors
python -m py_compile apps/reference/domains/decision_making/decision_making.py
```

---

> **If ROADMAP.md or TECHNICAL_APPENDIX.md is missing, respond `NOOP: missing <path>` and stop.**

