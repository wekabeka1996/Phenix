# Cross-Model Verdict: EP Brackets After Fill + Duplication Audit

**Date**: 2026-02-25  
**Reviewer**: Antigravity Principal Audit  
**Input Documents**:
1. `REVIEW_EP_BRACKETS_AFTER_FILL.md` (8 findings, verdict: FAIL)
2. `AUDIT_EXECUTION_MANAGER_DUPLICATION.md` (11 duplicate map entries, verdict: HIGH risk)
3. `FIX_REPORT_BRACKET_BUGS_20260224.md` (4 bugs fixed, 20 tests)

**Method**: Full independent codebase trace of every claim against actual code lines.

---

## 1. Загальний вердикт моделі — Чи погоджуюсь?

### REVIEW_EP_BRACKETS_AFTER_FILL: **ПОГОДЖУЮСЬ з FAIL, але з уточненнями**

Модель правильно ідентифікувала **6 реальних прогалин** (F-01 через F-06) та **2 structural debt items** (F-07, F-08). Інцидентний root cause дійсно виправлений. Але safety-клас прогалин реально існує в коді — я верифікував кожен claim.

### AUDIT_EXECUTION_MANAGER_DUPLICATION: **ПОГОДЖУЮСЬ з HIGH, але один claim неточний**

Дублювання реальне і ризикове. Один claim потребує перевірки (adapter "silent bump" — я **не знайшов** цього в поточному `binance_adapter.py`).

---

## 2. Верифікація кожного Finding (F-01 — F-08)

### ✅ F-01: Multi-TP dedup key — **ПІДТВЕРДЖУЮ, P1**

**Claim**: Dedup key `symbol|parent|kind` з `kind="TP"` блокує TP2.

**Мій трейс**:
- `fsm.py:1032-1033` — `_bracket_place_key` справді повертає `f"{symbol}|{parent_order_id}|{kind}"` де kind тільки "SL" або "TP"
- `fsm.py:2919-2922` — bracket_kind виводиться з `order_type`: STOP_MARKET→"SL", TAKE_PROFIT_MARKET→"TP" (без слоту)
- `fsm_manage.py:770-793` — ManageFlowFSM емітить TP1 та TP2 як окремі `DEC:PLACE_ORDER` з **однаковим** `parent_order_id` та **обидва** TAKE_PROFIT_MARKET

**Результат**: TP1 claim succeeds → TP1 completes → TP2 приходить з **таким же ключем** `BTCUSDT|12345|TP` → `_bracket_place_completed` вже містить цей ключ → **TP2 СКІПАЄТЬСЯ**.

**Моя оцінка**: Це **реальний баг**, не гіпотетичний. Будь-який символ з multi-TP конфігурацією (`tp_high_ratio != None` в стратегії) буде втрачати TP2.

**АЛЕ**: є нюанс якій модель пропустила. `fsm_manage.py:749-752` генерує `tp1_client_id` та `tp2_client_id` з різними `idempotent_key` (`{idem_base}_1` і `{idem_base}_2`). Тобто ManageFlowFSM вже диференціює TP1/TP2 на рівні client ID, але dedup координатор в `fsm.py` цього не бачить.

**Мій fix рівень**: P1 ✅, але fix простіший ніж пропонує модель. Замість додавання `bracket_slot` в DEC:PLACE_ORDER, можна просто витягти slot з `newClientOrderId` (якій вже завжди містить `_1` або `_2`). Мінімальна зміна:

```python
# В _execute_decision, рядок 2919-2922:
bracket_kind = (
    "SL" if str(order_type).upper() == "STOP_MARKET"
    else "TP" if str(order_type).upper() == "TAKE_PROFIT_MARKET"
    else None
)
# Додати slot:
bracket_slot = pld.get("bracket_slot") or ""
# В _bracket_place_key:
return f"{symbol}|{parent_order_id}|{kind}|{slot}"
```

---

### ✅ F-02: Inflight claim lifecycle — **ПІДТВЕРДЖУЮ, P1**

**Claim**: claim/release не під `finally`, CancelledError може залишити stuck claim.

**Мій трейс**:
- `fsm.py:2930-2937` — `claimed = self._claim_bracket_placement(...)` → якщо claimed, іде в try/except
- `fsm.py:3059-3074` — except block робить `release`, PLUS lines 3069-3074 — **після except** є ще один release check
- `fsm.py:5043-5068` — deferred path: claim → try → except (release inside) — **НЕ finally**

**Проблема**: `asyncio.CancelledError` НЕ наслідується від `Exception` в Python 3.9+. Це означає що `except Exception` на рядку 3059 НЕ ловить CancelledError. Якщо корутина скасовується під час `await self.adapter.place_stop_market_close_position()` (рядок 5048), inflight claim **залишається назавжди**.

```python
# Поточний код (fsm.py:5046-5068):
if claimed_sl:
    try:
        sl_resp = await self.adapter.place_stop_market_close_position(...)  # <-- CancelledError тут
        self._mark_bracket_placement_success(...)
    except Exception as e:       # <-- CancelledError НЕ тригерає це в Py3.9+
        self._release_bracket_placement_claim(...)  # <-- НЕ виконується
```

**Моя оцінка**: P1 ✅, і це навіть **серйозніше** ніж модель описала. `asyncio.CancelledError` — це `BaseException`, не `Exception`. Єдиний fix — `try/finally`:

```python
if claimed_sl:
    try:
        sl_resp = await self.adapter.place_stop_market_close_position(...)
        self._mark_bracket_placement_success(...)
    except BaseException:
        self._release_bracket_placement_claim(...)
        raise
```

або ще краще:
```python
if claimed_sl:
    try:
        sl_resp = await self.adapter.place_stop_market_close_position(...)
    except BaseException:
        self._release_bracket_placement_claim(...)
        raise
    else:
        self._mark_bracket_placement_success(...)
```

---

### ✅ F-03: Guardrail coverage — **ПІДТВЕРДЖУЮ, P1**

**Claim**: `FILLED_ENTRY_WITHOUT_BRACKETS` emitted лише в deferred path, не в PLACE_ORDER path.

**Мій трейс**:
- `fsm.py:5171-5178` — guardrail emit в `_place_deferred_brackets`: ✅ є
- `fsm.py:2908-3075` — `PLACE_ORDER` handler: шукаю `_emit_filled_entry_without_brackets` — **НЕ ЗНАЙДЕНО** в цьому блоці

**Результат**: Якщо bracket placement через PLACE_ORDER path (manage flow) фейлить, позиція залишається без SL/TP але **guardrail не спрацьовує**. Оператор не отримає FILLED_ENTRY_WITHOUT_BRACKETS event.

**Моя оцінка**: P1 ✅, згоден. Потрібен shared post-assessment.

**АЛЕ**: є важливий контекст який модель пропустила. PLACE_ORDER path (рядки 2908-3075) — це шлях для **manage flow** brackets. Deferred path (рядки 4974-5183) — для **limit entry fill** brackets. На практиці, якщо manage flow помилився, deferred path все одно спробує. Але це не гарантія — якщо manage path зробив dedup claim ПЕРШИЙ і зафейлив, deferred path побачить completed/inflight і скіпне.

---

### ✅ F-04: Naked position policy — **ПІДТВЕРДЖУЮ, P1 → але P2 в практиці**

**Claim**: `missing_count=2` не має enforcement policy.

**Мій трейс**:
- `fsm.py:1064-1091` — `_emit_filled_entry_without_brackets` записує в in-memory dict і емітить event, але далі **нічого не відбувається**
- Grep `_filled_entries_missing_brackets` → тільки writes на рядку 1083, ніхто не читає для прийняття рішень

**Моя оцінка**: Формально P1, але на практиці це **design-level gap**, не bug. Потрібен окремий design document "що робити при naked position". Варіанти: halt symbol, emergency close, bounded retries. Це скоріше P2 задача бо потребує product decision, не тільки code fix.

---

### ✅ F-05: Startup reconcile idempotence — **ПІДТВЕРДЖУЮ, P2**

**Claim**: Startup replay може re-attempt placement якщо brackets already exist.

**Мій трейс**:
- `fsm.py:5636-5665` — startup reconcile: перевіряє `status == "FILLED"`, потім одразу викликає `_recover_deferred_brackets_for_filled_entry`
- `_recover_deferred_brackets_for_filled_entry` (рядок 1108) — `.pop(order_id)` з `_pending_brackets` і потім `_place_deferred_brackets`
- `_place_deferred_brackets` (рядок 5007) — викликає `order_guardian.should_place_brackets` який **не перевіряє** чи вже є відкриті SL/TP на біржі
- `should_place_brackets` (guardian:601-641) — перевіряє лише `entry_meta.get("close_position")`, **не існуючі brackets**

**Результат**: Якщо WAL каже "pending" але SL/TP вже існують на біржі (наприклад, розміщені перед крашем), startup спробує розмістити дублікати → Binance -4130 "conflicting orders".

**Моя оцінка**: P2 ✅, згоден. Це шумний edge-case (наявність WAL + наявність brackets на біржі означає крах стався ПІСЛЯ placement але ДО WAL clear). Рідкісний, але реальний.

**Моя альтернативна пропозиція**: Замість pre-check "already protected", краще зробити **idempotent placement** — якщо -4130 повертається, трактувати це як success (brackets вже є). Це простіше і robust-ніше.

---

### ✅ F-06: Late cancel event — **ПІДТВЕРДЖУЮ, P1**

**Claim**: Cancel-event handler очищує pending без fill-aware recovery.

**Мій трейс**:
- `fsm.py:4698-4708` — `_handle_cancel_event`: якщо `order_id in self._pending_brackets`, робить `.pop()` і WAL clear з reason "cancelled"
- **Немає** виклику `_recover_deferred_brackets_for_filled_entry` або перевірки `executedQty`
- `fsm.py:1302-1308` — cancel path через `_cancel_pending_entries_for_symbol` **має** fill-aware recovery через `_is_fill_discovered_cancel_result`

**Проблема**: WS cancel event приходить асинхронно. Якщо ордер був **частково** заповнений (PARTIALLY_FILLED), а потім скасований, WS cancel event прийде раніше або пізніше. `_handle_cancel_event` просто drop pending brackets без перевірки чи була fill quantity. **Позиція існує, але brackets очищені.**

**Моя оцінка**: P1 ✅, і це один з найнебезпечніших gaps. Сценарій:
1. LIMIT entry order частково заповнюється (0.3 BTC з 1.0 BTC)
2. Cancel прилітає (решта 0.7 BTC скасовано)
3. `_handle_cancel_event` pop pending brackets
4. Позиція 0.3 BTC залишається **без SL/TP**

Fix: перед clear, перевірити executedQty. Якщо > 0, route до recovery.

---

### ✅ F-07: Duplicate consume path — **ПІДТВЕРДЖУЮ, P2**

**Мій трейс**:
- `fsm.py:1108-1131` — `_recover_deferred_brackets_for_filled_entry`: `.pop()` + WAL clear + `_place_deferred_brackets`
- `fsm.py:2235-2258` — `_on_order_fill`: `.pop()` + WAL clear + `_submit_async(_place_deferred_brackets)`

**Ці два блоки роблять ОДНЕ І ТЕ Ж**, але з різними деталями:
- `_on_order_fill` не має `schedule_async` параметра
- `_on_order_fill` не передає `source` для вкладеного logging
- `_recover_deferred_brackets_for_filled_entry` має `schedule_async` flag

**Моя оцінка**: P2 ✅, дрейф гарантований. `_on_order_fill` повинен делегувати до `_recover_deferred_brackets_for_filled_entry`.

---

### ✅ F-08: In-memory unsafe registry — **ПІДТВЕРДЖУЮ, P2**

Згоден. `_filled_entries_missing_brackets` губиться після restart. Але зважаючи на F-04, registry все одно не має enforcement policy, тому persistence без policy — лише половина рішення.

---

## 3. Верифікація Duplication Audit

### Оцінка кожного рядка Duplicate Map:

| # | Claim | Мій вердикт | Коментар |
|---|-------|-------------|----------|
| stopPrice validation | ✅ ПІДТВЕРДЖУЮ | `stopprice_validation.py` (domain) vs `binance_adapter.py:61-88` — дві **незалежні** implementations з різними функціями (`parse_stop_price` vs `_is_valid_stop_price`). Логіка ідентична але коди різні. |
| Conditional order types | ✅ ПІДТВЕРДЖУЮ | `stopprice_validation.py:13` `CONDITIONAL_ORDER_TYPES` vs `utils.py:111-112` — два frozen set-и. |
| clientOrderId guard | ✅ ПІДТВЕРДЖУЮ | `utils.py:165-223` vs `adapter:41-52` — generation vs validation дублюють length policy. |
| Quantity rounding | ✅ ПІДТВЕРДЖУЮ | `qty_normalizer.py:140-143` vs DM sizing — різні шляхи. |
| Quantity constraints policy | ⚠️ ЧАСТКОВО | Модель каже "adapter silently bumps minQty/minNotional" — я **НЕ ЗНАЙШОВ** silent bump в поточному `binance_adapter.py`. Grep по `bump`, `min_qty`, `minQty`, `quantize` — пусто. **Можливо це було видалено або модель помилилась.** `qty_normalizer.py` чітко каже "NO BUMP-UPS" (рядок 14). |
| Precision lookup | ✅ ПІДТВЕРДЖУЮ | `fsm_open.py:184-222` vs `decision_making.py:4577-4607` — обидва завантажують tick_size/step_size. |
| Bracket placement execution | ✅ ПІДТВЕРДЖУЮ | `fsm.py:4974-5183` vs `fsm.py:2908-3075` — dual path, вже описано вище. |
| Pending bracket consume | ✅ ПІДТВЕРДЖУЮ | = F-07. |
| Idempotent cancel semantics | ✅ ПІДТВЕРДЖУЮ | Три реалізації `-2011/-2013` handling. |
| Timeout orchestration | ✅ ПІДТВЕРДЖУЮ | `watchdog.py` vs `fsm.py` vs `orchestrator_fsm.py` — три рівні. |
| Sequential orchestration | ✅ ПІДТВЕРДЖУЮ | Supersede vs flip overlap. |
| Bracket existence checks | ✅ ПІДТВЕРДЖУЮ | `fsm.py:5348-5385` vs `order_guardian.py:691-760`. |

**Загальний вердикт**: 10/11 claims підтверджені. 1 claim (adapter silent bump qty) потребує перевірки — можливо це було раніше в коді але видалено.

---

## 4. Мої власні знахідки (модель пропустила)

### 🔸 NEW-1: `_on_order_fill` consume path пропускає dedup coordinator

**`fsm.py:2235-2258`** — `_on_order_fill` робить `self._pending_brackets.pop(order_id)` і потім `_submit_async(_place_deferred_brackets(...))`. Але він **НЕ ВИКЛИКАЄ** `_claim_bracket_placement` перед поданням! Dedup координатор активний тільки всередині `_place_deferred_brackets`.

Це означає: якщо `_on_order_fill` і `_execute_decision(PLACE_ORDER)` обидва отримали fill одночасно (WS event + REST poll), обидва шляхи можуть пройти `.pop()` (перший — success, другий — KeyError або missing), але `_place_deferred_brackets` вже має dedup всередині. Так що це safe **тільки тому що** `.pop()` — atomic для dict в CPython. Але це implementation detail, не architectural guarantee.

### 🔸 NEW-2: `_emit_place_order` в ManageFlowFSM використовує `msg.dst` як `src`

**`fsm_manage.py:1059`** — `src=msg.dst`. Якщо ManageFlowFSM отримує message від orchestrator де `dst="execution_position"`, то emitted PLACE_ORDER матиме `src="execution_position"` — що коректно. Але якщо msg.dst інший (наприклад через bus routing), `src` буде wrong. Це хрупкий pattern.

### 🔸 NEW-3: CancelledError propagation в _place_deferred_brackets swallowed

`_place_deferred_brackets` (fsm.py:4974-5183) має два рівні try/except: зовнішній для SL, внутрішній для TP. `BinanceAPIError` ловиться окремо, але `except Exception` ловить все крім `BaseException`. Якщо задача скасовується під час TP retry (рядок 5102-5104), `CancelledError` **НЕ перехоплюється** (бо Python 3.9+ CancelledError → BaseException), але inflight claim **вже release**. Тобто CancelledError "проходить" правильно для claim, але `_mark_bracket_placement_success` на рядку 5116 не виконується → заїзд у невизначений стан де SL placed, TP NOT placed, inflight released, completed NOT marked.

---

## 5. Моя оцінка пропозицій моделі

### Пакет P1-A: Multi-TP slot-aware dedup

| Аспект | Оцінка |
|--------|--------|
| Діагноз | ✅ Правильний |
| Пропоноване рішення | ⚠️ Можна простіше |
| Пріоритет P1 | ✅ Правильний |

**Моя альтернатива**: Замість додавання `bracket_slot` в DEC:PLACE_ORDER payload (що потребує зміни contract між ManageFlowFSM і ExecPosFSM), можна:
1. Витягти slot з `newClientOrderId` який вже містить slot info (`TP-xxx` з idempotent_key `_1` або `_2`)
2. АБО: змінити dedup key format на `symbol|parent|kind|clientOrderId` — кожен bracket вже має унікальний client ID

Це менш інвазивна зміна і не ламає міждоменний контракт.

### Пакет P1-B: Inflight claim lifecycle

| Аспект | Оцінка |
|--------|--------|
| Діагноз | ✅ Правильний, навть гірше ніж описано |
| Рішення | ✅ Правильне (try/finally) |
| Пріоритет P1 | ✅ Правильний — залипання може бути permanent |

**Повністю погоджуюсь**. Мій додатковий коментар: потрібно ловити `BaseException`, не `Exception`, через Python 3.9+ CancelledError semantics.

### Пакет P1-C: Guardrail coverage for PLACE_ORDER path

| Аспект | Оцінка |
|--------|--------|
| Діагноз | ✅ Правильний |
| Рішення | ✅ Правильне (shared helper) |
| Пріоритет P1 | ⚠️ Я б поставив P2 |

**Обґрунтування P2**: Guardrail — це observability, не prevention. Навіть без guardrail, відсутні brackets будуть помічені bracket-health check або order_guardian reconcile. Guardrail лише прискорює виявлення. P1 найкраще витратити на prevention (F-01, F-02, F-06).

### Пакет P1-D: Late cancel event fill-aware recovery

| Аспект | Оцінка |
|--------|--------|
| Діагноз | ✅ Правильний |
| Рішення | ✅ Правильне |
| Пріоритет P1 | ✅ Правильний — це може залишити naked position |

**Повністю погоджуюсь**. Це один з найнебезпечніших gaps.

### Пакет P2-E: Startup reconcile idempotence pre-check

| Аспект | Оцінка |
|--------|--------|
| Діагноз | ✅ Правильний |
| Рішення | ⚠️ Моя альтернатива краща |
| Пріоритет P2 | ✅ Правильний |

**Моя альтернатива**: Замість pre-check "already protected", зробити placement **idempotent by design** — якщо Binance повертає -4130 (duplicate order), трактувати як success. Це простіше, і покриває ширший клас edge cases (не тільки startup).

---

## 6. Моя рекомендована черга виконання

Відрізняється від моделі:

| # | Пакет | Причина пріоритету |
|---|-------|--------------------|
| **1** | **P1-B: try/finally inflight** | Найпростіший fix, найвищий ризик (permanent stuck = system-wide block) |
| **2** | **P1-D: Late cancel fill-aware** | Naked position — це safety-critical |
| **3** | **P1-A: Multi-TP dedup** | Впливає на стратегію, але тільки якщо multi-TP active |
| **4** | **P2-F07: Unify consume paths** | Запобігає дрейфу в recovery logic |
| **5** | **P1-C: Guardrail PLACE_ORDER** | Observability improvement, не prevention |
| **6** | **P2-E: Startup idempotence** | Рідкісний edge-case |

---

## 7. Про "execution_manager" дублювання

**Погоджуюсь з HIGH risk рівнем**, але **НЕ погоджуюсь** з підходом "великий рефактор".

### Мій погляд:

Дублювання — це **еволюційна архітектура**, не помилка. FSM система росла органічно і кожен path має свої edge cases. Спроба звести все до одного "execution_manager" може створити God Object з ще більшою складністю.

**Що робити натомість**:
1. **Shared contracts** (validators, policies) — ОК, це найнижчій ризик рефактору
2. **stopPrice SSOT** — обов'язково, бо adapter duplicate вже шкодить 
3. **qty_normalizer SSOT** — модель каже "adapter silently bumps", але я не знайшов цього в коді. Перевірити чи це актуально.
4. **Bracket coordinator** — це найбільший рефактор, і я б відклав його до P3
5. **Idempotent cancel** — три implementations, але всі працюють. Уніфікація — nice to have, не critical.

### Мій Minimal Action Plan:

```
Week 1: P1-B (try/finally) + P1-D (late cancel) → 2 файли, ~30 рядків
Week 2: P1-A (multi-TP dedup) + F-07 (unify consume) → ~50 рядків
Week 3: stopPrice SSOT (adapter imports domain validator) → 1 файл
```

Загальний effort: **~3 дні інженера**, а не "великий рефактор".

---

## 8. Підсумок

| Aspect | Model Verdict | My Verdict | Agreement |
|--------|--------------|------------|-----------|
| Overall FAIL | ✅ | ✅ | **Agree** |
| F-01 Multi-TP | P1 | P1 (simpler fix) | **Agree, different approach** |
| F-02 Inflight | P1 | P1 (even worse than stated) | **Agree, CancelledError is BaseException** |
| F-03 Guardrail | P1 | P2 (observability, not prevention) | **Disagree on severity** |
| F-04 Naked policy | P1 | P2 (needs product decision) | **Disagree on severity** |
| F-05 Startup | P2 | P2 (idempotent-by-design is better) | **Agree, different approach** |
| F-06 Late cancel | P1 | P1 (worst gap) | **Agree** |
| F-07 Duplicate consume | P2 | P2 | **Agree** |
| F-08 In-memory registry | P2 | P2 (useless without F-04 policy) | **Agree** |
| Duplication HIGH | ✅ | ✅ (1/11 claims unverified) | **Agree** |
| Execution order | A,B,D | B,D,A | **Disagree — inflight first** |

**Головний висновок**: Модель зробила якісний аудит. Safety gaps реальні. Але пріоритизація потребує корекції: **inflight finally (F-02) і late cancel (F-06) — це два найнебезпечніших gaps**, бо обидва можуть залишити систему в невизначеному стані назавжди без рестарту. Multi-TP (F-01) — важливий, але потребує active multi-TP config щоб тригернутись.
