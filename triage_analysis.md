#  ê Ω   ª ñ ∑  ∫ æ ¥ æ ≤ ∏ Ö  Ç æ á æ ∫  ª æ ≥ ñ ∫ ∏      ∏ π Ω è Ç Ç è    ñ à µ Ω Ω è  Ç    ≤ ∏ Ö æ ¥ É  ≤ execution

## 1. Features Ready Check
** ú ñ   Ü µ:** `apps/reference/domains/decision_making/decision_making.py::_check_and_trigger_decision_for_symbol()`

 õ æ ≥ ñ ∫  :  ü µ   µ ≤ ñ   è î Ç å   è `has_features = bool(state.get("features"))`.  Ø ∫ â æ features  ≤ ñ ¥   É Ç Ω ñ,    ñ à µ Ω Ω è deferred.
TTL/lag    æ   ñ ≤ Ω è Ω Ω è:  ù µ º   î  è ≤ Ω æ ó    µ   µ ≤ ñ   ∫ ∏    ≤ ñ ∂ æ   Ç ñ features.  ü æ Ç   ñ ± Ω æ  ¥ æ ¥   Ç ∏    µ   µ ≤ ñ   ∫ É `features_ready(symbol)`  ∑ TTL.

## 2. Trading Allowed Gates
** ú ñ   Ü µ:** `apps/reference/domains/risk_management/risk_management.py::_calculate_risk_parameters()`

 ü ñ ¥- ≥ µ π Ç ∏:
- **daily_loss/drawdown:** `current_daily_drawdown > max_drawdown` ‚Üí `is_trading_allowed = False`
- **score:** `risk_score > max_risk_score` ‚Üí `is_trading_allowed = False`
- **budgets/reservations:**  ù µ    µ   ª ñ ∑ æ ≤   Ω ñ  è ≤ Ω æ,    ª µ  î `EXPOSURE_LIMIT_EXCEEDED = "NRR-011"`

** ú ñ   Ü µ    µ   µ ≤ ñ   ∫ ∏:** `apps/reference/domains/decision_making/decision_making.py::_make_decision_for_symbol()`
```python
if not risk_params.get("is_trading_allowed", False):
    reject_reason = "Trading not allowed by risk manager"
```

## 3. QoS (Cooldown/NRR-012)
** ú ñ   Ü µ:** `apps/reference/domains/decision_making/decision_making.py::_qos_allow()`

- **RATE_LIMIT_EXCEEDED (NRR-012):**  ü µ   µ ≤ ñ   è î Ç å   è `intent_data["count"] >= max_intents_per_minute_per_symbol`
- **DEFER vs REJECT:**  ö æ Ω Ñ ñ ≥ É   É î Ç å   è  á µ   µ ∑ `qos_mode`:
  - `"defer"`:  ï º ñ Ç ∏ Ç å   è `EVT:INTENT_DEFERRED`  ∑ `next_allowed_ts`
  - `"enforce"`:  ë ª æ ∫ É î Ç å   è intent

## 4. Exposure Reservations
** ú ñ   Ü µ    Ç ≤ æ   µ Ω Ω è:** `vfoundation/apps/reference/domains/execution_position/exposure_guard.py::reserve()`
```python
self.state.reservations[key] = notional_usd
self.state.reservations_ts[key] = now
```

**TTL:** `pending_reservation_ttl_sec = 90` (default)

** û á ∏ â µ Ω Ω è:** `cleanup_expired_reservations()`  ≤ ∏ ¥   ª è î reservations    Ç     à ñ  ∑   TTL

## 5. Execution FSM OPEN Entry Point
** ú ñ   Ü µ:** `apps/reference/main.py::on_trade_intent_proposed()`

 ü æ   ª ñ ¥ æ ≤ Ω ñ   Ç å:
1. `EVT:TRADE_INTENT_PROPOSED`  ≤ ñ ¥ DecisionMaking
2. Bridge    µ   µ ≤ ñ   è î    ≤ ñ ∂ ñ   Ç å portfolio/features
3.  ö æ Ω ≤ µ   Ç É î  ≤ `CMD:OPEN`  ¥ ª è execution_position FSM
4. Execution FSM    Ç ≤ æ   é î reservation  á µ   µ ∑ `exposure_guard.reserve()`

** ü       æ   Ü ñ  ¥ ª è  ≤ ∏ ∫ ª ∏ ∫ É:**  ù µ º   î  è ≤ Ω ∏ Ö          æ   Ü ñ ≤,  ∑   ≤ ∂ ¥ ∏  ∫ æ Ω ≤ µ   Ç É î Ç å   è  è ∫ â æ  Ω µ º   î defer.</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\triage_analysis.md
