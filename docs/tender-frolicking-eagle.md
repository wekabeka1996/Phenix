# Plan: Fix 4 bugs in fsm_manage.py (Binance -4015/-1111/-1102/-2021)

## Summary

4 баги у `fsm_manage.py` створюють помилки при розміщенні SL/TP бракетів через Binance API.
Основний шлях (`fsm.py`) працює коректно; помилки виникають через дублюючий шлях у `fsm_manage.py`.

---

## Files to Modify

| File | Changes |
|------|---------|
| `apps/reference/domains/execution_position/fsm_manage.py` | 4 точкових виправлення |
| `config/aurora/domains.yaml` | Збільшити tp_widen_first_bps/tp_widen_second_bps |
| `tests/execution_position/test_fsm_manage_bracket_fixes.py` | Новий тест-файл |

---

## Fix 1: -1102 (Missing stopPrice for TAKE_PROFIT_MARKET)

**File:** `fsm_manage.py:989`

```python
# BEFORE (line 989):
"stopPrice": price if "STOP" in order_type else None,

# AFTER:
"stopPrice": price if order_type not in ("LIMIT", "MARKET") else None,
```

**Причина:** `"STOP" in "TAKE_PROFIT_MARKET"` = `False`, тому stopPrice = None для TP ордерів.
Також оновити аналогічну умову на рядку 997 для closePosition:

```python
# BEFORE (line 997):
if "STOP" in order_type and order_type != "STOP_LOSS" and bool(aget(self, "closePosition", False)):

# AFTER:
if order_type not in ("LIMIT", "MARKET") and order_type != "STOP_LOSS" and bool(aget(self, "closePosition", False)):
```

---

## Fix 2: -4015 (Client Order ID > 36 chars)

**File:** `fsm_manage.py` — додати імпорт та виправити 2 місця.

### 2a. Import (line ~24, після останнього import)

```python
from apps.reference.domains.execution_position.utils import (
    generate_client_order_id,
    quantize_stop_price,
    opposite_side,
)
```

### 2b. _place_brackets() lines 715-719

```python
# BEFORE:
            # Generate unique client order IDs
            position_id = f"{msg.rid}_{int(self.position_open_ts)}"
            sl_client_id = f"{position_id}_sl"
            tp1_client_id = f"{position_id}_tp1"
            tp2_client_id = f"{position_id}_tp2"

# AFTER:
            # Generate unique client order IDs (guaranteed <=32 chars via MD5 hash)
            symbol = msg.pld.get("symbol") or self.symbol
            idem_base = f"{msg.rid}_{int(self.position_open_ts)}"
            sl_client_id = generate_client_order_id("SL", symbol, idempotent_key=idem_base)
            tp1_client_id = generate_client_order_id("TP", symbol, idempotent_key=f"{idem_base}_1")
            tp2_client_id = generate_client_order_id("TP", symbol, idempotent_key=f"{idem_base}_2")
```

### 2c. _adjust_trailing_stop() lines 1354-1356

```python
# BEFORE:
        # Place new SL (will be handled by next message)
        position_id = f"{msg.rid}_{int(self.position_open_ts)}"
        new_client_id = f"{position_id}_sl_trail_{int(get_clock().now_sec())}"

# AFTER:
        # Place new SL (will be handled by next message)
        symbol = msg.pld.get("symbol") if msg.pld else self.symbol
        idem_trail = f"{msg.rid}_{int(self.position_open_ts)}_trail_{int(get_clock().now_sec())}"
        new_client_id = generate_client_order_id("SL", symbol or "", idempotent_key=idem_trail)
```

---

## Fix 3: -1111 (Precision — side-aware rounding)

**File:** `fsm_manage.py:922-952` — переписати `_quantize_prices()` делегуючи до `quantize_stop_price()` з utils.py.

```python
# BEFORE (lines 922-952):
    def _quantize_prices(
        self,
        symbol: Optional[str],
        sl_price: Optional[Decimal],
        tp1_price: Optional[Decimal],
        tp2_price: Optional[Decimal],
    ) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """Quantize prices to tick_size from instruments SSOT (FAIL-CLOSED: no fallback)."""
        if not symbol:
            raise ValueError(
                "symbol is required for price quantization (tick_size lookup)")
        if not getattr(self.config, "instruments", None) or symbol not in self.config.instruments:
            raise ValueError(
                f"instruments.{symbol}.tick_size is required for price quantization")

        tick_size_dec = Decimal(str(self.config.instruments[symbol].tick_size))
        if tick_size_dec <= 0:
            raise ValueError(
                f"instruments.{symbol}.tick_size must be > 0, got {tick_size_dec}")

        if sl_price is not None:
            sl_price = (
                sl_price / tick_size_dec).quantize(Decimal("1")) * tick_size_dec
        if tp1_price is not None:
            tp1_price = (
                tp1_price / tick_size_dec).quantize(Decimal("1")) * tick_size_dec
        if tp2_price is not None:
            tp2_price = (
                tp2_price / tick_size_dec).quantize(Decimal("1")) * tick_size_dec

        return sl_price, tp1_price, tp2_price

# AFTER:
    def _quantize_prices(
        self,
        symbol: Optional[str],
        sl_price: Optional[Decimal],
        tp1_price: Optional[Decimal],
        tp2_price: Optional[Decimal],
    ) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """
        Quantize prices to tick_size using side-aware rounding (FAIL-CLOSED).

        Delegates to quantize_stop_price() for consistent rounding with fsm.py:
        - BUY position -> brackets are SELL -> FLOOR rounding
        - SELL position -> brackets are BUY -> CEIL rounding
        """
        if not symbol:
            raise ValueError(
                "symbol is required for price quantization (tick_size lookup)")
        if not getattr(self.config, "instruments", None) or symbol not in self.config.instruments:
            raise ValueError(
                f"instruments.{symbol}.tick_size is required for price quantization")

        tick_size = float(self.config.instruments[symbol].tick_size)
        if tick_size <= 0:
            raise ValueError(
                f"instruments.{symbol}.tick_size must be > 0, got {tick_size}")

        # Bracket orders are placed on the OPPOSITE side of the position
        bracket_side = opposite_side(self.position_side) if self.position_side else "SELL"

        if sl_price is not None:
            sl_price = Decimal(str(quantize_stop_price(
                float(sl_price), tick_size, side=bracket_side)))
        if tp1_price is not None:
            tp1_price = Decimal(str(quantize_stop_price(
                float(tp1_price), tick_size, side=bracket_side)))
        if tp2_price is not None:
            tp2_price = Decimal(str(quantize_stop_price(
                float(tp2_price), tick_size, side=bracket_side)))

        return sl_price, tp1_price, tp2_price
```

---

## Fix 4: -2021 (Config bump)

**File:** `config/aurora/domains.yaml:436-442`

```yaml
# BEFORE:
  bracket_placement:
    tp_widen_first_bps: 20
    tp_widen_second_bps: 50
    retry_backoff_ms: [200, 400]

# AFTER:
  bracket_placement:
    tp_widen_first_bps: 25
    tp_widen_second_bps: 60
    retry_backoff_ms: [200, 400]
```

---

## Tests

**New file:** `tests/execution_position/test_fsm_manage_bracket_fixes.py`

Test cases:
1. **test_stop_price_set_for_take_profit_market** — stopPrice != None для TAKE_PROFIT_MARKET
2. **test_stop_price_set_for_stop_market** — stopPrice != None для STOP_MARKET
3. **test_stop_price_none_for_market** — stopPrice == None для MARKET/LIMIT
4. **test_client_order_id_max_length** — parametrize з довгими rid, перевірка len <= 36
5. **test_trailing_stop_client_id_max_length** — аналогічно для trail IDs
6. **test_quantize_prices_buy_position_floor** — BUY position -> FLOOR rounding
7. **test_quantize_prices_sell_position_ceil** — SELL position -> CEIL rounding
8. **test_quantize_prices_missing_symbol_raises** — ValueError без символу
9. **test_client_order_id_deterministic** — same inputs -> same output

---

## Verification

1. `pytest tests/execution_position/test_fsm_manage_bracket_fixes.py -v`
2. `pytest tests/ -k "execution_position" -v` — регресія
3. `pytest -v --maxfail=5` — повний прогон
