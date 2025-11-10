# 🚨 КРИТИЧНИЙ БУГ: TP/SL Infinite Loop при автоматичному закритті позиції

## Проблема

Коли система АВТОМАТИЧНО закриває позицію через TP/SL (TAKE_PROFIT_MARKET або STOP_MARKET заповняється):

1. API Binance ВИДАЄ `FILL` евент на TP/SL ордер → позиція закривається
2. Система отримує цей `FILL` як `msg.verb="FILL"`
3. **ManageFlowFSM.process()** ІНТЕРПРЕТУЄ цей FILL як НОВИЙ ENTRY FILL:
   ```python
   if self.state == ManageState.FLAT and msg.verb in ("PARTIAL_FILL", "FILL", "TRADE_EXECUTED"):
       self._on_fill(msg)
       self.state = ManageState.BRACKETS_PENDING
       return self._place_brackets(msg)  # ← СТВОРЮЄ НОВІ TP/SL!
   ```
4. **НОВІ TP/SL ОРДЕРИ СТВОРЮЮТЬСЯ** на закритій позиції!
5. Ці нові TP/SL залишаються orphaned, оскільки позиція вже закрита
6. **Цикл повторюється**, створюючи все більше і більше orphaned TP/SL ордерів

## Symptom

Логи показують:
- `✅ TP placed: {...}` (TP/SL ордер вкладений)
- Позиція закривається (автоматично через TP/SL)
- **ПОМИЛКА**: Negatives! Система відносить FILL від TP/SL як новий entry
- `✅ TP placed: {...}` (НОВІ TP/SL на закритій позиції!)
- Orphaned TP/SL накопичуються в ордерах

## Root Cause

Система НЕ розрізняє:
1. **Entry order FILL** → `side=BUY/SELL`, type=`MARKET/LIMIT` → позиція відкривається
2. **Exit order FILL** → `side=SELL/BUY`, type=`TAKE_PROFIT_MARKET/STOP_MARKET` → позиція закривається

При FILL від exit ордеру система трактує його як новий entry!

## Solution

**Відрізняти ENTRY від EXIT в process():**

```python
# Перевіріти тип ордеру що заповнився
if msg.verb in ("PARTIAL_FILL", "FILL", "TRADE_EXECUTED"):
    order_type = msg.pld.get("order_type") or msg.pld.get("type", "")

    # EXIT ордери: TAKE_PROFIT_MARKET, STOP_MARKET, LIMIT (closePosition=true)
    is_exit_order = order_type in ["TAKE_PROFIT_MARKET", "STOP_MARKET"] or \
                    (order_type == "LIMIT" and msg.pld.get("closePosition") == "true")

    if is_exit_order:
        # Позиція ЗАКРИЛАСЯ - переходимо у FLAT
        self.position_qty = None
        self.state = ManageState.FLAT
        self.sl_price = None
        self.tp_price = None
        return None  # Не створюємо нові TP/SL!
    elif self.state == ManageState.FLAT:
        # ENTRY ордер - позиція відкривається
        self._on_fill(msg)
        self.state = ManageState.BRACKETS_PENDING
        return self._place_brackets(msg)
```

## Impact

- **Severity**: 🔴 CRITICAL
- **Frequency**: 100% (щоразу коли позиція закривається автоматично)
- **Result**: Infinite accumulation of orphaned TP/SL orders → eventually blocks new orders

## Testing

1. Запустити систему
2. Дозволити позиціям відкритися
3. Дозволити TP/SL автоматично закрити позицію
4. **EXPECTED**: Позиція закривається, TP/SL видаляються, нові TP/SL НЕ створюються
5. **ACTUAL (BUG)**: НОВІ TP/SL створюються на закритій позиції, висять як сироти
