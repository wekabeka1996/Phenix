# Phase R0 — Observer (WAL ingest → state → alerts → report)

Ціль R0: **пасивний спостерігач**, який не впливає на торгівлю і дає:
- відтворюваний ingest WAL,
- state store (episodes/таймлайни),
- інваріанти/алерти,
- щоденний репорт.

> На R0 ми не робимо ML. Ми робимо “правильну інженерію даних” і контракт‑аудит.

---

## 0) Артефакти R0 (що має зʼявитись на виході)

У `logs/neocortex/` (або інший path з YAML):
- `offsets.json` — інкрементальний прогрес ingest
- `normalized_events.jsonl` (optional) — нормалізований стрім
- `alerts.jsonl` — алерти інваріантів
- `reports/YYYY-MM-DD.md` — щоденний репорт
- `neocortex.sqlite` / `neocortex.duckdb` — стор

---

## 1) Кроки реалізації (покроково)

### Крок 1.1 — Конфіги R0 (SSOT)

1) Додати `config/aurora/neocortex/system.yaml` (paths/logging/phase).
2) Додати `config/aurora/neocortex/ingest.yaml` (WAL rules + time normalization).
3) Додати `config/aurora/neocortex/store.yaml` (DB backend + retention).
4) Додати `config/aurora/neocortex/safety.yaml` (інваріанти thresholds, TTLs).

DoD:
- missing key → crash (Pydantic V2).
- unresolved `${VAR}` → crash.

### Крок 1.2 — WAL Reader (інкрементальний ingest)

**Вхід:** директорія WAL, glob, offsets.  
**Вихід:** потік рядків JSONL, які ще не були оброблені.

Політика:
- обробляємо файли у стабільному порядку (lexicographic по назві, або explicit “date sort”).
- offsets зберігаються як:
```json
{
  "files": {
    "2026-01-02.jsonl": {
      "bytes": 1234567,
      "lines": 9876,
      "last_hash": "..."
    }
  }
}
```

Edge cases:
- частково дописаний файл (немає `\n` в кінці) → не читаємо останній неповний рядок.
- ротація файлів → offsets по filename, не по inode.

DoD:
- повторний запуск не дублює події.

### Крок 1.3 — Normalizer (WAL → EventEnvelope)

Мета: зробити один контракт, незалежно від форми WAL запису.

**Mapping‑таблиця (приклад):**
- `ts_ms`:
  - якщо є `ts` → беремо `ts` і трактуємо як ms (YAML rule)
  - інакше якщо є `timestamp` → трактуємо як seconds (YAML rule) і множимо на 1000
- `rid`:
  - root `rid` або `pld.rid`
- `symbol`:
  - `pld.symbol` або `pld.instrument`
- `op/verb/src/dst`:
  - root поля або дефолт‑мапінг (але дефолт дозволений тільки якщо визначений у YAML)

DoD:
- будь‑який запис, що не може бути нормалізований, фіксується як `NEOCORTEX_ALERT` з `code=INGEST_NORMALIZATION_FAILED`.

### Крок 1.4 — Episode Builder (rid → lifecycle)

Мінімальний lifecycle:
- `TRADE_INTENT_PROPOSED` → “episode created”
- `CMD:OPEN`/`ORDER_ACK`/`ORDER_FILL` → “episode executing”
- `POSITION_OPENED` → “episode open”
- `CMD:CLOSE`/`POSITION_CLOSED` → “episode closed”

DoD:
- для кожного `rid` з intent маємо відновлюваний timeline.

### Крок 1.5 — Invariants/Alerts

Всі інваріанти конфігуруються в YAML (allowlist кодів, thresholds).

Початковий набір:
- `INVARIANT_INTENT_EXPIRED_NO_EXECUTION`
- `INVARIANT_POSITION_OPENED_NO_BRACKETS`
- `INVARIANT_QTY_ZERO_CLOSE_INTENT`
- `INVARIANT_FLIP_STORM`
- `INVARIANT_PORTFOLIO_STALE_WHEN_INTENT`

DoD:
- `alerts.jsonl` має стабільний формат і не змінюється без bump версії.

### Крок 1.6 — Report Generator

Щоденний репорт (структура):
1) Summary (скільки intents, скільки episodes, PnL summary якщо є)
2) Top alerts (by severity)
3) Churn/flip statistics
4) Data quality (bad lines, missing fields, integrity checks)

DoD:
- репорт відтворюваний при replay того ж WAL.

---

## 2) Тести R0 (мінімальна мапа)

- unit: timestamp normalization, rid extraction, symbol extraction
- unit: offsets (partial line handling)
- integration: ingest `tests/domains/neocortex/fixtures/wal_small.jsonl` → очікуваний `alerts.jsonl`

---

## 3) Коли R0 можна вважати завершеним

R0 завершений, якщо:
- ingest ідемпотентний;
- репорт/алерти відтворювані;
- немає hardcoded тюнінгів у домені (все у YAML);
- Neocortex не має жодних side‑effects на трейдинг.

