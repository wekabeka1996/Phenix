# Форензічний звіт по спробах відкриття ордерів за 2026-03-20

## 1. Scope

- Часове вікно аналізу: 2026-03-20 04:00:02 -> 21:20:03, локальний час +02:00.
- Джерела доказів:
  - logs/order_log_v1.jsonl
  - logs/trade_lifecycle.jsonl
  - logs/aurora_trades.log
  - logs/domain_mean_reversion.log
  - config/aurora/domains.yaml
  - config/aurora/trading.yaml
  - config/aurora/strategies/aurora.yaml
  - config/aurora/strategies/md_amr.yaml
  - apps/reference/domains/decision_making/safety_gates.py
  - apps/reference/domains/execution_position/open_executor.py
  - apps/reference/domains/execution_position/watchdog.py
  - apps/reference/telemetry/trade_lifecycle_logger.py
- Правило обліку:
  - Відкриваючою спробою вважаю або DecisionMaking ORDER_INTENT, або DecisionMaking ORDER_REJECTED без проміжного ORDER_INTENT.
  - ExposureGuard ORDER_INTENT трактую як підготовчий reservation step, а не як окрему спробу відкриття позиції.

## 2. Executive Summary

- Всього decision-level спроб відкриття: 68.
- З них:
  - 20 явних DecisionMaking ORDER_INTENT.
  - 48 прямих DecisionMaking ORDER_REJECTED без зафіксованого ORDER_INTENT у order_log_v1.
  - 5 ордерів реально пішли на біржу через ORDER_PLACED.
  - 3 інтента були валідні на рівні DecisionMaking, але відхилені вже на execution/exchange-рівні як NRR-018 MAKER_ONLY_REJECT.
  - 12 DOGEUSDT інтентів лишились у стані intent-only в order_log_v1, але додатковий cross-check по aurora_trades.log показує для них guard-level reject path, переважно trade_intent_boundary_audit.
- Розподіл reject-кодів за день:
  - NRR-026: 28
  - NRR-027: 17
  - NRR-018: 3
  - NRR-029: 2
  - NRR-030: 1
- По символах:

| Symbol | Placed | Rejected | Intent-only |
| --- | ---: | ---: | ---: |
| XRPUSDT | 0 | 15 | 0 |
| BNBUSDT | 1 | 16 | 0 |
| DOGEUSDT | 1 | 0 | 12 |
| BTCUSDT | 3 | 20 | 0 |

## 3. SSOT / Runtime Anchors

- directional_sanity.min_regime_confidence = 0.42. Це прямо підтверджує причину NRR-026 у багатьох reject.
- Для aurora entry policy: LIMIT + GTX.
- Для md_amr entry policy: LIMIT + GTX; у конфігу є gtx_fallback_to_market: true, але в наданих логах доказів реального fallback у MARKET немає.
- Глобальний watchdog fill_ttl_ms = 300000 ms, але pending entry може жити довше через per-timeframe pending_entry_ttl override.
- order_index.ttl_sec = 3600.
- trade_lifecycle_logger формує close_reason як TTL_EXPIRED_${self._orphan_ttl_sec}s і переводить запис у ORPHANED_TTL, якщо запис не став CLOSED/CANCELLED до cutoff.

## 4. Що доведено, що інферується, що не доведено

### Доведено

- Ризикові гейти працювали fail-closed: 48 спроб були відхилені до placement на біржу.
- П'ять ордерів реально були відправлені на біржу: 1 по DOGEUSDT, 1 по BNBUSDT, 3 по BTCUSDT.
- У наданих логах немає жодного доказу ORDER_FILLED для цих п'яти відкриваючих ордерів у межах дня.
- Є щонайменше один явний конфлікт між order_log_v1 і trade_lifecycle по rid aurora_BTCUSDT_1774024502404.
- aurora_trades.log підтверджує, що частина intent-only кейсів з order_log_v1 насправді отримувала GUARD_REJECT уже після EVENT_TRADE_INTENT_PROPOSED, а не просто зникала безслідно.
- domain_mean_reversion.log підтверджує, що mean_reversion по DOGEUSDT справді генерував сигнал, тобто проблема для цих кейсів була downstream після стратегії, а не у відсутності сигналу.

### Інферується

- Для DOGEUSDT intent-only кейсів order_log_v1 не є повним джерелом істини: частина з них, імовірно, відхилялася на trade_intent_boundary_audit path, який видно в aurora_trades.log, але не нормалізовано в order_log_v1 тим самим rid.
- Для BNBUSDT rid mdamr-0146f6b2d6e68a46 ордер, імовірно, вже став terminal/expired на біржі до моменту cancel-спроби, бо cancel path повернув order_status_before = EXPIRED_IN_MATCH.

### Не доведено на наданих артефактах

- Точна one-to-one відповідність між кожним DOGEUSDT rid із order_log_v1 і рядком GUARD_REJECT в aurora_trades.log, бо aurora_trades.log не містить rid.
- Чому trade_lifecycle для aurora_BTCUSDT_1774024502404 не був оновлений до CANCELLED після успішного timeout_cancellation.

## 5. Ордери, що реально дійшли до біржі

| Local time | RID | Symbol | Strategy | Side | Entry type | Exchange order id | Біржовий тип | Outcome |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 04:35:04 | rid-9e52932a3c11b014 | DOGEUSDT | mean_reversion | BUY | MARKET | 747734092 | MARKET / GTC | ORDER_PLACED, далі в trade_lifecycle = ORPHANED_TTL |
| 06:30:03 | mdamr-0146f6b2d6e68a46 | BNBUSDT | md_amr | SELL | LIMIT | 1317227402 | LIMIT / GTX | ORDER_PLACED -> ORDER_TIMEOUT -> ORDER_CANCELLATION_FAILED -> trade_lifecycle ORPHANED_TTL |
| 18:25:01 | aurora_BTCUSDT_1774023901779 | BTCUSDT | aurora | SELL | LIMIT | 12900837093 | LIMIT / GTX | ORDER_PLACED -> ORDER_CANCELLED reason = CANCEL_SUPERSEDED -> trade_lifecycle CANCELLED |
| 18:35:02 | aurora_BTCUSDT_1774024502404 | BTCUSDT | aurora | SELL | LIMIT | 12900973306 | LIMIT / GTX | ORDER_PLACED -> ORDER_TIMEOUT -> ORDER_CANCELLED success, але trade_lifecycle = ORPHANED_TTL |
| 19:15:00 | aurora_BTCUSDT_1774026900679 | BTCUSDT | aurora | SELL | LIMIT | 12901495175 | LIMIT / GTX | ORDER_PLACED -> ORDER_TIMEOUT -> ORDER_CANCELLED -> CANCEL_SUPERSEDED -> trade_lifecycle CANCELLED |

## 6. Deep Dive по кожному ордеру, що пройшов на біржу

### 6.1 DOGEUSDT rid-9e52932a3c11b014

- 04:35:04 система згенерувала DecisionMaking ORDER_INTENT на BUY 95953.0 по 0.093555, regime = LOW_VOLATILITY, regime_confidence = 0.5831059335192259.
- Через 0.7 с зафіксовано ORDER_PLACED з order_id = 747734092.
- Біржова відповідь вказує MARKET / GTC, status = NEW.
- У logs/order_log_v1.jsonl далі немає ні ORDER_TIMEOUT, ні ORDER_CANCELLED, ні ORDER_FILLED для цього rid.
- У logs/trade_lifecycle.jsonl запис існує як ORPHANED_TTL з close_reason = TTL_EXPIRED_3600s і close через 6898.9 с від intent.
- Висновок: ордер точно дійшов до біржі, але подальший lifecycle у primary execution log не закритий. Є пізній orphan close у trade_lifecycle, але немає підтвердженого execution-side завершення.

### 6.2 BNBUSDT mdamr-0146f6b2d6e68a46

- 06:30:03 DecisionMaking ORDER_INTENT: SELL 13.91 по 644.595, regime = LOW_VOLATILITY, regime_confidence = 0.7569186042961792.
- Через 0.7 с зафіксовано ORDER_PLACED, order_id = 1317227402.
- Біржова відповідь: LIMIT / GTX, status = NEW.
- Через приблизно 1800.5 с отримано ORDER_TIMEOUT, why = Order timeout: fill_timeout.
- Після цього система спробувала cancel, але отримала ORDER_CANCELLATION_FAILED:
  - success = false
  - reason = EXCEPTION_AFTER_2_RETRIES: [-2011] Unknown order sent. (no-nrr)
  - order_status_before = EXPIRED_IN_MATCH
- У trade_lifecycle цей же rid лишився ORPHANED_TTL з close_reason = TTL_EXPIRED_3600s та закрився лише через 9299.1 с від intent.
- Висновок: ордер був розміщений, не заповнився в allowed fill window, а cancel path не зміг консистентно завершити lifecycle. Це проблемний execution/telemetry кейс, але не факт капітального витоку, бо exchange-side до моменту cancel уже виглядав terminal.

### 6.3 BTCUSDT aurora_BTCUSDT_1774023901779

- 18:25:01 DecisionMaking ORDER_INTENT: SELL 0.142 по 69992.14678571429, regime = TREND_DOWN, regime_confidence = 0.4392064252388671.
- Через 1.3 с ORDER_PLACED, order_id = 12900837093.
- Біржова відповідь: LIMIT / GTX, status = NEW.
- Через 601.3 с trade_lifecycle уже має status = CANCELLED, close_reason = CANCEL_SUPERSEDED.
- order_log_v1 підтверджує ORDER_CANCELLED reason = CANCEL_SUPERSEDED, context = new_open_side=SELL.
- Висновок: це чистий supersede-cycle. Перший pending BTC SELL був знятий, бо система вирішила перевиставити новий SELL ордер.

### 6.4 BTCUSDT aurora_BTCUSDT_1774024502404

- 18:35:02 DecisionMaking ORDER_INTENT: SELL 0.143 по 69859.35678571429, regime = TREND_DOWN, regime_confidence = 0.4839616090559017.
- Через 5.9 с ORDER_PLACED, order_id = 12900973306.
- Біржова відповідь: LIMIT / GTX, status = NEW.
- Через приблизно 1200.2 с система згенерувала ORDER_TIMEOUT з why = Order timeout: fill_timeout.
- Через ще приблизно 0.7 с зафіксований ORDER_CANCELLED з reason = timeout_cancellation і adapter_response:
  - success = true
  - reason = CANCEL_SUCCESS
  - order_status_before = NEW
  - order_status_after = CANCELED
  - is_idempotent_success = true
- Але в trade_lifecycle той самий rid лишився status = ORPHANED_TTL, close_reason = TTL_EXPIRED_3600s, close_ts через 5401.0 с від intent.
- Головний висновок по цьому rid:
  - exchange/execution log каже: timeout-cancel успішний;
  - trade lifecycle каже: запис осиротів і закрився TTL-механізмом.
- Це не різні інтерпретації одного стану. Це взаємно конфліктні стани одного rid.
- Рівень ризику: S1 для observability/state-consistency, бо downstream аудит або аналітика по trade_lifecycle побачать цей кейс як orphan, хоча execution log показує штатне cancel-завершення.

### 6.5 BTCUSDT aurora_BTCUSDT_1774026900679

- 19:15:00 DecisionMaking ORDER_INTENT: SELL 0.143 по 69782.31357142857, regime = TREND_DOWN, regime_confidence = 0.5541324457130755.
- Через 0.6 с ORDER_PLACED, order_id = 12901495175.
- Через приблизно 1200.8 с ORDER_TIMEOUT.
- Після цього є два cancel-сигнали:
  - ORDER_CANCELLED reason = timeout_cancellation, adapter_response.reason = PRE_CHECK_TERMINAL_CANCELED, already_canceled = true
  - ORDER_CANCELLED reason = CANCEL_SUPERSEDED
- У trade_lifecycle rid має status = CANCELLED, close_reason = CANCEL_SUPERSEDED, close через 1201.2 с.
- Висновок: execution path визнав ордер уже terminal/canceled до явної cancel-операції, а потім ще отримав supersede signal. Це не так критично, як попередній кейс, бо підсумковий lifecycle status залишився CANCELLED, а не orphaned.

## 7. Exchange-level rejects після валідного інтенту

Це кейси, де DecisionMaking інтент відбувся, але ExecPosFSM / exchange-рівень відхилив ордер як MAKER_ONLY_REJECT.

| Local time | RID | Symbol | Side | Regime | Regime confidence | Reject |
| --- | --- | --- | --- | --- | ---: | --- |
| 04:00:02 | mdamr-82b79abf35c0ee8b | XRPUSDT | SELL | LOW_VOLATILITY | 0.43529581255416655 | NRR-018 MAKER_ONLY_REJECT |
| 19:35:01 | aurora_BTCUSDT_1774028101301 | BTCUSDT | SELL | TREND_DOWN | 0.6078870466914512 | NRR-018 MAKER_ONLY_REJECT |
| 20:05:03 | aurora_BTCUSDT_1774029903353 | BTCUSDT | SELL | TREND_DOWN | 0.6358568058459718 | NRR-018 MAKER_ONLY_REJECT |

Ключовий зміст:

- Це не safety gate reject.
- Це не відсутність regime confidence.
- Це execution-layer / venue-layer reject для GTX / maker-only entry поведінки.

## 8. Intent-only кейси без видимого execution outcome в order_log_v1

Усі ці кейси належать DOGEUSDT і мають DecisionMaking ORDER_INTENT, але в order_log_v1 немає ні ORDER_PLACED, ні ORDER_REJECTED, ні ORDER_TIMEOUT по тому ж rid. Додатковий cross-check по aurora_trades.log показує, що часово відповідні сигнали після EVENT_TRADE_INTENT_PROPOSED отримували GUARD_REJECT, переважно з причиною trade_intent_boundary_audit. Це зменшує ймовірність "безслідного зникнення" і натомість вказує на розрив нормалізації між aurora_trades.log та order_log_v1.

| Local time | RID | Side | Regime | Confidence | trade_lifecycle status | close delay, sec |
| --- | --- | --- | --- | ---: | --- | ---: |
| 07:00:04 | rid-965c765fbf6f8c1f | SELL | LOW_VOLATILITY | 0.30382752760655574 | ORPHANED_TTL | 7497.5 |
| 07:05:04 | rid-80b09a0ea64b410c | SELL | LOW_VOLATILITY | 0.30382752760655574 | ORPHANED_TTL | 7197.9 |
| 07:10:04 | rid-a6445de95b51f1ad | SELL | LOW_VOLATILITY | 0.30382752760655574 | ORPHANED_TTL | 6897.5 |
| 09:05:02 | rid-2aee81ccd82ad660 | BUY | LOW_VOLATILITY | 0.5839365231213384 | ORPHANED_TTL | 13199.3 |
| 09:10:02 | rid-b7e8afbe05b109e1 | BUY | LOW_VOLATILITY | 0.5839365231213384 | ORPHANED_TTL | 12898.9 |
| 12:45:01 | rid-1277a9b782d2e1a0 | SELL | MEAN_REVERSION | 0.2995952862275874 | ORPHANED_TTL | 10200.7 |
| 12:50:01 | rid-b118b217ed18eb36 | SELL | MEAN_REVERSION | 0.23533321652323236 | ORPHANED_TTL | 9901.0 |
| 12:55:01 | rid-0112d876314f37f0 | SELL | MEAN_REVERSION | 0.23533321652323236 | ORPHANED_TTL | 9600.7 |
| 13:15:03 | rid-5ea989946243de9b | SELL | LOW_VOLATILITY | 0.30986921285374464 | ORPHANED_TTL | 8398.8 |
| 15:35:02 | rid-60fa6f98f09c83a1 | BUY | LOW_VOLATILITY | 0.563867126712885 | ORPHANED_TTL | 10199.8 |
| 16:00:04 | rid-f1b59abfc32cca9a | BUY | LOW_VOLATILITY | 0.563867126712885 | ORPHANED_TTL | 8697.5 |
| 19:35:01 | rid-6649eede91d6e2e5 | BUY | MEAN_REVERSION | 0.36383268075440117 | ORPHANED_TTL | не видно у trade_lifecycle наданого фрагмента |

Висновок по цьому блоку:

- DOGEUSDT має найслабшу простежуваність у canonical order log, але не в усіх логах загалом.
- За aurora_trades.log більшість цих кейсів виглядає як boundary-audit reject уже після intent propose.
- Це не confirmed placement, бо ORDER_PLACED по цих rid відсутній.
- Найобережніший висновок: проблема не лише в observability gap, а в тому, що trade/boundary reject path не зводиться в той самий rid-centric audit trail, що й order_log_v1.

## 8.1 Cross-check по aurora_trades.log і domain_mean_reversion.log

### DOGEUSDT

- 04:35:04 aurora_trades.log підтверджує EVENT_TRADE_INTENT_PROPOSED, а 04:35:05 EVENT_TRADE_EXECUTION ACK по order_id = 747734092. Це узгоджується з order_log_v1 і підтверджує, що перший DOGE BUY реально пішов на біржу.
- 07:00:04, 07:05:04, 07:10:04, 09:05:02, 09:10:02, 12:45:01, 12:50:01, 12:55:01, 13:15:03, 15:35:02, 16:00:04, 19:35:01 aurora_trades.log показує EVENT_TRADE_INTENT_PROPOSED, а через приблизно 5 секунд GUARD_REJECT. Для більшості з них причина прямо вказана як trade_intent_boundary_audit.
- domain_mean_reversion.log по цих же часових точках підтверджує MR_SIGNAL з конкретними параметрами входу. Отже, mean_reversion сигнал справді існував і відсікався не всередині самої стратегії, а вже після emission на boundary/gateway рівні.
- Окремо:
  - 04:40:04 і 06:45:03 aurora_trades.log містить GUARD_REJECT по DOGEUSDT buy з причиною strategy_signal_gateway:flip_unknown_state.
  - Ці записи пояснюють додаткові guard-side deny події навколо DOGE, яких не видно як canonical ORDER_REJECTED у order_log_v1.

### BTCUSDT

- 18:25:01 -> 18:25:03 aurora_trades.log повністю підтверджує intent -> ACK для rid aurora_BTCUSDT_1774023901779.
- 18:35:02 aurora_trades.log показує EVENT_TRADE_INTENT_PROPOSED, потім 18:35:07 GUARD_REJECT trade_intent_boundary_audit, і вже 18:35:08 EVENT_TRADE_EXECUTION ACK по order_id = 12900973306.
- Це важливий доказ: guard-side reject повідомлення не гарантує, що execution був зупинений. Принаймні один BTC кейс пройшов до ACK попри попередній GUARD_REJECT у aurora_trades.log.
- 19:15:00 -> 19:15:01 aurora_trades.log підтверджує intent -> ACK для rid aurora_BTCUSDT_1774026900679.
- 19:35:01 і 20:05:03 по BTC є EVENT_TRADE_INTENT_PROPOSED, а через 5 секунд GUARD_REJECT trade_intent_boundary_audit. Це узгоджується з подальшими execution-level reject у canonical logs для цих часових вікон.

### BNBUSDT

- 06:30:03 aurora_trades.log підтверджує intent -> ACK по order_id = 1317227402.
- 10:15:02 і 16:15:05 aurora_trades.log показує GUARD_REJECT по BNBUSDT з причиною md_amr_handler:regime_not_allowlisted.
- Це додає ще один reject layer, який не зводиться один-в-один до NRR-кодів із order_log_v1: частина deny відбувається на handler/gateway рівні раніше за canonical execution reject.

## 9. Direct safety-gate rejects до виходу на біржу

### 9.1 XRPUSDT

| Local time | RID | Side | Code | Причина |
| --- | --- | --- | --- | --- |
| 06:45:04 | mdamr-76770771049ccc86 | BUY | NRR-027 | SAFETY_GATES:downtrend blocks long |
| 09:15:03 | mdamr-521785582387f57d | BUY | NRR-026 | regime_confidence=0.3076552322856415 < 0.42 |
| 10:15:02 | mdamr-1a8589fbfb63410f | SELL | NRR-027 | SAFETY_GATES:uptrend blocks short |
| 10:30:02 | mdamr-990e189a83a619b4 | SELL | NRR-026 | regime_confidence=0.2874842145887952 < 0.42 |
| 11:30:01 | mdamr-2e24a9e8144df1de | BUY | NRR-026 | regime_confidence=0.4062814207871106 < 0.42 |
| 12:00:03 | mdamr-5f9895687762dc3c | BUY | NRR-026 | regime_confidence=0.2383561614386794 < 0.42 |
| 12:15:04 | mdamr-de7c1d817d8d1b65 | BUY | NRR-026 | regime_confidence=0.2383561614386794 < 0.42 |
| 12:30:05 | mdamr-902aeac42d819669 | BUY | NRR-026 | regime_confidence=0.3558696404371671 < 0.42 |
| 13:45:05 | mdamr-f624bfd979d88358 | BUY | NRR-026 | regime_confidence=0.3530201242660716 < 0.42 |
| 15:00:05 | mdamr-9e02111368a11a12 | BUY | NRR-026 | regime_confidence=0.4131002744709955 < 0.42 |
| 15:15:01 | mdamr-616365b3803f3558 | BUY | NRR-027 | SAFETY_GATES:downtrend blocks long |
| 16:00:04 | mdamr-0b1e6a7cfbcdfdcf | BUY | NRR-026 | regime_confidence=0.3982916409224321 < 0.42 |
| 17:00:03 | mdamr-f9a8d9a894f15200 | BUY | NRR-026 | regime_confidence=0.3269332262237811 < 0.42 |
| 17:15:04 | mdamr-e1b1d18d3b4fb6ae | BUY | NRR-026 | regime_confidence=0.3822986538443226 < 0.42 |

Патерн XRPUSDT:

- Лонги переважно рубалися downtrend blocks long.
- Шорти або рубалися uptrend blocks short, або не проходили confidence gate.
- Жодна XRP-спроба не дійшла до successful placement.

### 9.2 BNBUSDT

| Local time | RID | Side | Code | Причина |
| --- | --- | --- | --- | --- |
| 05:30:04 | mdamr-368b9cb49988635e | SELL | NRR-026 | regime_confidence=0.3433302905410841 < 0.42 |
| 06:00:01 | mdamr-d548f95238ed63d4 | SELL | NRR-027 | SAFETY_GATES:uptrend blocks short |
| 06:15:01 | mdamr-d41e171b0f5d1468 | SELL | NRR-027 | SAFETY_GATES:uptrend blocks short |
| 09:15:03 | mdamr-a3c5beb2f27214e6 | BUY | NRR-026 | regime_confidence=0.3283263480401995 < 0.42 |
| 09:45:05 | mdamr-2c668ea87512f9de | SELL | NRR-026 | regime_confidence=0.24321223540243758 < 0.42 |
| 10:30:03 | mdamr-7e576eac40600223 | SELL | NRR-026 | regime_confidence=0.24448528156864835 < 0.42 |
| 10:45:04 | mdamr-f933288345946a88 | SELL | NRR-026 | regime_confidence=0.254448919223454 < 0.42 |
| 11:00:04 | mdamr-9855374e2fe01259 | SELL | NRR-026 | regime_confidence=0.3282755176532493 < 0.42 |
| 11:30:01 | mdamr-f2df34b35691f5c3 | BUY | NRR-026 | regime_confidence=0.3973268251554564 < 0.42 |
| 12:00:03 | mdamr-f7ada3cfbdf6b8de | BUY | NRR-027 | SAFETY_GATES:downtrend blocks long |
| 12:15:04 | mdamr-559e3c8697192f33 | BUY | NRR-026 | regime_confidence=0.304157664413269 < 0.42 |
| 12:30:05 | mdamr-83ca0a7ab9377da4 | BUY | NRR-026 | regime_confidence=0.28039133083971557 < 0.42 |
| 13:45:05 | mdamr-21a05f92efd771a7 | BUY | NRR-027 | SAFETY_GATES:downtrend blocks long |
| 16:00:05 | mdamr-5ebdadeae8326528 | BUY | NRR-027 | SAFETY_GATES:downtrend blocks long |
| 19:45:03 | mdamr-854215ff734d42dc | BUY | NRR-026 | regime_confidence=0.2772555414753724 < 0.42 |
| 20:45:03 | mdamr-70c0bf1157416d8d | BUY | NRR-026 | regime_confidence=0.2767693350511694 < 0.42 |

Патерн BNBUSDT:

- Переважає NRR-026: regime confidence майже весь день нижче 0.42.
- Коли confidence gate не спрацьовує, long-и все одно часто блокує downtrend, а short-и блокує uptrend.
- Лише одна BNB спроба дійшла до placement, але закінчилась timeout/cancel failure та пізнім orphan TTL.

### 9.3 BTCUSDT

| Local time | RID | Side | Code | Причина |
| --- | --- | --- | --- | --- |
| 09:05:02 | aurora_BTCUSDT_1773990302026 | SELL | NRR-029 | SAFETY_GATES:flash up blocks short |
| 09:20:02 | aurora_BTCUSDT_1773991202855 | SELL | NRR-027 | SAFETY_GATES:uptrend blocks short |
| 13:55:00 | aurora_BTCUSDT_1774007700474 | SELL | NRR-027 | SAFETY_GATES:uptrend blocks short |
| 14:05:00 | aurora_BTCUSDT_1774008300889 | SELL | NRR-026 | regime_confidence=0.3504423655124252 < 0.42 |
| 14:15:01 | aurora_BTCUSDT_1774008901971 | SELL | NRR-026 | regime_confidence=0.3504423655124252 < 0.42 |
| 14:30:03 | aurora_BTCUSDT_1774009802997 | SELL | NRR-026 | regime_confidence=0.3504423655124252 < 0.42 |
| 15:04:59 | aurora_BTCUSDT_1774011899905 | SELL | NRR-030 | SAFETY_GATES:bleed up blocks short |
| 15:20:00 | aurora_BTCUSDT_1774012800846 | SELL | NRR-027 | SAFETY_GATES:uptrend blocks short |
| 17:20:03 | aurora_BTCUSDT_1774020003038 | SELL | NRR-026 | regime_confidence=0.2829593880301214 < 0.42 |
| 17:45:04 | aurora_BTCUSDT_1774021504732 | SELL | NRR-026 | regime_confidence=0.3608842279691164 < 0.42 |
| 18:00:01 | aurora_BTCUSDT_1774022400993 | SELL | NRR-026 | regime_confidence=0.3978668244445262 < 0.42 |
| 18:15:01 | aurora_BTCUSDT_1774023301685 | SELL | NRR-027 | SAFETY_GATES:uptrend blocks short |
| 19:05:04 | aurora_BTCUSDT_1774026304352 | SELL | NRR-027 | SAFETY_GATES:uptrend blocks short |
| 19:45:02 | aurora_BTCUSDT_1774028702528 | SELL | NRR-029 | SAFETY_GATES:flash up blocks short |
| 20:35:00 | aurora_BTCUSDT_1774031700095 | SELL | NRR-027 | SAFETY_GATES:uptrend blocks short |
| 20:45:01 | aurora_BTCUSDT_1774032301366 | SELL | NRR-027 | SAFETY_GATES:uptrend blocks short |
| 21:05:02 | aurora_BTCUSDT_1774033502054 | SELL | NRR-027 | SAFETY_GATES:uptrend blocks short |
| 21:20:03 | aurora_BTCUSDT_1774034402991 | SELL | NRR-027 | SAFETY_GATES:uptrend blocks short |

Патерн BTCUSDT:

- Для short-сценаріїв домінує directional block: uptrend blocks short.
- Додатково два рази спрацював flash up blocks short і один раз bleed up blocks short.
- Вікно 18:25 -> 19:15 є єдиним періодом дня, коли BTC short-и реально проходили до placement.

## 10. Найважливіші висновки

### Finding A. Ризикові гейти реально блокували небезпечні входи

- Це доведено NRR-026, NRR-027, NRR-029, NRR-030 серіями.
- Найпоширеніший блокер дня: недостатня regime_confidence відносно порогу 0.42.

### Finding B. Є S1-конфлікт між execution log і trade_lifecycle

- RID: aurora_BTCUSDT_1774024502404.
- order_log_v1 показує штатний timeout-cancel success.
- trade_lifecycle показує ORPHANED_TTL.
- Це означає, що downstream звітність може помилятися щодо фактичного фінального стану ордера.

### Finding C. Є окрема observability gap зона по DOGEUSDT

- 12 DOGEUSDT rid мають DecisionMaking intent, але не мають видимого execution outcome в order_log_v1.
- aurora_trades.log показує, що часово відповідні кейси переважно були відхилені на trade_intent_boundary_audit.
- trade_lifecycle при цьому все одно закриває їх як ORPHANED_TTL.
- Для аудиту це означає: тільки по одному order_log_v1 відновити повний lifecycle по DOGE сьогодні неможливо; потрібен обов'язковий cross-log correlation.

### Finding F. Є щонайменше один race / contract inconsistency між guard reject і execution ack

- Кейс: BTCUSDT 18:35.
- aurora_trades.log спочатку фіксує GUARD_REJECT trade_intent_boundary_audit, а через 1 секунду для того ж symbol/time window є EVENT_TRADE_EXECUTION ACK order_id = 12900973306.
- Це означає, що guard reject у цьому контурі не є достатнім доказом фактичної зупинки execution path.
- Рівень ризику: S1 для контрактної консистентності audit events.

### Finding D. Назва TTL_EXPIRED_3600s не збігається з фактичним elapsed time у наданому trade_lifecycle

- Фактичні close delays для таких записів сьогодні лежать приблизно в діапазоні 5401.0 -> 13199.3 с.
- Це не доводить runtime bug само по собі, але точно доводить, що семантика close_reason не дорівнює фактичному часу від intent до close.

### Finding E. MAKER_ONLY_REJECT сьогодні був окремим execution-stage класом відмов

- XRPUSDT: 1 випадок.
- BTCUSDT: 2 випадки.
- Це важливо відрізняти від safety gate denies: тут інтент уже існував, а відмова сталася на execution / venue path.

## 11. Підсумок у двох реченнях

Система за день переважно не відкривала угоди через коректно працюючі safety gates і guard/boundary rejects, а ті небагато ордерів, що реально дійшли до біржі, здебільшого не були заповнені та завершилися через supersede, timeout або orphan-style lifecycle closure. Найсерйозніша проблема не в самих gate reject, а в неузгодженості між guard log, canonical order log і trade_lifecycle-state, особливо по aurora_BTCUSDT_1774024502404, BTC 18:35 race-case і по серії DOGEUSDT boundary-audit кейсів.
