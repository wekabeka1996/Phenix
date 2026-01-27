# ExecPosFSM Analysis

## Overview
The `ExecPosFSM` (Execution Position Finite State Machine) is a sophisticated orchestration layer that manages the execution lifecycle of cryptocurrency trading positions. It acts as a wrapper that routes commands to specialized flow FSMs and integrates with the Binance exchange adapter.

## Core Architecture

### 1. **FSM Orchestration Pattern**
The system uses a **three-FSM architecture per symbol**:
- **OpenFlowFSM**: Handles position entry logic
- **ManageFlowFSM**: Manages active positions and brackets (TP/SL)
- **CloseFlowFSM**: Handles position exit logic

This separation of concerns allows each flow to maintain its own state while the parent ExecPosFSM coordinates their interactions.

### 2. **Key Components**

#### Trading Execution
- **BinanceAdapter**: Direct integration with Binance Futures API
- **Order Types**: Supports MARKET and LIMIT entries with GTX (post-only) capability
- **Bracket Orders**: Automated TP/SL placement with retry logic for API rejections

#### Risk Management
- **ExposureGuard**: Pre-trade exposure validation with fail-closed semantics
- **OrderGuardian**: Continuous monitoring and cleanup of orphaned orders
- **OrderTimeoutWatchdog**: Tracks order acknowledgment and fill timeouts

#### State Management
- **WAL (Write-Ahead Log)**: Persists all decisions and state changes
- **CorrelationStore**: Tracks order relationships (entry → brackets)
- **OrderIndex**: Correlates WebSocket updates with placed orders

## Key Features & Patterns

### 3. **Fail-Closed Design Philosophy**
The code enforces **strict validation** throughout:

```python
# Example: No silent defaults for order_type
if not order_type:
    # REJECT - don't assume MARKET
    return error_message
```

**Critical fail-closed checks:**
- Instrument configuration must exist (tick_size, step_size, min_qty)
- Order fields must be explicit (no default order_type/tif)
- LIMIT orders require price, tif, and valid_for_ms
- Quantity normalization rejects orders that round to zero

### 4. **Exposure Management (EXP-FIX)**
Multi-layered exposure control:

```python
# Pre-flight check before placing orders
exposure_check = self.exposure_guard.can_open(
    symbol, notional_signed, portfolio_state
)

if not exposure_check["allowed"]:
    return ERR:OPEN with reason
```

**Features:**
- Real-time notional tracking (pending + postfill holds)
- Shadow notional verification against exchange
- Regime-based dynamic risk limits
- Post-close cooldown periods

### 5. **Order Lifecycle Management**

#### Entry Flow (CMD:OPEN)
```
DecisionMaking → TRADE_INTENT_PROPOSED
    ↓
ExecPosFSM validation:
  - Exposure check (fail-closed)
  - Quantity normalization
  - Cooldown validation
    ↓
OpenFlowFSM → DEC:OPEN
    ↓
Adapter execution:
  - MARKET: immediate + TP/SL
  - LIMIT: deferred TP/SL (on fill)
    ↓
OrderGuardian registration
```

#### Bracket Placement
Two strategies based on entry type:
- **MARKET entries**: Place TP/SL immediately after fill
- **LIMIT entries**: Defer until fill event (LIMIT-ENTRY-DEFERRED-BRACKETS)

```python
if order_type == "LIMIT":
    # Store for later placement
    self._pending_brackets[entry_order_id] = {
        "symbol": symbol,
        "sl": sl,
        "tp": tp,
        # ... metadata
    }
```

### 6. **Error Handling & Recovery**

#### Idempotent Cancellation
```python
# Treats -2011 (unknown order) as success
if self._is_unknown_order_error(e):
    LOG.info("Order already absent (-2011)")
    return success
```

#### TP/SL Retry Logic (PHASE A3)
When TP placement fails with -2021 (price too close):
```python
# Widen TP by 20bps and retry
tp_adj = tp * 1.002
# Exponential backoff: 200ms → 400ms
await clock.sleep_sec(0.2)
# Fallback to LIMIT reduceOnly if needed
```

### 7. **Quiet Hours & Trading Gates**

#### Quiet Hours
Configurable time windows where trading is blocked:
```python
def _in_quiet(quiet: list[str]) -> bool:
    # Format: ["22:00-06:00"] (wraps midnight)
    # Blocks trading during configured UTC windows
```

#### SYMBOL_TIDY Gate
Requires recent OrderGuardian cleanup before allowing entries:
```python
# Only allow entry if:
# 1. Guardian ran cleanup recently (< 6s ago), OR
# 2. Cooldown period expired since last block
```

### 8. **Observability & Logging**

#### Multi-Layer Logging
- **OrderLogger**: Structured JSON logs for audit trail
- **AuroraLogAdapter**: Trade intent and execution tracking
- **WAL**: Persistent event log for replay
- **MetricsCollector**: Performance and rejection metrics

```python
order_logger.write({
    "rid": decision.rid,
    "event_type": "ORDER_PLACED",
    "symbol": symbol,
    "qty_normalized": float(qty),
    "nrr_code": None,  # or rejection code
    # ... full context
})
```

## Advanced Features

### 9. **EP-01.3: Pending Entry TTL & Supersede**
Automatic cancellation of stale pending entries:

**Triggers:**
- Regime change (market conditions shift)
- Supersede (new intent for same symbol)
- Panic killswitch

**Implementation:**
```python
# On regime change
if pe_ttl_cfg.cancel_on_regime_change:
    self._cancel_pending_entries_for_symbol(
        symbol, reason="CANCEL_STALE_REGIME"
    )

# On new DEC:OPEN for symbol with pending entry
if has_pending and cancel_on_supersede:
    # Queue new open until cancel confirmed
    self._supersede_queue[symbol] = {"decision": decision}
```

### 10. **Leverage Bootstrap (TASK47c-P3)**
Syncs margin mode and leverage with exchange on startup:

```python
async def run_leverage_bootstrap(self) -> Set[str]:
    # Collect leverage configs from strategies
    # Sync each symbol's margin mode and leverage
    # Returns set of failed symbols (blocked from trading)
```

### 11. **Order Timeout Handling**
Two-phase timeout tracking:
- **ACK timeout**: Order not acknowledged by exchange
- **FILL timeout**: Order acknowledged but not filled

```python
# Watchdog triggers cancellation on timeout
async def _handle_order_timeout(self, deadline):
    # Attempt idempotent cancel
    # Log NRR-019 (timeout rejection code)
    # Emit monitoring event
```

### 12. **Orphan Order Cleanup**
OrderGuardian continuously monitors for orphaned brackets:

**Scenarios:**
- Position closed but TP/SL still open
- Multiple bracket sets for same symbol
- Brackets from old entries

```python
# Cleanup other brackets when placing new ones
await self.order_guardian.cleanup_other_brackets_for_symbol(
    symbol, keep_parent_order_id=entry_order_id
)
```

## Configuration Integration

### 13. **Multi-Source Configuration**
The FSM aggregates config from multiple YAML sources:

```python
# Trading mode (per-domain)
mode = config.get_domain_mode("execution_position")  # "testnet" or "live"

# Execution settings
exec_cfg = config.trading.execution
- cooldown_ms
- preflight_backoff_ms
- watchdog.ack_ttl_ms / fill_ttl_ms

# Instrument specs (SSOT)
instrument = config.instruments[symbol]
- tick_size, step_size, min_qty, min_notional
```

### 14. **Strategy Primacy for TP/SL**
Hierarchy for stop/target prices:
1. **Strategy explicit** (in DEC:OPEN payload)
2. **Config fallback** (strategies.aurora.assets[symbol].exit.sl_pct)
3. **Fail-closed** (reject if both missing)

```python
# Strategy provides explicit prices
explicit_sl = decision.pld.get("stop_price")
if explicit_sl is not None:
    sl = explicit_sl  # Use strategy value
else:
    # Fallback to config
    sl = mark * (1 - config.sl_pct)
```

## Operational Modes

### 15. **Shadow Mode**
Logs decisions without executing trades:
```python
if not self.shadow_mode and self.adapter:
    await self._execute_decision(decision)
else:
    LOG.info("Shadow mode - skipping execution")
```

### 16. **Live Execution Guardrails**
Safety checks prevent accidental live execution:
```python
if domain_mode == "testnet":
    if "testnet" not in self.adapter.base_url:
        LOG.critical("GUARDRAIL: Testnet mode with live URL!")
        return  # Block execution
```

## Event-Driven Architecture

### 17. **Key Events**

**Inbound:**
- `EVT:TRADE_INTENT_PROPOSED` → Route to OpenFlowFSM or CloseFlowFSM
- `EVT:PORTFOLIO_STATE_UPDATED` → Update exposure guard
- `EVT:REGIME_DETECTED` → Adjust risk limits, cancel stale entries
- `EVT:ORDER_ACK` / `EVT:ORDER_FILL` → Update tracking

**Outbound:**
- `DEC:OPEN` / `DEC:CLOSE` → Execution decisions
- `EVT:ORDER_PLACED` / `EVT:ORDER_REJECTED` → Order lifecycle
- `EVT:EXPOSURE_SUMMARY_UPDATED` → Risk monitoring

### 18. **Message Routing**
```python
def handle(self, msg: Message) -> Optional[Message]:
    if msg.verb == "OPEN":
        return open_flow.handle(msg)
    elif msg.verb == "TRADE_EXECUTED":
        return manage_flow.handle(msg)
    elif msg.verb == "CLOSE":
        return close_flow.handle(msg)
```

## Testing & Determinism

### 19. **Deterministic Time (DET-BT-13)**
Uses clock abstraction for reproducible backtests:
```python
from apps.reference.core.time import get_clock

# Instead of: await asyncio.sleep(0.5)
await get_clock().sleep_sec(0.5)  # Works in backtest & live
```

### 20. **Metrics & Observability**
Comprehensive metrics for monitoring:
```python
metrics = {
    "orphan_monitor": {
        "loops": 0,
        "cancels": 0,
        "tp_sl_placed_success": 0,
        # ...
    },
    "order_guardian": { /* ... */ },
    "gate": {
        "entry_blocked_tidy": 0,
        "entry_allowed_tidy": 0,
    }
}
```

## Best Practices Demonstrated

1. **Fail-Closed Validation**: No silent defaults, explicit requirements
2. **Idempotent Operations**: Graceful handling of duplicate events
3. **Event Deduplication**: Bounded memory tracking (BoundedEventDeduper)
4. **Correlation Tracking**: Full audit trail from intent to fill
5. **Resource Cleanup**: Automatic orphan detection and removal
6. **Configuration as Code**: Strongly-typed Pydantic models
7. **Observability**: Multi-layer logging and metrics
8. **Error Recovery**: Retry logic with exponential backoff

## Common Workflows

### Entry Execution
```
User Strategy → TRADE_INTENT_PROPOSED
  ↓
ExecPosFSM validates exposure & config
  ↓
OpenFlowFSM generates DEC:OPEN
  ↓
BinanceAdapter places MARKET/LIMIT order
  ↓
OrderGuardian registers tracking
  ↓
Watchdog monitors for ACK/FILL
  ↓
On FILL: Place TP/SL brackets
  ↓
ManageFlowFSM monitors position
```

### Position Close
```
CMD:CLOSE received
  ↓
Set closing flag (prevent bracket race)
  ↓
Cancel existing TP/SL brackets
  ↓
Place reduce-only MARKET order
  ↓
Wait for settlement (2s)
  ↓
Reconcile: Cancel any remaining brackets
  ↓
Clear closing flag
```

## Summary
This FSM demonstrates production-grade trading system architecture with:
- **Reliability**: Fail-closed validation, idempotent operations
- **Safety**: Multiple guard layers, exposure management
- **Observability**: Comprehensive logging and metrics
- **Maintainability**: Separation of concerns, configuration-driven
- **Resilience**: Error recovery, timeout handling, orphan cleanup

The code represents a mature approach to algorithmic execution that prioritizes correctness and auditability over convenience.
