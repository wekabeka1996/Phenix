# market_data

Root upstream domain. Ingests raw market data from Binance WebSocket feeds, aggregates into structured ticks, constructs OHLCV bars, and emits deterministic events for downstream consumption.

## Architecture

```
Binance WS (bookTicker + configured trade stream: trade or aggTrade)
        │
        ▼
┌─────────────────────────────────────────────┐
│  Multi-process path (production)            │
│  MarketDataWorker  ──IPC Queue──▶  MarketDataProxy  ──FSM──▶  events  │
│  (separate process)                (main process)                      │
└─────────────────────────────────────────────┘
        │                                          │
        ▼                                          ▼
┌──────────────────┐                    ┌──────────────────┐
│ WebSocketAggregator │                 │   BarAggregator   │
│ raw WS → tick dict  │                 │ ticks → OHLCV bars│
└──────────────────┘                    └──────────────────┘
```

**Two data paths** (config-gated via `use_multiprocessing`):
- **Multi-process** (`worker.py` → IPC → `proxy.py`) — production default. Isolates WS I/O in a separate process.
- **Single-process** (`market_data_connector.py`) — legacy path. Used when `use_multiprocessing=false`.

## File Map

| File | LOC | Role |
|------|-----|------|
| `__init__.py` | 26 | Lazy import dispatcher |
| `bar_aggregator.py` | 509 | **SSOT bar constructor** — tick → Bar → EVT:BAR_CLOSED |
| `market_data_connector.py` | 493 | Legacy single-process WS connector |
| `worker.py` | 661 | Isolated WS data collection process |
| `proxy.py` | 454 | Bridges worker process with FSM (main process) |
| `websocket_aggregator.py` | 369 | Aggregates raw WS events into structured tick dicts |

## Events

### Emitted (owned)
| Event | Emitter(s) | Schema |
|-------|-----------|--------|
| `EVT:MARKET_TICK_RECEIVED` | connector, proxy | `schemas/market_tick_received_v1.json` |
| `EVT:BAR_CLOSED` | bar_aggregator | `schemas/bar_closed_v1.json` |
| `EVT:ANCHOR_UPDATED` | connector, proxy | `schemas/anchor_updated_v1.json` |

### Deprecated
| Event | Deprecated Since | Reason |
|-------|-----------------|--------|
| `EVT:MARKET_TICK_FORWARDED` | 2026-03-14 | No active emitter |

### Consumed
None — this is the root upstream domain with no inbound event dependencies.

## Downstream Consumers

| Event | Consumer Domains |
|-------|-----------------|
| `EVT:MARKET_TICK_RECEIVED` | feature_engineering (FE), bar_aggregator (internal) |
| `EVT:BAR_CLOSED` | feature_engineering, decision_making, bootstrap |
| `EVT:ANCHOR_UPDATED` | feature_engineering |

## SSOT Rules

1. **BarAggregator** is the single bar constructor. No other domain constructs OHLCV bars.
2. **WebSocketAggregator** is the single tick aggregator. Raw WS messages → structured tick dict.
3. **No TTL enforcement** within this domain. `tick_ttl_ms` and `bar_ttl_ms` are consumed by downstream domains (FE, DM).
4. **Bar type** (`Bar` dataclass) is defined in `feature_engineering/bar_resampler.py` and re-exported via `shared/types.py`.

## Known Debt

| Priority | Item |
|----------|------|
| ~~P1~~ | ~~**Dead code:** `market_ws_client.py`~~ — deleted in LEGACY-PURGE-WAVE-1 (2026-03-15) |
| P2 | **Default timeframe mismatch:** `domain_builder.py` fallback is `[60, 300]`, `BarAggregator.__init__` default is `[180, 300]`. Should be unified. |
| P2 | **Absorption stub:** `websocket_aggregator.py` hardcodes `"absorption": "0.0"` — never computed |
| P2 | **Memory leak risk:** `seen_trade_ids` set in WebSocketAggregator has no size limit |
| P3 | **WS URL duplication:** Binance WS URLs hardcoded in 2 files (connector, worker) |
| ~~P3~~ | ~~**Deprecated methods:** `set_feature_engineering()`~~ — deleted in LEGACY-PURGE-WAVE-1 (2026-03-15) |
| ~~P3~~ | ~~**Dead imports:** `asdict` in bar_aggregator, `time` in connector~~ — deleted in LEGACY-PURGE-WAVE-1 (2026-03-15) |

## Configuration

Managed via `AuroraConfig`:
- `trading.market_data.use_multiprocessing` — selects data path
- `trading.market_data.websocket_streams` — explicit WS stream list; must include `bookTicker` and one trade stream (`trade` or `aggTrade`)
- `trading.market_data.bar_aggregator.enabled` — enables/disables bar construction
- `trading.market_data.bar_aggregator.timeframes_sec` — bar timeframes (default fallback: `[60, 300]` in domain_builder)
- `trading.market_data.poll_interval_sec` — worker poll interval
- `system.market_data.queue_maxsize` — IPC queue size
- `system.market_data.trade_silence_reconnect_sec` — reconnect threshold when trade events stop but bookTicker still flows
- `system.market_data.proxy_batch_size` — proxy consumption batch size
