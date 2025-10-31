# Аналіз кодових точок логіки прийняття рішення та виходу в execution

## 1. Features Ready Check
**Мі� це:** `apps/reference/domains/decision_making/decision_making.py::_check_and_trigger_decision_for_symbol()`

Логіка: Перевіряєть� я `has_features = bool(state.get("features"))`. Якщо features від� утні, рішення deferred.
TTL/lag порівняння: Немає явної перевірки � віжо� ті features. Потрібно додати перевірку `features_ready(symbol)` з TTL.

## 2. Trading Allowed Gates
**Мі� це:** `apps/reference/domains/risk_management/risk_management.py::_calculate_risk_parameters()`

Під-гейти:
- **daily_loss/drawdown:** `current_daily_drawdown > max_drawdown` → `is_trading_allowed = False`
- **score:** `risk_score > max_risk_score` → `is_trading_allowed = False`
- **budgets/reservations:** Не реалізовані явно, але є `EXPOSURE_LIMIT_EXCEEDED = "NRR-011"`

**Мі� це перевірки:** `apps/reference/domains/decision_making/decision_making.py::_make_decision_for_symbol()`
```python
if not risk_params.get("is_trading_allowed", False):
    reject_reason = "Trading not allowed by risk manager"
```

## 3. QoS (Cooldown/NRR-012)
**Мі� це:** `apps/reference/domains/decision_making/decision_making.py::_qos_allow()`

- **RATE_LIMIT_EXCEEDED (NRR-012):** Перевіряєть� я `intent_data["count"] >= max_intents_per_minute_per_symbol`
- **DEFER vs REJECT:** Конфігуруєть� я через `qos_mode`:
  - `"defer"`: Емітить� я `EVT:INTENT_DEFERRED` з `next_allowed_ts`
  - `"enforce"`: Блокуєть� я intent

## 4. Exposure Reservations
**Мі� це � творення:** `vfoundation/apps/reference/domains/execution_position/exposure_guard.py::reserve()`
```python
self.state.reservations[key] = notional_usd
self.state.reservations_ts[key] = now
```

**TTL:** `pending_reservation_ttl_sec = 90` (default)

**Очищення:** `cleanup_expired_reservations()` видаляє reservations � тарші за TTL

## 5. Execution FSM OPEN Entry Point
**Мі� це:** `apps/reference/main.py::on_trade_intent_proposed()`

По� лідовні� ть:
1. `EVT:TRADE_INTENT_PROPOSED` від DecisionMaking
2. Bridge перевіряє � віжі� ть portfolio/features
3. Конвертує в `CMD:OPEN` для execution_position FSM
4. Execution FSM � творює reservation через `exposure_guard.reserve()`

**Прапорці для виклику:** Немає явних прапорців, завжди конвертуєть� я якщо немає defer.</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\triage_analysis.md
