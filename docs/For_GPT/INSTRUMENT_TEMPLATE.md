# INSTRUMENT_TEMPLATE.md
Уніфікований шаблон інструменту (крипто-активу) у системі Aurora.

```yaml
instrument:
  symbol: BTCUSDT            # торгова пара
  exchange: binance          # біржовий ринок
  base_asset: BTC
  quote_asset: USDT
  leverage: 10               # плечо за замовчуванням
  min_notional: 10.0         # мінімальний обсяг в квоті
  quantity_precision: 3      # точність кількості
  price_precision: 2         # точність ціни
  min_qty: 0.001             # мінімальний обсяг позиції
  min_price: 0.01            # мінімальний рівень ціни
  step_size: 0.001           # мінімальний крок кількості
  tick_size: 0.01            # крок ціни
  max_position_size: 5.0     # максимальна експозиція
  max_leverage: 20           # максимальне плече
  contract_type: PERPETUAL    # тип контракту
  regime_multipliers:
    normal: 1.0
    volatile: 0.8
    crisis: 0.5
  risk:
    max_drawdown_pct: 2.5
    risk_fraction: 0.1
  tp_sl:
    default_tp_bps: 50
    default_sl_bps: 25
  tp_sl_overrides:
    min_sl_bps: 20
    min_tp_bps: 30
  funding_rate_sensitivity: 0.5
  notes: |
    Приклад загального опису умов інструменту.
    Текст може містити уточнення по лімітах або ризиковим заборонам.
```

Кожен параметр задає поведінку бортиха на конкретному активі: `symbol`/`exchange` визначають маршрут, `leverage` та `max_position_size` лімітують експозицію, `step_size`/`tick_size` приводять ордери до біржових вимог.  
Розділ `regime_multipliers` адаптує розмір позицій під різні стани волатильності, `risk` тримає гіперпараметри обмежень збитків і фракції капіталу, а `tp_sl` задає типові відступи тейк-профіту і стоп-лоссу.
