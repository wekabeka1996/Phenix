# Neocortex (Living Latent) — концепт нового домену/процесу для Aurora FSM

Ціль: додати в екосистему Aurora **окремий процес** (“нейрокортекс”), який **живе в латенті**, постійно **оновлює внутрішній стан**, **планує** і **навчається** на ринку як на середовищі.  
На **першому етапі** він **не впливає на торгівлю** (read‑only): харчується подіями/логами/станом ринку та аналізує рішення системи (вхід/вихід), будуючи власний “мозок”.

> Якщо потрібен **повністю ізольований** Neocortex (окремий процес, **без імпортів/звʼязку з кодом цього репо** і без будь‑якої інтеграції в рантайм Aurora) — див. `apps/reference/domains/neocortex/docs/NEOCORTEX_ISOLATED_DOMAIN_PLAN.md`.
> Повний план реалізації Neocortex як домену (аудит `living_latent`, патерни `vfoundation`, конфіги/тести/DoD) — див. `apps/reference/domains/neocortex/docs/NEOCORTEX_DOMAIN_IMPLEMENTATION_PLAN.md`.
> Навігація по всій документації домену (SSOT): `apps/reference/domains/neocortex/docs/README.md`.

Документ спирається на:
- твою поточну торгову архітектуру (vFoundation/FSM + домени `apps/reference/*` + SSOT YAML у `config/aurora/*`)
- код‑фрагменти “живого латента”, які ти витягнув у `living_latent/core/*`

---

## 1) Поточна система як “середовище”

Твоя Aurora FSM — це вже готове середовище з багатою телеметрією:
- **Подієва шина**: `FSMCore.emit()` → `EVT:*` (in‑proc), домени слухають/публікують.
- **Ключові домени**:
  - `market_data` → тики/стрім (ринкова реальність)
  - `feature_engineering` → фічі (OBI/TFI/delta/vol/…)
  - `risk_management` → дозволи/ризик‑гейти/сайзинг
  - `position_tracking` + `account_observer` → портфель, позиції, “freshness”
  - `decision_making` → рішення/інтенти (Aurora + MeanReversion), flip/orchestration, арбітраж
  - `execution_position` → реальна постановка/менеджмент ордерів, TP/SL, close, відновлення
- **SSOT конфіги**:
  - `config/aurora/instruments.yaml` — точність/мін‑ноушнл, leverage, margin_pct, max_notional_utilization
  - `config/aurora/strategies.yaml` — assignments стратегії↔символ + arbitration
  - `config/aurora/strategies/*.yaml` — політика стратегій (пороги, режимні мультиплікатори)
  - `config/aurora/domains.yaml` / `config/aurora/trading.yaml` / `config/aurora/system.yaml` / `config/aurora/regime.yaml`
- **Подієвий слід**: `ops/wal/*.jsonl` (WAL із `op/verb/pld/src/dst/rid` + hash‑ланцюг).

Нейрокортекс на R0 (read‑only) має дивитися на це як на реальне середовище RL/контролю:
- стан середовища = фічі ринку + стан портфеля + останні рішення + їхні наслідки
- дія агента (поки “віртуальна”) = пропозиція/план/гіпотеза, яку ми не виконуємо в системі, а лише логимо
- нагорода = PnL‑сигнал (пізніше), або проксі‑reward на ранній стадії (якість входу/виходу, ризик‑покарання)

---

## 2) Що саме дає `living_latent/core` (ідея + механіка)

Ці файли — фрагменти більшого LLA‑проєкту. Вони не підключаються “як є” (є імпорти на відсутні модулі типу `living_latent.system.*`, `living_latent.obs.*`, `living_latent.r2.*`).  
Але вони дають **сильний дизайн‑каркас**: як зробити “цифрове життя”, яке:
- має внутрішній стан,
- моделює світ,
- планує зміни,
- оцінює результат,
- і не ламає себе через safety‑гейти.

### 2.1. Ключові концепти (переклад на просту мову)

- **Observation (спостереження)**: в оригіналі це `telemetry.py` (GPU/CPU/IO).  
  Ідея: “кожен тик” → вимір середовища.

- **World Model (модель світу)**: `world.py` (ансамбль прогнозних моделей).  
  Дає **surprisal** (наскільки несподівано) та **disagreement** (наскільки невпевнено).

- **EFE (Expected Free Energy)**: `efe.py` = surprisal + disagreement (з вагами).  
  По‑людськи: “наскільки світ зараз непередбачуваний/новий”.

- **Empowerment**: `empowerment.py` (оцінка керованості/контролю).  
  По‑людськи: “чи можу я реально впливати діями на майбутнє”.

- **Viability**: `viability.py` (one‑class AE + conformal tau).  
  По‑людськи: “я в нормальному режимі чи в аномалії/ООD”.

- **Planning / Bridges**: `bridge_slerp.py`, `slerp.py`, `planner.py`  
  План = траєкторія в латенті (або просторі параметрів), з cost/penalties та rollback guard.

- **Evaluation**: `evaluator.py`, `score.py`, `metrics_ctx.py`  
  Оцінка ефекту плану по метриках до/після.

- **Safety gates**: `cvar_policy.py`, `dro_gate.py`, `reachability.py`, `panic_stop.py`, `warmup.py`  
  Це “нерви безпеки”: CVaR‑гейт, DRO‑гейт, reachability, panic file, прогрів/стадії.

- **Action Governor / Policy shims**: `governor.py`, `policy_shim*.py`  
  Контроль частоти/інтенсивності “дій”, анти‑спам, анти‑thrash.

### 2.2. Найважливіше: тут уже є “контур життя”

Типовий цикл (узагальнено):
1) отримали Observation  
2) оновили WorldModel  
3) порахували EFE + Empowerment + Homeostasis/Viability  
4) згенерували план (bridge)  
5) пропустили через safety‑гейти (CVaR/DRO/latency/…)  
6) застосували або відкотили (guard window)  
7) записали в blackbox/WAL + зберегли метрики/ефекти  

Це дуже схоже на те, що ти хочеш зробити для ринку — просто треба “переприв’язати” сенсори/нагороду.

---

## 3) Переприв’язка “живого латента” до ринку

### 3.1. Заміна Telemetry → Market/Portfolio Telemetry

Замість `Observation(gpu_temp, cpu_load, …)` потрібен новий тип спостереження, умовно:

**NeocortexObservation** (приклад полів, не фінальний контракт):
- `ts`
- `symbol`
- `market`: bid/ask/spread, mid, vol, micro‑return, window volume
- `features`: OBI/TFI/delta_price/volatility_state/ema_bias/liquidity_kappa/… (те, що вже рахує `feature_engineering`)
- `regime`: TREND/FLAT/… + confidence
- `portfolio`: equity, margin used/free, exposure, current pos qty/side, entry price, unrealized pnl
- `decision_context`: останній intent/дія системи (OPEN/CLOSE/NO_TRADE + why)
- `execution_result`: ack/fill/cancel/brackets status (коли доступно)

Джерела для R0:
- найкраще: **WAL** `ops/wal/*.jsonl` (вже структуровано)
- додатково: `logs/order_log_v1.jsonl`, `logs/aurora_core.log` (як fallback)

### 3.2. Reward/Valence (нагорода “за PnL”)

На ранніх етапах reward можна зробити багатокомпонентним:
- `realized_pnl` (коли закрили позицію)
- `unrealized_pnl` (як shaping)
- ризик‑штрафи: drawdown, перевищення експозиції, volatility spikes
- штрафи за “погану якість”: відкрився і одразу закрився без сенсу, часті flip, “голі” позиції без брекетів

В термінах living_latent:
- **valence** = “корисність/прибуток” (PnL‑сигнал)
- **homeostasis** = “здоров’я системи” (ризик‑метрики, стабільність, відсутність аварій, latency бюджети)

### 3.3. Action space нейрокортексу (поки read‑only)

Щоб він міг “планувати”, але не ламав торгівлю, дії на R0/R1 такі:
- `NO_OP` (переважно)
- `PROPOSE_*` (пропозиції) → лише лог/подія:
  - зміна порогів (signal_threshold, entry_threshold, cooldown, regime multipliers)
  - зміна sizing‑мультиплікаторів (але не execution!)
  - перемикання “пріоритетів” на hybrid символах (arbitration hints)
  - “risk mode suggestions” (зменшити/підвищити агресивність)
  - алерти про порушення контрактів (flip qty=0, brackets missing, crash during close…)

Суть: нейрокортекс спочатку вчиться **бачити**, **пояснювати**, **планувати**, але не “тисне кнопки”.

---

## 4) Як це має виглядати в vFoundation‑архітектурі

### 4.1. Neocortex як окремий процес

Рекомендовано зробити `neocortex` як сервіс:
- свій `main.py`/runner
- свій лог‑дир (`ops/neocortex/*` або `logs/neocortex/*`)
- свій WAL/manifest/snapshots (як у `vfoundation` та як у `living_latent/core/manifest.py`)

Він піднімається окремо від трейдера, і падіння нейрокортексу **не впливає** на торгівлю.

### 4.2. Інгест подій (R0: без змін у трейдері)

**Важливо (щоб не було “сліпоти” в idle):** одного WAL зазвичай достатньо для **аудиту/каузальності** (що система вирішила і що сталося на біржі), але **недостатньо** для “щільного” навчання World Model/VAE, бо це дає selection‑bias (бачимо світ переважно в моменти дій). Тому правильно мислити як **2 канали Perception**:
- **Journal (durable):** `ops/wal/*.jsonl` → низька частота, повний причинний ланцюг (`rid/why`), ідеально для епізодів “intent→execution→pnl” та контракт‑аудиту.
- **State Stream (best‑effort):** окремий щільний потік “станів середовища” (features/market/portfolio snapshot) **незалежно від того, чи були інтенти**. Для R0/R1 достатньо downsample 1–5 Hz на символ (або раз на бар), а не кожен тик.

**Варіант A (найпростіший, 0 змін коду Aurora):**
- tail `ops/wal/*.jsonl`
- фільтрувати потрібні `verb` (`FEATURES_CALCULATED`, `TRADE_INTENT_PROPOSED`, `POSITION_OPENED`, `POSITION_CLOSED`, `ORDER_FILLED`, …)
- будувати власний state store

**Варіант B (акуратніший канал, мінімальні зміни):**
- додати “tap” у `FSMCore.emit()` або в `AuroraBridge`, який дублює частину подій у файл `ops/neocortex/feed.jsonl`
- нейрокортекс читає тільки цей feed

**Варіант B2 (рекомендований для World Model):**
- зробити окремий “features tape” (`ops/neocortex/features_tape.jsonl` або pub/sub), який отримує регулярні snapshots з `feature_engineering`/`market_data` (з decimation + drop‑policy)
- нейрокортекс споживає tape для латенту/моделі світу, а WAL — для прив’язки до рішень/виконання

**Варіант C (майбутнє):**
- pub/sub (Redis/NATS/Kafka), але це вже R2+

### 4.3. Контракти повідомлень (приклад)

Нейрокортекс має використовувати `vfoundation.core.protocol.Message` як канонічний конверт.

**Imports (споживає):**
- `EVT:FEATURES_CALCULATED`
- `EVT:PORTFOLIO_STATE_UPDATED`
- `EVT:TRADE_INTENT_PROPOSED` (+ why_chain)
- `CMD:OPEN` / `CMD:CLOSE` (якщо дублюється у WAL)
- `EVT:ORDER_FILLED` / `EVT:POSITION_OPENED` / `EVT:POSITION_CLOSED`
- `EVT:REGIME_DETECTED` (якщо є)

**Exports (публікує, але не впливає):**
- `EVT:NEOCORTEX_STATE_UPDATED` (стан/метрики/латент)
- `EVT:NEOCORTEX_PLAN_PROPOSED` (план/дія‑пропозиція + обґрунтування)
- `EVT:NEOCORTEX_ALERT` (контракт‑порушення, аномалії, “голі позиції”, flip storms)

**Головний принцип**: будь‑який `CMD:*` від нейрокортексу на ранніх етапах заборонено (fail‑closed).

### 4.4. Actuation Safety (R3): Modulation Interface замість hot‑patch конфігів

Для Phase 3 (R3) критично **не “патчити” YAML/`AuroraConfig` напряму з іншого процесу**. Це породжує race‑conditions, дрейф конфігу та “зомбі‑позиції” (особливо на hybrid‑символах).

Правильніший патерн під vFoundation: **керована модуляція** (runtime overlay), яка застосовується **синхронно** у безпечній точці циклу `decision_making`, а SSOT YAML лишається незмінним.

**Пропозиція контракту:**
- Neocortex генерує тільки *пропозиції*: `EVT:NEOCORTEX_MODULATION_PROPOSED` (read‑only у R0–R2).
- Для R3 (за дозволом) трейдер приймає `CMD:APPLY_MODULATION` (або `CMD:DM_MODULATE`) у `decision_making`.
- `decision_making` на початку свого такту читає активні модуляції з `ModulationStore` і рахує **effective‑params** = base (SSOT) + overlay (bounded deltas), не мутуючи базовий конфіг.

**ModulationStore (всередині трейдера) має гарантувати:**
- **Allowlist** параметрів + **жорсткі межі** (наприклад `entry_threshold_bias ∈ [-0.10, +0.10]`, `size_mult ∈ [0.5, 1.5]`)
- **TTL + версіонування + idempotent_key** (щоб уникати “флапання”)
- **Rate‑limit** (max updates / хвилину / символ)
- **Гейти узгодженості**: заборонити “структурні” зміни (перемикання стратегій/assignments) поки є відкрита позиція; дозволяти тільки “м’які ручки” (пороги, cooldown, risk‑множники)
- **Аудит‑трейс**: `EVT:MODULATION_ACCEPTED/REJECTED/APPLIED` + окремий `ops/neocortex/modulations.jsonl` (не SSOT)

Так Neocortex у Phase 3 стає *не “редактором конфігів”*, а контрольованим джерелом **тимчасових модифікаторів**, які система застосовує безпечно та відкатує автоматично по TTL.

---

## 5) “Нейрокортекс” як домен: внутрішні модулі

Рекомендована декомпозиція (щоб відповідати vFoundation принципам “LLM‑friendly modularity”):

1) **Ingestor**
   - читає WAL/feed
   - нормалізує події в єдиний контракт спостережень
   - веде offset/last_hash (idempotent ingestion)

2) **State Store**
   - тримає компактний стан по символах (останній features/regime/position/…)
   - робить snapshot (для DR)

3) **World Model**
   - простий baseline на R0 (EMA/AR)
   - ансамбль/torch на R1/R2

4) **Latent Builder**
   - перетворює observation → `z_t` (ембед)

5) **Planner**
   - будує “bridge” в латенті/параметрах (по мотивам `bridge_slerp.py`, `slerp.py`)

6) **Evaluator**
   - оцінює (що було до/після) і навчає policy/world model (по мотивам `evaluator.py`, `metrics_ctx.py`)

7) **Safety Layer**
   - CVaR gate (для PnL‑tail)
   - DRO gate (hazard на невизначеності/аномалії)
   - warmup stages (поступове “дорослішання”)
   - panic/kill switch

8) **Output**
   - пише `neocortex_blackbox.jsonl` + `neocortex_wal.jsonl`
   - генерує “пояснення” (WHY + explain_ref)

---

## 6) Фази розвитку (реалістичний план)

### Phase 0 (R0): “Спостерігач”
- Читає `ops/wal`, будує:
  - timeline по кожному символу (intent → open → brackets → close)
  - “якість рішень” (без втручання)
  - алерти по контрактах (на кшталт твоїх кейсів BTC)
- Видає `EVT:NEOCORTEX_ALERT` + `EVT:NEOCORTEX_STATE_UPDATED` (лише лог)

### Phase 1 (R1): “Оцінювач + латент”
- Формує dataset “епізодів” (трейд як епізод)
- Вчиться прогнозувати (простий world model), рахує EFE/empowerment
- Генерує план‑пропозиції (але не виконує)

### Phase 2 (R2): “Тіньовий радник”
- Паралельно з торгівлею робить **shadow‑decision**:
  - “що б я зробив?” + “чому?”
  - порівнює зі справжньою системою
- Готує “proof‑kernel” інваріанти (LTL‑стиль): `OPEN -> F BRACKETS`, “no naked position”, “no qty=0 close intent”, …

### Phase 3 (R3): “Мінімальні безпечні інтервенції”
Тільки коли буде готовність:
- **ніякого hot‑patch SSOT/YAML**: лише `Modulation Interface` у `decision_making` (див. розділ 4.4)
- чіткий allowlist ручок (пороги/множники/cooldown) в малих межах + TTL
- людський підтверджувач (human‑in‑the‑loop) або “двоключ” (operator + gates)
- жорсткі safety gates (CVaR, max churn, max switch/hour) + лог `accepted/rejected/applied`

---

## 7) Важливі практичні зауваження

1) **living_latent/core зараз не є готовим пакетом**: бракує `living_latent/__init__.py` і залежних модулів. Його треба або:
   - перенести як “reference” (не виконуваний код), або
   - акуратно інтегрувати/переписати імпорти та контракт під vFoundation.

2) **R0 має бути максимально простим і надійним**: ingest → state → алерти → jsonl.  
   Усе “навчання” — холодний шлях (не заважати торговому hot‑path).

3) **Нейрокортекс не має “боротися” з risk/exposure guards**, він має навчитися жити в їхніх межах і пропонувати зміни так, щоб вони проходили гейти.

---

## 8) Наступний практичний крок (що робимо далі)

### 8.1. Якщо робимо “ізольований домен” (без впливу і без звʼязку з кодом)

Дотримуйся плану: `apps/reference/domains/neocortex/docs/NEOCORTEX_ISOLATED_DOMAIN_PLAN.md` (offline‑first, ingest копій WAL, свої контракти/логи/репорти, без інтеграції в Aurora runtime).

### 8.2. Якщо колись знадобиться інтегрований варіант (всередині цього репо)

Тоді наступним кроком може бути R0‑скелет у цьому репо:
- `apps/neocortex/` (окремий runner)
- читання `ops/wal/*.jsonl` (інкрементально)
- формування `NeocortexObservation` + `neocortex_blackbox.jsonl`
- базові алерти по контрактах (brackets missing, qty=0 close intent, flip storms, crash signatures)
- простий “latent” (EMA‑ембед) + `EVT:NEOCORTEX_STATE_UPDATED` у файл
