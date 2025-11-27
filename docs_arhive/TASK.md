
---

# План виправлень (пріоритет A → C)

## A1) **Жорсткий cancel-on-close + повний reconcile**

Проблема: закриття позиції не скасовує умовні TP/SL автоматично на біржі — це норма API, їх треба знімати вручну. ([Stack Overflow][1])
Binance дозволяє `closePosition=true` для STOP/TP, але це **не** означає авто-чистку для інших умовних ордерів.

Що робимо:

* На переході в `FLAT` і в усіх шляхах `DEC:CLOSE` викликаємо **локальний reconcile**: `GET /fapi/v1/openOrders?symbol=...` → скасовуємо все `TAKE_PROFIT_MARKET`/`STOP_MARKET` із `reduceOnly=true` або `closePosition=true`.
  У вас вже є універсальна мітла `cleanup_orphaned_bracket_orders()` (працює по всіх символах/періодично). Викличте її **точково** по символу **одразу після** закриття (ви вже робите best-effort async-виклик після fill, залишаємо і додаємо синхронний шлях при `CLOSE`).
* Під час стартап-синку ви вже робите стартовий cleanup (залишаємо).
* Адаптер уміє читати openOrders та скасовувати (-2011 уже хендлите з повтором) — цього достатньо.

**Точки коду:**

* ExecPosFSM: залишаємо існуючий async-cleanup після fill і додаємо **обов’язковий** sync-reconcile (по символу) у гілці `DEC:CLOSE` перед/відразу після закриття. Спираємось на `cleanup_orphaned_bracket_orders(symbol)` і `get_open_orders(symbol)`.

---

## A2) **Анти-гонка: блокувальник брекетів на «шляху до FLAT»**

Проблема: ретраї TP/SL після `-2021` або пізні `ensure_brackets` можуть прилетіти вже на **0-позицію**, поки FSM ще не перевівся у `FLAT`.

Що робимо:

* Ввести атомарний прапор `_closing_position[symbol]=True` при старті `CLOSE`/exit-fill, знімати після reconcile.
* У **ManageFlowFSM** перед `_place_brackets()` перевіряти: якщо `_closing_position` або `position_qty==0` → **нічого не ставимо**.
* Класифікація EXIT vs ENTRY у вас уже є (FILL в `FLAT` із перевіркою `type/closePosition/reduceOnly`) — це база, її використовуємо як тригер для прапора.
* `_place_brackets()` — додати early-return за прапором (і перевіркою позиції).

---

## A3) **Pre-flight перед TP/SL + керований backoff для `-2021`**

Проблема: `-2021` = «would immediately trigger» для умовних ордерів → миттєві ретраї віконцем затримки легко потрапляють уже на 0-позицію.

Що робимо:

* **Перед кожним POST TP/SL** перевірити через `/fapi/v2/positionRisk`, що `positionAmt != 0` — інакше **SKIP**, логуємо `TP_SL_SKIPPED_NO_POSITION`. У вас вже є `get_open_positions()` на адаптері.
* В `_place_brackets()` залишаємо валідації цін і додаємо **динамічний offset_bps** (BTC ≈10, ETH ≈8, альти 12–15) замість жорстких 5 bps.
* Ретраї `-2021`: експоненційний backoff (200ms → 400 → 800; максимум 3), **перед кожним ретраєм** знову перевіряємо `positionAmt`. Якщо 0 — **аборт**. (Binance описує роботу STOP/TP/`workingType`, деталі тригеру — у доках.)

---

## B1) **Ідемпотентність `newClientOrderId` і `-4116`**

Проблема: дублі `newClientOrderId` → фантомні цикли; при ретраї інколи генерується новий ID вже «після факту».

Що робимо:

* Леджер `{symbol, side, kind(tp|sl)} → clientOrderId, orderId, created_at}` (in-memory + короткий TTL/Redis).
* На `-4116` робимо: `GET order by origClientOrderId` → якщо існує — **reuse** та **skip** дубль-пост; інакше — генеруємо **новий** і йдемо в POST.
  Офіційний код `-4116` зафіксований у довіднику помилок.

**Точки коду:** адаптер `create_order()/cancel_order()` — місця вже є; додаємо обробку `-4116` за схемою вище.

---

## B2) **Post-CLOSE reconcile + періодичний GC**

* Після будь-якого `CLOSE`/перехід у `FLAT`: одразу `get_open_orders(symbol)` → `cancel` усі reduceOnly/closePosition. (Локальний швидкий прохід.)
* Фонова мітла вже реалізована, лишається **включити/підкрутити інтервал**: `periodic_interval_sec ≈ 60–120`, `run_on_startup=true`.

---

## C) **Observability (мінімум, але по ділу)**

Додати події:

* `TP_SL_RETRY_ATTEMPT/-2021/-4116`, `TP_SL_RETRY_ABORTED_NO_POSITION`, `RECONCILE_CANCELLED{count}`.
* Метрики orphan-cleanup: `cancels`, `errors`, `skipped_age`, `skipped_rate_limit`, уже частково є — доповнити лічильники.

---

# Мінімальні зміни в конфігах (приклад)

```yaml
execution:
  manage:
    brackets:
      offset_bps:
        BTCUSDT: 10
        ETHUSDT: 8
        default: 15
    orphan_monitor:
      run_on_startup: true
      periodic_interval_sec: 90
      min_order_age_sec: 5
      batch_cancel_limit: 50
    retries:
      max_for_2021: 3
      backoff_ms_base: 200
```

Обґрунтування: `workingType/closePosition` працюють як у доках; `-2021` — тригер занадто близький до `markPrice`; `-4116` — дубль ID; нічого «магічного».

---

# Точні місця у вашому коді (куди лізти)

* **ManageFlowFSM (ENTRY/EXIT + брекети):** гілка FILL у `FLAT` і `_place_brackets()` — там ставимо прапор та early-return.
* **ExecPosFSM (cleanup):** використати існуючі `cleanup_orphaned_bracket_orders(symbol)` і стартап-cleanup; додати sync-reconcile по символу у `DEC:CLOSE`.
* **Adapter (I/O):** тут уже є `get_open_orders`/`cancel_order` і обробка `-2011`; додаємо гілку `-4116` і pre-flight `positionRisk` перед POST TP/SL.

---

# Тест-план (мінімум, що треба покрити)

1. **CLOSE→reconcile, позиція=0, висячих немає**: відкрити позицію, створити TP/SL, закрити `MARKET`, перевірити що `openOrders(symbol)` порожні ≤1–2с після переходу у `FLAT`.
2. **-2021 backoff**: навмисно поставити TP надто близько до `markPrice`, зловити `-2021`, переконатися у backoff та що при `positionAmt=0` ретраї **не** відбуваються.
3. **-4116**: зімітувати дубль `newClientOrderId`, перевірити reuse/skip.
4. **EXIT-fill не спонукає нові брекети**: FILL `TAKE_PROFIT_MARKET` → переконатися, що `_place_brackets()` навіть не викликається.
5. **Periodic GC**: залишити орфанні на символі без позиції, дочекатися періодичного прибирання (лог: `ORPHAN_CLEANUP cancelled N`).

---

# DoD (приймаємо роботу, коли…)

* Після будь-якого `CLOSE` **≤2s**: `openOrders(symbol)` **не** містять STOP/TP `reduceOnly/closePosition`.
* `TP_SL_SKIPPED_NO_POSITION` присутній у випадках, коли `positionRisk` показує 0.
* `-2021` має максимум 3 ретраї з backoff; більше немає «TP/SL на нульову позицію».
* Нуль **маржин-ліку**: `totalOpenOrderInitialMargin` → 0 при `positionAmt=0`.
* У логах є `RECONCILE_CANCELLED count>0` у кейсах ручного закриття.

---

Якщо хочеш — кидай звіт 2-го агента, я звірю гіпотези/таймлайни й підкручу деталі. Але для старту цього більш ніж достатньо — можна брати і робити PR-пакет по пунктах A1–A3, далі B1–B2, потім C.

**Джерела Binance:** `closePosition/workingType` і поведінка STOP/TP (USDT-M), WS-правила для `closePosition`, коди помилок `-2021`/`-4116`.

**Власний код, на який спираємось:** стартап-cleanup, мітла орфанів, класифікація EXIT/ENTRY, адаптерні методи.


