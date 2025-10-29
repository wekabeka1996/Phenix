# Critical Issues Analysis Report

## Introduction

This report provides a detailed analysis of critical issues discovered during the investigation of project logs. The analysis focuses on understanding the root causes of the problems within the codebase.

---

## 1. State Contamination in `DecisionMaking`

**Problem:** Critical data blending ("state contamination") between different trading instruments in the `DecisionMaking` component. The system makes trading decisions for one asset (e.g., BTCUSDT) using risk parameters or market data from another asset (e.g., ETHUSDT).

**Root Cause Analysis:**
The investigation of `apps/reference/domains/decision_making/decision_making.py` confirms that the `DecisionMaking` class uses instance-wide variables `self.latest_features`, `self.latest_risk`, and `self.latest_portfolio` to store the most recent data received from different event streams.

- `on_features()` overwrites `self.latest_features`.
- `on_risk()` overwrites `self.latest_risk`.

These handlers are triggered by events that are symbol-specific. However, the internal state is not segregated by symbol. When `_try_make_decision()` is triggered, it uses whatever data is present in these variables, regardless of which symbol it belongs to. This creates a race condition where a `RISK_ASSESSMENT` event for `BTCUSDT` can be immediately followed by a `FEATURES_CALCULATED` event for `ETHUSDT`, leading `_try_make_decision` to incorrectly combine `ETHUSDT` features with `BTCUSDT` risk data.

**Recommendation:**
Refactor the internal state of `DecisionMaking` to be a dictionary keyed by symbol. For example:
```python
self.state_by_symbol = {
    # "BTCUSDT": {"features": ..., "risk": ..., "portfolio": ...},
    # "ETHUSDT": {"features": ..., "risk": ..., "portfolio": ...}
}
```
Each event handler should update the state for its specific symbol, and `_try_make_decision` should be called with a symbol context to ensure data consistency.

---

## 2. Significant Delay in Event Emission

**Problem:** A significant delay (over 800 ms) was observed between the approval of a trade intent and the actual emission of the `EVT:TRADE_INTENT_PROPOSED` event. This latency means the system acts on stale data.

**Root Cause Analysis:**
The code in `_try_make_decision()` in `decision_making.py` performs several operations after the decision to trade is logically made and logged, but before the event is emitted. These operations include:
1.  Constructing a detailed `why_payload`.
2.  Generating a unique `intent_id` via hashing.
3.  Assembling the final `trade_intent_payload`.
4.  Calling `self.fsm.emit()`.

While individually small, the aggregate time taken for these steps, potentially combined with other factors like system load, logging I/O, or inefficient object creation, can introduce noticeable latency. An 800ms delay is critical in high-frequency trading and can lead to significant slippage.

**Recommendation:**
The event emission should happen as soon as the decision is made. The generation of auxiliary data (like `why_payload` or `intent_id`) should be optimized or, if possible, handled asynchronously if it's not part of the critical path for order execution. The principle should be to emit the event first and handle secondary logging or processing afterwards.

---

## 3. Zero Quantity Order Calculation

**Problem:** The logic for calculating order quantity for high-priced assets (like BTC) results in zero-quantity orders, leading to the rejection of potentially profitable trades.

**Root Cause Analysis:**
The issue lies in the position sizing logic within `_try_make_decision`. The code uses the formula `(qty_raw // lot_step) * lot_step` to adjust the quantity to the required lot size. The `//` operator in Python performs floor division.

For a high-priced asset, the raw calculated quantity (`qty_raw`) can be very small (e.g., `0.000787`). If the `lot_step` is `0.001`, the expression `0.000787 // 0.001` evaluates to `0.0`. Multiplying this by `lot_step` results in a final quantity of `0.0`, which is then correctly rejected for being below the minimum order size. This is a flaw in the rounding logic.

**Recommendation:**
The use of standard floating-point arithmetic for financial calculations is discouraged. The `decimal` module should be used for all price and quantity calculations to ensure precision. The rounding logic should be corrected to use proper rounding functions that respect the `lot_step`, for example, using `Decimal.quantize`.

Corrected Logic Example:
```python
from decimal import Decimal, ROUND_DOWN

lot_step = Decimal("0.001")
calculated_qty = (Decimal(str(qty_raw))).quantize(lot_step, rounding=ROUND_DOWN)
```

---

## 4. Incorrect Event Filtering in `feature_engineering`

**Problem:** The `feature_engineering` component filters out `trade` events, which prevents the correct calculation of the Trade Flow Imbalance (TFI) indicator.

**Root Cause Analysis:**
The `on_market_tick` function in `apps/reference/domains/feature_engineering/feature_engineering.py` contains the following logic:
```python
data_type = payload.get("data_type", "")
if data_type == "trade":
    self.logger.debug("Skipping trade event - using only bookTicker for features")
    # ...
    return
```
This explicitly ignores all incoming trade data. The TFI is a measure of the imbalance between buy and sell volume from actual trades. By filtering these events, the TFI calculation is always based on zero or stale volume data, rendering it useless and corrupting the `signal_score` in the `DecisionMaking` component.

**Recommendation:**
The filter must be removed or modified. The `feature_engineering` component should process both `bookTicker` (for order book features like OBI) and `trade` (for trade-based features like TFI) events. The logic should be updated to aggregate trade volumes and correctly calculate TFI based on the flow of actual trades.

---

## 5. "Blind Spot" and Inefficient Decision Triggers

**Problem:** The `DecisionMaking` component initiates the decision-making process (`_try_make_decision`) upon every single incoming event (`features`, `risk`, `portfolio`), even if the other required data points are stale or not yet present.

**Root Cause Analysis:**
The investigation of `apps/reference/domains/decision_making/decision_making.py` confirms this behavior. Each event handler unconditionally triggers a full decision cycle:
- The `on_features` method calls `self._try_make_decision()` on line **116**.
- The `on_risk` method calls `self._try_make_decision()` on line **137**.
- The `on_portfolio` method calls `self._try_make_decision()` on line **158**.

While the guard clause at the beginning of `_try_make_decision` (lines **230-239**) prevents a decision from being made with incomplete data, this "trigger-on-every-event" approach is highly inefficient. It leads to a large number of redundant, useless processing cycles that consume CPU resources. More critically, it exacerbates the risk of state contamination described in Issue #1, as it constantly creates opportunities for data from different symbols to be partially updated and incorrectly evaluated together.

**Recommendation:**
Refactor the triggering mechanism. Instead of calling `_try_make_decision` from every handler, the handlers should only update the symbol-specific state. A single, more intelligent trigger point should be used. For instance, `_try_make_decision` should only be called from the `on_features` handler, as features are typically the most frequent update and represent the "last piece" of the puzzle needed to make a timely decision. This would ensure that a decision cycle for a symbol is only initiated when fresh market data is available and all other data points (`risk`, `portfolio`) are ready.

---

## 6. Continuous Intent Generation for Open Positions

**Problem:** The system repeatedly generates new trade intents even after a position for a specific symbol is already open. This results in a constant stream of rejections due to the position accumulation protection logic (`POSITION_ACCUMULATION_BLOCKED`).

**Root Cause Analysis:**
The core of the issue lies in the stateless nature of the decision cycle within `apps/reference/domains/decision_making/decision_making.py`. The logic to prevent position accumulation (lines **368-407**) works correctly by blocking new trades in the same direction. However, the component fails to manage its state appropriately after this rejection.

Specifically, after a trade intent is rejected for any reason (including `POSITION_ACCUMULATION_BLOCKED`), the method `self.clear_internal_state()` is called (e.g., on line **406**). This method erases the `self.latest_features` and `self.latest_risk` data. As a result, the component immediately becomes ready to process the next market tick from scratch, re-evaluating the same market conditions and arriving at the same (rejected) conclusion. It lacks a state to signify "a position is open for this symbol, so stop evaluating entry signals and wait for an exit signal."

**Recommendation:**
Implement a more robust state management system within `DecisionMaking`. Instead of clearing the state after every rejection, the component should maintain the state of open positions. When a position is confirmed to be open for a symbol, the decision logic for that symbol should explicitly switch from evaluating "entry" signals to evaluating "exit" or "reversal" signals. This prevents the generation of redundant entry intents and reduces noise in the logs, allowing the system to focus only on valid, actionable opportunities.

. "Позиції-привиди" через ігнорування часткових виконань
Проблема: CloseFlowFSM, відповідальний за автоматичне закриття позицій за часом, активується тільки при отриманні події FILL і повністю ігнорує PARTIAL_FILL.
Локація: Файл: fsm_close.py, Клас: CloseFlowFSM, Функція: handle, Рядки: ~60-63.
Наслідок: Якщо позиція відкривається через одне або кілька часткових виконань (що є нормальним ринковим сценарієм), CloseFlowFSM для неї ніколи не активується. В результаті, таймер max_hold_sec не запускається, і система "не знає" про існування цієї позиції з точки зору управління її життєвим циклом. Така позиція залишається відкритою на біржі без будь-якого контролю, що неминуче призведе до збитків при несприятливому русі ринку.
8. "Сліпа зона" в управлінні ризиком відразу після відкриття позиції
Проблема: ManageFlowFSM, який відповідає за управління ризиком відкритої позиції (трейлінг-стопи, переведення в беззбиток), починає застосовувати свої правила не в момент відкриття позиції (FILL або PARTIAL_FILL), а тільки після отримання наступної події оновлення ринкових даних (UPD).
Локація: Файл: fsm_manage.py, Клас: ManageFlowFSM, Функція: handle, Рядки: ~80-86.
Наслідок: Створюється критичний проміжок часу, протягом якого позиція є абсолютно незахищеною. Якщо відразу після входу в ринок відбудеться різкий ціновий рух проти позиції, система не відреагує, оскільки її логіка управління ризиком ще не активна. Це гарантує отримання максимального збитку в ситуаціях раптової волатильності.
9. Відсутність відновлення стану FSM управління позиціями після перезапуску
Проблема: Механізм відновлення після збою (Disaster Recovery) коректно завантажує стан позицій у PositionTracking зі знімка, але не відновлює внутрішні стани FSM-машин ManageFlowFSM та CloseFlowFSM.
Локація: Файли: main.py (логіка запуску), fsm_manage.py, fsm_close.py (ініціалізація станів).
Наслідок: Після перезапуску системи, на рахунку можуть бути відкриті позиції, про які PositionTracking знає. Однак, ManageFlowFSM і CloseFlowFSM запускаються у своєму початковому стані FLAT. Вони не "пам'ятають", що потрібно управляти цими відновленими позиціями. Як наслідок, для всіх активних на момент збою угод повністю вимикається управління ризиком: не працюють ні стоп-лоси, ні тейк-профіти, ні закриття за часом. Це перетворює всі активні позиції на некеровані, що є прямою загрозою для капіталу.

Проблема: Небезпечна ініціалізація торгового плеча (leverage). Система не має механізму підтвердження, що потрібне плече було успішно встановлено перед початком торгівлі, і продовжує роботу з потенційно невірними параметрами.
Локація: Файл: binance_execution_adapter.py, Функція: initialize_margin_settings, Рядки: ~109-114.
Наслідок: Якщо виклик API для встановлення плеча (_set_leverage) зазнає невдачі з будь-якої причини (окрім помилки -4046), система продовжить роботу, але компонент DecisionMaking буде розраховувати розмір позиції, виходячи з плеча, вказаного в конфігурації. Реальне плече на біржі може бути іншим (наприклад, стандартним 20х). Це призведе до відкриття позиції, що в рази перевищує розрахований ризик, і багаторазово збільшить імовірність ліквідації.
Ланцюг:
Під час запуску initialize_margin_settings намагається встановити плече 5x для BTCUSDT.
API Binance повертає тимчасову помилку (наприклад, 502 Bad Gateway), яка не обробляється специфічно. Викликається logger.error і цикл продовжується для інших інструментів.
Реальне плече на біржі для BTCUSDT залишається 20x.
DecisionMaking отримує сигнал і розраховує розмір позиції, припускаючи, що плече дорівнює 5x.
BinanceExecutionAdapter успішно відкриває позицію. Через фактичне плече 20х, ця позиція виявляється в 4 рази більшою, ніж планувалося, що веде до катастрофічних збитків при найменшому несприятливому русі ціни.
Проблема: Використання потенційно застарілих даних про капітал для прийняття торгових рішень.
Локація: Файл: account_connector.py, Клас: AccountConnector, Рядок: ~58 (self.update_interval = 30).
Наслідок: Дані про баланс рахунку та відкриті позиції оновлюються лише раз на 30 секунд. У періоди високої волатильності або активної торгівлі, DecisionMaking може протягом майже 30 секунд приймати нові рішення, базуючись на неактуальному значенні equity. Якщо за цей час відбувся збиток, система буде розраховувати надмірно великі позиції, що прискорить втрати (ефект "снігової кулі").
Проблема: Потенційне використання застарілої ціни при розрахунку кількості (qty).
Локація: Файл: decision_making.py, Функція: _try_make_decision, Рядки: ~525-531.
Наслідок: Логіка розрахунку price_ref має запасний варіант використання self.latest_portfolio['last_price']. Однак, немає жодної перевірки, наскільки "старою" є ця ціна. Якщо потік ринкових даних (feature_engineering) перерветься, а потік даних портфеля (position_tracking) продовжить надходити, система може розрахувати кількість для нової угоди, використовуючи ціну годичної давності. Це призведе до відкриття позиції з абсолютно невірним обсягом і миттєвого збитку.
Проблема: Відсутність механізму "аварійної зупинки" при критичних помилках API.
Локація: Файл: account_connector.py, Функція: _get_account_info, Рядки: ~154-156. Файл: binance_execution_adapter.py, Функція: _place_binance_order, Рядки: ~428-430.
Наслідок: При отриманні критичних помилок від API Binance (наприклад, помилка автентифікації 401 або помилка доступу 403), компоненти лише логують помилку і продовжують роботу в штатному режимі. Система не переходить в безпечний стан (наприклад, "тільки закриття" або повна зупинка). Це створює ризик, що DecisionMaking, не отримуючи оновлень про реальний стан рахунку, продовжить генерувати торгові наміри, які будуть або відхилятися, або (в гіршому випадку) виконуватися з непередбачуваними наслідками, якщо проблема з API тимчасова. Це призводить до розсинхронізації стану та потенційних збитків.

Аналіз не є вичерпним. Поглиблене дослідження виявило додаткові архітектурні дефекти, що створюють серйозні фінансові ризики.

Продовжую звіт.

10. Відсутність портфельного управління ризиками (Portfolio-Level Risk Management)

Проблема: Компонент RiskManagement працює виключно на рівні окремого торгового інструменту (symbol). Повністю відсутня логіка, яка б оцінювала сукупний ризик по всьому портфелю.

Локація: Файл: risk_management.py, Клас: RiskManagement.

Наслідок: Система може одночасно генерувати сигнали на відкриття позицій по кількох висококорельованих активах (наприклад, BTC та ETH), не усвідомлюючи, що сукупний ризик перевищує всі допустимі межі. Відсутність лімітів на денну просадку (daily drawdown limit) або сукупне кредитне плече означає, що серія збиткових угод не зупинить систему, і вона продовжуватиме торгувати до повної ліквідації рахунку.

11. Ілюзія ідемпотентності: Відсутність механізму запобігання дублюванню ордерів

Проблема: Хоча в коді передається idempotent_key, не існує жодного компонента, який би відстежував використані ключі та запобігав повторній відправці ордера.

Локація: Файл: fsm_open.py, Функція: handle. Файл: binance_execution_adapter.py, Функція: place_order.

Наслідок: При збої або перезапуску системи після відправки ордера, але до отримання підтвердження від біржі, система спробує відправити той самий ордер ще раз. Це призведе до відкриття подвійної позиції, що подвоює ризик і є неконтрольованою дією.

Ланцюг:

Система генерує CMD:OPEN з унікальним idempotent_key.

BinanceExecutionAdapter успішно відправляє ордер на біржу.

Система перезавантажується до того, як AccountObserver або інший механізм підтвердить виконання ордера.

Після перезапуску, логіка відновлення (якщо вона існує) може повторно ініціювати той самий CMD:OPEN.

Оскільки ніде не ведеться облік відправлених idempotent_key, BinanceExecutionAdapter відправляє другий, ідентичний ордер, що призводить до подвоєння позиції та ризику.

12. "Висячі" ордери через нереалізовану логіку скасування

Проблема: Система використовує ордери типу GTC ("Good-Till-Cancel"), що передбачає їх існування до виконання або скасування. Однак функція cancel_order в адаптері є лише заглушкою (placeholder).

Локація: Файл: binance_execution_adapter.py, Функція: cancel_order, Рядки: ~334-342.

Наслідок: Якщо система відправляє лімітний ордер і ринкова ціна йде в іншому напрямку, цей ордер залишається активним на біржі невизначений час. Якщо пізніше система вирішить увійти в позицію в протилежному напрямку, цей старий, "забутий" ордер може бути несподівано виконаний за вкрай невигідною ціною, що призведе до миттєвого збитку. Це створює на рахунку міни уповільненої дії.

13. Генерація хибних сигналів через розриви в ринкових даних

Проблема: Компонент feature_engineering розраховує зміну ціни (delta_price) як просту різницю між поточним та попереднім тіком. Відсутня будь-яка перевірка часового інтервалу (timestamp) між цими тіками.

Локація: Файл: feature_engineering.py, Функція: _calculate_features_with_history, Рядки: ~206-213.

Наслідок: У випадку короткочасного збою з'єднання з WebSocket (навіть на кілька секунд), перший тік після відновлення з'єднання буде порівнюватися з останнім тіком до збою. Це створить штучний, величезний delta_price, який не відображає реальну ринкову динаміку. Оскільки delta_price використовується в RiskManagement для оцінки ризику, це може призвести до помилкового блокування торгівлі (is_trading_allowed = false) на волатильному, але здоровому ринку, або, навпаки, до ігнорування реального ризику. Це спричиняє або втрату можливостей, або неадекватну оцінку ризику.
14. Прийняття рішень на основі застарілого стану портфеля ("Stale State")
Проблема: Компонент DecisionMaking не очищує дані про портфель (self.latest_portfolio) після прийняття або відхилення торгового рішення. Це створює тривалу "сліпу зону", протягом якої система продовжує приймати рішення, базуючись на неактуальній інформації про власні позиції та капітал.
Локація: Файл: decision_making.py, Функція: clear_internal_state, Рядки: ~448-456. Коментар у коді прямо вказує: Note: latest_portfolio is NOT cleared here as it should persist.
Наслідок: Цей дефект має два руйнівні наслідки:
Втрата прибуткових угод: Якщо позиція закривається (вручну або іншим механізмом), DecisionMaking не дізнається про це до наступного оновлення від AccountConnector (яке відбувається раз на 30 секунд). Протягом цього часу він буде продовжувати відхиляти нові валідні сигнали на вхід по цьому ж інструменту, посилаючись на POSITION_ACCUMULATION_BLOCKED, хоча насправді позиції вже немає.
Неконтрольоване накопичення ризику: Якщо система зазнала збитку (наприклад, через частковий стоп-лос), DecisionMaking буде продовжувати розраховувати розмір нових позицій на основі старого, більшого значення капіталу (equity), доки не прийде наступне оновлення. Це систематично призводить до відкриття позицій з надмірним ризиком.
Ланцюг (Втрата можливості):
Система має відкриту позицію long BTCUSDT. DecisionMaking зберігає цей стан у self.latest_portfolio.
Трейдер вручну закриває цю позицію на біржі.
Через 2 секунди DecisionMaking отримує новий сильний сигнал на long BTCUSDT.
Функція _try_make_decision перевіряє self.latest_portfolio (який ще не оновився) і бачить, що позиція нібито існує.
Сигнал відхиляється з причиною POSITION_ACCUMULATION_BLOCKED.
Через 28 секунд надходить оновлення від AccountConnector, self.latest_portfolio оновлюється, але сприятливий момент для входу вже втрачено.
Цей звіт завершує аналіз критичних помилок. Виявлені проблеми охоплюють дефекти в логіці, стани гонитви, архітектурні недоліки та неадекватне управління станом, кожен з яких може призвести до значних фінансових втрат.