# ORDER_LOGGER_AUDIT.md

## Summary
Audit of current order logging and NRR codes completed. Found extensive logging infrastructure with JSONL event streams, WhyCodes enum, and reservation mechanisms. Key gaps: inconsistent formats, potential NRR collisions, missing unified schema. Propose additive L1-ORDER-LOGGER schema for normalization.

## Current State Inventory

### Logging Points
- **JSONL Logs**: `logs/aurora_events.jsonl`, `logs/domain_decision_making.log`, `logs/orders_*.jsonl`
- **Event Types**: EVT:ORDER_STATE_CHANGED, GUARD_RATE_LIMIT_EXCEEDED, ORDER_PLACED
- **Metrics**: `vfoundation/apps/reference/telemetry/metrics.py` - order state counters/histograms
- **FSM Hooks**: `apps/reference/domains/execution_position/fsm.py` - place_market_entry(), generate_client_order_id()
- **Adapter Logs**: `vfoundation/adapters/binance_adapter.py` - create_order() with clientOrderId

### NRR Codes in Use
- **NRR-011**: Exposure limit exceeded (exposure_guard.py)
- **NRR-012**: Rate limit exceeded (decision_making.py QoS)
- **Source**: `vfoundation/core/why_codes.py` WhyCode enum

### Reservation System
- **TTL**: 90s default (exposure_guard.py)
- **Cleanup**: Automatic via TTL expiration
- **Purpose**: Prevent exposure violations during order placement

### Cooldown Mechanisms
- **Symbol Cooldown**: 3s default (decision_making.py)
- **Exposure Block Cooldown**: 10s default (decision_making.py)
- **CB Cooldown**: Configurable in circuit breaker logic

## Gaps Identified
1. Inconsistent log formats across domains
2. NRR codes not centralized in single catalog
3. Missing unified order lifecycle schema
4. Reservation logs not tied to order IDs
5. No standardized rejection reason structure

## Normalization Table

| Current Code | Normalized NRR | Description | Source File |
|-------------|---------------|-------------|-------------|
| NRR-011 | NRR-011 | Exposure limit exceeded | exposure_guard.py |
| NRR-012 | NRR-012 | Rate limit exceeded | decision_making.py |
| exposure_block_cooldown_active | NRR-013 | Exposure block cooldown active | decision_making.py |
| symbol_cooldown_active | NRR-014 | Symbol cooldown active | decision_making.py |
| EXCHANGE_ORDER_REJECTED | NRR-015 | Exchange rejected order | why_codes.py |
| TIMEOUT_ORDER_EXPIRED | NRR-016 | Order timeout expired | why_codes.py |

## Proposed L1-ORDER-LOGGER Schema (Additive)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://phenix.trade/schemas/order-logger/v1",
  "type": "object",
  "properties": {
    "rid": {"type": "string", "description": "Request ID"},
    "timestamp": {"type": "string", "format": "date-time"},
    "event_type": {
      "enum": ["ORDER_INTENT", "ORDER_PLACED", "ORDER_REJECTED", "ORDER_STATE_CHANGED"]
    },
    "order_id": {"type": ["string", "null"]},
    "client_order_id": {"type": ["string", "null"]},
    "symbol": {"type": "string"},
    "side": {"enum": ["BUY", "SELL"]},
    "quantity": {"type": "number"},
    "price": {"type": ["number", "null"]},
    "nrr_code": {"type": ["string", "null"], "pattern": "^NRR-\\d{3}$"},
    "why_code": {"type": ["string", "null"]},
    "reservation_id": {"type": ["string", "null"]},
    "adapter_response": {"type": ["object", "null"]},
    "metadata": {"type": "object"}
  },
  "required": ["rid", "timestamp", "event_type", "symbol"]
}
```

## Test Plan

### Unit Tests
1. **Schema Validation**: Validate all log entries against L1 schema
2. **NRR Code Coverage**: Test all NRR codes are logged correctly
3. **Reservation Logging**: Verify reservation_id in order logs
4. **FSM Integration**: Test ORDER_STATE_CHANGED events

### Integration Tests
1. **End-to-End Order Flow**: Place order, verify complete log chain
2. **Rejection Scenarios**: Test all NRR codes trigger correct logs
3. **Reservation Cleanup**: Verify TTL expiration logs

### Files for Future Changes
- `vfoundation/core/why_codes.py` - Add new NRR codes
- `apps/reference/domains/decision_making/decision_making.py` - Add schema logging
- `apps/reference/domains/execution_position/fsm.py` - Integrate schema fields
- `vfoundation/adapters/binance_adapter.py` - Include adapter_resp in logs
- `vfoundation/core/exposure_guard.py` - Add reservation logging
- `vfoundation/apps/reference/telemetry/metrics.py` - Update for new schema</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\artifacts\ORDER_LOGGER_AUDIT.md
