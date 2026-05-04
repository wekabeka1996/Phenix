# Phase R2 — Shadow Advisor (shadow intents + divergence report)

Ціль R2: Neocortex генерує “тіньові” інтенти (без впливу) і порівнює їх із реальною поведінкою Aurora.

---

## 0) Вхід/вихід R2

**Вхід:**
- Observation/state (R0)
- metrics (EFE/viability/empowerment) (R1)
- WAL + реальні `EVT:TRADE_INTENT_PROPOSED` (Aurora)

**Вихід:**
- `shadow_intents.jsonl`
- divergence report (Markdown)

---

## 1) Action Space (SSOT у YAML)

R2 не робить “slerp‑містки в латенті” як ціль. Він працює у **просторі дій**, який легко перекласти в трейдинг:
- `HOLD`
- `OPEN_LONG`
- `OPEN_SHORT`
- `CLOSE`
- `REDUCE_RISK`
- `MODULATE` (тільки як пропозиція, не як дія)

---

## 2) Router/Scoring (без магії)

Всі ваги та гейти — з YAML:
- hard gates: freshness TTL, viability calibrated, max churn/hour, risk limits
- soft score: expected return proxy, risk proxy, EFE penalty, empowerment bonus

Вимога:
- selection детермінований: `rng_seed` + bucketed time.

---

## 3) Побудова ShadowIntent

ShadowIntent завжди має:
- `idempotent_key`
- `why[]` з метриками і причинами гейтів
- посилання на observation snapshot (наприклад `raw_ref` або `window_id`)

Формат: див. `apps/reference/domains/neocortex/docs/EVENTS.md` (`EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED`).

---

## 4) Divergence Report (Aurora vs Neocortex)

Для кожного `symbol` і тайм‑bucket:
- `aurora_action` (витягуємо з `EVT:TRADE_INTENT_PROPOSED`)
- `cortex_action` (shadow)
- `match/mismatch`
- “why mismatch” (коротко)

Метрики:
- mismatch rate
- “cortex would have skipped but aurora traded” rate
- churn proxy (скільки разів cortex хотів flip)

---

## 5) Коли R2 можна вважати завершеним

R2 завершений, якщо:
- shadow intents генеруються стабільно і без спаму (idempotent_key);
- divergence report відтворюваний по replay того ж WAL;
- контракти подій/логів стабільні (schema + versioning).

