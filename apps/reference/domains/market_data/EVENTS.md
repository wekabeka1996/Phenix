# Market Data Events

## Overview

The `market_data` domain is primarily an **event producer** that emits real-time market data events to downstream consumers. It does not consume events but serves as the primary data source for the trading system.

**Event Production:** ✅ **ACTIVE**
**Event Consumption:** ❌ **NONE**
**Event Types:** 1 output event type
**Event Frequency:** 0.5 Hz per symbol (configurable)

## Event Architecture

### Event Flow

```
MarketDataConnector ── EVT:MARKET_TICK_RECEIVED ──► Feature Engineering
    │                                                (Anchor Updates)
    │
    └─ EVT:MARKET_TICK_RECEIVED ──► Decision Making
                                      (Trading Signals)
    │
    └─ EVT:MARKET_TICK_RECEIVED ──► Risk Management
                                      (Position Monitoring)
```

### Event Processing Model

#### Synchronous Processing
- **Event Emission:** Immediate emission after data processing
- **No Buffering:** Real-time emission without queuing
- **Fire-and-Forget:** No acknowledgment required from consumers

#### Error Handling
- **Emission Failures:** Logged but don't block processing
- **Consumer Errors:** Isolated from producer (circuit breaker pattern)
- **Data Loss:** Acceptable for real-time data (freshness priority)

## Event Specifications

### EVT:MARKET_TICK_RECEIVED

**Purpose:** Real-time market data emission with calculated features for trading decisions.

**Emission Frequency:** Every 2 seconds per symbol (configurable via `poll_interval_sec`)

**Event Schema:**

```json
{
  "event_type": "EVT:MARKET_TICK_RECEIVED",
  "timestamp": 1703123456789,
  "correlation_id": "md_1234567890_001",
  "payload": {
    "ts": 1703123456789,
    "symbol": "SOLUSDT",
    "price": "123.45",
    "bid": "123.40",
    "ask": "123.50",
    "mid": "123.45",
    "bid_size": "150.5",
    "ask_size": "200.3",
    "buy_volume": "45",
    "sell_volume": "32",
    "data_type": "market_tick_aggregated",
    "data_source": "websocket_live",
    "debug_info": "BID/ASK: 150/200, Trades: BUY=45 SELL=32"
  },
  "metadata": {
    "domain": "market_data",
    "component": "MarketDataConnector",
    "version": "1.0",
    "environment": "live"
  }
}
```

#### Field Definitions

##### Core Market Data
- **ts** (`integer`): Unix timestamp in milliseconds when data was received
- **symbol** (`string`): Trading pair symbol (e.g., "SOLUSDT", "ETHUSDT")
- **price** (`string`): Last traded price (decimal string for precision)
- **bid** (`string`): Best bid price
- **ask** (`string`): Best ask price
- **mid** (`string`): Mid price: (bid + ask) / 2

##### Order Book Data
- **bid_size** (`string`): Total bid size at best bid price
- **ask_size** (`string`): Total ask size at best ask price

##### Trade Flow Data
- **buy_volume** (`string`): Recent buy volume (aggressive buyers)
- **sell_volume** (`string`): Recent sell volume (aggressive sellers)

##### Metadata
- **data_type** (`string`): Always "market_tick_aggregated"
- **data_source** (`string`): "websocket_live", "websocket_testnet", "rest_live", "rest_testnet"
- **debug_info** (`string`): Human-readable summary for debugging

## Event Processing Logic

### Data Collection

#### Primary Data Sources
1. **WebSocket Streams:** Real-time bookTicker and trade data
2. **REST API Polling:** Fallback for comprehensive market data
3. **Kline Data:** Historical price data for delta calculations

#### Data Aggregation
```python
# WebSocketAggregator processing
def on_book_ticker(self, symbol, bid, bid_size, ask, ask_size, timestamp):
    # Update order book state
    self.book_state[symbol] = {
        'bid': Decimal(bid),
        'bid_size': Decimal(bid_size),
        'ask': Decimal(ask),
        'ask_size': Decimal(ask_size),
        'timestamp': timestamp
    }

def on_trade(self, symbol, price, quantity, is_buyer_maker, timestamp):
    # Aggregate trade data in time windows
    window_key = timestamp // (self.window_seconds * 1000)
    if window_key not in self.trade_windows[symbol]:
        self.trade_windows[symbol][window_key] = {
            'buy_volume': Decimal('0'),
            'sell_volume': Decimal('0'),
            'trades': []
        }

    # Classify trade direction
    if is_buyer_maker:  # Buyer is market maker = Sell trade
        self.trade_windows[symbol][window_key]['sell_volume'] += Decimal(quantity)
    else:  # Seller is market maker = Buy trade
        self.trade_windows[symbol][window_key]['buy_volume'] += Decimal(quantity)
```

### Feature Calculation

#### Order Book Imbalance (OBI)
```python
def calculate_obi(self, bid_size, ask_size):
    """Calculate Order Book Imbalance"""
    total_size = bid_size + ask_size
    if total_size == 0:
        return Decimal('0')
    return (bid_size - ask_size) / total_size
```

#### Trade Flow Imbalance (TFI)
```python
def calculate_tfi(self, buy_volume, sell_volume):
    """Calculate Trade Flow Imbalance"""
    total_volume = buy_volume + sell_volume
    if total_volume == 0:
        return Decimal('0')
    return (buy_volume - sell_volume) / total_volume
```

#### Price Delta
```python
def calculate_price_delta(self, current_price, previous_price):
    """Calculate price change percentage"""
    if previous_price == 0:
        return Decimal('0')
    return (current_price - previous_price) / previous_price
```

### Event Emission

#### Emission Trigger
```python
async def _fetch_and_emit_data(self):
    """Main polling loop that fetches data and emits events"""
    while self.running:
        try:
            # Fetch data from all sources
            market_data = await self._fetch_market_data()

            # Process each symbol
            for symbol in self.config.symbols:
                if symbol in market_data:
                    # Get aggregated tick data
                    tick_data = self.websocket_aggregator.get_market_tick(symbol)

                    # Emit event
                    await self._emit_market_tick(symbol, tick_data)

            # Wait for next poll interval
            await asyncio.sleep(self.config.poll_interval_sec)

        except Exception as e:
            self.logger.error(f"Error in polling loop: {e}")
            await asyncio.sleep(self.config.poll_interval_sec)
```

#### Event Emission Method
```python
async def _emit_market_tick(self, symbol, tick_data):
    """Emit market tick event with processed data"""
    try:
        event_payload = {
            "ts": tick_data.get('timestamp', int(time.time() * 1000)),
            "symbol": symbol,
            "price": str(tick_data.get('price', '0')),
            "bid": str(tick_data.get('bid', '0')),
            "ask": str(tick_data.get('ask', '0')),
            "mid": str(tick_data.get('mid', '0')),
            "bid_size": str(tick_data.get('bid_size', '0')),
            "ask_size": str(tick_data.get('ask_size', '0')),
            "buy_volume": str(tick_data.get('buy_volume', '0')),
            "sell_volume": str(tick_data.get('sell_volume', '0')),
            "data_type": "market_tick_aggregated",
            "data_source": self._get_data_source_type(),
            "debug_info": self._generate_debug_info(tick_data)
        }

        # Emit event
        await self.fsm.emit_event("EVT:MARKET_TICK_RECEIVED", event_payload)

        self.logger.info(f"📊 {symbol} Tick: bid={tick_data.get('bid_size', 0)}@{tick_data.get('bid', 0)}, "
                        f"ask={tick_data.get('ask_size', 0)}@{tick_data.get('ask', 0)}, "
                        f"trades: BUY={tick_data.get('buy_volume', 0)} SELL={tick_data.get('sell_volume', 0)}")

    except Exception as e:
        self.logger.error(f"Failed to emit market tick for {symbol}: {e}")
```

## Event Consumers

### Primary Consumers

#### Feature Engineering Domain
**Consumption Pattern:** Synchronous processing of anchor updates
**Processing:** Real-time price feeds for macro feature calculation
**Integration:** Callback-based updates via `update_anchor_price()`

```python
# FeatureEngineering consumer example
async def on_market_tick_received(self, event):
    """Process market tick for feature engineering"""
    symbol = event.payload['symbol']

    # Update anchor prices for macro sync
    if symbol in self.config.macro_sync.anchors:
        await self.update_anchor_price(symbol, event.payload)
```

#### Decision Making Domain
**Consumption Pattern:** Real-time signal generation
**Processing:** Feature-based trading signal calculation
**Integration:** Event-driven signal processing pipeline

#### Risk Management Domain
**Consumption Pattern:** Continuous position monitoring
**Processing:** Real-time P&L and risk metric updates
**Integration:** Live position risk assessment

### Consumer Requirements

#### Event Processing Guarantees
- **At-Least-Once Delivery:** Events may be redelivered on failures
- **No Ordering Guarantees:** Events may arrive out of sequence
- **No Persistence:** Events are not stored (fire-and-forget model)

#### Error Handling Requirements
- **Idempotent Processing:** Consumers must handle duplicate events
- **Circuit Breakers:** Consumers should implement failure isolation
- **Graceful Degradation:** Continue operation despite event loss

## Event Monitoring

### Key Metrics

#### Emission Metrics
```
market_data_events_emitted_total{symbol="SOLUSDT"} 120
market_data_event_emission_duration_seconds{symbol="SOLUSDT"} 0.023
market_data_events_failed_total{symbol="SOLUSDT"} 0
```

#### Data Quality Metrics
```
market_data_data_freshness_seconds{symbol="SOLUSDT"} 1.5
market_data_price_validity_ratio{symbol="SOLUSDT"} 0.99
market_data_event_completeness_ratio{symbol="SOLUSDT"} 1.0
```

#### Consumer Health Metrics
```
market_data_consumer_processing_duration_seconds{consumer="feature_engineering"} 0.015
market_data_consumer_errors_total{consumer="decision_making"} 2
market_data_consumer_backlog_size{consumer="risk_management"} 0
```

### Alert Conditions

#### Critical Alerts
- **Event Emission Stopped:** No events emitted for > 5 minutes
- **High Emission Latency:** Event processing > 100ms (95th percentile)
- **Data Freshness Degradation:** Data > 10 seconds old

#### Warning Alerts
- **Event Emission Errors:** > 1% of events fail to emit
- **Consumer Processing Errors:** > 5% of events fail consumer processing
- **Data Quality Issues:** > 1% invalid data points

### Log Analysis

#### Successful Processing
```
INFO  📊 SOLUSDT Tick: bid=150.5@123.40, ask=200.3@123.50, trades: BUY=45 SELL=32
INFO  ✅ Event EVT:MARKET_TICK_RECEIVED emitted for SOLUSDT
```

#### Error Conditions
```
ERROR ❌ Failed to emit market tick for SOLUSDT: Connection timeout
WARN  ⚠️  Consumer feature_engineering failed to process event: Invalid data format
ERROR ❌ Event emission failed for SOLUSDT: FSM not available
```

#### Performance Monitoring
```bash
# Monitor event emission rate
tail -f logs/market_data.log | grep "📊.*Tick:" | wc -l

# Check for emission errors
grep "❌ Failed to emit" logs/market_data.log | tail -10

# Monitor data freshness
grep "📊.*Tick:" logs/market_data.log | awk '{print $1}' | tail -5
```

## Testing Event Processing

### Unit Tests

#### Event Emission Tests
```python
def test_market_tick_emission(self):
    """Test that market ticks are properly emitted"""
    # Setup
    connector = MarketDataConnector(self.fsm, self.config)

    # Mock data
    tick_data = {
        'price': Decimal('123.45'),
        'bid': Decimal('123.40'),
        'ask': Decimal('123.50'),
        'bid_size': Decimal('150.5'),
        'ask_size': Decimal('200.3'),
        'buy_volume': Decimal('45'),
        'sell_volume': Decimal('32'),
        'timestamp': 1703123456789
    }

    # Execute
    await connector._emit_market_tick('SOLUSDT', tick_data)

    # Verify
    self.fsm.emit_event.assert_called_once_with(
        "EVT:MARKET_TICK_RECEIVED",
        mock.ANY  # Detailed payload verification
    )
```

#### Event Payload Tests
```python
def test_event_payload_structure(self):
    """Test event payload contains all required fields"""
    # Execute emission
    await self.connector._emit_market_tick('SOLUSDT', self.sample_tick_data)

    # Verify payload structure
    call_args = self.fsm.emit_event.call_args
    event_type, payload = call_args[0]

    required_fields = [
        'ts', 'symbol', 'price', 'bid', 'ask', 'mid',
        'bid_size', 'ask_size', 'buy_volume', 'sell_volume',
        'data_type', 'data_source', 'debug_info'
    ]

    for field in required_fields:
        self.assertIn(field, payload)
```

### Integration Tests

#### End-to-End Event Flow
```python
def test_end_to_end_event_processing(self):
    """Test complete event flow from data fetch to consumer"""
    # Setup mock consumer
    consumer = MockFeatureEngineering()
    self.fsm.register_event_handler("EVT:MARKET_TICK_RECEIVED", consumer.on_market_tick)

    # Start connector
    await self.connector.start()

    # Wait for event processing
    await asyncio.sleep(3)

    # Verify consumer received events
    self.assertTrue(len(consumer.received_events) > 0)

    # Verify event data integrity
    event = consumer.received_events[0]
    self.assertEqual(event.payload['symbol'], 'SOLUSDT')
    self.assertIn('price', event.payload)
```

#### Consumer Failure Tests
```python
def test_consumer_failure_isolation(self):
    """Test that consumer failures don't affect event emission"""
    # Setup failing consumer
    failing_consumer = MockFailingConsumer()
    self.fsm.register_event_handler("EVT:MARKET_TICK_RECEIVED", failing_consumer.on_market_tick)

    # Setup working consumer
    working_consumer = MockWorkingConsumer()
    self.fsm.register_event_handler("EVT:MARKET_TICK_RECEIVED", working_consumer.on_market_tick)

    # Emit event
    await self.connector._emit_market_tick('SOLUSDT', self.sample_tick_data)

    # Verify working consumer still received event
    self.assertEqual(len(working_consumer.received_events), 1)

    # Verify failing consumer threw error but didn't block
    self.assertTrue(failing_consumer.failed)
```

## Troubleshooting

### Common Event Issues

#### No Events Being Emitted
**Symptoms:** Consumers not receiving EVT:MARKET_TICK_RECEIVED events
**Causes:**
- Connector not started or crashed
- FSM not available or misconfigured
- Data fetching failures blocking emission
**Solutions:**
- Check connector logs for startup errors
- Verify FSM connectivity
- Test data fetching independently

#### Invalid Event Payloads
**Symptoms:** Consumers receiving malformed event data
**Causes:**
- Data source returning invalid data
- Feature calculation errors
- Serialization issues
**Solutions:**
- Validate data source responses
- Check feature calculation logic
- Add payload schema validation

#### Event Emission Delays
**Symptoms:** Events arriving with significant delays
**Causes:**
- High polling intervals
- Processing bottlenecks
- Network latency to data sources
**Solutions:**
- Reduce poll_interval_sec
- Optimize processing logic
- Monitor network connectivity

### Debug Procedures

#### Enable Event Tracing
```python
# Enable detailed event logging
import logging
logging.getLogger('vfoundation.fsm.events').setLevel(logging.DEBUG)

# Trace specific events
self.fsm.add_event_tracer("EVT:MARKET_TICK_RECEIVED", lambda e: print(f"Event: {e}"))
```

#### Manual Event Emission
```python
# Test event emission manually
from apps.reference.domains.market_data.market_data_connector import MarketDataConnector

connector = MarketDataConnector(fsm, config)
sample_data = {
    'price': Decimal('123.45'),
    'bid': Decimal('123.40'),
    'ask': Decimal('123.50'),
    'bid_size': Decimal('150.5'),
    'ask_size': Decimal('200.3'),
    'buy_volume': Decimal('45'),
    'sell_volume': Decimal('32'),
    'timestamp': 1703123456789
}

await connector._emit_market_tick('SOLUSDT', sample_data)
```

#### Consumer Debugging
```python
# Debug consumer event handling
class DebugConsumer:
    async def on_market_tick_received(self, event):
        print(f"Received event: {event.event_type}")
        print(f"Payload: {event.payload}")
        print(f"Timestamp: {event.timestamp}")

        # Validate payload
        required_fields = ['symbol', 'price', 'bid', 'ask']
        for field in required_fields:
            if field not in event.payload:
                print(f"ERROR: Missing required field: {field}")
```

---

*Event Documentation Version: 1.0*
*Last Updated: January 15, 2024*
*Event Types: 1 output event*
*Test Coverage: Event emission and payload validation*</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\market_data\EVENTS.md
