# Risk Map: Execution Position Domain
**Baseline Analysis (Qualitative)**

## 🚨 Top 10 High-Risk Areas (Hot Path)

| File | Component | Risk Factor | Why it matters |
| :--- | :--- | :--- | :--- |
| `fsm_open.py` | `handle` (Guards) | **Config Fallback** | Uses hardcoded defaults (`MIN_NOTIONAL=5.0`) if config is missing. Can allow invalid orders on different symbols. |
| `fsm_open.py` | `handle` (Rounding) | **Silent Mutation** | Rounds qty/price down to step size. Might execute slightly less than intended without clear feedback. |
| `fsm_close.py` | `_check_close_conditions` | **Disabled Logic** | Returns `None` (autonomous close disabled). If upstream dies, position is stuck open (Soldier Pattern risk). |
| `fsm.py` | `_on_order_ack` | **State Consistency** | Updates internal state based on ACK. If ACK is lost or reordered (UDP), state might desync. |
| `fsm.py` | `_on_order_fill` | **Idempotency** | Checks `_processed_events` set. If this set isn't pruned, it causes a Memory Leak over time. |
| `fsm.py` | `watchdog` | **Timeout Handling** | `OrderTimeoutWatchdog` is critical for avoiding "zombie orders". If loop blocks, watchdog triggers late. |
| `exposure_guard.py` | `check` | **Race Conditions** | Checks limits against local state. If `portfolio_update` lags `order_ack`, we might double-spend exposure. |
| `idempotent_cancel.py` | `cancel_order_idempotent` | **Retry Storm** | If `max_retries` is high and API is slow, can cause request floods (API ban risk). |
| `fsm_open.py` | `idempotency_store` | **Memory/GC** | manual `_cleanup_idempotency_store` call on every handle. Efficient, but fail-open if handle isn't called. |
| `fsm_close.py` | `hydrate` | **Trust Boundary** | Trusts injected `position_data` blindly. Malformed hydrations can corrupt FSM state. |

## 📉 Coverage Gaps (Inferred)
Since `pytest-cov` was unavailable, these are estimated gaps based on file reading:
1.  **Error Paths**: `fsm.py` adapter failures (`BinanceAPIError`) and timeout handling are likely under-tested.
2.  **Corner Cases**: `fsm_open.py` rounding logic for weird step sizes (e.g. 1e-8) or very large numbers.
3.  **Race Conditions**: Concurrent `CMD:OPEN` + `EVT:FILL` + `EVT:PORTFOLIO_UPDATE` flows.

## 🛡️ Recommended Hardening
1.  **Strict Config Validation**: Fail fast if `instrument_specs` are missing in `fsm_open.py` instead of using defaults.
2.  **Memory Cap**: Enforce `maxlen` on `_processed_events` in `fsm.py`.
3.  **Failsafe Close**: Re-enable a "hard timeout" backup in `fsm_close.py` (e.g. 24h fallback even if upstream is silent).
