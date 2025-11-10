# Домен Execution Position (Виконання Позицій)

## Огляд

Домен **execution_position** є core execution engine системи, що відповідає за відкриття, управління та закриття торгових позицій на Binance Futures. Домен реалізує складну FSM архітектуру з трьома окремими flows (Open, Manage, Close) та забезпечує надійне, idempotent виконання ордерів з comprehensive error handling та monitoring.

## Архітектура

### Triple FSM Architecture
Домен використовує **три окремих FSM** для кожного аспекту position lifecycle:

#### 1. OpenFlowFSM (`fsm_open.py`)
**Відповідальність:** Обробка команд відкриття позицій
- **States:** IDLE → CANDIDATE → READY → EMIT_DEC_OPEN → DONE
- **Guards:** min_notional, quantity/price validation, cooldown protection
- **Output:** DEC:OPEN з validated order parameters

#### 2. ManageFlowFSM (`fsm_manage.py`)
**Відповідальність:** Управління відкритими позиціями
- **States:** Управління TP/SL brackets, exposure monitoring
- **Features:** Dynamic TP/SL adjustment, exposure guards
- **Integration:** OrderGuardian для cleanup orphaned orders

#### 3. CloseFlowFSM (`fsm_close.py`)
**Відповідальність:** Закриття позицій за умовами
- **States:** FLAT → OPENED → CLOSE_COND → EMIT_DEC_CLOSE → DONE
- **Triggers:** Time-based, event-driven (EVT:FILL, EVT:REJECTED)
- **Output:** DEC:CLOSE з reduce_only=true

#### 4. ExecPosFSM (`fsm.py`) - Orchestrator
**Роль:** Головний оркестратор, що маршрутизує команди до відповідних flow FSM
- **Per-symbol routing:** Окремий стан для кожного торгового символу
- **Integration:** BinanceAdapter, CorrelationStore, MetricsCollector
- **Features:** Circuit breaker, quiet hours, exposure limits

## Події (Events)

### Вхідні Команди (Consumed)

#### CMD:OPEN
**Тригер:** Запит на відкриття нової позиції

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "side": "BUY",
  "qty": "0.001",
  "order_type": "LIMIT",
  "price": "45000.50",
  "tif": "GTC",
  "tp_bps": 50,
  "sl_bps": 25
}
```

#### CMD:CLOSE
**Тригер:** Запит на закриття позиції

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "close_type": "MARKET"
}
```

#### CMD:ADJUST
**Тригер:** Зміна TP/SL рівнів

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "tp_price": "46000.00",
  "sl_price": "44000.00"
}
```

### Вихідні Рішення (Emitted)

#### DEC:OPEN
**Тригер:** OpenFlowFSM успішно провалидував та підготував ордер

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "side": "BUY",
  "qty": "0.001",
  "price": "45000.50",
  "tif": "GTC",
  "client_order_id": "exec_pos_1234567890",
  "tp_price": "45225.25",
  "sl_price": "44625.13"
}
```

#### DEC:CLOSE
**Тригер:** CloseFlowFSM визначив умови для закриття

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "close_type": "MARKET",
  "reduce_only": true
}
```

#### DEC:ADJUST
**Тригер:** ManageFlowFSM коригує TP/SL

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "tp_price": "45500.00",
  "sl_price": "44200.00"
}
```

## Ключові Компоненти

### Execution Adapters
- **BinanceAdapter:** Live trading execution
- **SimulatedAdapter:** Backtesting/paper trading
- **AuroraLogAdapter:** Enhanced logging для Aurora

### Risk Management
- **ExposureGuard:** Position size limits, portfolio exposure
- **OrderGuardian:** Cleanup orphaned TP/SL orders
- **SoftClip:** Quantity validation та adjustment

### Monitoring & Observability
- **MetricsCollector:** Performance metrics та KPIs
- **OrderTimeoutWatchdog:** Detection stale orders
- **AuroraLogAdapter:** Structured logging

### Utilities
- **Order Index:** Fast order lookup та correlation
- **Idempotent Cancel:** Safe order cancellation
- **Drift Monitor:** Detection execution drift

## Контракти та Валідація

### Order Contracts (`contracts.py`)
```python
class OrderPayload(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=20)
    side: Side  # BUY/SELL
    qty: Decimal = Field(..., gt=0)
    order_type: OrderType = OrderType.LIMIT
    price: Optional[Decimal] = Field(None, gt=0)
    tif: TimeInForce = TimeInForce.GTC
```

### Validation Rules
- **Quantity:** MIN=0.001, MAX=1000.0, STEP=0.001
- **Price:** MIN=0.01, MAX=1,000,000, STEP=0.01
- **Notional:** MIN=10.0 USD equivalent
- **TP/SL:** Anti-2021 protection, quantization

### Enums
- **Side:** BUY, SELL
- **OrderType:** MARKET, LIMIT, STOP_LIMIT, TAKE_PROFIT_MARKET
- **TimeInForce:** GTC, IOC, FOK
- **OrderStatus:** PENDING, PLACED, PARTIAL, FILLED, CANCELLED

## API Інтеграція

### Binance Futures API
- **Order Placement:** `/fapi/v2/order` (POST)
- **Order Cancellation:** `/fapi/v2/order` (DELETE)
- **Order Status:** `/fapi/v2/order` (GET)
- **Position Info:** `/fapi/v2/positionRisk` (GET)

### Authentication & Security
- HMAC-SHA256 signature для всіх запитів
- Timestamp validation (within 5 seconds)
- Rate limiting: 10 orders/second, 100,000/day
- Idempotency через client_order_id

## Risk Management

### Exposure Controls
- **Position Limits:** Per-symbol position size limits
- **Portfolio Exposure:** Total portfolio risk limits
- **Circuit Breaker:** Automatic trading halt on errors

### Order Protection
- **Anti-2021:** TP/SL validation against mark price
- **Quantity Validation:** Min/max/step enforcement
- **Price Validation:** Reasonable price range checks
- **Cooldown Protection:** Minimum time between orders

### Error Handling
- **Retry Logic:** Exponential backoff для transient errors
- **Circuit Breaker:** Halt trading after consecutive failures
- **Graceful Degradation:** Continue operation despite partial failures

## Тестування

### Test Coverage
- **Unit Tests:** 63 тестових методи (contracts, utils, FSM logic)
- **Integration Tests:** End-to-end order flows
- **Test Adapters:** Simulated execution для deterministic testing

### Test Categories
#### Utils Testing (`test_execution_position_utils.py`)
- **37 tests:** Quantization, validation, TP/SL calculations
- **Coverage:** 100% utils functions

#### Contracts Testing (`test_execution_position_contracts.py`)
- **23 tests:** Pydantic validation, enum testing
- **Coverage:** All contract validations

#### FSM Testing (`test_execution_position_basic.py`)
- **3 tests:** Basic FSM state transitions
- **Coverage:** Core orchestration logic

## Продуктивність

### Performance Characteristics
- **Latency:** < 100ms для order validation
- **Throughput:** 10 orders/second (API limited)
- **Memory:** ~50MB baseline + 1KB per active position
- **CPU:** Minimal processing, mostly I/O bound

### Optimization Features
- **Async Processing:** Non-blocking order operations
- **Batch Operations:** Grouped API calls де можливо
- **Caching:** Order state caching для fast lookups
- **Metrics:** Real-time performance monitoring

## Deployment

### Configuration
```yaml
execution_position:
  max_position_qty: 1.0
  max_portfolio_exposure: 10000
  order_cooldown_sec: 1.0
  quiet_hours: ["22:00-06:00"]
  circuit_breaker_threshold: 5

binance_api:
  testnet:
    api_key: "test_key"
    api_secret: "test_secret"
  live:
    api_key: "live_key"
    api_secret: "live_secret"
```

### Environment Variables
```bash
EXECUTION_POSITION_MAX_QTY=1.0
EXECUTION_POSITION_COOL_DOWN=1.0
BINANCE_API_KEY="your_api_key"
BINANCE_API_SECRET="your_api_secret"
```

## Monitoring

### Key Metrics
- `execution_position_orders_total` - Total orders processed
- `execution_position_orders_failed` - Failed order attempts
- `execution_position_positions_active` - Currently open positions
- `execution_position_pnl_realized` - Realized P&L tracking

### Health Checks
- API connectivity validation
- Order placement/cancellation testing
- Position synchronization checks
- Circuit breaker status monitoring

## Troubleshooting

### Common Issues
1. **Rate Limit Exceeded** - Implement backoff, reduce frequency
2. **Invalid Order Parameters** - Check quantity/price validation
3. **API Authentication Failed** - Verify credentials, check permissions
4. **Position Desync** - Check correlation store, restart if needed

### Debug Mode
```python
# Enable detailed logging
LOG.setLevel(logging.DEBUG)

# Enable metrics collection
metrics_collector = MetricsCollector(enable_debug=True)
```

## Архітектурні Рішення

### Чому Triple FSM?
- **Separation of Concerns:** Each flow має власну логіку
- **Testability:** Independent testing кожного flow
- **Maintainability:** Isolated changes без side effects

### Чому Shadow Mode?
- **Risk Mitigation:** Validation без live execution
- **Testing:** Deterministic behavior для CI/CD
- **Gradual Rollout:** Safe production deployment

### Чому Idempotency?
- **Reliability:** Safe retry після network failures
- **Consistency:** Guaranteed execution exactly once
- **Recovery:** Automatic reconciliation після restarts

## Майбутні Покращення

### Short-term
- [ ] WebSocket integration для real-time execution
- [ ] Advanced TP/SL strategies (trailing stops)
- [ ] Multi-exchange support
- [ ] Performance optimization

### Long-term
- [ ] Machine learning для order timing
- [ ] Cross-exchange arbitrage
- [ ] Advanced risk models
- [ ] Distributed execution

---

**Версія документації:** 1.0
**Дата створення:** 9 листопада 2025 г.
**Автор:** QuantumTraderX Analysis</content>
<filePath">c:\Users\user\Music\Phenix\apps\reference\domains\execution_position\Readme\README.md
