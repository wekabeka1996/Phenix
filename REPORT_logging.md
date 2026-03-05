# VFOUNDATION OBSERVABILITY: LOGGING SINKS & GAPS

Цей звіт є результатом аудиту логування (sinks), де система зберігає метрики та фічі у реальному часі та під час виконання Alpha Search.

## 1. Таблиця Sinks (Де реально пишуться дані)

| Sink Name | Формат | Шлях (Path) | Ротація / Обмеження | Джерело (Code Writer) | Умови активації | Per-symbol? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Global WAL** | JSONL | `ops/wal/YYYY-MM-DD.jsonl` | Щоденна (через ім'я файлу) | `vfoundation/dr/wal.py:append()` | Події з `record_wal=True` | Ні |
| **Features Log** | JSONL | `logs/features/{symbol}.log` | **ВІДСУТНЯ** (Unbounded) | `feature_engineering.py:204` | Завжди (на кожен tick/bar) | **Так** |
| **Order Log** | JSONL | `logs/order_log_v1.jsonl` | **ВІДСУТНЯ** (Unbounded) | `order_logger.py:104` | Події ордерів (FSM Exec) | Ні |
| **Shadow Intents**| JSONL | `data/shadow_intents.jsonl` | **ВІДСУТНЯ** (Unbounded) | `neocortex/transport/adapter.py:714`| При увімкненому Neocortex | Ні |
| **Aurora Core** | TXT/JSON| `logs/aurora_core.log` | `RotatingFileHandler` | `logging_setup.py:153` | Завжди (через `observability.yaml`)| Ні |
| **Aurora Events** | TXT/JSON| `logs/aurora_events.log` | `RotatingFileHandler` | `logging_setup.py:212` | Завжди (через `observability.yaml`)| Ні |
| **Domain Logs** | TXT/JSON| `logs/domain_{name}.log` | `RotatingFileHandler` | `logging_setup.py:189` | Завжди (через `observability.yaml`)| Ні |
| **Alpha Health** | JSONL | `{session}/aggregate/health.jsonl`| Обмежено сесією бектесту | `alpha_search/.../reporting.py:70` | Alpha Search Run | Ні |
| **Alpha Summary** | JSONL | `{session}/aggregate/summary.jsonl`| Обмежено сесією бектесту | `alpha_search/.../reporting.py:79` | Alpha Search Run | Ні |
| **Alpha Metrics** | CSV | `{session}/.../aggregate_metrics.csv`| Обмежено сесією бектесту | `alpha_search/.../reporting.py:62` | Alpha Search Run | Ні |

---

## 2. Аналіз: Чи існує "features_engine.log" та чи він повний?

**Ні, єдиного файлу не існує.** Замість цього `FeatureEngineering` створює пер-символьні файли (`logs/features/BTCUSDT.log`, `logs/features/SOLUSDT.log` тощо). 

**Чи містить він повний payload? НІ.**
У `FeatureEngineering._log_features_to_file` пишеться виключно словник `features` (`json.dumps(features)`). 
Це критичний пропуск, оскільки там **ВІДСУТНІ**:
- `ts` (Час обчислення / час тіку)
- `tf_sec` (Таймфрейм — чи це tick, чи це закриття 3m/5m бару)
- `warmup` (Статус готовності індикаторів)
- `price_motion` та `bar` (Сам ціновий контекст)
Без цих полів відновити точний стан ринку або відрізнити "шум" від реального закриття свічки в Alpha Search/Neocortex вкрай важко.

---

## 3. Виявлені "Пропуски" (Gaps) та Ризики

1. **Memory / Disk Leak (Unbounded Growth):**
   * Файли `logs/features/{symbol}.log`, `logs/order_log_v1.jsonl` та `data/shadow_intents.jsonl` відкриваються через класичний `open(..., "a")` без будь-якої ротації (RotatingFileHandler або Timed). 
   * Оскільки FeatureEngineering пише `features` на **кожен ринковий тік** (через `on_market_tick` з `tf_sec=0`), файл розростається експоненційно швидко, що неминуче призведе до переповнення диска (Disk Exhaustion) на довгих лайв-ранах.
2. **I/O Bottleneck у критичному шляху:**
   * Відкриття та запис файлу (`open("...", "a")`) відбувається синхронно всередині пайплайну обробки тіків (`_calculate_and_emit_features_for_tf`). Це створює затримки на рівні мікросекунд для кожного тіку.
3. **Втрата контексту (Context Gap):**
   * Подія `EVT:FEATURES_CALCULATED` містить багатий payload, але FSM не пише цю подію у WAL (бо це високонавантажена подія). Через це єдиним джерелом стану залишається обрізаний `{symbol}.log`, який не містить `ts_ms` та `tf_sec`.

---

## 4. Рекомендації (Де підчепитись / Що має робити Shadow Domain)

Для Shadow-домену (Neocortex) необхідно повністю перебрати на себе відповідальність за логування фічей, щоб розвантажити `FeatureEngineering`:

1. **Де підчепитись:**
   * Neocortex (через `transport/adapter.py`) має слухати подію `EVT:FEATURES_CALCULATED`.
   * Саме він має агрегувати ці події та батчами (асинхронно) писати їх у **єдиний** `data/features_engine.parquet` або JSONL-файл з правильною ротацією (наприклад, по годинах або днях).
2. **Що замінити:**
   * Функцію `_log_features_to_file` у `apps/reference/domains/feature_engineering/feature_engineering.py` потрібно **ВИДАЛИТИ**.
   * Це усуне I/O bottleneck та небезпеку переповнення диска.
3. **Що має зберігати Neocortex:**
   * Весь payload: `{"ts": ..., "symbol": ..., "tf_sec": ..., "features": {...}, "warmup": {...}}`. Це дозволить ідеально синхронізувати стан ринку з `TRADE_INTENT` під час навчання.
4. **OrderLoggerV1:**
   * Необхідно перевести з `open("...", "a")` на `SafeRotatingFileHandler` або інтегрувати його запис напряму в WAL/Neocortex.