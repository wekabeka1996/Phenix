# Neocortex — система конфігурації (YAML SSOT, без дефолтів)

Ціль: домен Neocortex має бути повністю керований YAML‑конфігами з **Pydantic V2** валідацією і **без** hardcoded параметрів/фолбеків у коді.

---

## 1) Принципи (hard rules)

1) **SSOT = YAML**. Будь‑який параметр, що впливає на поведінку — лише з YAML.
2) **No defaults** у коді (для поведінкових параметрів). Якщо ключ відсутній → startup crash.
3) **extra='forbid'** у всіх Pydantic моделях.
4) **No degraded mode** для критичних речей (наприклад “якщо нема torch → інша математика”).
5) Дозволена підстановка ENV лише через `${VAR}` у YAML, але:
   - якщо після резольву лишився `${...}` → startup crash.

---

## 2) Де живуть конфіги

Рекомендовано (щоб узгоджувалося з Aurora структурою):
```
config/aurora/neocortex/
  system.yaml
  ingest.yaml
  store.yaml
  models.yaml
  planner.yaml
  intents.yaml
  safety.yaml
```

Ці файли — **єдине джерело** параметрів Neocortex.

---

## 3) Резольвер: pipeline завантаження (креслення)

```mermaid
flowchart TD
  A[Load YAML fragments] --> B[Resolve ${ENV_VARS}]
  B --> C[Deep merge (fail on type conflicts)]
  C --> D[Detect duplicate dot-paths (SSOT)]
  D --> E[Guard: no unresolved ${...}]
  E --> F[Pydantic V2 validate (extra=forbid)]
  F --> G[Freeze: compute config hash]
  G --> H[Expose typed resolver to domain]
```

### 3.1. Duplicate dot-paths (SSOT guard)

Правило: будь‑який leaf‑параметр може бути визначений тільки в одному YAML.  
Якщо знайдені дублікати → crash з листом шляхів та файлів.

### 3.2. Заборона дефолтів у моделях (no‑defaults guard)

Окремий unit test має перевіряти, що у `apps/reference/domains/neocortex/config_models.py`:
- кожне поле, яке є параметром домену, оголошене як обовʼязкове (`Field(...)`);
- не використані `default=...` або `default_factory=...` для поведінкових параметрів.

---

## 4) Контракт файлів (мінімальний скелет)

Див. також: `apps/reference/domains/neocortex/docs/NEOCORTEX_DOMAIN_IMPLEMENTATION_PLAN.md` розділ `6.4`.

Підхід: всі YAML мають мати корінь `neocortex:` і не містити зайвих ключів.

---

## 5) Найчастіші вузькі місця конфігів (і як їх уникнути)

1) **Одиниці часу** (seconds vs ms)  
→ Виносимо правила у `ingest.yaml.time.assume_unit_for_fields`.

2) **Розбіжності схем WAL**  
→ Normalizer має мати явний mapping в YAML (які поля брати як `ts/rid/symbol`).

3) **Параметри моделей**  
→ Виносимо все: learning rate, dims, ensemble size, thresholds, warmups. Нічого не “припускаємо”.

