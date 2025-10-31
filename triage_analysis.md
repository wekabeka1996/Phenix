#                                                                                                            execution

## 1. Features Ready Check
**          :** `apps/reference/domains/decision_making/decision_making.py::_check_and_trigger_decision_for_symbol()`

            :                            `has_features = bool(state.get("features"))`.          features                 ,                deferred.
TTL/lag                     :                                                           features.                                                  `features_ready(symbol)`    TTL.

## 2. Trading Allowed Gates
**          :** `apps/reference/domains/risk_management/risk_management.py::_calculate_risk_parameters()`

      -          :
- **daily_loss/drawdown:** `current_daily_drawdown > max_drawdown`     `is_trading_allowed = False`
- **score:** `risk_score > max_risk_score`     `is_trading_allowed = False`
- **budgets/reservations:**                                     ,           `EXPOSURE_LIMIT_EXCEEDED = "NRR-011"`

**                             :** `apps/reference/domains/decision_making/decision_making.py::_make_decision_for_symbol()`
```python
if not risk_params.get("is_trading_allowed", False):
    reject_reason = "Trading not allowed by risk manager"
```

## 3. QoS (Cooldown/NRR-012)
**          :** `apps/reference/domains/decision_making/decision_making.py::_qos_allow()`

- **RATE_LIMIT_EXCEEDED (NRR-012):**                            `intent_data["count"] >= max_intents_per_minute_per_symbol`
- **DEFER vs REJECT:**                                         `qos_mode`:
  - `"defer"`:                    `EVT:INTENT_DEFERRED`    `next_allowed_ts`
  - `"enforce"`:                      intent

## 4. Exposure Reservations
**                             :** `vfoundation/apps/reference/domains/execution_position/exposure_guard.py::reserve()`
```python
self.state.reservations[key] = notional_usd
self.state.reservations_ts[key] = now
```

**TTL:** `pending_reservation_ttl_sec = 90` (default)

**                :** `cleanup_expired_reservations()`                reservations                   TTL

## 5. Execution FSM OPEN Entry Point
**          :** `apps/reference/main.py::on_trade_intent_proposed()`

                          :
1. `EVT:TRADE_INTENT_PROPOSED`        DecisionMaking
2. Bridge                                     portfolio/features
3.                       `CMD:OPEN`        execution_position FSM
4. Execution FSM                reservation            `exposure_guard.reserve()`

**                                      :**                                         ,                                                             defer.</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\triage_analysis.md
