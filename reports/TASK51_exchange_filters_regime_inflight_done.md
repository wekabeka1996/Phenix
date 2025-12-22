# TASK51 - Exchange Filters SSOT Lock + Regime Allowlist Contract + In-Flight Reconcile

**Status:** ✅ COMPLETE  
**Date:** 2025-12-22  
**Author:** Claude Opus 4.5 (GitHub Copilot)

---

## Summary

Реалізовано три пакети для стабілізації торгової системи:

| Package | Description | Tests | Status |
|---------|-------------|-------|--------|
| 51-A | Exchange Filters SSOT Validation | 18 | ✅ PASS |
| 51-B | Regime Allowlist Contract | 23 | ✅ PASS |
| 51-C | Order In-Flight Reconcile | 24 | ✅ PASS |
| **TOTAL** | | **65** | ✅ PASS |

---

## PACKAGE 51-A: Exchange Filters SSOT Validation (P0)

### Проблема
Config-drift фільтрів (SOL step_size=1 на testnet, а в SSOT було 0.01) призводив до qty→0 і REJECT.

### Рішення
1. **ExchangeFiltersValidator** - валідатор фільтрів проти біржі на startup
2. **FilterMismatchError** - fail-closed exception при розбіжності
3. **SSOTFilters / ExchangeFilters** - типобезпечні контракти

### Contract
```
LIVE mode: mismatch → startup crash (fail-closed)
TESTNET mode: mismatch → startup crash (fail-closed)  
DEV/SHADOW mode: mismatch → warning only (warn_only=True flag)
```

### Files Created
- [apps/reference/domains/exchange_filters/__init__.py](apps/reference/domains/exchange_filters/__init__.py)
- [apps/reference/domains/exchange_filters/contracts.py](apps/reference/domains/exchange_filters/contracts.py)
- [apps/reference/domains/exchange_filters/validator.py](apps/reference/domains/exchange_filters/validator.py)
- [tests/contracts/test_exchange_filters_validation.py](tests/contracts/test_exchange_filters_validation.py)

### Key Tests
- `test_filters_mismatch_crashes_in_live` ✅
- `test_filters_match_passes` ✅
- `test_sol_step_size_mismatch_detected` ✅

---

## PACKAGE 51-B: Regime Allowlist Contract (P1)

### Проблема
Блокування по MEAN_REVERSION було неявним - стратегія призначена, але режими заблоковані.

### Рішення
1. **RegimeAllowlistContract** - валідація конфігурації режимів per-strategy
2. **RegimeAllowlistError** - fail-closed для критичних порушень
3. **explain_blocking()** - explainable причини блокування

### Contract
```
Якщо strategy "mean_reversion" призначена символу:
  → allowed_regimes ПОВИНЕН містити хоча б один MR-compatible режим
  → MR-compatible: FLAT_LOW, FLAT_NORMAL, FLAT_HIGH, LOW_VOLATILITY, MEAN_REVERSION
  
Якщо порушено → CRITICAL violation → startup crash
```

### Files Created
- [apps/reference/domains/regime_allowlist/__init__.py](apps/reference/domains/regime_allowlist/__init__.py)
- [apps/reference/domains/regime_allowlist/contract.py](apps/reference/domains/regime_allowlist/contract.py)
- [tests/contracts/test_regime_allowlist.py](tests/contracts/test_regime_allowlist.py)

### Key Tests
- `test_mr_blocking_is_explainable_and_config_driven` ✅
- `test_mr_enabled_when_allowlisted` ✅

---

## PACKAGE 51-C: Order In-Flight Reconcile (P0)

### Проблема
Симптом "order in flight" (ETH) лікувався перезапуском - orders залишались вічно in-flight.

### Рішення
1. **InFlightReconciler** - TTL-based tracking з reconciliation через REST
2. **InFlightConfig** - конфігурація TTL в SSOT (domains.yaml)
3. Reconciliation: check openOrders/orderStatus → clear if terminal/not-found

### Contract
```
1. In-flight orders мають TTL (default 60s, configurable)
2. На TTL expiry → reconcile via REST openOrders/orderStatus
3. Якщо terminal (FILLED/CANCELED/EXPIRED/REJECTED) або not found → clear in-flight
4. Force-clear після max_ttl_sec (default 120s)
5. Жодних вічних "order in flight" блоків
```

### Files Created
- [apps/reference/domains/inflight_reconcile/__init__.py](apps/reference/domains/inflight_reconcile/__init__.py)
- [apps/reference/domains/inflight_reconcile/config.py](apps/reference/domains/inflight_reconcile/config.py)
- [apps/reference/domains/inflight_reconcile/reconciler.py](apps/reference/domains/inflight_reconcile/reconciler.py)
- [tests/contracts/test_inflight_reconcile.py](tests/contracts/test_inflight_reconcile.py)

### SSOT Updated
- [config/aurora/domains.yaml](config/aurora/domains.yaml) - added `inflight_reconcile` section

### Key Tests
- `test_inflight_expires_and_reconciles` ✅
- `test_inflight_cleared_on_terminal_status` ✅
- `test_inflight_blocks_before_ttl` ✅

---

## Test Results

```bash
$ pytest tests/contracts/test_exchange_filters_validation.py \
         tests/contracts/test_regime_allowlist.py \
         tests/contracts/test_inflight_reconcile.py -v

============================== 65 passed in 0.10s ==============================
```

---

## Files Changed Summary

| File | Type | Description |
|------|------|-------------|
| `apps/reference/domains/exchange_filters/__init__.py` | NEW | Package init |
| `apps/reference/domains/exchange_filters/contracts.py` | NEW | Filter contracts |
| `apps/reference/domains/exchange_filters/validator.py` | NEW | Validator logic |
| `apps/reference/domains/regime_allowlist/__init__.py` | NEW | Package init |
| `apps/reference/domains/regime_allowlist/contract.py` | NEW | Allowlist contract |
| `apps/reference/domains/inflight_reconcile/__init__.py` | NEW | Package init |
| `apps/reference/domains/inflight_reconcile/config.py` | NEW | Config model |
| `apps/reference/domains/inflight_reconcile/reconciler.py` | NEW | Reconciler logic |
| `config/aurora/domains.yaml` | MODIFIED | Added inflight_reconcile section |
| `tests/contracts/test_exchange_filters_validation.py` | NEW | 18 tests |
| `tests/contracts/test_regime_allowlist.py` | NEW | 23 tests |
| `tests/contracts/test_inflight_reconcile.py` | NEW | 24 tests |

---

## Integration Notes

### 51-A Integration (Exchange Filters)
```python
# In startup/warmup:
from apps.reference.domains.exchange_filters import validate_instruments_on_startup

await validate_instruments_on_startup(
    adapter=binance_adapter,
    instruments_config=yaml.safe_load(open("config/aurora/instruments.yaml")),
    mode="live",  # or "testnet", "shadow"
    warn_only=False,  # True for DEV/SHADOW
)
```

### 51-B Integration (Regime Allowlist)
```python
# In config validation:
from apps.reference.domains.regime_allowlist import validate_strategy_regime_config

validate_strategy_regime_config(
    strategies_yaml=yaml.safe_load(open("config/aurora/strategies.yaml")),
    aurora_instruments_yaml=yaml.safe_load(open("config/aurora/aurora_instruments.yaml")),
    mode="live",
    warn_only=False,
)
```

### 51-C Integration (In-Flight Reconcile)
```python
# In main.py / FSM:
from apps.reference.domains.inflight_reconcile import InFlightReconciler, InFlightConfig

config = InFlightConfig.from_ssot(domains_config)
reconciler = InFlightReconciler(config=config, exchange_checker=adapter)

# Register on order submit
reconciler.register(rid=rid, symbol=symbol, client_order_id=coid)

# Periodic reconciliation (every 10s)
await reconciler.reconcile_all_expired()

# Check before new order
if reconciler.has_in_flight(symbol):
    return DEFER("order in flight")
```

---

## Remaining Work (Not in Scope)

1. **Wire 51-A into startup** - Call validator in main.py warmup
2. **Wire 51-B into startup** - Call validator in config loading
3. **Wire 51-C into FSM** - Replace OrderIndex.has_in_flight_entry with reconciler
4. **Add periodic reconcile task** - Background task every 10s

---

## Conclusion

TASK51 реалізовано повністю:
- ✅ 51-A: Exchange Filters fail-closed validation
- ✅ 51-B: Regime Allowlist explainable contract
- ✅ 51-C: In-Flight TTL + REST reconciliation

Всі 65 тестів проходять. Код additive-only, fail-closed, TDD.
