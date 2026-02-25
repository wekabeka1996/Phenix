# Архітектурний Аудит: Домен Risk Management

**Дата аудиту:** 24 лютого 2026 р.
**Об'єкт аудиту:** Домен `risk_management` (`risk_management.py`, `daily_gate.py`, `schemas/risk_assessment_v1.json`)

Цей документ містить вичерпний архітектурний аудит домену управління ризиками, здійснений з позицій ключових інженерних ролей.

---

## 1. Експертна оцінка з 4-х ролей (Deep Criticism)

### 📈 Senior Quantitative Risk Manager
* **Математична точність (Decimal):** Використання `decimal.Decimal` у `daily_gate.py` (`_d()`, `_fmt_usd()`, `_fmt_pct()`) є правильним кроком для фінансових систем, щоб уникнути помилок рухомої коми. Проте, метод `_to_dec(x)` у `risk_management.py` та `_d(x)` "ковтають" винятки (`InvalidOperation`, `ValueError`) і повертають `Decimal("0")`. Якщо вхідна ціна (`price`) пошкоджена, це призведе до обнулення, а наступний розрахунок `%` зміни ціни може спричинити `ZeroDivisionError` (хоча є перевірка `price <= 0`).
* **Модель скорингу ризику:** Формула `risk_score = (delta_price_pct * w1 + abs(obi) * w2 + abs(tfi) * w3 + (1-absorption) * w4)` є простою лінійною комбінацією, затиснутою в діапазон `[0, 1]`. 
* **Невідповідність Контрактів (КРИТИЧНО):** Схема `risk_assessment_v1.json` жорстко вимагає наявності полів `kelly_fraction`, `cvar_limit_usd` та `max_drawdown_percent` у масиві `risk_parameters`. Однак код емітує лише `is_trading_allowed` та `risk_score` (посилаючись на те, що інші параметри розраховує `DecisionMaking`). Це призведе до **провалу валідації схеми** на рівні `FSMCore`.

### 🛡️ SRE / Reliability Engineer
* **Fail-Closed Стратегія:** 
  - Реалізація `try...except` у `on_features_calculated` з поверненням `{"is_trading_allowed": False, "reason": "RISK_INTERNAL_ERROR"}` працює ідеально з точки зору Fail-Closed.
  - У `DailyRiskState.can_open()` перевірка `if self._equity_open <= 0 or self._equity_now <= 0:` надійно блокує торгівлю, якщо портфельні дані ще не надійшли.
* **Стійкість Збереження Стану (State Persistence):** Використання тимчасового файлу (`.tmp`) з подальшим `replace()` у `_save_state()` є хорошою практикою для уникнення пошкодження файлу під час аварійного завершення.
* **Amnesia Leak (Втрата пам'яті):** Якщо файл стану `data/risk_gate_state.json` стає нечитабельним (корупція JSON), метод `_load_state()` викликає `self.reset()`. При наступному оновленні портфеля система встановить `_equity_open = _equity_now`. Якщо це станеться в середині дня після просадки на 15%, система **забуде просадку** і дозволить торгувати далі. Це прихований Fail-Open.

### 🏛️ vFoundation Architect
* **FSMCore & Message Protocol:** Домен правильно використовує `Message` і дотримується ортогональності через підписки на `EVT:FEATURES_CALCULATED`.
* **Розрив Why-Chain (КРИТИЧНО):** У `on_features_calculated` генерується новий `rid` (`rid = str(uuid.uuid4())`), і вхідний `event.rid` повністю ігнорується. Це **руйнує наскрізне трасування (Traceability)** системи. Події більше неможливо зв'язати від Alpha до Execution.
* **SSOT (Single Source of Truth):** Перевірка `isinstance(config, dict)` із підняттям помилки є зразковою імплементацією SSOT. Але пряма інстанціація `DomainConfigResolver` та `DailyRiskState` всередині `__init__` створює високу зв'язність (coupling).

### 🔒 Security & Compliance Auditor
* **Маніпуляція даними:** Збереження критичного стану (`risk_gate_state.json`) у звичайний файл відкриває вектор для локальної маніпуляції (Local Privilege Escalation). Зміна `reference_equity` у файлі дозволить обійти ліміти ризику. Для Compliance рівня BlackRock потрібне криптографічно підписане WORM сховище або Redis з ACL.
* **Debug Оверрайди:** `_debug_disable_daily_loss_limit` (Task 47). Хоча він емітує `EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE`, наявність цього коду у production-ready гілці створює ризик "людської помилки", коли неправильний конфіг розблокує торгівлю при збитках.

---

## 2. Оцінка за 10-бальною шкалою (Scoring)

| Критерій | Оцінка | Обґрунтування |
|----------|:------:|---------------|
| **Strictness of SSOT** | **9/10** | Відмова від словників (`dict`), жорстке використання `AuroraConfig`. Пряме звернення до властивостей (`config.domains.risk_management`). Відмінна строгість. |
| **Fail-Closed Integrity** | **8/10** | Загалом надійно, але конвертація `_to_dec(x)` у `0` при помилках та скидання `equity_open` при пошкодженні файлу знижують бал. |
| **Mathematical Precision** | **7/10** | Тип `Decimal` використовується повсюдно, але виявлена невідповідність між параметрами ризику у коді і обов'язковими полями JSON-схеми. |
| **Event-Driven Orthogonality**| **7/10** | Домен правильно реагує на події (не має прямих RPC-викликів до інших доменів), але емісія подій містить жорстко зашиті payload-структури. |
| **Observability & Traceability**| **4/10** | **Провал:** Перегенерація `rid` замість прокидання `parent_span_id` або використання оригінального `rid` руйнує розподілене трасування. |
| **Concurrency & Thread Safety** | **5/10** | Відсутні блокування (`threading.Lock`) у `DailyRiskState.on_portfolio()`. Можливий Race Condition при одночасному оновленні портфеля. |
| **Latency Impact (Hot Path)** | **6/10** | Синхронний запис у файл (`_save_state`) під час виклику `on_portfolio` може блокувати Event Loop, створюючи спайки Latency. |
| **Complexity & Maintainability**| **8/10** | Код розбитий на логічні класи (`RiskManagement` та `DailyRiskState`). Читабельність висока. |
| **Disaster Recovery** | **6/10** | Локальний файл. Не підтримує відновлення з глобального `WAL` (Write-Ahead Log), що вимагається Конституцією §8. |
| **Testability** | **9/10** | Наявність методу `test_risk_thresholds` та підтримка режиму `backtest` (без запису стану на диск) роблять систему легкою для тестування. |

---

## 3. Глибокий аналіз вразливостей та "вузьких місць"

### 🔴 Вузьке місце 1: Синхронний File I/O на Hot Path
Метод `DailyRiskState.on_portfolio()` викликає `_maybe_reset()`, який, у свою чергу, робить синхронний запис на диск `_save_state()` (open, write, replace). Якщо події `EVT:PORTFOLIO_STATE_UPDATED` надходять часто (наприклад, при кожній зміні Mark Price), це повністю заблокує GIL (або Event Loop, якщо використовується Async), що збільшить затримку обробки ринку для всього процесу.

### 🔴 Вузьке місце 2: Schema Validation Crash
Схема `risk_assessment_v1.json` вимагає (required):
```json
"required": ["kelly_fraction", "cvar_limit_usd", "max_drawdown_percent", "is_trading_allowed"]
```
Але метод `_calculate_risk_parameters` повертає лише:
```python
return {
    "is_trading_allowed": is_trading_allowed,
    "risk_score": float(risk_score)
}
```
Якщо в `FSMCore` увімкнено `SchemaValidator` (Phase 14), кожна емітована подія `EVT:RISK_ASSESSMENT_COMPLETED` буде відкинута як невалідна, повністю паралізуючи систему рішень.

### 🔴 Вузьке місце 3: Розрив Причинно-Наслідкового Ланцюга
```python
# У методі on_features_calculated
rid = str(uuid.uuid4())
```
Це грубе порушення `Constitution v2.2 §9.2` (Distributed Tracing). `rid` повинен передаватися з вхідного `event`, щоб можна було відстежити `why_chain` від генерації фічів до відкриття ордера.

### 🔴 Вузьке місце 4: State Amnesia (Amnesia Leak)
У `_load_state()`:
```python
except Exception:
    # Corrupt state → fail-closed reset (and drop the bad file)
    ...
    self.reset()
```
Наступний `on_portfolio` побачить, що `self._equity_open <= 0`, і перезапише `self._equity_open = self._equity_now`. Якщо це трапилось о 15:00 UTC після збитку в -10%, система забуде про цей збиток і дозволить ще -10% просадки. Це прихований Fail-Open стан.

---

## 4. 🔍 Глибокі знахідки (Deep Follow-up Findings)
*   **Маскування помилок конфігурації:** У `risk_management.py` метод `_to_dec(x)` ловить `InvalidOperation` та повертає `Decimal("0")`. Це перетворює пошкоджені або відсутні вхідні фічі на "нульовий ризик", що є антипатерном (помилки даних повинні призводити до Fail-Closed, а не до ігнорування).
*   **Сумнівна метрика ризику (Risk Score):** Обчислення `risk_score` базується на `abs(delta_price) / price`. Для низьколіквідних інструментів або під час прострілів (flash crashes) ця формула може давати аномальні викиди, оскільки не використовує логарифмічну прибутковість або згладжену волатильність.
*   **Відсутність потокобезпеки (Thread Safety):** `DailyRiskState.on_portfolio` змінює стан і викликає `_save_state()`. Оскільки немає `threading.Lock`, одночасне надходження оновлень портфеля може пошкодити JSON-файл або призвести до стану перегонів (Race Condition).
*   **Порушення Single Responsibility:** У класі `RiskManagement` міститься метод `test_risk_thresholds`. Доменна бізнес-логіка не повинна містити в собі фреймворк для власного юніт-тестування.

---

## 5. Рекомендації по покращенню (Action Plan)

### 🚀 Короткострокові (Quick Wins)
1. **Виправити Trace ID (RID):**
   Видалити `rid = str(uuid.uuid4())` та використовувати `event.rid` для емітованої події, щоб зшити `why_chain`.
2. **Синхронізувати Схему та Код:**
   Оновити `risk_assessment_v1.json`, зробивши `kelly_fraction` та інші параметри опціональними, або наповнювати їх у Payload (наприклад, через Pydantic-моделі).
3. **Додати Threading Lock у `DailyRiskState`:**
   Створити `self._lock = threading.Lock()` та обгорнути виклики `on_portfolio` та `_save_state`, щоб запобігти Race Conditions.

### 🏗️ Стратегічні (Architecture Shifts)
1. **DR & State Persistence (Згідно Constitution §8):**
   Вилучити локальний JSON файл для `risk_gate_state.json`. Замість цього інтегрувати стан з розподіленим `RedisIdempotencyStore` або `WAL`. Це дозволить системі надійно підніматись після збоїв та уникне "Amnesia Leak".
2. **Асинхронний I/O або Throttling:**
   Якщо стан має зберігатися локально, винести I/O операції в окремий бекграунд-потік або робити `_save_state()` лише при значній зміні Equity (наприклад, > 0.1%), щоб не навантажувати Hot Path на кожному тіку портфеля.
3. **Строга типізація Payload (Phase 14C):**
   Замість формування сирих словників (`payload = {"symbol": symbol, ...}`), створити Pydantic модель `RiskAssessmentPayload` у `vfoundation/core/payloads.py` та формувати подію через неї. Це гарантуватиме відповідність контракту ще до серіалізації.