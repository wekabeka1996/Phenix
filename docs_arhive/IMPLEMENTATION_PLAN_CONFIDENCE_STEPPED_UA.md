# Домeн «Подієва Впевненість» та Ступенева ROI‑політика: дизайн і покрокова імплементація

Цей документ формалізує ідею «ступеневої впевненості» в автоматичному трейдингу: система на кожному фіксованому порогу ROI (прибуток у $) переоцінює ймовірність подальшого росту й вирішує — фіксувати прибуток зараз чи просунути тейк‑профіт до наступного порогу. Реалізація зберігає наявну архітектуру та контракти, інтегрується через події й конфігурацію, з підтримкою тіньового режиму (shadow) та безпечних фолбеків.

---

## 1) Бізнес‑логіка «ступеневої впевненості» (fixed‑USD steps)

- Ідея: працюємо зі сталими порогами ROI у $, наприклад: 1.20 → 2.20 → 3.20 …
- На порозі Tᵢ система оцінює «впевненість продовження руху вгору» p_up.
  - Якщо p_up ≥ θᵢ (порог впевненості для цього ступеня) — ми «просуваємо» TP на наступний поріг Tᵢ₊₁.
  - Якщо p_up < θᵢ — фіксуємо прибуток на Tᵢ (утримуємо/ставимо TP на Tᵢ, не просуваємо далі).
- При досягненні наступного порогу Tᵢ₊₁ — все повторюється з вищим θᵢ₊₁ (наприклад 60% → 70% → 80%).
- Захист від відкату: якщо ціна відкотилась понад X bps від локального максимуму чи прийшли негативні сигнали (ризик/режим/подія) — припиняємо ескалацію, а при потребі знижуємо TP до попереднього рівня або фіксуємо.

Тлумачення ROI ($):
- Для LONG: ROI_usd ≈ (mark_price − entry_price) × qty × contract_size − fees.
- Для SHORT: ROI_usd ≈ (entry_price − mark_price) × qty × contract_size − fees.
- Реальне значення беремо з поточної підсистеми PnL/position_tracking (не дублюємо обчислення, лише споживаємо).

---

## 2) Новий домен: «confidence» (подієва впевненість)

Призначення: незалежний домен, який агрегує ринкові ознаки, події та сигнали (в т.ч. з `reward_engine_v3plus`) і повертає рекомендації щодо просування TP між фіксованими ROI‑ступенями.

Пропонована структура: `apps/reference/domains/confidence/`
- `contracts.py` — типи/енуми (Pydantic):
  - `ConfidenceEvaluationRequest` (position_id, symbol, side, entry_price, qty, roi_steps, current_step, market_snapshot, regime, risk_score, events, alpha_preds, ts)
  - `ConfidenceEvaluationResult` (p_up ∈ [0,1], decision: HOLD_NOW|ADVANCE_STEP|TAKE_PROFIT_NOW, next_target_usd?, why_code?, features)
  - `StepPolicy` (mapping поріг→θᵢ, timeouts, retrace_bps, max_hold_bars, cooldown)
  - `ConfidenceEventType` (перелік подій, узгоджений з подієвою моделлю)
- `engine.py` — `ConfidenceEngine` (агрегує сигнали → p_up, деталі нижче)
- `policy.py` — `SteppedRoiPolicy` (впроваджує правила ескалації/зупинки)
- `service.py` — `ConfidenceService` (обробка подій/кеш стану на позицію; API для FSM)
- `adapters/` — тонкі адаптери до існуючих доменів (decision_making, execution_position, regime_detector, risk_management)
- `logger.py` — окремий логгер/метрики (telemetry hooks)

Джерела даних (read‑only):
- `decision_making` — alpha‑сигнали/ймовірності/напрямок
- `regime_detector` — контекст режиму (TREND_UP/DOWN, HIGH_VOLATILITY тощо)
- `risk_management` — інтегральний risk_score й алерти (крос‑валідація)
- `position_tracking` — equity/позиції/ROI ($), локальний максимум ціни від входу (для retrace‑правила)
- `reward_engine_v3plus` — подійні інтенсивності (Event component) і/або risk_reward

Вихід домену (`ConfidenceAdvice`):
- `action`: HOLD_NOW | ADVANCE_STEP(to=Tᵢ₊₁) | TAKE_PROFIT_NOW(at=Tᵢ)
- `p_up`, `threshold`, `valid_until_ts`, `why_code`, `features_dump`

---

## 3) Використання наявних файлів reward_engine як «материнського ядра»

Замість прямої інтеграції «в лоб» — робимо адаптер:
- Використовуємо `alysha_core/reward_engine_v3plus/components/event.py`, `risk.py`, `risk_reward.py` для одержання ознак/інтенсивностей подій.
- `engine.py` домену `confidence` просить в адаптера обчислити набори ознак (feature_vector) і повертає агрегований `p_up`.
- Після стабілізації логіки — переносимо мінімально потрібні частини в домен `confidence`, і видаляємо `reward_engine_v3plus` з репо (за окремим PR; з тестами на регресію).

Причина: це дає чисті межі доменів, не змішує «reward» та «confidence», і спрощує подальшу еволюцію/тестування.

---

## 4) Інтеграційні точки з поточною архітектурою

Ключові вузли (реперні файли для орієнтування):
- `apps/reference/domains/decision_making/decision_making.py` — генерація EVT:TRADE_INTENT_PROPOSED
- `apps/reference/domains/execution_position/fsm.py` — оркестрація Open/Manage/Close
- `apps/reference/domains/execution_position/fsm_manage.py` — керування SL/TP, трейлінг, стани TRACKING/BRACKETS_*
- `apps/reference/domains/execution_position/contracts.py` — валідація TP/SL, правила Binance (-2021, workingType)
- `apps/reference/main.py` — мост AuroraBridge і реєстрація слухачів подій

Рекомендований механізм:
- Додати «confidence‑gate» на рівень `ManageFlowFSM` перед постановкою/оновленням TP.
  - На події досягнення ROI‑порогу (визначаємо за PnL/позицією) — `ManageFlowFSM` викликає `ConfidenceService.evaluate(request)`.
  - За результатом: `ADVANCE_STEP` → «пересунути TP» на наступний поріг; `HOLD_NOW`/`TAKE_PROFIT_NOW` → поставити/залишити TP на поточному рівні.
- Подієва шина (FSM bus):
  - `CMD:CONFIDENCE_EVAL_REQUEST(position_id, step, roi_usd)`
  - `EVT:CONFIDENCE_EVALUATED(position_id, p_up, step, decision, next_target?)`
  - Для сумісності — пряме синхронне API у `ManageFlowFSM` (без складного брокера) + емісія EVT для ланцюжка подій/логів.

Перевага цієї точки інтеграції: ми не зачіпаємо `DEC:OPEN`/вхід у позицію та не ризикуємо з «гоночними» умовами на відкритті. Зміни локалізовані у керуванні TP/SL.

---

## 5) Конфігурація (YAML) і фічефлаги

Додати секцію до `config/aurora/trading.yaml`:

```yaml
trading:
  execution:
    manage:
      confidence_gate:
        enabled: false           # починаємо у shadow‑режимі
        mode: shadow             # shadow|active
        steps_usd: [1.20, 2.20, 3.20]   # глобальні дефолти
        per_symbol_overrides: {}        # {SYMBOL: [..]}
        min_confidence:
          step_1: 0.60
          step_2: 0.70
          step_3: 0.80
        retrace_bps_cancel: 35         # відкат від локального максимуму для скасування ескалації
        max_hold_bars: 10              # щоб не висіти безкінечно
        timeout_ms: 150                # budget на eval, інакше фолбек
        risk_hard_gate:
          max_risk_score: 0.85         # якщо вище — заборонити ескалацію
        weights:                        # простий rule‑based aggregator (за замовчуванням)
          alpha_conf: 0.35
          regime_conf: 0.20
          momentum: 0.15
          reward_event_pos: 0.15
          reward_event_neg: -0.25
```

Примітки:
- `enabled=false`, `mode=shadow` — за замовчуванням не впливає на торгові рішення, лише логує.
- По мірі валідації вмикаємо `active` для окремих символів (через overrides).

---

## 6) Алгоритм оцінки p_up (ConfidenceEngine)

Проста й надійна базова версія (без ML):
- Ознаки x:
  - `alpha_conf` (з DecisionMaking/моделей) — нормалізована оцінка апсайду.
  - `regime_conf` (з regime_detector) — тренд/волатильність, унітарна вага.
  - `momentum` (короткострокова) — знак і величина останнього імпульсу.
  - `reward_event_pos` — позитивні події (trend‑confirming, volume‑surge), від 0..1.
  - `reward_event_neg` — негативні події (ARCE_ALERT, model_uncertainty, liquidity_shortage), 0..1 з від’ємною вагою.
  - `risk_score` (з risk_management) — використовується як hard‑gate: якщо > порога — p_up обнуляємо або зменшуємо.
  - `drawdown_from_high_bps` — якщо великий локальний відкат → штраф p_up.
- Агрегація: `raw = Σ wᵢ · xᵢ`; `p_up = clip(σ(raw + b), [0,1])` або проста лінійна нормалізація з сечею.
- Порівняння з θᵢ з `StepPolicy` для рішення.

Це детерміністично, прозоро для аудиту й безпечне на першому етапі. Далі можна замінити на ML‑класифікатор, не змінюючи контрактів.

---

## 7) Зміни у ManageFlowFSM (мінімальні, безпечні)

У `apps/reference/domains/execution_position/fsm_manage.py`:
- Додати «check‑gate» перед встановленням/оновленням TP, який:
  1) Визначає поточний ступінь за ROI ($) і найближчий поріг Tᵢ.
  2) Формує `ConfidenceEvaluationRequest` та викликає `ConfidenceService.evaluate()`.
  3) На `ADVANCE_STEP` — викликає існуючу логіку оновлення TP на Tᵢ₊₁ (через вже наявні хелпери з валідаціями (-2021, workingType, offset_bps)).
  4) На `HOLD_NOW`/`TAKE_PROFIT_NOW` — утримує/заставляє TP = Tᵢ.
- Всі помилки/таймаути → фолбек «як сьогодні» (без зміни поведінки) і інкремент метрик.

Важливо: зберегти атомарність/ідемпотентність при оновленні/скасуванні TP (врахувати `oco_emulation`, `atomic_close` в конфігу; використовувати вже існуючі ідентифікатори `client_order_id` + `IdempotentCancelHelper`).

---

## 8) Події/журналювання/метрики

- EVT:
  - `EVT:CONFIDENCE_EVALUATED`: {position_id, step, p_up, θᵢ, decision, next_target?}
  - `EVT:CONFIDENCE_STEP_ADVANCED`: {position_id, from: Tᵢ, to: Tᵢ₊₁, why_code}
  - `EVT:CONFIDENCE_FALLBACK`: {position_id, reason: timeout|error|risk_gate}
- Метрики:
  - `confidence_evals_total`, `confidence_advances_total`, `confidence_fallbacks_total`
  - `avg_hold_bars`, `avg_gain_from_advance` (оцінка доданої вартості)
- Логи: breadcrumbs у `event_chain` + окремий `confidence_logger` (debug‑трасування ознак/ваг для прозорості).

---

## 9) Ризики, труднощі та як їх обійти

- Binance інваріанти (‑2021 «would immediately trigger», workingType):
  - Використовуємо існуючі валідації `TPSLValidationRules` та `offset_bps`, `MARK_PRICE` за замовчуванням.
- Немає справжнього OCO на ф’ючерсах:
  - Вмикаємо/поважаємо `oco_emulation: true` та «atomic close». На просуванні TP → прибираємо попередній TP і ставимо новий; SL незмінний.
- Гоночні умови між станами BRACKETS_PENDING/PLACED/EMIT_DEC_ADJUST:
  - Гейт викликати лише у стабільних станах (TRACKING/BRACKETS_PLACED). Інші — відкладати (дефер) в коротку чергу FSM.
- Невизначеність/збої джерел даних:
  - Таймаут `timeout_ms`, фолбек «без змін».
  - Якщо нема alpha/regime — використовуємо скорочений вектор x та підвищуємо θ.
- Перетримка позиції/просідання:
  - `retrace_bps_cancel`, `max_hold_bars`, hard‑gate по `risk_score`.
- Ідемпотентність і WAL‑сумісність:
  - Усі рішення фіксуємо EVT у WAL; `client_order_id` з префіксом, наприклад `CONF`.

---

## 10) Покроковий план впровадження (з мінімальним ризиком)

Фаза A — ізольована побудова (shadow):
1. Створити домен `confidence/` з `contracts.py`, `engine.py`, `policy.py`, `service.py`, `adapters/`.
2. Додати адаптер до `reward_engine_v3plus` (читання подій/ознак без side‑effects).
3. Додати конфіг `trading.execution.manage.confidence_gate` (disabled + shadow).
4. Написати unit‑тести на `policy` і `engine` (штучні дані).
5. Підключити `ConfidenceService` до bus (слухати оновлення портфелю/режиму/маркету) і логувати `EVT:CONFIDENCE_EVALUATED` без впливу на FSM.

Фаза B — інтеграція з ManageFlowFSM (active‑behind‑flag):
1. У `fsm_manage.py` додати виклик `ConfidenceService` «перед виставленням/оновленням TP».
2. Якщо `enabled=true` і `mode=active` → застосовувати рішення; інакше лише логувати.
3. Додати метрики та короткий дебаг‑лог у `event_chain` з `why_code`.
4. E2E‑тести на симуляторі (`simulated_adapter`) з різними сценаріями: «ескалація», «відкат», «ризик‑gate».

Фаза C — стабілізація та міграція ядра:
1. Зібрати статистику «доданої вартості» від ескалацій (на тестнет/реплей).
2. Якщо якірна якість досягнута — скопіювати мінімальний піднабір логіки з `reward_engine_v3plus` до домену `confidence`.
3. Видалити `alysha_core/reward_engine_v3plus` з репозиторію (окремий PR), оновити тести.

---

## 11) Причинно‑наслідкові зв’язки й гарантії безпеки

- Переоцінка на порозі Tᵢ з вищим θᵢ → скорочення частки «зайвих» ескалацій при зростанні.
- Обов’язковий SL і незмінність SL при ескалації TP → контроль даунсайду не погіршується.
- Retrace‑stop для ескалації → обмеження ризику від «перетримки».
- Shadow‑режим і фічефлаг → інтеграція без каскаду помилок; при будь‑якій помилці — збереження поточної поведінки.
- WAL‑логування рішень → детермінованість і відтворюваність для аудиту.

---

## 12) Мінімальні зміни коду (оглядово)

- НОВЕ: `apps/reference/domains/confidence/` (+ unit‑тести в `tests/`)
- ЗМІНИ: `apps/reference/domains/execution_position/fsm_manage.py`
  - «confidence‑gate» хук перед постановкою/оновленням TP; обробка результатів/таймауту.
- ЗМІНИ: `config/aurora/trading.yaml`
  - Секція `trading.execution.manage.confidence_gate` (feature flag + параметри).
- ОПЦІЙНО: `apps/reference/main.py`
  - Реєстрація сервісу/слухачів подій (якщо використовуємо bus‑події для тіньового журналювання).

---

## 13) Подальші покращення

- Динамічні (pct) кроки замість фіксованих $ або гібрид: $‑кроки з мінімальним %‑порогом.
- Байєсівський апдейтер p_up із урахуванням історичної «правдивості» моделей.
- Персоналізація θᵢ по режимам ринку й символам (автокалібрування).
- Легка ML‑модель (logit/XGBoost) за незмінних контрактів — заміна rule‑based ядра.

---

## 14) Підсумок

Запропонований домен «подієвої впевненості» додається у керування відкритою позицією на етапі TP, мінімально й безпечно інтегрується у `ManageFlowFSM`, використовує наявну подієву/ризикову інфраструктуру та файли `reward_engine_v3plus` як джерело ознак. Поетапне розгортання (shadow → active) і жорсткі фолбеки гарантують відсутність каскадних помилок та спрощують аудит поведінки.

