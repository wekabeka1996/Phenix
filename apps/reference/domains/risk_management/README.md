# risk_management — Domain README

> **Authoritative domain documentation.** For auto-generated docs see `docs/` (may be stale).

## 1. Purpose

`risk_management` is a **risk scorer and daily drawdown gate**. It receives market features, computes a composite risk score, maintains a daily drawdown gate with persistent state, and emits `EVT:RISK_ASSESSMENT_COMPLETED` with the `is_trading_allowed` verdict for downstream decision_making.

**It does NOT own execution exposure, leverage, or position sizing.**

## 2. Responsibility Boundary

Owns:
- Composite risk score computation (weighted formula)
- Daily drawdown/loss gate (DailyRiskState)
- `is_trading_allowed` verdict
- Persistent daily state (disk-backed, corruption-resilient)

Does NOT own:
- Execution exposure tracking (→ execution_position/exposure_guard)
- Leverage limits (→ execution_position/leverage_service)
- Position sizing (→ decision_making/strategy_gateway)
- Concentration limits (not implemented)
- Order reject codes (→ NormalizedRejectReasons in decision_making)

## 3. Architecture

```
EVT:FEATURES_CALCULATED ──→ RiskManagement._calculate_risk_parameters()
                              ├── risk_score = weighted(delta_price_pct, OBI, TFI, absorption)
                              ├── DailyRiskState.can_open() ──→ daily drawdown gate
                              └── EVT:RISK_ASSESSMENT_COMPLETED { is_trading_allowed, risk_score, ... }

EVT:PORTFOLIO_STATE_UPDATED ──→ DailyRiskState.update_equity()
                                  └── tracks daily reference_equity, current_equity, drawdown
```

### Two-layer gating
1. **Daily drawdown gate** (`DailyRiskState`): fail-closed portfolio-level gate. Blocks all trading when daily drawdown exceeds `max_realized_loss_pct` (default 8%). Resets at configurable UTC hour. State persists to disk; corruption triggers recovery mode (blocks until next calendar day).
2. **Per-instrument risk score** (`RiskManagement`): weighted composite score from multi-signal features. If `risk_score > max_risk_score`, trading is blocked for that instrument.

## 4. Events

### Consumed (2)

| Event | Source | Handler |
|-------|--------|---------|
| `EVT:FEATURES_CALCULATED` | feature_engineering | `on_features_calculated` — calculates risk parameters |
| `EVT:PORTFOLIO_STATE_UPDATED` | position_tracking | `on_portfolio_state_updated` — updates daily equity tracking |

### Emitted (2)

| Event | Target | Purpose |
|-------|--------|---------|
| `EVT:RISK_ASSESSMENT_COMPLETED` | decision_making | Risk parameters + `is_trading_allowed` verdict |
| `EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE` | monitoring | Debug-only: emitted when daily gate is disabled via config |

## 5. File Map (3 source files, 990 LOC)

| File | LOC | Role |
|------|-----|------|
| `risk_management.py` | 639 | Core: risk score computation, event handling, WhyCode logging |
| `daily_gate.py` | 346 | Daily drawdown gate: persistent state, fail-closed, corruption recovery |
| `__init__.py` | 5 | Package init, re-exports `RiskManagement` |

### Schemas (1)
| File | Event |
|------|-------|
| `schemas/risk_assessment_v1.json` | `EVT:RISK_ASSESSMENT_COMPLETED` |

## 6. Fail-Closed Rules

- **Missing config → ConfigContractError** (no silent fallback)
- **Dict config → TypeError** (enforces AuroraConfig object)
- **None/invalid numeric → ValueError** (`_to_dec()` strict conversion)
- **No equity data → blocks trading** (DailyRiskState)
- **Corrupted state file → blocks until next calendar day** (recovery mode)
- **Missing risk weights → ConfigContractError**
- **Debug override → observable** (emits EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE)

## 7. WhyCode Usage

| WhyCode | Context |
|---------|---------|
| `RISK_DRAWDOWN_LIMIT` | Daily drawdown gate blocks trading |
| `RISK_NOT_ALLOWED` | Daily gate blocks for non-drawdown reasons |
| `RISK_SCORE_HIGH` | Per-instrument risk score exceeds threshold |

All imported from canonical `vfoundation/core/why_codes.py`.

## 8. Config Dependencies

| Config Path | Purpose |
|-------------|---------|
| `domains.risk_management.trading_allowed_thresholds.max_risk_score` | Per-instrument risk score threshold |
| `domains.risk_management.data_sources.portfolio_state` | Portfolio state config |
| `domains.risk_management.risk_score_weights.*` | Risk score weight config (OBI, TFI, delta_price, absorption) |
| `trading.risk.daily.max_realized_loss_pct` | Daily drawdown limit (default 8%) |
| `trading.risk.daily.reset_hour_utc` | Daily gate reset hour |
| `domains.debug.disable_daily_loss_limit` | Debug-only: bypass daily gate |

## 9. Cross-Domain Coupling

| Direction | What | Why |
|-----------|------|-----|
| RM → vfoundation | WhyCode, FSMCore, Message | Infrastructure |
| RM → config | AuroraConfig, DomainConfigResolver | Config resolution |
| DM → RM | `domains.risk_management.trading_allowed_thresholds.max_risk_score` config read | Risk threshold for strategy gateway |
| PT → RM | Event-based only (EVT:PORTFOLIO_STATE_UPDATED) | Clean event-driven |

No direct imports FROM risk_management in any other domain.

## 10. Forbidden Patterns

- Do NOT bypass `DailyRiskState` for trading allow/deny decisions
- Do NOT add execution exposure logic — that belongs to `execution_position`
- Do NOT add position sizing logic — that belongs to `decision_making`
- Do NOT use `NormalizedRejectReasons` — RM uses `WhyCode` for structured rejections
- Do NOT add silent permissive fallbacks — all gates must be fail-closed
- Do NOT use `disable_daily_loss_limit` in production — debug/shadow mode only

## 11. Testing

```bash
pytest tests/domains/risk_management/ -v   # 6 test files, 54 functions
pytest tests/risk_management/ -v           # 1 test file, 2 functions (persistence)
```

**Total test surface:** ~15 files, ~73 test functions.

## 12. Known Structural Debt

- `domain_dict.json` was garbled (whitespace-only descriptions) — rewritten in 2026-03-14 audit
- Auto-generated docs in `docs/` may be stale — authoritative source is this README
- `test_risk_strategy_fsm.py` references non-existent `risk_strategy` domain (unconditionally skipped)

---
*Version: 2.0.0 — Created 2026-03-14 (RM-DOMAIN-AUDIT)*
