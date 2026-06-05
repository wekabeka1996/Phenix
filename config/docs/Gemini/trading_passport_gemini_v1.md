# 📄 Semantic Configuration Passport: `config/aurora/trading.yaml` (Part 1: Core Trade Logic)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/trading_passport_gemini_v1.md
> - Scope: Lines 1-100 of `config/aurora/trading.yaml`
> - Purpose: Capability mapping for trading modes, TCA preferences, risk budgets, and market data syncing.

Цей паспорт описує **можливості** та **межі впливу (Sensitivity)** конфігурацій торгового ядра, ризик-бюджетів та збору даних. Значення вказані як діапазони або типи.

---

## 1. Binance API Connections (`binance_api`)
- **Capability:** Визначає точки входу (`rest_url`) та облікові дані (credentials) для двох окремих ізольованих середовищ: `live` (Production) та `testnet`. Ключі завантажуються виключно через змінні оточення (Environment Variables) для безпеки.

## 2. Trading Mode (`trading.mode`)
- **Capability:** Глобальний перемикач режимів роботи бота (напр. `live`, `testnet`, `hybrid_live_data_testnet_exec`).
- **Sensitivity:** У режимі `hybrid` система використовує реальні стакани (Order Books) з `live` API для генерації фічів, але відправляє ордери виключно на `testnet`. Це критичний механізм для тестування нових ШІ-політик без ризику для реального капіталу (Zero Blast Radius).

## 3. TCA Preferences (Transaction Cost Analysis)
Керує допусками на якість виконання ордерів:
- **`max_slippage_bps` / `max_slippage_pct`:** 
  - *Capability:* Максимально допустиме проковзування (Slippage) ціни. Якщо біржа не може виконати ордер у цих межах — система Fail-Closed.
- **`max_latency_ms`:** Максимальний час між зародженням наміру (`Intent`) та підтвердженням від біржі (`Fill`). Використовується для моніторингу затримок.
- **`maker_preference` / `execution_priority`:** `enum`. Стратегія формування лімітних ордерів: чи боротися за спред (Maker), чи бити по ринку заради гарантії входу (Taker/Speed).

## 4. Risk Budgets (`trading.risk_budgets`)
Захищає капітал від "Товстих Хвостів" (Fat Tails) розподілу прибутковості.
- **`trade_cvar95_max_bps` / `session_cvar95_max_bps`:** Обмеження за моделлю Conditional Value at Risk (CVaR).
- **`max_portfolio_risk_pct` / `max_single_position_risk_pct`:** `float` (%).
  - *Capability:* Глобальні хард-ліміти на розмір маржі, вкладеної в ринок.
  - *Sensitivity:* 🔽 Перетиснені бюджети блокуватимуть нові входи навіть при чудових ринкових умовах. 🔼 Розширення бюджетів підвищує ймовірність каскадних маржин-колів (Cascade Liquidations) при флеш-крешах.

## 5. Active Risk Management (`trading.risk`)
Динамічний контроль агресії на основі мікроструктури.
- **`max_daily_drawdown_limit` / `daily`:**
  - *Capability:* Система Daily Stop-Loss. Якщо поточний або нереалізований збиток (Drawdown) за добу (від `reset_time_utc`) перевищує поріг, бот зупиняє торгівлю.
- **`score_weights`:** Ваги для підрахунку загального `Risk Score` (на базі `delta_price`, `obi`, `tfi`, `absorption_inverse`).
- **`trading_allowed_thresholds.max_risk_score`:**
  - *Capability:* Абсолютний ліміт ризику. Якщо ринковий `Risk Score` (від 0.0 до 1.0) перевищує цей поріг, нові трейди жорстко блокуються (але закриття існуючих позицій дозволяється).
- **`soft_limits`:** `clip_min_notional_usdt`, `directional_ratio_max`. Управління балансуванням портфелю. Якщо у нас перекіс у `LONG` позиції по всьому ринку, система буде автоматично "кліпати" (урізати розмір) нові лонги і сприяти відкриттю шортів.
- **`regime_adaptation`:** Динамічно зсуває пороги входу залежно від виявленого ринкового тренду (`trend_up`, `trend_down`, `flat`).

## 6. Market Data (`trading.market_data`)
Налаштування прослуховування біржі.
- **`poll_interval_sec`:** Частота фонового опитування (для REST fallback).
- **`websocket_streams`:** `list[string]`. Рівні підписки (напр. `bookTicker` - кращі ціни, `trade` - потік агресивних угод).
- **`use_multiprocessing`:** `bool`.
  - *Capability:* Якщо увімкнено, Data Ingestion виноситься в окремий процес ОС. Це звільняє Event Loop для `decision_making`, мінімізуючи latency.
- **`macro_sync`:** (Синхронізація з еталонами).
  - *Capability:* Корелює поточний актив з основними "якорями" (`anchors`, зазвичай BTC/ETH) в межах вікна (`window`).
  - *Sensitivity:* `time_diff_threshold_ms` відхиляє макро-кореляцію, якщо затримка (lag) даних між активами занадто велика.
- **`bar_aggregator.timeframes_sec`:** Перелік таймфреймів для "прожарки" класичних свічкових індикаторів у пам'яті бота.

## 7. Execution Domain (Start) & Ops
- **`ops.panic_killswitch`:** `bool`. Головна "червона кнопка". Переведення в `true` миттєво паралізує можливість відкривати нові угоди.
- **`execution.manage.brackets`:** Автоматичне накладання Stop-Loss (`sl`) та Take-Profit (`tp`) з використанням віртуального OCO (One Cancels the Other) для чистоти виконання.