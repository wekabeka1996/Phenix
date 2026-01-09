# Startup Guards

Startup Guards are critical safety mechanisms that run during the application initialization phase, before any trading domains are started. Their purpose is to ensure the **Static Configuration** (SSOT) matches the **Runtime Reality** (Exchange State).

If a guard fails in **LIVE/PRODUCTION** mode, the system follows a **Fail-Closed** policy: it will log a CRITICAL error and exit immediately (`sys.exit(1)`).

## Exchange Filters Guard (`exchange_filters`)

This guard validates that the instrument configurations in `config/aurora/instruments.yaml` (SSOT) are compliant with the exchange's trading rules (fetched via `/fapi/v1/exchangeInfo`).

### Why is this needed?
If our local configuration assumes a `step_size` of `0.001` (3 decimals), but the exchange requires `0.01` (2 decimals), any order submission will be rejected by the exchange. Detecting this at startup prevents runtime order failures and "silent" rejections.

### Validation Rules

| Filter | Key in instruments.yaml | Key in Exchange Info | Comparison Rule (Fail-Closed) |
| :--- | :--- | :--- | :--- |
| **Lot Size** | `step_size` | `LOT_SIZE.stepSize` | SSOT must match Exchange exactly. |
| **Min Qty** | `min_qty` | `LOT_SIZE.minQty` | SSOT >= Exchange (We cannot submit less than min). |
| **Notional** | `min_notional` | `MIN_NOTIONAL.notional` | SSOT >= Exchange. |
| **Tick Size** | `tick_size` (optional) | `PRICE_FILTER.tickSize` | SSOT == Exchange. |

### Configuration (`system.yaml`)

```yaml
system:
  # Enable the guard (default: true)
  validate_instruments_on_startup: true
  
  # Dev/Shadow only: Log warnings instead of crashing
  warn_only_filters: false 
```

### Policy
*   **LIVE/PRODUCTION:** Fail-Closed. Any CRITICAL mismatch -> Crash.
*   **TESTNET:** Fail-Closed.
*   **DEV/SHADOW:** Can use `warn_only_filters: true` to proceed with warnings.

### Implementation Details
*   **Batch Validation:** The guard fetches all symbols in a single request to avoid rate limits.
*   **Code Location:** `apps/reference/domains/exchange_filters/validator.py`
*   **Integration:** `apps/reference/main.py` (before domain initialization).
