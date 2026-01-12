# AURORA 5M BARS AUDIT REPORT

## 1. Verdict: YES

**5-хвилинні бари (300s) реально будуються, існують у пайплайні та використовуються стратегією Aurora.**

Це не "фантом" і не просто rolling window. Існує окремий механізм побудови OHLC-барів, події закриття барів, і обробка цих подій у Feature Engineering.

---

## 2. Evidence (Докази)

### A. Побудова (Builder)
* **File:** `apps/reference/domains/market_data/bar_aggregator.py`
* **Mechanism:** Клас `BarAggregator` агрегує тіки (`EVT:MARKET_TICK_RECEIVED`) у бари.
* **Configs:** Дефолтні таймфрейми прописані прямо в коді: `timeframes_sec=[180, 300]` (3m і 5m). Також вони можуть бути перевизначені в `system.yaml`.
* **Event:** Емітить `EVT:BAR_CLOSED` з повним об'єктом Bar (OHLCV).

### B. Споживання (Consumer)
* **File:** `apps/reference/domains/feature_engineering/feature_engineering.py`
* **Listener:** `self.fsm.listen("EVT:BAR_CLOSED", self.on_bar_closed)` (рядок 150).
* **Logic:** Метод `on_bar_closed` (рядок 457) отримує бар, створює "синтетичний тік" на момент закриття бару (bar.close, bar.end_ts) і запускає розрахунок фіч.
* **Output:** Емітить `EVT:FEATURES_CALCULATED` з полем `"tf_sec": 300`.

### C. Використання (Usage)
* **File:** `apps/reference/domains/decision_making/aurora_handler.py`
* **Guard:** `if tf_sec and tf_sec != self.timeframe_sec: return` (рядок 639).
* **Validation:** Оскільки `config/aurora/strategies/aurora.yaml` встановлює `timeframe_sec: 300`, AuroraHandler **ПРИЙМАЄ** події з `tf_sec: 300`.
* **Nuance:** AuroraHandler також приймає тікові фічі (де `tf_sec` відсутнє/None), оскільки умова `if tf_sec` стає False. Тобто стратегія працює в "гібридному" режимі: тіки + 5m snapshots.

---

## 3. Distinction: Rolling vs Bar

Важливо розрізняти два типи "5m даних" у системі:

1.  **5m Bar Features (Snapshot)**:
    *   **Source:** `BarAggregator` -> `EVT:BAR_CLOSED` -> `FeatureEngineering`
    *   **Timing:** Приходять *раз на 5 хвилин*.
    *   **Identification:** Мають поле `tf_sec: 300` у логах/івентах.
    *   **Data:** Це знімок стану фіч (OBI, TFI, etc.) саме на момент закриття 5м свічки.

2.  **5m Rolling Window Features (Continuous)**:
    *   **Source:** `compute_price_motion_block` (in `price_motion.py`)
    *   **Timing:** Рахуються *кожен тік*.
    *   **Identification:** Поля `pm_norm_300s`, `ret_300s`, `vol_pct_300s`.
    *   **Data:** Це ковзне вікно (останні 300с від поточного моменту), а не фіксована свічка.

**Aurora використовує обидва типи**, але вони приходять у різних подіях.

---

## 4. Impact (Вплив на торгівлю)

1.  **Частота прийняття рішень:**
    *   Aurora приймає рішення **на кожному тіку** (через тікові фічі).
    *   Додатково, раз на 5 хв, приходить "баровий" івент, який теж тригерить `AuroraScoringKernel`.

2.  **Логування:**
    *   Усі фічі пишуться в `logs/features/{symbol}.log`.
    *   Ви побачите там записи без `tf_sec` (тікові) і записи з `"tf_sec": 300` (барові).
    *   Окремого файлу `bars.tsv` немає, але дані є в JSON-lines потоці.

---

## 5. Gaps (Прогалини)

*   Відсутнє (або не знайдене) явне використання OHLC (High/Low) всередині `FeatureEngineering`. Хоча `BarAggregator` передає OHLC, `FeatureEngineering` використовує звідти переважно close price та time для розрахунку своїх метрик. Чисті патерни свічкового аналізу (напр. "hammer" чи "doji") на даний момент не реалізовані, хоча інфраструктура для них (BarAggregator) є.
*   Змішування тікових і барових сигналів в Aurora може призводити до "шуму", якщо логіка ядра не розрізняє їх контекст (хоча ядро stateless і йому байдуже).

---
