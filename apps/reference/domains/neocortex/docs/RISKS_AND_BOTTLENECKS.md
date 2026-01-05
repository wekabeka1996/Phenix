# Neocortex — вузькі місця, ризики, “де зламається першим”

Цей документ — checklist проблемних місць, які треба закласти в дизайн/тести **до** написання коду.

---

## 1) Дані (WAL / stream)

### 1.1. Дрейф схеми WAL

Симптоми:
- `ts` vs `timestamp`, `rid` у root vs `pld.rid`, різні назви `symbol/instrument`.

Ризик:
- неправильна кореляція епізодів, “пропажа” подій, хибні алерти.

Мітігація:
- Normalizer з явним YAML mapping + unit tests на фікстурі з різними варіантами.

### 1.2. Одиниці часу (seconds/ms)

Ризик:
- інваріанти TTL почнуть спрацьовувати неправильно, “вічні” intents або “миттєві” timeouts.

Мітігація:
- `ingest.yaml.time.assume_unit_for_fields` + тест на кожен варіант.

### 1.3. Частково дописані WAL файли

Ризик:
- злам JSON парсингу, дублікати, offset drift.

Мітігація:
- ingest читає тільки повні рядки (до `\n`) і тримає byte‑offset.

### 1.4. Обʼєм WAL (performance)

Ризик:
- повільний replay, великі витрати RAM/IO.

Мітігація:
- інкрементальний ingest + індекси в store (rid/symbol/ts).
- денні “rollups” для report.

---

## 2) ML/математика (R1+)

### 2.1. Selection bias (якщо вчитись лише на WAL)

Ризик:
- world model/viability будуть “сліпі” в idle‑періодах.

Мітігація:
- state stream (`features_tape.jsonl`) як SSOT для R1.

### 2.2. Детермінізм і відтворюваність

Ризик:
- router/планер дає різні рішення на тому ж replay → неможливо дебажити.

Мітігація:
- `rng_seed` у YAML + bucketed time для idempotent_key.
- unit tests “same input → same output”.

### 2.3. Числова стабільність

Ризик:
- NLL/EMA/нормалізації вибухають, NaN у метриках.

Мітігація:
- clamp rules в YAML + NaN guards → `NEOCORTEX_ALERT` + safe skip.

---

## 3) Інтеграція (in-proc / R3)

### 3.1. Випадковий вплив на торгівлю (regression)

Ризик:
- Neocortex почне емити intent/команди до готовності.

Мітігація:
- жорстка фаза `phase=R0|R1|R2` у YAML, яка забороняє будь‑який actuation код‑путь.
- contract tests: “no CMD:* emitted in R0–R2”.

### 3.2. Спам інтенцій

Ризик:
- bridge/EP отримують шквал сигналів.

Мітігація:
- idempotent_key + rate limits + churn limiter (все в YAML).

---

## 4) Операційні ризики

- Логи ростуть без контролю → retention policy у YAML.
- Немає “версій” моделей/конфігів → додати hash у `NEOCORTEX_STATE_UPDATED`.

