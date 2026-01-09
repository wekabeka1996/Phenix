# EXF_01: Exchange Filters Walkthrough

## 1. Overview
The `exchange_filters` domain serves as a **Startup Guard**. Its purpose is to validate that the local configuration (`instruments.yaml`) strictly matches the remote exchange constraints ("Exchange Info"). This prevents runtime "Filter Failures" when placing orders.

## 2. Contracts (`contracts.py`)
### `SSOTFilters`
Represents the local source of truth.
**Source:** `instruments.yaml` (section `instruments.<SYMBOL>`).
**Fields:**
*   `step_size`: (Decimal) The quantity precision (e.g., "0.001").
*   `min_qty`: (Decimal) The absolute minimum quantity (e.g., "0.001").
*   `min_notional`: (Decimal) The minimum order value in USDT (e.g., "5").
*   `tick_size`: (Decimal, Optional) Price precision.

### `ExchangeFilters`
Represents the remote reality.
**Source:** Binance API `GET /fapi/v1/exchangeInfo`.
**Mapping:**
*   `step_size` <- `filterType: LOT_SIZE` -> `stepSize`
*   `min_qty` <- `filterType: LOT_SIZE` -> `minQty`
*   `min_notional` <- `filterType: MIN_NOTIONAL` -> `notional` (fallback to `minNotional`)

### `FilterMismatch`
Describes a single validation failure. Calculates `severity` ("CRITICAL" vs "WARNING").

## 3. Validator Logic (`validator.py`)
### Extraction
The validator iterates through the raw API response `filters` list to find `LOT_SIZE`, `MIN_NOTIONAL`, and `PRICE_FILTER`.
**Edge Case:** If `MIN_NOTIONAL` is missing, it falls back to a default of "5" (checking multiple keys).

### Comparison Rules
1.  **Step Size:** Exact match required. `SSOT < Exchange` is CRITICAL (risk of reject). `SSOT > Exchange` is WARNING.
2.  **Min Qty:** Exact match required. `SSOT < Exchange` is CRITICAL.
3.  **Min Notional:**
    *   `SSOT < Exchange`: CRITICAL. (e.g., Local=5, Exchange=10 -> Order of 6 rejected).
    *   `SSOT > Exchange`: WARNING. (e.g., Local=10, Exchange=5 -> Order of 12 accepted).

## 4. Assumptions
*   All numeric values in JSON are strings and parseable to Decimal.
*   The symbol exists in the Exchange Info response.
*   The API returns `LOT_SIZE` filter (mandatory).

---

# EXF_02: Endpoint Truth

## 1. Endpoint Analysis
**Method:** `BinanceAdapter.get_exchange_info(symbol)`
**Implementation:** `apps/reference/adapters/binance_adapter.py`
**URL Path:** `/fapi/v1/exchangeInfo`

## 2. Verdict
*   **Protocol:** **Futures API** (`fapi`). This confirms we are validating against the correct market (USD-M Futures), NOT Spot (`/api/v3`).
*   **Environment:** The adapter respects the base URL configuration. If `system.mode` is testnet, the adapter uses the testnet URL, and validation occurs against Testnet limits.

## 3. Parameter Mapping
*   `symbol`: Passed directly as query param `?symbol=BTCUSDT`.
*   The response is a full dictionary containing `symbols: [...]` list.

---

# EXF_03: Decimal Rules

## 1. Type Safety
**Implementation:** All parsing uses `Decimal(str(value))`.
**Significance:** Avoids floating point errors (e.g., `0.0001000000000000001`). Comparisons are exact.

## 2. Critical Rules
| Field | Condition | Severity | Rationale |
|---|---|---|---|
| `step_size` | `SSOT != Exchange` | Mismatch | General mismatch |
| `step_size` | `SSOT < Exchange` | **CRITICAL** | We send more precision than allowed -> REJECT. |
| `min_qty` | `SSOT < Exchange` | **CRITICAL** | We send less than min -> REJECT. |
| `min_notional` | `SSOT < Exchange` | **CRITICAL** | We send order < min notional -> REJECT. |
| `min_notional` | `SSOT > Exchange` | WARNING | We are conservative. Safe. |

## 3. Coverage
Existing logic converts all inputs to `Decimal` before comparison.
**Verdict:** Safe and Correct.

---

# EXF_04: Integration Point

## 1. Where?
In `apps/reference/main.py`, inside the `main()` or `App.run()` sequence.
**Timing:**
1.  After `adapter` is initialized and confirmed working (time sync).
2.  Before `DecisionMaking` and other domains start (fail-fast).

## 2. Code Snippet
```python
# ... adapter init ...

# TASK-EXF-04: Startup Filter Validation
from apps.reference.domains.exchange_filters.validator import validate_instruments_on_startup, FilterMismatchError

try:
    await validate_instruments_on_startup(
        adapter=adapter,
        instruments_config=config.instruments_dict, # Need access to raw dict or Pydantic map
        mode=config.system.mode,
        warn_only=config.system.warn_only_filters # Suggested config flag
    )
except FilterMismatchError as e:
    LOG.critical(f"STARTUP VALIDATION FAILED: {e}")
    sys.exit(1)
```

## 3. Configuration
New flags needed in `system` section of `config.yaml`:
*   `validate_filters_on_startup` (bool, default=True)
*   `warn_only_filters` (bool, default=False)

---

# EXF_05: Policy & Observability

## 1. Failure Policy
**Fail-Closed.**
If a critical mismatch is found, the system **MUST** refuse to start.
Running with mismatched filters guarantees runtime errors on execution.

## 2. Observability
*   **Log:** `CRITICAL` log with full list of mismatches.
*   **Stdout:** Print nice table of mismatches before exit.
*   **Metric:** `c_startup_filter_mismatch_total` (Counter). Incremented before crash.

## 3. Exception Handling
The `FilterMismatchError` contains a list of `filter_mismatch` objects. These should be formatted into a readable error message.

---

# EXF_06: E2E Test Plan

## Scenario: Block Startup on Mismatch
1.  **Setup:**
    *   Mock `BinanceAdapter.get_exchange_info`.
    *   Return `stepSize="0.01"` for BTCUSDT.
    *   Set local config `instruments.yaml` to `step_size="0.001"`.
2.  **Action:**
    *   Run `main.py` (or the integration test harness).
3.  **Expectation:**
    *   System exits with code 1.
    *   Log contains "CRITICAL: step_size mismatch".

## Scenario: Allow Startup on Match
1.  **Setup:**
    *   Mock `stepSize="0.001"`.
    *   Local config `stepSize="0.001"`.
2.  **Action:** Run startup.
3.  **Expectation:**
    *   Proceeds to "Starting domains..."
