# Aurora+Scalp v0.1.0 Release Notes

**Release Date**: 30              2025
**Version**: v0.1.0
**Status**: Production Ready (64/64 tests passing)

## Highlights

### Core Risk Management
- **ExposureGuard (20%)**: Portfolio-level exposure limits with fail-closed behavior on stale positions
- **DailyGate**: Daily drawdown limits with circuit breaker functionality
- **Post-fill Hold**: Race condition prevention between order fills and portfolio updates
- **Shadow Notional**: Safety auditing via Binance API validation (non-blocking)

### Operational Controls (OPS)
- **Panic Killswitch**: Emergency stop for all trading activity
- **Quiet Hours**: UTC-based time restrictions for trading windows
- **Symbol Allowlist**: Configurable symbol restrictions (empty = no restrictions)

### Order Lifecycle & Correlation (AUR-004)
- **OrderIndex**: TTL-based correlation system (rid     idempotent_key     clientOrderId     exchangeOrderId)
- **Audit Logging**: Structured JSONL event logging with WHY-codes and RID correlation
- **Terminal State Handling**: Proper cleanup on FILLED/CANCELED/REJECTED/EXPIRED events

### Telemetry & Observability
- **Metrics API**: `/statdump` endpoint returning real-time system metrics
- **Metrics Summary Tool**: CLI tool for Prometheus metrics aggregation (`tools/metrics_summary.py`)
- **Granular Logging**: Domain-specific log files with structured event correlation

### Quality Assurance
- **Decision QoS**: Anti-spam protection with symbol/exposure cooldowns and rate limiting
- **Normalized Reject Reasons**: Standardized error codes (NRR-001 to NRR-014) for consistent debugging
- **Features Pipeline Tests**: End-to-end validation from market data to trade decisions
- **BinanceAdapter Migration**: HTTP client migration to httpx with `.session` attribute for testing

## Breaking Changes / Config Updates

### New Configuration Keys
```yaml
execution:
  exposure:
    max_portfolio_pct: 20.0  # Portfolio exposure limit (%)
    pending_ttl_sec: 30      # Reservation TTL for race condition prevention

risk:
  daily:
    max_drawdown_pct: 5.0    # Daily drawdown limit (%)

ops:
  panic_killswitch: false    # Emergency stop flag
  quiet_hours_utc: []        # UTC time ranges: ["09:00-17:00"]
  allowlist_symbols: []      # Empty = no restrictions

decision:
  qos:
    exposure_block_cooldown_sec: 10
    symbol_cooldown_sec: 3
    max_intents_per_minute_per_symbol: 6
```

### Schema Validation
- Updated `config/_schemas/aurora_trading.schema.json` with validation for all new config sections
- Frozen snapshot: `config/_schemas/frozen/aurora_trading_20251030.json`

## Operational Guide

### Health Checks
```bash
# Quick system check
pytest -q  # Should show 64/64 passed

# Metrics summary
python tools/metrics_summary.py
cat reports/summary_gate_status.json

# Real-time status
curl -s http://127.0.0.1:8000/statdump | jq .
```

### Monitoring
- **Metrics**: Prometheus-compatible metrics available via `/metrics` endpoint
- **Logs**: Domain-specific logs in `logs/` directory
- **Events**: Structured events in `logs/aurora_events.jsonl`
- **Coverage**: Test coverage report in `reports/coverage.txt`

### Configuration
- **Active Config**: `configs/master_config_v1.yaml`
- **Frozen Config**: `configs/frozen/master_config_v1_20251030.yaml`
- **Schema**: `config/_schemas/aurora_trading.schema.json`

## Known Issues

None identified. All critical paths tested with 64/64 integration tests passing.

## Migration Notes

- No breaking API changes - all existing configurations remain compatible
- New config keys are optional with sensible defaults
- OPS controls are additive and can be enabled incrementally
- Exposure limits default to 20% portfolio notional

---

**Full Test Suite**: 64/64 integration tests passing
**Code Quality**: Ruff + mypy clean
**Architecture**: FSM-based with proper state isolation and idempotency
