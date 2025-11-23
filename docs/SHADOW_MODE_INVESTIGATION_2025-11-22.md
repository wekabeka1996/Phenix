# Shadow Mode Investigation Report
**RID**: `SHADOW-MODE-ROOT-CAUSE-INVESTIGATION-2025-11-22`
**Date**: 2025-11-22
**Status**: 🔴 **CRITICAL** - All orders going to shadow mode instead of Binance testnet

---

## Executive Summary

**Problem**: System boots successfully, but all orders are executed in **shadow mode** (simulation) instead of hitting Binance testnet API.

**Root Cause**: `BinanceExecutionAdapter` is **never instantiated**. The `ExecPosRuntimeV2` receives `adapter=None`, causing `ExecutionService` to skip all API calls.

**Impact**:
- ❌ No real orders placed on Binance testnet
- ❌ No WebSocket connection to USER_DATA_STREAM
- ❌ No fills, no positions tracked from exchange
- ✅ Risk/Decision/Market Data work correctly (shadow_live profile active)

---

## Investigation Trail

### 1. Configuration Analysis

**modes.yaml** (active profile):
```yaml
profiles:
  shadow_live:
    trading_mode: shadow_live
    domains:
      market_data: live          # ✅ Works (live WebSocket data)
      feature_engineering: live  # ✅ Works
      decision_making: live      # ✅ Works
      risk_management: testnet   # ✅ Works
      execution_position: testnet  # ⚠️ SHOULD use testnet API, but doesn't
      audit_trail: live          # ✅ Works

default_profile: shadow_live
```

**Expected behavior**: `execution_position: testnet` → use Binance testnet API with credentials.
**Actual behavior**: Orders go to shadow mode (no API calls).

---

### 2. Code Path Analysis

#### **Entry Point**: `apps/reference/main.py:826`

```python
def initialize_domains(config) -> FSMCore:
    # ...
    execution_position = build_execution_runtime(
        config=config,
        fsm=fsm
        # ⚠️ NO adapter parameter passed!
    )
```

**Issue #1**: `adapter` is **not passed** to `build_execution_runtime`.

---

#### **Factory**: `apps/reference/domains/execution_position/runtime_factory.py:47-50`

```python
def build_execution_runtime(
    config: Any,
    fsm: Any,
    adapter: Any = None,  # ⚠️ Defaults to None
    price_service: Any = None
) -> Any:
    # ...
    return V2RuntimeFacade(
        config=config_dict,
        adapter=adapter,  # ⚠️ None passed through
        price_service=price_service
    )
```

**Issue #2**: `adapter=None` is accepted and propagated to runtime.

---

#### **Facade**: `runtime_factory.py:58-61`

```python
class V2RuntimeFacade:
    def __init__(self, config: Dict[str, Any], adapter: Any = None, price_service: Any = None):
        self.runtime = ExecPosRuntimeV2(
            config=config,
            adapter=adapter,  # ⚠️ None passed to runtime
            price_service=price_service
        )
```

**Issue #3**: `adapter=None` propagated to `ExecPosRuntimeV2`.

---

#### **Runtime**: `shadow_execpos/runtime.py:63-70`

```python
class ExecPosRuntimeV2:
    def __init__(
        self,
        config: Dict[str, Any],
        adapter: Any,  # ⚠️ Receives None
        price_service: Any,
        # ...
    ):
        # ...
        self.execution_service = ExecutionService(adapter)  # ⚠️ None passed
```

**Issue #4**: `ExecutionService` receives `adapter=None`.

---

#### **Execution Service**: `shadow_execpos/execution_service.py:36-56`

```python
class ExecutionService:
    def __init__(self, adapter: Any):
        self.adapter = adapter  # ⚠️ None stored

    async def _call_adapter(self, fn_or_str: Union[Any, str], *args, **kwargs) -> Any:
        if not self.adapter:
            return None  # 🛑 ALL API CALLS RETURN None!
```

**Issue #5**: **Every API call returns `None` immediately** because `self.adapter` is `None`.

---

### 3. Missing Adapter Creation

The `BinanceExecutionAdapter` is **never instantiated** anywhere in the codebase.

**Legacy behavior** (pre-V2 refactor):
```python
# OLD CODE (removed):
adapter = BinanceExecutionAdapter(fsm=fsm, config=config)
execution_position = ExecPosFSM(fsm, config, adapter=adapter)
```

**Current V2 behavior**:
```python
# NEW CODE (missing adapter creation):
execution_position = build_execution_runtime(config, fsm)
# ⚠️ No adapter instantiation!
```

---

### 4. Environment Variables Check

**Required for testnet API**:
```bash
BINANCE_TESTNET_API_KEY=<your_key>
BINANCE_TESTNET_API_SECRET=<your_secret>
USE_TESTNET=1
```

**Actual values** (checked via PowerShell):
```powershell
$env:BINANCE_TESTNET_API_KEY     # ❌ Empty
$env:BINANCE_TESTNET_API_SECRET  # ❌ Empty
$env:USE_TESTNET                 # ❌ Empty
```

**Fallback behavior** in `binance_execution_adapter.py:168-172`:
```python
if not shadow_mode and (not self.api_key or not self.api_secret):
    logger.warning("[BinanceAdapter] API credentials not found, falling back to shadow mode")
    self.shadow_mode = True  # ⚠️ FORCES shadow mode even if adapter exists
```

**Issue #6**: Even if adapter were created, missing credentials would force `shadow_mode=True`.

---

## Root Cause Summary

**Primary Cause**: `BinanceExecutionAdapter` is **never instantiated** in V2 runtime.

**Contributing Factors**:
1. `build_execution_runtime()` does not create adapter internally
2. `main.py` does not create adapter before calling factory
3. No environment variables set for API credentials
4. No configuration fallback for testnet credentials

**Result**: `ExecutionService` operates with `adapter=None` → all API calls return `None` → shadow mode simulation.

---

## Solution Options

### Option A: Create Adapter in Factory (Recommended)

**Modify**: `runtime_factory.py::build_execution_runtime()`

```python
def build_execution_runtime(
    config: Any,
    fsm: Any,
    adapter: Any = None,
    price_service: Any = None
) -> Any:
    """Factory to create the execution runtime."""
    config_dict = config.to_dict() if hasattr(config, "to_dict") else config

    # If adapter not provided, create it
    if adapter is None:
        from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter
        adapter = BinanceExecutionAdapter(
            fsm=fsm,
            config=config,
            shadow_mode=False  # Let adapter auto-detect based on credentials
        )
        adapter.start()  # Start WebSocket if credentials exist

    return V2RuntimeFacade(
        config=config_dict,
        adapter=adapter,
        price_service=price_service
    )
```

**Pros**:
- ✅ Minimal code changes
- ✅ Factory pattern encapsulates adapter creation
- ✅ Backwards compatible (still accepts externally-created adapter)

**Cons**:
- ⚠️ Factory becomes less pure (has side effects)

---

### Option B: Create Adapter in main.py

**Modify**: `main.py::initialize_domains()`

```python
def initialize_domains(config) -> FSMCore:
    global fsm, execution_position

    # Create FSM
    fsm = FSMCore()

    # Create execution adapter
    from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter
    exec_adapter = BinanceExecutionAdapter(
        fsm=fsm,
        config=config,
        shadow_mode=False  # Auto-detect from credentials
    )
    exec_adapter.start()

    # Build runtime with adapter
    execution_position = build_execution_runtime(
        config=config,
        fsm=fsm,
        adapter=exec_adapter  # ✅ Pass created adapter
    )
```

**Pros**:
- ✅ Explicit dependency injection
- ✅ Factory remains pure
- ✅ Easy to test with mock adapters

**Cons**:
- ⚠️ More verbose
- ⚠️ main.py knows about adapter implementation

---

### Option C: Create Adapter Inside ExecPosRuntimeV2

**Modify**: `shadow_execpos/runtime.py::__init__()`

```python
class ExecPosRuntimeV2:
    def __init__(
        self,
        config: Dict[str, Any],
        adapter: Any = None,
        price_service: Any = None,
        # ...
    ):
        # If adapter not provided, create default
        if adapter is None:
            from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter
            adapter = BinanceExecutionAdapter(
                fsm=None,  # No fsm needed for V2
                config=config,
                shadow_mode=False
            )
            adapter.start()

        self.execution_service = ExecutionService(adapter)
```

**Pros**:
- ✅ Self-contained runtime
- ✅ No changes needed in main.py or factory

**Cons**:
- ⚠️ Tight coupling (runtime knows about Binance)
- ⚠️ Harder to test with mock adapters

---

## Recommended Fix: **Option A** (Factory Creation)

**Rationale**:
- Factory is the natural place for dependency creation
- Maintains backwards compatibility
- Minimal code changes
- Testable (can still inject mock adapter)

**Implementation Steps**:

1. **Set environment variables** (immediate fix for credentials):
   ```powershell
   $env:BINANCE_TESTNET_API_KEY = "your_testnet_api_key_here"
   $env:BINANCE_TESTNET_API_SECRET = "your_testnet_secret_here"
   $env:USE_TESTNET = "1"
   ```

2. **Modify `runtime_factory.py`** to create adapter if not provided (code above).

3. **Test**:
   ```bash
   python -m apps.reference.main
   # Verify logs show:
   # "[BinanceAdapter] Using TESTNET credentials"
   # "[BinanceAdapter] Initialized with shadow_mode=False, testnet=True"
   # "[BinanceAdapter] Starting WebSocket connection to USER_DATA_STREAM"
   ```

4. **Validate order execution**:
   - Check `order_log_v1.jsonl` for `ORDER_PLACED` events (not just `ORDER_INTENT`)
   - Check Binance testnet UI for open orders
   - Verify WebSocket receives `executionReport` events

---

## Verification Checklist

After fix, confirm:

- [ ] `BinanceExecutionAdapter` created with `shadow_mode=False`
- [ ] Environment variables loaded correctly
- [ ] WebSocket connects to `wss://stream.binancefuture.com/ws/`
- [ ] Orders appear on Binance testnet exchange
- [ ] `order_log_v1.jsonl` shows `ORDER_PLACED` events
- [ ] Fills trigger position updates via WebSocket
- [ ] No "shadow_mode=True" warnings in logs

---

## Related Files

**Core Files**:
- `apps/reference/main.py` (lines 826-828) - Factory invocation
- `apps/reference/domains/execution_position/runtime_factory.py` (lines 17-50) - Factory logic
- `apps/reference/domains/execution_position/shadow_execpos/runtime.py` (lines 51-70) - Runtime init
- `apps/reference/domains/execution_position/shadow_execpos/execution_service.py` (lines 36-56) - Adapter check
- `apps/reference/domains/execution_position/binance_execution_adapter.py` (lines 83-213) - Adapter init

**Config Files**:
- `config/modes.yaml` (default_profile: shadow_live)
- `system_config.yaml` (merged config)

**Logs**:
- `logs/order_log_v1.jsonl` - Order events (currently only intents, no placements)

---

## Next Steps

1. **Immediate**: Set environment variables with Binance testnet credentials
2. **Code Fix**: Implement Option A (factory adapter creation)
3. **Testing**: Verify order placement on testnet exchange
4. **Documentation**: Update deployment guide with required env vars
5. **Monitoring**: Add alert if `shadow_mode=True` detected in production

---

**Status**: 🔴 **AWAITING FIX**
**Priority**: **P0** - Blocks real trading functionality
**Estimated Fix Time**: 30 minutes (Option A implementation)
