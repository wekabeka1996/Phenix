# 📄 Semantic Configuration Passport: `config/aurora/trading.yaml` (Part 2: Execution & AI Integration)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/trading_passport_gemini_v2.md
> - Scope: Lines 101-189 of `config/aurora/trading.yaml`
> - Purpose: Capability mapping for execution limits, guardians, and LLM orchestration bounds.

Цей паспорт описує механізми захисту капіталу на рівні біржі (Execution Position) та архітектурні межі втручання зовнішнього ШІ (LLM Orchestration).

---

## 7. Execution Domain (Continued)

### `execution.manage.orphan_monitor`
- **Capability:** Асинхронний збирач сміття (Garbage Collector). Знаходить і скасовує ордери на біржі, які не відстежуються системою.
- **Sensitivity:** `batch_cancel_limit` та `rate_limit_per_min` захищають від банів по API (Rate Limiting) при масовому скасуванні.

### `execution.manage.emergency`
- **Capability:** Аварійний вихід з ринку (`emergency_sl_bps`). Якщо ціна раптово пробиває цей поріг, система ініціює `MARKET` закриття позиції та блокує торгівлю на кількість барів `wait_mode_bars`.

### `execution.cooldown_after_close_ms` / `anti_race_close_ms`
- **Capability:** 
  - `cooldown_after_close`: Захист від "пінг-понгу" (перевідкриття тієї ж позиції одразу після закриття).
  - `anti_race_close_ms`: Технічний інваріант, що запобігає спробам змінити TP/SL (Manage) для позиції, на яку вже відправлено наказ закриття.

### `execution.exposure`
Абсолютні ліміти ризику та капіталу на рівні піддомену екзекуції.
- **`max_equity_utilization_pct` / `max_portfolio_fraction`:** `float`. Скільки % від загального балансу дозволено використовувати під маржу.
- **`max_directional_ratio`:** `float`. Контроль дельти (напр. макс. різниця між об'ємом лонгів і шортів).
- **`count_pending_orders` / `exclude_reduce_only`:** Визначає, чи рахувати ще не виконані лімітки як активний ризик (Консервативний режим `true`).
- **`leverage_defaults`:** Дефолтні плечі по активах (напр. 20х для BTC).

### `execution.order_params`
- **Capability:** Дефолтні параметри біржових наказів (наприклад, `timeInForce: GTC`, `workingType: MARK_PRICE` для стопів). Захист від випадкових ринкових проковзувань при стопах (Stop loss спрацьовує по Mark Price, а не Last Price).

### `execution.watchdog`
Запобіжники втрати пакетів.
- **`ack_ttl_ms` / `fill_ttl_ms`:** Якщо біржа не підтвердила отримання ордера (ACK) за 8 секунд, або ордер висить без виконання (Fill) занадто довго, Watchdog ініціює протокол скасування/відновлення.

### `execution.preflight_backoff_ms`
- **Capability:** Список затримок. Експоненційний бекофф для перевірки статусу позиції перед встановленням TP/SL (оскільки після MARKET-ордера WebSocket біржі може затримувати підтвердження балансу).

### `execution.order_guardian`
- **Capability:** Вмикає persistent ledger (`unified: true`, `ledger_db_path: data/order_ledger.db`). Гарантує ідемпотентність і дозволяє боту пережити краш процесу без втрати стану відкритих ордерів.

---

## 8. Domain Configuration Mappings (`domain_configuration` / `risk_management`)
- **Capability:** Роутинг середовищ. Чітко вказує кожному домену, звідки брати дані. 
- **Sensitivity:** Критично для режиму `hybrid`. Data-домени (`market_data`, `feature_engineering`, `decision_making`) примусово читають `live` потоки, тоді як `risk_management` рахує свій портфель за `testnet` станом.

---

## 9. LLM Orchestration (`llm_orchestration`)

Архітектурний міст між зовнішніми LLM (як Neocortex) та ядром системи. Встановлює **Bounded Control** (жорсткі межі влади ШІ).

### `mode` / `llm_role`
- **Capability:** Визначає ступінь автономії (`hybrid_advisory` або `advisory`). У поточному стані LLM лише "рекомендує" дії, але не може обійти базовий FSM (якщо FSM проти, інтент від ШІ не пройде).

### `allowlist_symbols` / `symbols_llm`
- **Capability:** Пісочниця для ШІ (AI Sandbox). ШІ має право оперувати виключно на дозволених тикерах (наприклад, `1000PEPEUSDT`). 
- **Причинність:** Захищає основні ліквідні інструменти (BTC/ETH) від фінансових збитків у випадку "галюцинацій" мовної моделі.

### `intent_policy` (Хард-ліміти ШІ)
Найважливіший захисний контур від непередбачуваності генеративних моделей.
- **`max_open_intents` / `cooldown_sec`:** Ліміт спаму. ШІ не може відкрити більше 3 інтентів одночасно і має чекати 30 секунд між ними.
- **`allow_limit_only: true`:** ШІ **заборонено** бити по ринку (MARKET ордери). Він може виставляти лише пасивні лімітки.
- **`require_tp_sl: true`:** ШІ зобов'язаний супроводжувати кожен намір на вхід захисними стопами. Голі ордери відхиляються на рівні парсера.
- **`max_notional_usd` / `max_qty`:** Обмежує максимальну вартість одного трейду від ШІ (напр. 100 USD), капсулюючи фінансовий ризик помилки.
- **`max_price_deviation_bps`:** Захист від "Товстого Пальця" (Fat Finger). Якщо ШІ намагається поставити ордер на 20% нижче поточної ціни (через галюцинацію цифр), система скасує цей намір.
