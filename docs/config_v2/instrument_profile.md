# Instrument Profile Specification (Config v2)

> Уніфікований опис інструменту (монети) для всіх доменів у config v2.

## 1. Призначення

Instrument profile — це уніфікований опис одного інструменту (symbol) для всіх доменів системи. Він замінює розмазане визначення `trading.instruments.*` у старому `trading.yaml`, забезпечуючи єдине джерело правди для технічних характеристик, лімітів, ризиків та поведінки кожного активу.

Профіль включає:
- Технічні параметри (precision, limits) для виконання ордерів.
- Ризик-параметри (leverage, drawdown) для управління експозицією.
- Адаптації під режими (regime_multipliers) для динамічної поведінки.
- TP/SL defaults для автоматичного управління позиціями.

## 1.1. InstrumentProfile dataclass

Реалізовано як `apps.reference.config_models.InstrumentProfile` — frozen dataclass з усіма необхідними полями.

## 1.2. Resolver `resolve_instrument_profile`

Функція `apps.reference.config_symbols.resolve_instrument_profile(cfg: AuroraConfig, symbol: str) -> InstrumentProfile` є канонічним шляхом отримання профілю інструменту. Підтримує config v2 (`instruments.yaml` + `overrides.yaml`) з fallback на legacy `trading.instruments.*`.

## 2. YAML-шаблон

Приклад структури в `instruments.yaml`:

```yaml
instruments:
  BTCUSDT:
    exchange: binance
    base_asset: BTC
    quote_asset: USDT
    precision:
      quantity: 3
      price: 2
    limits:
      min_notional: 10.0
      min_qty: 0.001
      min_price: 0.01
      max_position_size: 5.0
      max_leverage: 20
    tp_sl:
      default_tp_bps: 50
      default_sl_bps: 25
      overrides:
        min_sl_bps: 20
        min_tp_bps: 30
    regime_multipliers:
      normal: 1.0
      volatile: 0.8
      crisis: 0.5
    risk:
      max_drawdown_pct: 2.5
      risk_fraction: 0.1
    notes: |
      Основний BTC/USDT perpetual contract на Binance.
      Використовується як базовий актив для тестування.

  ETHUSDT:
    exchange: binance
    base_asset: ETH
    quote_asset: USDT
    precision:
      quantity: 2
      price: 2
    limits:
      min_notional: 5.0
      min_qty: 0.01
      min_price: 0.01
      max_position_size: 10.0
      max_leverage: 25
    tp_sl:
      default_tp_bps: 40
      default_sl_bps: 20
      overrides:
        min_sl_bps: 15
        min_tp_bps: 25
    regime_multipliers:
      normal: 1.0
      volatile: 0.7
      crisis: 0.4
    risk:
      max_drawdown_pct: 3.0
      risk_fraction: 0.15
    notes: |
      Ethereum perpetual contract.
      Вищий leverage через більшу ліквідність.
```

### Логічні блоки полів

- **precision**: Точність для quantity (кількість) та price (ціна) — використовується для округлення ордерів.
- **limits**: Біржові обмеження — min_notional, min_qty, max_position_size тощо — для валідації ордерів.
- **tp_sl**: Типові відступи для take-profit та stop-loss у базисних пунктах, з overrides для мінімальних значень.
- **regime_multipliers**: Множники для адаптації розміру позицій під режими волатильності (normal, volatile, crisis).
- **risk**: Ризик-параметри — max_drawdown_pct для лімітів збитків, risk_fraction для фракції капіталу.

## 3. Правила overrides

Overrides дозволяють кастомізувати профіль на рівні symbol або профілю, без зміни базового instruments.yaml.

### Структура overrides.yaml

```yaml
overrides:
  symbols:
    BTCUSDT:
      limits:
        max_position_size: 3.0  # override для BTC
      risk:
        risk_fraction: 0.05     # нижчий ризик для BTC
  regimes:
    volatile:
      BTCUSDT:
        regime_multipliers:
          volatile: 0.6  # додатковий override для BTC у volatile режимі
```

#### 3.1. Nested `limits.*` overrides (TASK 7.6)

- Поля `max_leverage`, `max_position_size`, `min_notional`, `min_qty`, `min_price` **завжди** описуються під `limits.*` у базовому профілі та в overrides.
- Приклад override після TASK 7.6:

```yaml
overrides:
  symbols:
    SOLUSDT:
      limits:
        max_leverage: 125
        max_position_size: 15.0
        min_notional: 5.0
      tp_sl:
        default_tp_bps: 80
```

- Валідатор (`tools/config_validator_v2.py`) блокує "мертві" топ-рівневі поля виду `symbols.SOLUSDT.max_leverage`.
- `resolve_instrument_profile` застосовує порядок merge: **template defaults → instruments.yaml → overrides.yaml.symbols → regime/profile overrides** і повертає `InstrumentProfile.source="config_v2"` при успіху.

### Порядок пріоритетів у resolve_instrument_profile(symbol)

Resolver `resolve_instrument_profile(symbol)` збирає фінальний профіль з наступних джерел (від низького до високого пріоритету):

1. **Default template**: базові значення, якщо поле відсутнє в instruments.yaml (наприклад, precision=2, якщо не вказано).
2. **instruments.yaml**: основний профіль для symbol.
3. **overrides.yaml (symbols level)**: per-symbol overrides.
4. **overrides.yaml (regimes level)**: додаткові overrides для конкретного режиму (якщо активний regime_detector).

Фінальний профіль гарантує:
- **Обов'язкові поля**: exchange, base_asset, quote_asset, precision.quantity, precision.price, limits.min_notional, limits.min_qty, limits.max_leverage.
- **Інваріанти**: non-negative precision, positive limits, regime_multipliers у [0,1], risk_fraction у [0,1].

## 4. Споживачі instrument_profile

- **execution_position**: використовує precision (step_size, tick_size), limits (min_qty, max_position_size) для формування ордерів; tp_sl defaults для bracket placement.
- **decision_making**: використовує min_notional для фільтрації ідей, precision для розрахунків розміру, risk_fraction для sizing.
- **risk_management**: використовує risk.max_drawdown_pct для daily limits, risk_fraction для position sizing, regime_multipliers для адаптації.
- **regime_detector**: може використовувати regime_multipliers для динамічних коефіцієнтів (якщо інтегровано).
