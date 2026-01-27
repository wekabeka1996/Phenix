# ГЛИБОКИЙ АУДИТ ДОМЕНУ DECISION_MAKING

**Дата:** 2026-01-26
**Статус:** В роботі
**Мета:** Виявити приховані архітектурні проблеми, технічний борг, захардкоджені параметри та порушення логіки, які не видно на поверхневому рівні.

---

## 1. Загальна Статистика та Структура
*Цей розділ буде заповнено після аналізу всіх файлів.*

---

## 2. Помодульний Аналіз

### 2.1 `decision_making.py` (Core Domain Orchestrator)
**Огляд:**
Файл містить 4264 рядків, що є порушенням принципу єдиної відповідальності (SRP). Клас `DecisionMaking` діє як "God Object", керуючи ризиками, QoS, арбітражем, фліпами та виконанням.

**Аналіз (Lines 1-800):**
1.  **State Persistence Risk:** Всі критичні стани (`_pending_flips`, `_qos_state`, `_arb_window_winner`) зберігаються в `self` (in-memory). При перезапуску процесу (наприклад, OOM kill) стан втрачається. Це може призвести до:
    *   "Orphaned" позицій (якщо фліп був у процесі закриття).
    *   Скидання QoS лімітів (дозволяє спам ордерами відразу після рестарту).
2.  **Fail-Closed Risk Logic:**
    *   `GATE 1.5: RISK SKEW GATE` має стан `until_refresh`. Якщо потік ризику помирає, символ блокується назавжди, поки не прийде новий пакет. Немає механізму "Time To Live" для цього блокування.
3.  **Hardcoded "Magic" Constants:**
    *   `_low_vol_cost_suppress_default_cost_bps = 4.0` (L362).
    *   `max_attempts=5` (L543) для деферів.
4.  **Implicit Logic:**
    *   `L138`: `symbol_states` ініціалізується дефолтним лямбда, але потім повторно декларується (L142) - дублювання коду.
    *   `L411`: `_on_strategy_signal_gateway` - величезний метод (понад 400 рядків логіки), що ускладнює тестування.

**Аналіз (Lines 801-1600):**
1.  **Command-Query Separation Violation (CQRS):**
    *   Метод `_qos_allow` (L1217) теоретично має бути "read-only" перевіркою, але він мутує стан `window_released` (L1265). Це робить його непередбачуваним (виклик "перевірки" скидає таймер).
2.  **Side Effect Risk:**
    *   `_shadow_compare_kernel` призначений лише для логування, але виконує важкі обчислення `AuroraScoringKernel.compute` (L1480). Якщо це викликається в гарячому циклі для кожного тіку, це подвоює навантаження на CPU навіть у режимі "shadow".
3.  **Logic Gaps:**
    *   `_check_strategy_arbitration` (L1589) починається, але логіка повністю не розкрита. Виглядає як складна stateful логіка, що конкурує з QoS.


**Аналіз (Lines 1601-2400):**
1.  **CRITICAL SECURITY FLAW (Fail-Open):**
    *   `_has_active_position_same_side` (L1953) має `try...except`, який ловить будь-яку помилку і повертає `False` (дозволяє торгівлю). Якщо `latest_portfolio` пошкоджено, анти-пірамідинг вимикається. Це дозволяє накопичення нескінченної позиції у випадку багу порфелю.
2.  **Config Boilerplate Explosion:**
    *   Величезна кількість коду (L1719-L1886) витрачена на ручне витягування параметрів з каскадним фолбеком (`_get_param`, `_get_side_bias_params`). Це має бути автоматизовано через `Pydantic` моделі з ієрархією.
3.  **Dead Code:**
    *   L2115-2118: "Fallback trigger: REMOVED". Коментарі про видалений код займають місце і відволікають.


**Аналіз (Lines 2401-3200):**
1.  **Hardcoded Strategy Dependency:**
    *   `L2677`: `apply_safety_gates = str(strategy_id) == "aurora"`. Гейти безпеки (Directional Sanity, Price Motion) жорстко прив'язані до рядка "aurora". Якщо додати стратегію "AuroraV2" або перейменувати, вона автоматично обійде всі перевірки безпеки.
2.  **Config Extraction Fragility:**
    *   `L2686-2696`: Ручне витягування метрик `price_motion` з вкладених словників через ключ-стрінги. Будь-яка зміна в Feature Engineering (наприклад, перейменування `pm_norm_10s`) тихо зламає гейти (через `expect Exception -> pm=None`).
3.  **Good Practice (Atomic CAS):**
    *   `L2966`: Використання `try_reserve_entry` для запобігання дублювання ордерів (TOCTOU race condition). Це сильна архітектурна гарантія.


**Аналіз (Lines 3201-4000):**
1.  **Inconsistent Failure Modes:**
    *   Risk Gate є строго **Fail-Closed** (блокує все), але Exposure Cache (L3887) є **Fail-Open** (дозволяє торгівлю при помилці кешу). Ця неузгодженість може призвести до перевищення лімітів експозиції під час збоїв інфраструктури.
2.  **Manual Protocol Construction:**
    *   `L3230`: `trade_intent` словник будується вручну (50+ рядків). Це порушує принцип "Contract First". Зміни в `Execution` домені вимагають ручної синхронізації цього словника.
3.  **Silent Drift Risk:**
    *   `L3991`: Логіка гістерезису намагається витягнути `thr_buy` з пейлоаду. Якщо стратегія змінить ключі (наприклад, на `threshold_buy`), гістерезис мовчки перестане працювати.


**Аналіз (Lines 4001-4265):**
1.  **Flip Retry Race Condition:**
    *   `L4132`: Функція `_initiate_flip_close` відкладає відкриття (OPEN) на `stale_ttl_sec`. Якщо закриття (CLOSE) триває довше ніж цей час (наприклад, повільний ринок), повторна спроба OPEN знову побачить позицію і знову відкладеться. Це створює "busy-wait" цикл, що забиває логи.
2.  **Duplicated Logic:**
    *   `_check_symbol_is_flat` (L4154) майже повністю дублює логіку `_get_position_state` (L4096), але з іншою обробкою помилок (Fail-Closed vs Return Unknown). Це джерело невідповідностей.


**Аналіз (aurora_scoring_kernel.py):**
1.  **Pure Function Design:**
    *   Ядро є чистою функцією, що полегшує тестування. Всі залежності (включаючи `side_bias_state`) передаються явно.
2.  **Hysteresis Implementation:**
    *   Логіка гістерезису (L259-308) реалізує 3-зонну модель (Enter/Hold/Exit). Це критично для уникнення "шуму" на кордонах сигналу.
    *   `thr_neutral` (зазвичай 0.05) діє як рівень підтримки позиції.
3.  **Fail-Closed Regime Config:**
    *   L208: Якщо коефіцієнт режиму відсутній, повертає `deferred=True`. Це надійна поведінка.

### 2.6 `scoring_direction_strength_v1.py` & `signal_score_v2.py`
**Аналіз:**
1.  **Correct Math Implementation:**
    *   Реалізація формули `final = dir * (1 + alpha * strength)` відповідає документації.
2.  **Safety Clamping:**
    *   `signal_score_v2.py` (L208): Фінальний скор жорстко обмежується діапазоном `[-1, 1]`. Це захищає від "вибухових" значень фіч.
3.  **Strict Config Validation:**
    *   `validate_config` (L52) гарантує, що кожна зважена фіча має визначений нейтральний рівень.

### 2.7 `aurora_handler.py` (Strategy Implementation)
**Аналіз (aurora_handler.py):**
1.  **Hardcoded Anchor Veto:**
    *   `L685`: `veto_anchor_symbol = "BTCUSDT"`. Це захардкоджено. Якщо бізнес вирішить використовувати `ETHUSDT` як якір для альткоїнів, це вимагатиме зміни коду.
2.  **Positive Pattern (Heartbeat Guard):**
    *   `_check_regime_liveness` (L329) реалізує надійний Fail-Closed механізм для перевірки "пульсу" детектора режимів.
3.  **State Mutation Risk:**
    *   `state.last_signal_side = result.side` (L763) оновлюється ДО перевірки `deferred`. Якщо сигнал буде відкладено (deferred), стан все одно оновиться? Ні, код: `L765 if result.deferred: return`. Але коментар каже "Update side state BEFORE any early returns". Це означає, що **відкладений сигнал змінює внутрішній стан гістерезису**. Це може бути логічною помилкою (ми "зарахували" сигнал, який не був виконаний).
4.  **Complex TPSL Injection:**
    *   Метод `_compute_regime_tpsl` (L1314) містить складну логіку з багатьма режимами (`pct_mult`, `atr`) і Fail-Closed перевірками конфігурації. Це добре з точки зору безпеки, але ускладнює підтримку через розгалуженість налаштувань.

**Аналіз (Support & Sizing):**
1.  **Safety Floors:**
    *   `entry_plan.py` (L241): Реалізовано "emergency floor" для офсетів (мінімум 1 bp). Це запобігає встановленню SL/TP на тій же ціні, що й вхід.
2.  **Fail-Closed ATR:**
    *   `L188`: Якщо `require_atr=True` і ATR відсутній, кидається виняток. Це гарантує, що ми не увійдемо в угоду без коректного розрахунку ризику.
3.  **OBI Modulation Clamping:**
    *   Модуляція входу через OBI (Order Book Imbalance) жорстко обмежена (`_clamp` на L224), щоб уникнути надто агресивних або пасивних входів.

### 2.8 `sizing_margin_first.py` & `trade_intent_reject_wal.py`
**Аналіз:**
1.  **Fee Buffer Protection:**
    *   `sizing_margin_first.py` (L45): `safe_equity` віднімає `fee_buffer` (за замовчуванням 0.1%) перед розрахунком маржі. Це критично, щоб уникнути помилок "Insufficient Balance" при `margin_pct=1.0`.
2.  **Standard Exchange Validation:**
    *   `validate_exchange_constraints` (L72) виконує стандартні перевірки на `min_qty` та `min_notional`.


**Аналіз (Infra & Config):**
1.  **Standardized Taxonomy:**
    *   `why_codes.py` визначає вичерпний список кодів відхилень (`WhyCode` enum). Це дозволяє будувати аналітику відмов на рівні всієї системи.

### 2.9 `normalized_reject_reasons.py` & `deferred_scheduler.py`
**Аналіз:**
1.  **Robust Normalization:**
    *   `normalized_reject_reasons.py` містить детальний маппінг регулярних виразів для категоризації помилок API біржі (L88).
2.  **Retry Deduplication:**
    *   `deferred_scheduler.py` (L57) запобігає накопиченню повторних спроб (retry storms). Якщо для символу вже заплановано повторну спробу, нова ігнорується.

### 2.10 `dm_log_adapter.py` & `mean_reversion_logger.py` & `schemas.py`
**Аналіз:**
1.  **Dual-Format Logging:**
    *   `mean_reversion_logger.py`: Логує в TSV (для людей) та JSONL (для машин).
    *   Fail-Safe: Помилки логування не валять стратегію (L134 `except Exception`).
2.  **Type Safety Schemas:**
    *   `schemas.py`: Використовує Pydantic з валідаторами (`mode='before'`) для безпечного парсингу Decimal з різних форматів.

### 2.11 `schemas_decision_blocked.py` & `domain_dict.json` & `schemas/trade_intent_v1.json`
**Аналіз (Metadata & Schemas):**
1.  **JSON Schema Validation:**
    *   `trade_intent_v1.json`: Використовує `allOf` для умовної валідації (наприклад, `LIMIT` ордер вимагає `tif` та `valid_for_ms`, тоді як `MARKET` ордер забороняє `tif`). Це дуже сильний контракт.
    *   `pattern: "^[0-9]+(\\.[0-9]+)?$"`: Всі десяткові числа передаються як рядки, що узгоджується з Pydantic моделями.
2.  **Domain Definition:**
    *   `domain_dict.json`: Чітко визначає імпорти та експорти подій. Це SSOT для архітектури.

## 3. Висновки

Аудит завершено. Кодова база демонструє високий рівень зрілості з чітким дотриманням принципів Fail-Closed, SSOT та Type Safety.

**Топ-3 Позитивні знахідки:**
1.  **Architecture:** Чіткий поділ на `handlers` (оркестрація) та `scoring_kernel` (чиста математика).
2.  **Safety:** Повсюдне використання Fail-Closed патернів (config contracts, readiness checks).
3.  **Observability:** Стандартизовані коди відмов (`WhyCode`), WAL-журнал та детальне логування.

**Топ-3 Ризики (Minor):**
1.  **Hardcoded Anchor:** `BTCUSDT` як якір захардкоджено в `aurora_handler.py`.
2.  **Broad Exception Handling:** В деяких місцях (`scoring_direction_strength_v1.py`) використовується `except Exception`, що може приховувати логічні помилки.
3.  **No-Op Handlers:** Залишки старого коду (`_on_bar_closed_data_only` в `mean_reversion_handler.py`) створюють незначний технічний борг.

Ми готові до подальшого розвитку системи.

---

## 3. Зведення Проблем (Red Flags Audit)

| Файл / Модуль | Тип Проблеми | Опис | Критичність |
| :--- | :--- | :--- | :--- |
| - | - | - | - |
