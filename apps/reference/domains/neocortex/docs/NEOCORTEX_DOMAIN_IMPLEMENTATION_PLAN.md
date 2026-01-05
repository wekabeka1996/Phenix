# Neocortex Domain — повний план реалізації (living_latent × vFoundation × Aurora)

Цей документ — практичний план створення домену **Neocortex** у Phenix/Aurora, з:
- всебічним аудитом `living_latent/core/*` (що є, що зламано, де стаб/мок/фолбек, що переносимо/переписуємо);
- коротким дослідженням патернів `vfoundation/*` та `apps/reference/*` (event bus, WAL, Message, ConfigLoader, DomainConfigResolver);
- повним дизайном **взаємозвʼязків**, **генерації інтенцій**, **системи конфігурації (YAML SSOT + Pydantic V2, без дефолтів/фолбеків)**;
- картою тестування та чітким **Definition of Done** (коли домен вважається завершеним);
- планом ліквідації “костилів/моків/стабів/фолбеків” із living_latent через порт у production‑домен.

Повʼязані документи:
- Концепт домену: `apps/reference/domains/neocortex/docs/NEOCORTEX_DOMAIN_CONCEPT.md`
- План повної ізоляції (без звʼязку з кодом/рантаймом): `apps/reference/domains/neocortex/docs/NEOCORTEX_ISOLATED_DOMAIN_PLAN.md`

---

## 1) Стратегія: що саме будуємо і як не зламати систему

### 1.1. Цільові режими (phases / readiness levels)

Ми будуємо Neocortex як домен з чотирма рівнями готовності:

- **R0 — Observer**: тільки читає (WAL/події), будує state store, метрики, алерти. **0 впливу на трейдинг.**
- **R1 — Learner**: тренує латент/viability/world model на “щільному” state stream, рахує EFE/empowerment. **0 впливу.**
- **R2 — Shadow Advisor**: генерує “shadow intents” (що б зробив), порівнює з реальними рішеннями, пише розбіжності. **0 впливу.**
- **R3 — Controlled Actuation**: обмежений вплив (спочатку тільки “мʼякі ручки” або окремий intent‑канал з allowlist + TTL + audit). **Входить лише після safety‑аудиту.**

### 1.2. Ключовий інваріант цього плану

**У домені заборонені:**
- hardcoded параметри, “магічні числа”, dict‑дефолти параметрів, env‑перемикачі поведінки;
- runtime fallbacks (degraded mode) типу “якщо нема torch → EMA”, “якщо не вистачає даних → fail‑open”;
- неявні дефолти в Pydantic моделях (усі тюнінгові поля мають бути **обовʼязковими** у YAML).

**Єдине джерело істини для конфігурації — YAML**, розбитий на окремі файли + строгий резольвер + Pydantic V2 валідація.

Це означає: якщо чогось не вистачає — **старт домену має падати** (fail‑closed), а не “підставляти якось”.

---

## 2) Аудит `living_latent/core/*`: що там є і чому воно не production

`living_latent/core/*` — це фрагменти LLA‑проєкту (не повністю перенесені). Вони корисні як **ідеї/скелет**, але напряму як домен Aurora непридатні через:
- зламану пакувальну структуру (імпорти на неіснуючі `living_latent.system.*`, `living_latent.obs.*`, `living_latent.common.*`);
- численні **stubs/mocks/fallbacks** (Router stub, OffPolicyLearner stub, OT Sinkhorn stub, torch‑fallback, telemetry mock, fail‑open viability, env‑керовані shims);
- hardcoded параметри у коді (`PARAMS = {...}`, дефолти в pydantic, константи поведінки);
- використання випадковості без контролю (random noise у плануванні/оцінці без seed‑контракту);
- логіка частково “демо/смоук” (`if __name__ == '__main__'`, синтетичні дані, “для прикладу”).

### 2.1. Мапа модулів living_latent (корисне ядро)

Нижче — коротко, що з модулів варте порту/перепису, і що є проблемою:

- `config.py`
  - **Проблема**: дефолти всюди, fallback pydantic v1/v2, env overrides.
  - **Що робимо**: перепис у Neocortex‑конфіги без дефолтів, тільки YAML.

- `world.py` + `efe.py`
  - **Ідея**: ансамбль world model → `surprisal` (NLL) + `disagreement` → EFE.
  - **Проблема**: torch‑fallback “degraded mode”, демо‑приклади.
  - **Що робимо**: “torch required” + чіткий online/offline train контракт + тест на стабільність.

- `viability.py`
  - **Ідея**: one‑class AE + conformal tau.
  - **Проблема**: `is_alive()` робить fail‑open якщо tau None; нормалізація з hardcoded “16GB max”, fixed epochs.
  - **Що робимо**: fail‑closed для actuation (до калібрації — тільки спостереження), усі норм‑константи в YAML.

- `empowerment.py`
  - **Ідея**: InfoNCE‑оцінка BA‑bound + проксі + Gramian fallback.
  - **Проблема**: багаторівневі fallbacks/рандом, немає чіткого математичного контракту для ринку.
  - **Що робимо**: чітко визначити “actions” у трейдингу і оцінювати empowerment як MI(a; s_{t+1}) з контрольованою апроксимацією (без fallback chain).

- `planner.py` (BridgeExecutor) + `bridge_slerp.py` (GuidedSlerpPlanner) + `selector.py`
  - **Ідея**: планування “містків” між станами/атракторами, вибір по J‑скорингу з дистанційним штрафом.
  - **Проблема**: noise injection, placeholder viability projection, CVaR fallback‑import у selector, багато демо‑логіки.
  - **Що робимо**: визначити план як “послідовність policy‑дій/перемикачів режимів” у трейдингу, а не геометрію в R^n без сенсу; зробити router/selector детермінованими і перевіреними.

- `dro_gate.py`
  - **Проблема**: це прямо “deterministic stub”.
  - **Що робимо**: або видаляємо на R0–R2, або реалізуємо справжню DRO‑гейт‑математику (OT/Sinkhorn або інший робастний критерій) з тестами.

- `router/__init__.py`, `learn/__init__.py`
  - **Проблема**: stubs “щоб не падали імпорти”.
  - **Що робимо**: в production домені stubs заборонені — або справжня реалізація, або модуль не існує і домен не стартує.

### 2.2. Класи проблем, які треба “випалити” при порту

1) **Fallback‑поведінка** (ImportError → degraded, “fail‑open”, “safe fallback defaults”)  
→ замінити на **fail‑closed** + явні залежності/конфіги.

2) **Hardcoded тюнінги** (пороги, альфи, таймінги, weights)  
→ винести 1:1 у YAML і зробити Pydantic‑обовʼязковими.

3) **Невідтворюваність** (рандом без seed)  
→ `rng_seed` у YAML + детермінізм у важливих місцях (router/selector).

4) **Неправильна “Telemetry” семантика**  
→ замість GPU/CPU метрик: market/portfolio/system features.

---

## 3) Дослідження `vfoundation` + поточної Aurora конфіг‑архітектури

### 3.1. Подієва модель і протокол повідомлень

**Message** (Pydantic): `vfoundation/core/protocol.py`  
Ключові поля:
- `op`, `verb`, `src`, `dst`, `rid`, `ts`, `ttl_ms`, `idempotent_key`, `pld`, `why`, `data_ref`, …
Обмеження:
- `why` ≤ 80 символів (є `truncate_why()`).

**Event bus**: `vfoundation/core/fsm_core.py`  
`FSMCore.listen("EVT:...", callback)` / `FSMCore.emit("EVT:...", payload, why, data_ref)`

**Router (опціонально для доменів)**: `vfoundation/core/routing.py`  
Є idempotency (single‑flight), circuit breaker, WAL append before handler.

### 3.2. WAL та DR‑патерни

- `vfoundation/dr/wal.py`: append + hash chain (`_prev/_hash`), read_by_rid, verify_chain.
- `vfoundation/dr/replay.py`: replay по `rid` + integrity verify + merkle root.
- `vfoundation/dr/snapshot.py`: примітивні snapshots (але для Neocortex краще окремий store).

**Висновок для Neocortex:** WAL — головний “audit substrate”, а Neocortex має вміти:
1) читати WAL інкрементально;
2) перевіряти цілісність ланцюга (де можливо);
3) корелювати події через `rid` + `span_id` (якщо є).

### 3.3. SSOT YAML + Pydantic‑валідація у Aurora

**ConfigLoader**: `apps/reference/config_loader.py`  
Важливі патерни:
- YAML load + deep_merge (fail‑closed на конфліктах типів);
- provenance map (звідки взявся параметр);
- строгий режим конфліктів/дублікатів шляхів (SSOT‑інваріант);
- ENV підстановки тільки через `${VAR}` у YAML (але це не “параметр у коді”).

**Pydantic V2 schema**: `apps/reference/config_models.py`  
Патерн:
- `ConfigDict(extra='forbid')`, валідатори, fail‑fast на старті.

**DomainConfigResolver**: `apps/reference/domain_config.py`  
Важливо:
- canonical‑only доступ (`config.domains`), без fallback на legacy.

**Висновок для Neocortex:** ми робимо аналогічно, але жорсткіше:
- Neocortex конфіги — **без дефолтів**;
- resolver не має жодних fallback‑гілок;
- домен не має “дотягувати” поведінку з env‑перемикачів.

---

## 4) Архітектура Neocortex: модулі, взаємозвʼязки, потоки даних

### 4.1. Топологія: 2 варіанти запуску (обидва підтримуємо)

**Варіант A (рекомендовано для R0–R2): Standalone process**
- Neocortex запускається окремо (свій entrypoint), читає WAL/стріми з файлів/DB.
- Не залежить від in‑proc FSM подій.
- Вплив на трейдинг = **0**.

**Варіант B (для low‑latency R2/R3): In‑proc domain**
- Neocortex реєструється як домен у FSM (слухає `EVT:*`, емить `EVT:NEOCORTEX_*`).
- Вплив може бути **тільки** після explicit enable у YAML (R3).

### 4.2. Вхідні дані (inputs) і контракти

**Мінімум для R0 (достатньо WAL):**
- `ops/wal/*.jsonl` (або його копія) — каузальний слід (рішення → виконання).

**Для R1+ потрібен щільний State Stream:**
- або `EVT:FEATURES_CALCULATED` (якщо фічі в WAL/стрімі регулярні),
- або окремий `features_tape.jsonl` (1–5Hz або бар‑частота), щоб уникати selection bias.

### 4.3. Вихідні артефакти (outputs)

Навіть в in‑proc варіанті вихід Neocortex має бути “best effort” і не ламати hot‑path:
- `logs/neocortex/state.jsonl` — латент/метрики
- `logs/neocortex/alerts.jsonl` — інваріанти/аномалії
- `logs/neocortex/shadow_intents.jsonl` — shadow‑інтенти (R2)
- `ops/wal/*.jsonl` — тільки якщо домен вбудований і використовує vfoundation WAL (audit trail).

### 4.4. Внутрішні компоненти (production модульність)

1) **Ingestor**
   - інкрементально читає WAL (offset store)
   - нормалізує події до внутрішнього контракту `EventEnvelope`
   - будує `Episode` звʼязки (rid, symbol, lifecycle)

2) **State Store**
   - тримає стан по `symbol` і `rid` (позиція, останні фічі, останній intent, режим)
   - дає snapshot/restore (SQLite/DuckDB + JSONL індекси)

3) **Dataset Builder (R1+)**
   - формує датасети:
     - “tick/bar sequences”
     - “trade episodes”
     - “decision windows” (до/після intent)

4) **Latent / World Model (R1+)**
   - latent encoder (AE/VAE) + world model p(z_{t+1}|z_t, a_t)
   - ensemble/uncertainty (disagreement)

5) **Viability**
   - OOD gate (conformal tau), але: **до калібрації — заборона actuation**, дозволено тільки лог/алерт.

6) **EFE / Empowerment**
   - EFE з world model (без fallback)
   - empowerment як MI(a; s_{t+1}) апроксимація на дискретному наборі дій

7) **Planner / Router**
   - генерує кандидатні дії/плани (для трейдингу це не “slerp у R^n”, а space дій: HOLD/OPEN/CLOSE/REDUCE_RISK/MODULATE)
   - router ранжує, застосовує risk gates, робить deterministic selection

8) **Intent Generator**
   - формує **shadow intent** або **trade intent** у форматі, сумісному зі `schemas/trade_intent_v1.json`
   - завжди додає `why[]` і `schema_ref/dto_version`

9) **Safety Layer**
   - allowlist дій/інтервенцій
   - TTL, rate‑limit, idempotency key, invariants
   - “no structural changes under open position” (інваріант)

### 4.5. Карта взаємозвʼязків доменів (events map)

> Це “канонічна” карта для in‑proc інтеграції. У Standalone‑режимі те ж саме відновлюється із WAL/стрімів.

**IN (що Neocortex споживає):**
- `EVT:FEATURES_CALCULATED` (джерело: `feature_engineering`) — фічі ринку + `price_ref`.
- `EVT:RISK_ASSESSMENT_COMPLETED` (джерело: `risk_management`) — risk score/гейти/експозиції.
- `EVT:PORTFOLIO_STATE_UPDATED` (джерело: `position_tracking`) — позиції/еквіті/маржа/freshness.
- `EVT:REGIME_DETECTED` (джерело: `regime_detector`) — режим ринку + confidence.
- `EVT:TRADE_INTENT_PROPOSED` (джерело: `decision_making`) — “що зробила Aurora” для порівняння (R2).
- `EVT:ORDER_ACK`, `EVT:ORDER_FILL`, `EVT:POSITION_OPENED`, `EVT:POSITION_CLOSED` (джерело: `execution_position`) — наслідки.

**OUT (що Neocortex продукує):**
- `EVT:NEOCORTEX_STATE_UPDATED` — латент/метрики/ефекти (тільки лог/моніторинг).
- `EVT:NEOCORTEX_ALERT` — порушення інваріантів, OOD, churn, “flip storms”.
- `EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED` — shadow intent (R2).
- `EVT:NEOCORTEX_TRADE_INTENT_PROPOSED` — окремий intent‑канал (R3, gated).
- `EVT:NEOCORTEX_MODULATION_PROPOSED` — overlay‑пропозиції (R3, gated).

### 4.6. Внутрішні контракти даних (мінімум, який треба формалізувати)

**EventEnvelope (нормалізована подія з WAL/EVT):**
- `event_id`, `ts_ms`, `op`, `verb`, `src`, `dst`, `rid`, `span_id`, `parent_span_id`
- `payload` (dict)
- `raw_ref` (file:line), `hash_prev/hash`

**Observation (стан середовища на кроці t):**
- `symbol`, `ts_ms`
- `features` (числові фічі; тип/список — з YAML)
- `portfolio` (скорочено: позиція/еквіті/маржа/side/qty)
- `regime` (label + confidence)

**Episode (трейд як епізод):**
- `rid`, `symbol`, `side`, `open_ts_ms`, `close_ts_ms`
- `entry_price_ref`, `exit_price_ref`
- `pnl`, `max_adverse_excursion`, `max_favorable_excursion` (якщо доступно)

**PlanCandidate / ShadowIntent:**
- `symbol`, `ts_ms`, `action` (`HOLD|OPEN_LONG|OPEN_SHORT|CLOSE|REDUCE_RISK|MODULATE`)
- `confidence`, `efe`, `empowerment`, `viability_score`
- `why[]` (обмеження довжин/кількості — з YAML)

### 4.7. Рекомендована структура коду Neocortex (в цьому репо)

```
apps/reference/domains/neocortex/
  __init__.py
  neocortex.py                  # domain class (in-proc)
  main.py                       # entrypoint (standalone/inproc)
  docs/                         # SSOT документація домену

  config_loader.py              # YAML -> dict (merge/guards)
  config_models.py              # Pydantic V2 (no defaults, extra=forbid)
  config_resolver.py            # accessor без fallback

  ingest/
    wal_reader.py               # інкрементальний reader + offsets
    normalizer.py               # EventEnvelope

  store/
    repo.py                     # SQLite/DuckDB репозиторій
    models.py                   # Episode/State таблиці (або Pydantic)

  models/
    world_model.py
    viability.py
    latent.py

  metrics/
    efe.py
    empowerment.py

  planner/
    action_space.py
    router.py
    scoring.py

  intents/
    builders.py                 # TradeIntent/ShadowIntent
    schemas.py                  # jsonschema validators (trade_intent_v1)

  safety/
    gates.py                    # invariants, TTL, churn, freshness
    allowlist.py

  report/
    alerts.py
    daily_report.py
```

Технічні правила:
- **жодних optional imports** для критичних компонентів (torch/jsonschema тощо) — залежності фіксуються у requirements/pyproject;
- **жодних `os.getenv` для поведінки домену** (тільки YAML резольвер з `${VAR}`).

---

## 5) Генерація інтенцій: контракти, шлях у систему, safety

### 5.1. Види інтенцій Neocortex

- **ShadowIntent** (R2): “що б я зробив” — тільки лог/репорт.
- **TradeIntent** (R3): реальна `EVT:TRADE_INTENT_PROPOSED` (або окремий `EVT:NEOCORTEX_TRADE_INTENT_PROPOSED`), що може бути конвертований bridge‑ом у `CMD:OPEN/CLOSE`.
- **ModulationProposal** (альтернатива R3): пропозиція overlay‑параметрів (пороги/множники/cooldown) без зміни SSOT.

### 5.2. Контракт TradeIntent (узгоджуємось з існуючим schema)

Мінімально сумісний payload має відповідати `apps/reference/domains/decision_making/schemas/trade_intent_v1.json`.

Neocortex‑інтент повинен:
- заповнювати `instrument/side/order.qty/order.price/order.price_ref/reduce_only`;
- мати `tca_budget`, `risk_budget`, `size` — **з YAML**, не “припустимо”;
- містити `why[]` (пояснюваність) з ключовими метриками: EFE, viability score, empowerment, policy decision, gates;
- ставити `dto_version` і `schema_ref`.

### 5.3. Безпека і гейти для інтенцій

**R0–R2:** будь‑який реальний `TradeIntent` заборонений.

**R3 (тільки після аудиту):**
- allowlist symbol/strategy
- allowlist типів дій (спочатку тільки CLOSE/REDUCE_RISK або тільки thresholds overlays)
- TTL + rate‑limit + idempotency_key
- інваріанти:
  - “no structural change (strategy switch) якщо позиція відкрита”
  - “no open intent якщо portfolio stale / features stale”
  - “no repeated flips” (churn limiter)

### 5.4. Алгоритм генерації TradeIntent (як робимо “нормальну математику”)

**Вхід:** Observation + internal state (latent/world model) + budgets/config.  
**Вихід:** payload під `trade_intent_v1.json` або shadow intent.

Пайплайн (R2 shadow → R3 trade):
1) **Action proposals**: згенерувати кандидати дій з дискретного action space (YAML).
2) **World model roll‑out**: оцінити наслідки дій (очікуваний розподіл next‑state / returns proxy).
3) **Risk proxy**: оцінити tail‑ризик (CVaR/vol regime) і перевірити hard gates (YAML).
4) **Score**: корисність = (expected return proxy) − λ·risk − η·EFE + κ·empowerment (ваги з YAML).
5) **Select**: deterministic router (seed з YAML) обирає 1 дію на символ.
6) **Build intent**:
   - `instrument` = symbol
   - `side` = buy/sell (з action)
   - `order.price_ref` = з features (або середня/mark, чітко визначено в YAML)
   - `order.price` = price_ref або policy‑корекція (YAML)
   - `order.qty` = функція від notional_target та instrument constraints (все з YAML/SSOT)
   - `p`, `payoff_ratio_r` = з моделі/евристики (але параметри — з YAML)
   - `tca_budget`, `risk_budget`, `size` = з YAML (без “консервативних якщо нема”)
   - `why[]` = метрики + причини гейтів + версії моделей

### 5.5. Ідемпотентність, аудит і “не спамити систему”

Для будь‑якого intent (shadow або trade) має бути стабільний `idempotent_key`:
- формат (приклад): `neocortex:<phase>:<symbol>:<action>:<bucket_ts>:<model_hash>`
- `bucket_ts` = округлення часу за YAML (наприклад 5s/30s), щоб один і той самий сигнал не плодив 100 інтенцій.

Аудит:
- всі рішення Neocortex пишуться у власний `logs/neocortex/*.jsonl`;
- якщо Neocortex вбудований in‑proc — дублювати критичні рішення у WAL (best‑effort, без падіння hot‑path).

### 5.6. Мінімальна математична специфікація (адаптація living_latent → трейдинг)

**Стан середовища**: `s_t = concat(market_features_t, portfolio_features_t, regime_features_t)`  
**Латент**: `z_t = Encoder(s_t)` (AE/VAE).

**World model**: апроксимація `p(z_{t+1} | z_t, a_t)` або `p(s_{t+1} | s_t, a_t)` (енсамбль).

**Surprisal**: `Surp_t = -log p(z_t | z_{t-1}, a_{t-1})` (NLL під world model).  
**Disagreement**: дисперсія прогнозів ансамблю (епістемічна невизначеність).

**EFE (proxy)**: `EFE_t = w_s * EMA(Surp_t) + w_d * EMA(Disagree_t)` (ваги/EMA з YAML).  
У трейдингу EFE використовується як **штраф за “непередбачуваність/новизну”**, а не як єдина ціль.

**Viability**: реконструкційна помилка AE + conformal tau; якщо `error > tau` → стан поза “viable envelope”.

**Empowerment (proxy)**: `I(a; z_{t+1} | z_t)` для дискретного `a` (HOLD/OPEN/CLOSE/…), оцінюється InfoNCE/контрастивно.  
У трейдингу empowerment корисний як “контрольованість” (де дії мають прогнозований ефект), але не як привід торгувати без risk gates.

---

## 6) Система конфігурації Neocortex (YAML SSOT + Pydantic V2, без дефолтів)

### 6.1. Принципи

1) **Жодних дефолтів у коді** для поведінкових/тюнінгових параметрів.
2) **Жодних fallback гілок** (імпорт/дані/порогові значення).
3) Якщо конфіг неповний/невалідний → **crash на старті** з точним шляхом параметра.
4) **extra='forbid'** скрізь (ніяких “зайвих ключів”).
5) Дозволено підстановка ENV тільки через YAML (`${VAR}`), але:
   - якщо `${VAR}` не резольвиться → це вважається помилкою валідації (спец‑перевірка).

### 6.2. Рекомендована структура YAML (окремі файли)

```
config/aurora/neocortex/
  system.yaml        # paths, runtime, mode, logging
  ingest.yaml        # wal ingest, offsets, integrity checks
  store.yaml         # sqlite/duckdb, retention, snapshot policy
  models.yaml        # latent/world/viability/efe/empowerment hyperparams
  planner.yaml       # action space, router scoring, constraints
  intents.yaml       # intent schema settings, budgets, idempotency, gating
  safety.yaml        # allowlists, TTLs, rate limits, invariants
```

**Єдиним джерелом конфігів є ці YAML**, а не env або hardcoded dict.

### 6.3. Резольвер і валідація

План реалізації:
- `apps/reference/domains/neocortex/config_loader.py`: завантажує всі `config/aurora/neocortex/*.yaml`, робить deep_merge + duplicate‑path detection + env‑substitution.
- `apps/reference/domains/neocortex/config_models.py`: Pydantic V2 моделі **без дефолтів** (усі `Field(...)`).
- `apps/reference/domains/neocortex/config_resolver.py`: простий accessor/resolver (аналог `DomainConfigResolver`, але без fallback).

Додатково (обовʼязково):
- **“unresolved env var guard”**: після резольву жоден рядок не може містити шаблон `${...}`.
- **“no defaults guard”**: у Pydantic моделях Neocortex заборонені дефолти (CI‑тест, який перевіряє `model_fields`).

### 6.4. YAML контракт (скелети файлів і обовʼязкові ключі)

Нижче — **мінімальний скелет**. Усі ключі мають бути присутні (ніяких implicit defaults).

**`config/aurora/neocortex/system.yaml`**
```yaml
neocortex:
  phase: "R0"                 # R0|R1|R2|R3
  run_mode: "standalone"      # standalone|inproc
  rng_seed: 12345

  paths:
    work_dir: "logs/neocortex"
    inbox_wal_dir: "ops/wal"
    inbox_features_tape: "ops/neocortex/features_tape.jsonl"

  logging:
    jsonl: true
    level: "INFO"
    rotate_days: 7
```

**`config/aurora/neocortex/ingest.yaml`**
```yaml
neocortex:
  ingest:
    wal:
      file_glob: "*.jsonl"
      offsets_path: "logs/neocortex/offsets.json"
      verify_hash_chain: true
      require_hash_fields: false
      max_bad_lines: 0

    time:
      # порядок спроб витягти timestamp з різних WAL варіантів
      fields_priority: ["ts", "timestamp"]
      # правила нормалізації seconds/ms (без евристик у коді)
      assume_unit_for_fields:
        ts: "ms"
        timestamp: "s"
```

**`config/aurora/neocortex/store.yaml`**
```yaml
neocortex:
  store:
    backend: "sqlite"  # sqlite|duckdb
    path: "logs/neocortex/neocortex.sqlite"
    retention_days:
      events: 30
      alerts: 90
      intents: 90
```

**`config/aurora/neocortex/models.yaml`**
```yaml
neocortex:
  models:
    viability:
      alpha: 0.10
      window: 256
      min_count: 128
      retrain_every_s: 300
      tau_floor: 0.005
      feature_norm:
        method: "robust_z"      # robust_z|minmax|zscore
        clip_abs: 5.0

    world_model:
      kind: "gru_ensemble"
      input_dim: 64
      latent_dim: 16
      hidden_dim: 64
      ensemble_size: 3
      learning_rate: 0.0001

    efe:
      surprisal_weight: 0.02
      disagreement_weight: 0.50
      ema_alpha: 0.10

    empowerment:
      kind: "infonce"
      k_neg: 16
      temperature: 0.07
```

**`config/aurora/neocortex/planner.yaml`**
```yaml
neocortex:
  planner:
    action_space: ["HOLD", "OPEN_LONG", "OPEN_SHORT", "CLOSE", "REDUCE_RISK"]

    scoring:
      w_return: 1.0
      w_risk: 1.0
      w_efe: 1.0
      w_empowerment: 1.0

    router:
      min_score: 0.0
      max_actions_per_minute_per_symbol: 6
```

**`config/aurora/neocortex/intents.yaml`**
```yaml
neocortex:
  intents:
    mode: "shadow"   # shadow|emit_neocortex_trade_intent|emit_trade_intent
    dto_version: "1.0.0"
    schema_ref: "trade_intent_v1.json"
    valid_for_ms: 5000

    tca_budget:
      max_slippage_bps: "10"
      max_latency_ms: 500
      maker_preference: "neutral"

    risk_budget:
      trade_cvar95_max_bps: "100"
      session_cvar95_max_bps: "200"

    size:
      kelly_fraction: "0.10"
      notional_cap_usd: "500"
```

**`config/aurora/neocortex/safety.yaml`**
```yaml
neocortex:
  safety:
    allowlist:
      symbols: ["BTCUSDT", "ETHUSDT"]
      actions: ["HOLD", "CLOSE", "REDUCE_RISK"]  # R0-R2: не використовується для actuation

    gates:
      require_viability_calibrated_for_intents: true
      max_churn_per_hour: 6
      features_ttl_sec: 30
      portfolio_ttl_sec: 15
```

> Усі значення тут наведені як приклад; ключовий принцип — **немає дефолтів у коді**.

---

## 7) Карта тестування: що, як і коли тестуємо

### 7.1. Рівні тестів

1) **Config Contract Tests (must)**
   - missing key → crash
   - extra key → crash
   - unresolved `${VAR}` → crash
   - “no defaults” enforcement for Neocortex models
   - заборона `os.getenv`/env‑flags у `apps/reference/domains/neocortex/*` (окрім резольвера `${VAR}`)

2) **Unit Tests (core math)**
   - viability: calibrator, tau, OOD decisions (без fail‑open)
   - world model: shape/градієнти/стабільність/детермінізм з seed
   - EFE: surprisal/disagreement компоненти
   - empowerment: MI proxy стабільність
   - router/selector: детермінізм та інваріанти

3) **Contract Tests (events)**
   - generated TradeIntent валідний під `trade_intent_v1.json`
   - why‑chain обрізається/нормалізується під 80 символів для Message.why (якщо використовується)

4) **Integration Tests (pipelines)**
   - WAL ingest → normalized events → state store → alerts
   - R2 shadow: dataset → scoring → shadow_intents.jsonl

5) **Replay/Regression Tests**
   - фіксований шматок WAL (golden) → стабільний репорт/алерти (diff‑контроль)

### 7.2. Як запускати (майбутня інструкція)

Плануємо стандартизувати:
- `pytest -q tests/domains/neocortex`
- `python -m apps.reference.domains.neocortex.main --config-dir config/aurora/neocortex --run-id ...`
- `python -m apps.reference.domains.neocortex.tools.validate_intents --in logs/neocortex/shadow_intents.jsonl`

### 7.3. Тестові фікстури/дані (що потрібно додати)

- `tests/domains/neocortex/fixtures/wal_small.jsonl` — мінімальний WAL з 1 епізодом.
- `tests/domains/neocortex/fixtures/features_tape_small.jsonl` — щільний stream для R1.
- `tests/config/aurora/neocortex/` — повний набір YAML (усі ключі присутні).
- golden outputs (наприклад `expected_alerts.jsonl`, `expected_report.md`) для regression‑diff.

---

## 8) Definition of Done (коли домен “готовий”)

### 8.1. DoD для R0 (Observer)

- інкрементальна інгестація WAL з offset store (ідемпотентність)
- відновлення епізодів/таймлайну по `rid`/symbol
- алерти інваріантів + репорт
- **0 побічних ефектів на трейдинг**
- повний config‑контракт: немає дефолтів/фолбеків

### 8.2. DoD для R1 (Learner)

- є state stream / dataset builder
- viability калібрується і працює стабільно
- world model/efe/empowerment дають відтворювані метрики
- немає degraded‑режимів “якось”

### 8.3. DoD для R2 (Shadow Advisor)

- генерує shadow intents (не впливаючи на систему)
- щоденний divergence‑репорт: “Aurora зробила X, Cortex пропонував Y”
- валідні контракти інтенцій (schema tests)

### 8.4. DoD для R3 (Controlled Actuation)

- формальний safety‑RFC (окремий документ)
- allowlist + TTL + rate limits + audit trail в WAL
- інваріанти (no structural change while position open, no churn, freshness gates)
- можливість повного “kill switch” без зміни коду (через YAML reload або operator action)

---

## 9) План ліквідації стабів/моків/фолбеків living_latent (детально)

### 9.1. Загальний підхід

1) **Не “підключати living_latent як є”** в production домен.
2) Зробити **порт** алгоритмів у `apps/reference/domains/neocortex/*` з:
   - чистими імпортами
   - нульовими stubs
   - нульовими fallbacks
   - конфігами тільки з YAML
3) `living_latent/*` лишається як reference (або поступово видаляється після порту).

### 9.2. Backlog робіт “по слідах” проблемних модулів

- Torch fallback у `living_latent/core/world.py`
  - рішення: torch — mandatory dependency; якщо нема → crash на старті.
  - тести: import test + minimal forward/train test.

- Fail‑open у `living_latent/core/viability.py` (tau None → True)
  - рішення: для R0/R1 дозволяємо працювати без tau, але **забороняємо intent generation** до калібрації.
  - тести: “no intents before calibrated”.

- Stub Router / Stub OffPolicyLearner
  - рішення: або реалізація, або модуль не існує (і код не має optional import).
  - тести: router selection deterministic.

- OT Sinkhorn stub / DRO stub
  - рішення: або викинути з R0–R2, або реалізувати повноцінно.
  - тести: властивості метрики/монотонність, edge‑cases.

- Policy shims на env (`LLA_*`) / triggers
  - рішення: вся політика тільки з YAML; тригери — окремий “operator control” шар, але не як конфіг.
  - тести: config‑driven behavior.

- Hardcoded weights/thresholds у score/selector/cvar_policy
  - рішення: 1:1 в YAML, `Field(...)` обовʼязково.
  - тести: missing‑field crash.

### 9.3. Портинг‑карта (що робимо з файлами living_latent)

**Переписати/портувати як Neocortex‑ядро (без stubs/fallbacks):**
- `living_latent/core/world.py` → `apps/reference/domains/neocortex/models/world_model.py`
- `living_latent/core/viability.py` → `apps/reference/domains/neocortex/models/viability.py`
- `living_latent/core/efe.py` → `apps/reference/domains/neocortex/metrics/efe.py`
- `living_latent/core/empowerment.py` → `apps/reference/domains/neocortex/metrics/empowerment.py`
- `living_latent/core/cvar_policy.py` → `apps/reference/domains/neocortex/safety/cvar_gate.py` (тільки якщо реально потрібно)

**Не переносити напряму (переробити під трейдинг‑семантику):**
- `living_latent/core/telemetry.py` (GPU/CPU) → замінити на market/portfolio/system observations.
- `living_latent/core/bridge_slerp.py` (геометричні “мости”) → action‑space planner у трейдингу.

**Викинути/заборонити у production:**
- `living_latent/core/router/__init__.py` (stub)
- `living_latent/core/learn/__init__.py` (stub)
- `living_latent/core/dro_gate.py` (stub) — або реальна реалізація, або нуль використання.

---

## 10) Порядок реалізації (roadmap по кроках)

1) **R0**: WAL ingestor + state store + invariants/alerts + report.
2) **Config system**: YAML fragments + loader + Pydantic V2 no‑defaults + contract tests.
3) **R1**: dataset builder + viability + world model + EFE.
4) **R2**: shadow intents + divergence report + schema validation.
5) **R3 (окремо)**: actuation RFC + modulation/intent channel + safety audit.
