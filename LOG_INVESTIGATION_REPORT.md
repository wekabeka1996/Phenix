# Звіт про глибоке дослідження логів та архітектурний аудит системи Phenix

## 1. Вступ та Методологія
Було проведено сканування та фільтрацію всіх лог-файлів у директорії `logs/` (понад 50 файлів `.log`). Було знайдено тисячі записів, які для зручності аналізу були дедубльовані та очищені від рутинного спаму (наприклад, циклічні повідомлення `live_tail`, відсутність фічей `ta_ensemble`).

Нижче наведено вичерпний аналіз унікальних критичних помилок та попереджень, визначення причинно-наслідкових зв'язків (Causal Chains) та ідентифікація легасі-коду і протиріч.

---

## 2. Критичні помилки та Помилки (CRITICAL / ERROR)

### 2.1. `CRITICAL - ALERT: Risk Gate Violation - Risk gate at 92.0% exceeds threshold 80%`
* **Джерело:** `decision_making.DecisionMaking.alerts` (domain_decision_making.log)
* **Суть:** Система блокує понад 90% всіх намірів (intents) на торгівлю.
* **Причинно-наслідковий зв'язок:** Спричинено масовими відхиленнями з боку гейтів: `REGIME_GATE_BLOCKED` (режим ринку не дозволено), `FLIP_GATE_UNKNOWN` (невідомий стан фліпу) та `FLIP_ORCHESTRATION: BLOCK` (спроба пірамідингу в той самий бік). 
* **Аналіз:** Це захисний механізм, який працює як задумано, але така висока кількість відхилень свідчить про розсинхронізацію між генерацією сигналів (strategy/alpha) та системою виконання (decision making). Стратегія постійно "спамить" сигналами, які апріорі є невалідними з точки зору поточного стану виконання (наприклад, пропозиція SELL, коли вже відкритий SHORT).

### 2.2. `ERROR - WebSocket error: No PONG received after 10.0 seconds / ConnectionTimeoutError`
* **Джерело:** `market_data_worker` (aurora_market_data.log)
* **Суть:** Втрата з'єднання з Binance WSS через відсутність відповіді PONG.
* **Причинно-наслідковий зв'язок (КРИТИЧНО):** Це є прямим наслідком архітектурного дефекту в `vfoundation/dr/wal.py`. Синхронні виклики `os.fsync` всередині асинхронного Event Loop (`asyncio`) блокують потік виконання. `market_data_worker` не встигає обробити пінг-понги фреймів WebSocket, що призводить до обривів з'єднання.
* **Протиріччя:** Блокуюче I/O в асинхронному циклі порушує базові принципи побудови високопродуктивних торгових ядер. Це фундаментальний баг платформи.

### 2.3. `ERROR - Failed to emit exposure update event: Payload validation failed for EVT:EXPOSURE_SUMMARY_UPDATED: 'exposure_summary' is a required property`
* **Джерело:** `execution_position.exposure_manager` (domain_execution_position.log)
* **Суть:** Pydantic суворо блокує генерацію подій, оскільки не передається обов'язкове поле `exposure_summary`.
* **Причинно-наслідковий зв'язок:** Результат впровадження Phase 6 виконання кордонів (execution boundary closures). Система стала суворішою (`extra="forbid"`), і старий неякісний код в `exposure_manager` тепер не може проковтнути неповний payload. Подія не створюється.
* **Легасі:** Адаптер генерує подію старим способом (через `kwargs`), ігноруючи нові суворі контракти.

### 2.4. `ERROR - ❌ PLACE_ORDER failed: [-1111] Precision is over the maximum defined for this asset`
* **Джерело:** `execution_position.close_executor` (domain_execution_position.log)
* **Суть:** Біржа відхиляє ордер на закриття через те, що кількість знаків після коми в ціні або об'ємі перевищує ліміт біржі.
* **Причинно-наслідковий зв'язок:** Баг нормалізації в модулі закриття. Часто пов'язаний із дублюванням параметрів (`positionAmt` проти `position_amount`). Нормалізатор опрацьовує старе поле, а ордер формується з необробленого, що призводить до відправки "сирих", не округлених значень на біржу (наприклад, після часткових виконань або обчислення комісій).

### 2.5. `ERROR - Orphan cleanup failed: 1 validation error for Message`
* **Джерело:** `order_guardian` (order_guardian.log)
* **Суть:** Помилка валідації Pydantic під час спроби очистити залишені/завислі (orphan) ордери.
* **Причинно-наслідковий зв'язок:** `OrderGuardian` намагається напряму створити `Message` або `CancelSubmissionRawPayload` старим методом `cleanup_before_close()` або `cleanup_orphans()`, минаючи нові типізовані адаптери (Package 10/11), що порушує суворі контракти SSOT. Це яскравий приклад легасі-порушення кордонів архітектури (Phase 6).

---

## 3. Попередження (WARNING)

### 3.1. `WARNING - NRR-EXECUTION-NO-DOWNSTREAM-EVENT - XRPUSDT buy (trade_intent_boundary_audit:no_downstream_event)`
* **Джерело:** `execution_position.fsm.IntentBoundaryAudit` (aurora_trades.log)
* **Суть:** Торговий намір був прийнятий системою виконання, але не згенерував жодної наступної події.
* **Причинно-наслідковий зв'язок:** Як виявлено під час аудиту `vfoundation`, файл `core/fsm_emit_compat.py` має дефект: конструкція `except TypeError` "ковтає" легітимні помилки всередині слухачів подій. Код падає, помилка приховується, і FSM опиняється у стані "розщеплення свідомості" (split-brain) без логування падіння.

### 3.2. `WARNING - LEVERAGE_SSOT_MISMATCH: [...] target=35 != instruments.execution.target_leverage=25 (SSOT is instruments.yaml, strategy value is IGNORED)`
* **Джерело:** `leverage_config` (domain_execution_position.log)
* **Суть:** Виявлено конфлікт конфігурацій кредитного плеча між старою конфігурацією стратегії та новим єдиним джерелом істини (SSOT).
* **Легасі/Протиріччя:** Старі стратегії (`aurora`, `mean_reversion`) все ще зберігають власні параметри плеча. Завдяки правилу домену (YAML + Pydantic = SSOT), система коректно ігнорує легасі-значення та використовує `instruments.yaml`.

### 3.3. `WARNING - IDEMPOTENT_CANCEL: getOrder pre-check failed: [-1102] Mandatory parameter 'orderid' was not sent`
* **Джерело:** `execution_position.fsm` (domain_execution_position.log)
* **Суть:** FSM намагається скасувати ордер, але `orderid` дорівнює `null` або порожній.
* **Причинно-наслідковий зв'язок:** Можливо, ордер ще не отримав ідентифікатор від біржі (затримка мережі, асинхронність), або ідентифікатор було втрачено під час перезапуску процесу (DEF-005 restart identity edge cases). Система робить спроби скасувати "повітря", що витрачає API-ліміти.

### 3.4. `WARNING - TASK47c-E: OpenFlowFSM initialized without LeverageService. Leverage verification will be SKIPPED`
* **Джерело:** `execution_position.fsm_open` (domain_execution_position.log)
* **Суть:** В ініціалізації відсутній сервіс перевірки маржі.
* **Легасі:** Це залишок старого або shadow-режиму, де справжня перевірка була тимчасово вимкнена. Може бути небезпечно, якщо цей код потрапить у продакшн без відповідної заміни.

---

## 4. Висновки: Архітектурні протиріччя та причини

На основі проаналізованих логів вимальовуються кілька основних дефектних ланцюгів у системі, що підлягають негайному вирішенню (згідно з Phase 6 MetaFSM2 roadmap):

1. **Ізоляція виконання та Блокуючий цикл (Fundamental Architectural Contradiction):**
   Наявність `os.fsync` всередині WAL (`dr/wal.py`) в асинхронному циклі — критична помилка, що руйнує WebSocket-з'єднання (`No PONG received`). Це порушує базовий концепт асинхронного FSM і створює ризик "зависання" всього ядра під час інтенсивного I/O.
2. **Тихе поглинання виключень (Masking Layer):**
   Логи `NRR-EXECUTION-NO-DOWNSTREAM-EVENT` показують, що FSM здатна розірвати ланцюг обробки ордеру без жодного `Traceback`. Це пов'язано з `fsm_emit_compat.py` (`except TypeError`), який маскує реальні падіння як "неуспішний еміт події". Суперечить правилу `Phenix domain laws: Fail closed when evidence is insufficient or contradictory`.
3. **Легасі кордонів модулів (Phase 6 Strangler Fig leaks):**
   Помилки валідації Pydantic (наприклад, `1 validation error for Message` в Order Guardian або відсутність `exposure_summary` в Exposure Manager) свідчать про те, що старий нетипізований код намагається напряму спілкуватися з новою, суворою шиною подій. Цей код має бути переписаний з використанням нових "швів" (typed seams - Package 11).
4. **Помилки нормалізації (Precision Error):**
   `-1111 Precision is over the maximum` при закритті є наслідком технічного боргу: дублювання змінних `positionAmt` та `position_amount`. Відсутність єдиної точки нормалізації призводить до того, що на біржу відправляються флоати типу `0.1000000000001` замість `0.1`.
5. **Спам генератора стратегій:**
   Надлишок блокувань від Risk Gate (понад 90%) та помилки `FLIP_ORCHESTRATION: BLOCK` показують, що стратегії генерують односпрямовані наміри (наприклад, SELL після SELL) без урахування існуючого стану позиції.

Усі ці проблеми підтверджують поточний стан завдання: перед продовженням міграції MetaFSM2 необхідно усунути **8 критичних фундаментальних багів у `vfoundation`**, вирішити **дублювання positionAmt/position_amount**, та завершити типізацію викликів `OrderGuardian` (Package 11).