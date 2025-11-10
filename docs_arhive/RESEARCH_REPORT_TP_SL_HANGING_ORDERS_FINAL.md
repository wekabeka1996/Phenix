# 🔍 Звіт-дослідження (READ-ONLY): «Висячі TP/SL» і «Порожні TP/SL після закриття позиції»

Дата: 2025-11-07
RID: RESEARCH_TP_SL_HANGING_ORDERS_071125
Статус: завершено (аналіз без змін коду)

---

## 1) Executive Summary

- Симптоми
  - Висячі TP/SL після закриття позиції (manual/market close).
  - Порожні TP/SL на 0‑й позиції (створені ретраєм або гонкою після CLOSE).
  - Margin leak: значення `totalOpenOrderInitialMargin` > 0 за відсутності позицій.
  - Періодичні відмови `-2021` (would immediately trigger) і `-4116` (duplicate clientOrderId).
- Головні корені
  - Відсутність повного cancel‑on‑close на рівні оркестрації (API не знімає TP/SL автоматично).
  - Гонки WS/REST: постановка/ретрай TP/SL під час або після фактичного закриття позиції.
  - Недостатній відступ/квантизація під `MARK_PRICE` → `-2021` → запізнілий ретрай на 0‑й позиції.
  - Необліковані дублі `newClientOrderId` → «фантомні» спроби.

---

## 2) Точки в коді (що перевіряти)

- apps/reference/domains/execution_position/fsm.py:904
  - Після ENTRY ACK виконує `get_open_orders(symbol)` і визначає `existing_sl`/`existing_tp` перед постановкою брекетів. Ризик — REST знімок може лагувати.
- apps/reference/domains/execution_position/fsm.py:930–980
  - Паралельна постановка SL/TP (`asyncio.gather`) і ретраї TP при `-2021` (+20 bps) з fallback у LIMIT reduceOnly. Ризик — повтор може відпрацювати на 0‑й позиції.
- apps/reference/domains/execution_position/fsm.py:687–701
  - DEC:CLOSE: скасовує тільки SL/TP, що відомі у `_symbol_brackets`. Невідомі/не відтрекинені брекети залишаються до orphan‑cleanup.
- apps/reference/domains/execution_position/fsm.py:1498+
  - `cleanup_orphaned_bracket_orders()`: періодичний/стартап‑скан і відміна orphan’ів. Якщо інтервал великий — «висячі» ордери існують довше.
- apps/reference/domains/execution_position/fsm_manage.py:210–280
  - `handle()`: розпізнавання ENTRY vs EXIT по `order_type|type|closePosition|reduceOnly`. Якщо у WS payload бракує ключів — ризик помилкової постановки нових брекетів.
- apps/reference/domains/execution_position/fsm_manage.py:312–437
  - `_place_brackets()`: постановка SL/TP після ENTRY. Потрібно враховувати стан «закриваємось», інакше можливі порожні TP/SL при гонках.
- apps/reference/domains/execution_position/fsm_manage.py:820–900
  - `_handle_bracket_fill()`: OCO‑емуляція (SL→скасувати TP і навпаки). При manual CLOSE не скасовує обидва — бо це не BRACKET_FILL.
- apps/reference/adapters/binance_adapter.py:291, 299, 742, 745, 769–778, 781, 805–814
  - Формування conditional payload (`closePosition=true`, `workingType=MARK_PRICE`, `priceProtect=true`, `newClientOrderId`). Перевірити відповідність розрахункам і обробку `-4116`.
- apps/reference/adapters/binance_adapter.py:314–374
  - `cancel_order()`: обробка `-2011` (Unknown order) з повтором, поведінка при symbol mismatch.
- apps/reference/domains/execution_position/utils.py:165, 216, 126
  - `calc_tp_sl_from_mark()`, `validate_not_immediate()`, `generate_client_order_id()`: анти‑2021 інваріанти, квантизація, стабільність CID.

---

## 3) План витягу артефактів із логів і READ‑API/WS (на 3–5 інцидентах)

- Таймлайни (мілісекунди) на RID:
  - ENTRY ACK/FILL → TP/SL POST (тип, `stopPrice`, `workingType`, `priceProtect`, `newClientOrderId`) → можливі `-2021/-4116` → retry (час) → момент, коли REST показує `positionAmt == 0` → факт `TP/SL PLACED` після цього.
- WS події (USER_DATA_STREAM):
  - `ORDER_TRADE_UPDATE`: поля `wt` (workingType), `cp` (closePosition), `pP` (priceProtect), `X` (execution status).
  - `CONDITIONAL_ORDER_TRADE_UPDATE`/`CONDITIONAL_ORDER_TRIGGER_REJECT`: текст `reason` на відмові (`-2021`).
- REST‑снапшоти навколо CLOSE:
  - `GET /fapi/v1/openOrders?symbol=SYMBOL` — до/після CLOSE: чи були масові відміни conditional.
  - `GET /fapi/v2/account` — `totalOpenOrderInitialMargin` на символи без позицій (margin leak).
  - `GET /fapi/v1/openOrder?symbol=SYMBOL&origClientOrderId=CID` — підтвердити «Order does not exist» (`-2011`).

Примітка: Зведіть 3–5 таймлайнів у секції «Результати», додаючи часові мітки з логів `logs/aurora_core.log`, `logs/order_log_v1.jsonl`, `event_chain.log` та з REST/WS журналів.

---

## 4) Гіпотези та чек‑лист перевірок

- H‑Cancel‑on‑Close:
  - Після будь‑якого CLOSE (manual/market) чи був повний cancel conditional ордерів по символу (через `openOrders`)? Якщо ні — «supply‑side orphan».
  - Де дивитися: fsm.py:687–701, fsm.py:1498+ (orphan cleanup конфіг/виклики).
- H‑WorkingType Drift:
  - Чи співпадає `workingType` у payload із джерелом розрахунку `stopPrice` (MARK_PRICE vs CONTRACT_PRICE)? Розбіжність ⇒ `-2021`.
  - Де дивитися: fsm_manage.py `_place_brackets()`, utils.py:165/216, binance_adapter.py:299/771/807.
- H‑Retry Race:
  - Чи є retry TP/SL після того, як `positionAmt == 0` (REST)?
  - Де дивитися: fsm.py:930–980 (ретраї TP), adapter — створення/повтор POST із `newClientOrderId`.
- H‑ID Ledger:
  - При `-4116` — чи повторно використовується `newClientOrderId`, чи одразу генерується новий без `GET /fapi/v1/openOrder`? Ризик «фантомних» спроб.
  - Де дивитися: binance_adapter.py:742/778/814.
- H‑Margin Leak:
  - У моменти блокувань чи завищений `totalOpenOrderInitialMargin` на символи без позиції?
  - Де дивитися: `GET /fapi/v2/account` + `openOrders`.

---

## 5) Що віддати (очікувані артефакти)

- 3–5 таймлайнів (мс) з кореляцією WS/REST/логів на RID.
- Таблицю «симптом → причина → місце в коді (файл:рядок/функція)».
- Список конкретних orphan‑ордерів: `orderId`, `clientOrderId`, `type`, `closePosition/reduceOnly`, `createTime`, `updateTime`, чому не були скасовані.
- Окремо кейси `CONDITIONAL_ORDER_TRIGGER_REJECT` з текстом `reason`.

Шаблон таблиці orphan‑ордерів:
- symbol | orderId | clientOrderId | type | closePosition | reduceOnly | createTime | updateTime | примітка (чому не скасовано)

---

## 6) Процесні рекомендації (без змін коду)

- Pre‑flight перед POST TP/SL:
  - REST `account` → `positionAmt != 0` для символа.
  - Для `MARK_PRICE`: перевірити, що `stopPrice` має достатній відступ від поточного mark (з урахуванням `tickSize`) — інакше логувати `TP_SL_SKIPPED_*`.
- Reconcile‑on‑Close:
  - Одразу після переходу FSM у FLAT — `GET /fapi/v1/openOrders?symbol=SYMBOL` і відміна всіх `STOP_MARKET/TAKE_PROFIT_MARKET` з `reduceOnly=true` або `closePosition=true` (операційна процедура/скрипт).
- Періодичний orphan‑cleanup (кожні 5 хв):
  - Скан `openOrders` по всіх символах із `positionAmt == 0` → відміна conditional.
  - Вести метрику `orphaned_brackets_total` і сумарну «залиплу» маржу.
- Backoff для `-2021`:
  - Максимум 2–3 ретраї з експоненційною затримкою; далі — інцидент і пауза ретраїв по символу.
- Ідемпотент‑ledger для `newClientOrderId`:
  - Для retry спочатку `GET /fapi/v1/openOrder?origClientOrderId=CID` — якщо існує/виконано, не створювати нові.

---

## 7) Матриця «симптом → причина → де в коді»

- TP/SL висять після manual close → немає повного cancel → apps/reference/domains/execution_position/fsm.py:687–701; fsm.py:1498+
- Нові TP/SL на 0‑й позиції → ретрай/гонка після CLOSE → fsm.py:930–980; apps/reference/adapters/binance_adapter.py:742/778/814
- ORDER_CANCELLATION_FAILED (`-2011`) → намагаємось скасувати вже відсутній ордер → apps/reference/adapters/binance_adapter.py:314–374
- `-2021` при створенні TP/SL → недостатній offset/квантизація → apps/reference/domains/execution_position/utils.py:165/216; fsm_manage.py `_place_brackets()`
- `-4116` duplicate → без перевірки існуючого ордера за CID → apps/reference/adapters/binance_adapter.py:742/778/814
- Margin leak → orphans не очищаються одразу → fsm.py:1498+ (cleanup)

---

## 8) Нотатки щодо спостережуваності

- Логувати ретраї: `TP_SL_RETRY_-2021`, `TP_SL_RETRY_-4116` (attempt, CID, ts).
- Заміряти WS‑lag: різниця `updateTime` Binance vs час обробки у listener’ах (`EVT:ORDER_ACK`/`EVT:ORDER_FILL`).
- Після `ORDER_TIMEOUT` — знімок `totalOpenOrderInitialMargin`, `openOrders count` по символу.
- Ledger по `newClientOrderId`: `{CID, symbol, side, notional, reason, ts}`.

---

## 9) Результати (заповнюється за підсумками витягу)

- Таймлайн 1 (RID=9165880d-cf80-4881-b642-2a4d4ab8b6db, symbol=BNBUSDT)
  - 1762537603830 ORDER_PLACED: client_order_id=ENTRY-a0d302dcb7, order_id=891919127
  - 1762537668064 ORDER_TIMEOUT: fill_timeout, client_order_id=ENTRY-a0d302dcb7, order_id=891919127
  - 1762537668579 ORDER_CANCELLATION_FAILED: order_id=891919127 (-2011 expected from adapter log)

- Таймлайн 2 (RID=9980aed7-ad57-44cd-9e85-8b37d7429528, symbol=ETHUSDT)
  - 1762537606889 ORDER_PLACED: client_order_id=ENTRY-3a11dea7c8, order_id=6866526798
  - 1762537668584 ORDER_TIMEOUT: fill_timeout, client_order_id=ENTRY-3a11dea7c8, order_id=6866526798
  - 1762537668889 ORDER_CANCELLATION_FAILED: order_id=6866526798

- Таймлайн 3 (RID=16611c5f-c9af-43cc-9133-aedc67853836, symbol=BTCUSDT)
  - 1762537630820 ORDER_PLACED: client_order_id=ENTRY-517dcc4372, order_id=9001747353
  - 1762537696050 ORDER_TIMEOUT: fill_timeout, client_order_id=ENTRY-517dcc4372, order_id=9001747353
  - 1762537696936 ORDER_CANCELLATION_FAILED: order_id=9001747353

- Таймлайн 4 (RID=950f2727-fb8b-4e70-a2e0-5a9d5b6730f4, symbol=SOLUSDT)
  - 1762537633197 ORDER_PLACED: client_order_id=ENTRY-ae1174f0c7, order_id=1281004265
  - 1762537696936 ORDER_TIMEOUT: fill_timeout, client_order_id=ENTRY-ae1174f0c7, order_id=1281004265
  - 1762537697229 ORDER_CANCELLATION_FAILED: order_id=1281004265

- Таймлайн 5 (RID=e5d3da67-bbf1-44c1-a37e-0c9af21311cf, symbol=SOLUSDT)
  - 1762537643105 ORDER_PLACED: client_order_id=ENTRY-0f9140cfcb, order_id=1281005277
  - 1762537705612 ORDER_TIMEOUT: fill_timeout, client_order_id=ENTRY-0f9140cfcb, order_id=1281005277
  - 1762537706264 ORDER_CANCELLATION_FAILED: order_id=1281005277

- Перелік потенційних orphan‑ордерів (за логікою таймлайнів; REST знімок не виконували)
  - BNBUSDT: order_id=891919127 (ENTRY-a0d302dcb7) — не було підтверджено успішне скасування в логах після TIMEOUT
  - ETHUSDT: order_id=6866526798 (ENTRY-3a11dea7c8) — аналогічно
  - BTCUSDT: order_id=9001747353 (ENTRY-517dcc4372) — аналогічно
  - SOLUSDT: order_id=1281004265 (ENTRY-ae1174f0c7); order_id=1281005277 (ENTRY-0f9140cfcb)
  - Примітка: це кандидати; для підтвердження потрібен READ `GET /fapi/v1/openOrders` по символах.

- Кейси `CONDITIONAL_ORDER_TRIGGER_REJECT`
  - У наявних логах прямих записів `TRIGGER_REJECT` не виявлено. Для наступних сесій рекомендуємо зберігати WS `CONDITIONAL_ORDER_*` події окремим логом для кореляції з `-2021`.

---

Цей документ містить повний план перевірок, чіткі посилання на код (з файлами та рядками), вимоги до артефактів і процесні рекомендації. Він дозволяє підтвердити гіпотези щодо «висячих/порожніх TP/SL» виключно засобами читання логів і READ‑API/WS, без змін у коді.
