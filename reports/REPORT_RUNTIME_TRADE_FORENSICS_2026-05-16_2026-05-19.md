# REPORT_RUNTIME_TRADE_FORENSICS_2026-05-16_2026-05-19

Статус: PARTIAL_FAIL_CLOSED

## Прямі відповіді

- ТАК: у цьому runtime є окремі прибуткові зрізи по монеті та по режиму.
- FACT: найкраща монета серед доведено закритих угод це XRPUSDT: net after fees = +40.73618088 USDT, win rate = 50.00%, але вибірка лише 2 доведено закриті угоди.
- FACT: найкращий режим серед доведено закритих угод це TREND_DOWN: net after fees = +112.85958736 USDT, win rate = 100.00%, але вибірка лише 1 доведено закрита угода.
- FACT: якщо обрізати все зайве по fail-closed логіці та залишити тільки доведено закриті угоди, вся система в сумі не прибуткова: net after fees = -2.77297888 USDT.
- FACT: якщо дивитись лише на gross realized PnL без комісій, proven subset дає +13.50376000 USDT, але комісії повністю з'їдають цей плюс.

## Межі звіту

- Вікно runtime за order log: 2026-05-16T10:25:04.344000+00:00 .. 2026-05-19T16:30:00.289000+00:00.
- Вікно спостереження за trade_lifecycle: 2026-05-16T10:09:52.498000+00:00 .. 2026-05-19T16:47:18.852000+00:00.
- Основні джерела доказів: logs/order_log_v1.jsonl, logs/trade_lifecycle.jsonl.
- Метод: одноразовий streaming-розбір JSONL з fail-closed підходом до всіх епізодів, де немає канонічного close-fill або немає доказу біржового виконання.

## Що саме покриває звіт

- FACT: звіт покриває всі 6 канонічних ORDER_PLACED епізодів поточного runtime.
- FACT: окремо винесено 2 неконанічні / неоднозначні епізоди, які видно в lifecycle, але не можна чесно включати в proven PnL.
- FACT: часткові fill-и всередині одного canonical rid згорнуті в один торговий епізод, а не рахуються як окремі угоди.

## Доведені факти

- FACT: у logs/order_log_v1.jsonl є 148 ORDER_INTENT, 417 DECISION_INTENT_REJECTED, 6 ORDER_PLACED, 17 ORDER_FILLED, 3 ORDER_CANCELLED, 1 ORDER_REJECTED, 1 ORDER_TIMEOUT.
- FACT: до біржового submit boundary дійшло 6 канонічних епізодів.
- FACT: 5 із 6 submit-ів були активовані entry fill-ами.
- FACT: лише 3 із 5 активованих канонічних входів мають доведений close через канонічний ORDER_FILLED exit.
- FACT: gross realized PnL по доведено закритому subset = +13.50376000 USDT.
- FACT: entry fees по доведено закритому subset = 5.41342594 USDT.
- FACT: exit fees по доведено закритому subset = 10.86331294 USDT.
- FACT: net after trade fees по доведено закритому subset = -2.77297888 USDT.
- FACT: proven win rate по доведено закритому subset = 1 / 3 = 33.33%.
- FACT: already-paid entry fees по всіх 5 активованих канонічних входах = 9.32916592 USDT.
- FACT: sidecar згенерував 389891 suppression events, 1585 evaluated events, 112 recommended events, 112 close-requested events і 112 close-request-state events.

## Головний висновок

- FACT: система не є прибутковою на рівні всього proven closed subset цього runtime.
- FACT: локально прибуткові зрізи існують, але вони вузькі й мають малу вибірку.
- FACT: позитивний внесок у proven subset дає тільки XRPUSDT у режимі TREND_DOWN.
- FACT: BNBUSDT та частина XRP епізодів залишаються незавершеними або неоднозначними, тому я не маю права домалювати їм прибуток або win.
- INFERENCE: один XRPUSDT BUY після boundary error -1007, імовірно, все ж відкрився на біржі, але його фінал у поточному evidence set недоведений.

## Усі канонічні біржові епізоди

| placed_rid | symbol | side | regime | submit outcome | activation evidence | close evidence | gross realized pnl | known fees | net after fees | classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mdamr-0976be2f4bca1269 | BNBUSDT | SELL | LOW_VOLATILITY | ORDER_PLACED -> ORDER_TIMEOUT -> ORDER_CANCELLED | fill відсутній | відсутній | n/a | 0.00000000 | n/a | PLACED_NOT_FILLED |
| mdamr-c0dc956ee42c3a82 | BNBUSDT | BUY | MEAN_REVERSION | ORDER_PLACED | entry fill 15.29 @ 653.75 | POSITION_DISAPPEARANCE_ATTRIBUTED / unknown_disappearance | UNPROVEN | 1.99916750 відомий entry fee | UNPROVEN | DISAPPEARED_UNPROVEN |
| mdamr-c38fb3f60db601fa | XRPUSDT | BUY | MEAN_REVERSION | ORDER_PLACED | entry fill 7040.4 @ 1.4133 | ORDER_FILLED SL @ 1.4039 | -66.17976000 | 5.94364648 | -72.12340648 | CLOSED_PROVEN |
| aurora_BTCUSDT_1779067200283 | BTCUSDT | SELL | HIGH_VOLATILITY | ORDER_PLACED | entry fill 0.101 @ 77050.0 | ORDER_FILLED SL @ 77434.4 | -38.82440000 | 4.68475976 | -43.50915976 | CLOSED_PROVEN |
| mdamr-076a86230131256e | XRPUSDT | BUY | TREND_DOWN | ORDER_PLACED | часткові entry fill-и сумарно 6810.8 @ 1.3706 | ORDER_FILLED TP @ 1.3880 | 118.50792000 | 5.64833264 | 112.85958736 | CLOSED_PROVEN |
| mdamr-38c5a48005391671 | XRPUSDT | BUY | TREND_DOWN | ORDER_PLACED | часткові entry fill-и сумарно 7016.3 @ 1.3658 | close до кінця runtime відсутній | UNPROVEN | 1.91657248 відомий entry fee | UNPROVEN | OPEN_OR_UNCLOSED |

## Неоднозначні біржові епізоди

| episode | evidence chain | classification | impact |
| --- | --- | --- | --- |
| XRPUSDT BUY 6991.1 / boundary rid mdamr-b88071adc579575a | 2026-05-18T00:00:06.510000+00:00 ORDER_REJECTED з помилкою [-1007] Timeout waiting for response from backend server. Send status unknown; execution status unknown. -> 2026-05-18T00:01:40.857000+00:00 у trade_lifecycle видно portfolio_position_amt=6991.1, portfolio_entry_price=1.4007, manage_flow_has_no_active_lifecycle -> 2026-05-18T10:35:53.311000+00:00 POSITION_DISAPPEARANCE_ATTRIBUTED для 6991.1 @ 1.4007 | PROBABLE_EXCHANGE_EXPOSURE_WITHOUT_CANONICAL_LIFECYCLE | виключено з proven PnL та proven win rate, бо немає канонічного entry fill / exit fill / fee trace |
| ETHUSDT short 4.605 @ 2175.47 | lifecycle показує unknown disappearance на початку runtime, але в order_log_v1.jsonl немає matching ORDER_PLACED / ORDER_FILLED у межах цього runtime | PREEXISTING_OR_EXTERNAL_CARRY_OVER | виключено з поточного trade scorecard |

## Де система реально заробляла

### Рейтинг По Монетах

| symbol | proven closed | wins | losses | proven win rate | gross realized pnl | net after fees | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| XRPUSDT | 2 | 1 | 1 | 0.5000 | 52.32816000 | 40.73618088 | найкраща монета в proven subset |
| BTCUSDT | 1 | 0 | 1 | 0.0000 | -38.82440000 | -43.50915976 | збиткова |

Висновок по монетах:

- FACT: XRPUSDT є прибутковою монетою в межах доведено закритого subset.
- FACT: XRPUSDT має найвищий proven net result: +40.73618088 USDT after fees.
- FACT: XRPUSDT також має найвищий proven win rate серед монет: 50.00%.
- FACT: BTCUSDT у proven subset збитковий і має win rate 0.00%.

### Рейтинг По Режимах

| regime | proven closed | wins | losses | proven win rate | gross realized pnl | net after fees | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TREND_DOWN | 1 | 1 | 0 | 1.0000 | 118.50792000 | 112.85958736 | найкращий режим у proven subset |
| HIGH_VOLATILITY | 1 | 0 | 1 | 0.0000 | -38.82440000 | -43.50915976 | збитковий |
| MEAN_REVERSION | 1 | 0 | 1 | 0.0000 | -66.17976000 | -72.12340648 | збитковий |

Висновок по режимах:

- FACT: TREND_DOWN є прибутковим режимом у proven subset.
- FACT: TREND_DOWN має найбільший proven net result: +112.85958736 USDT after fees.
- FACT: TREND_DOWN має найбільший proven win rate: 100.00%.
- IMPORTANT: ця перевага базується лише на 1 доведено закритій угоді, тому це сильний локальний сигнал, але не статистично стабільний режимний verdict.

## Підсумок По Всіх Доведено Закритих Угодах

| metric | value |
| --- | --- |
| canonical ORDER_PLACED episodes | 6 |
| activated canonical entries | 5 |
| proven closed episodes | 3 |
| proven wins | 1 |
| proven losses | 2 |
| proven win rate | 33.33% |
| gross realized pnl, proven closed only | +13.50376000 USDT |
| entry fees, proven closed only | 5.41342594 USDT |
| exit fees, proven closed only | 10.86331294 USDT |
| net pnl after trade fees, proven closed only | -2.77297888 USDT |

Короткий висновок:

- FACT: так, окремі монета й режим приносять прибуток.
- FACT: ні, весь proven closed subset не показує чистого прибутку після комісій.

## Вже Сплачені Комісії Поза Proven Closed Subset

| metric | value |
| --- | --- |
| known entry fees across all 5 activated canonical entries | 9.32916592 USDT |
| unresolved entry fees already paid on BNB disappeared + latest XRP open | 3.91573998 USDT |
| interpretation | навіть без реконструкції невідомих виходів система вже витратила 3.91573998 USDT entry commissions на епізоди, які ще не можна чесно оцінити по PnL |

## Decision-Level Blocked Intents

### Підсумок По NRR Кодах

| class | nrr_code | threshold_verdict | count | meaning |
| --- | --- | --- | --- | --- |
| regime confidence floor | NRR-026 | BLOCK | 254 | жорсткий блок, бо regime_confidence < 0.42 |
| directional sanity | NRR-027 | PASS | 109 | directional veto після проходження confidence threshold |
| flash motion gate | NRR-029 | PASS | 30 | flash-up / flash-down veto |
| price-motion insufficiency | NRR-028 | PASS | 13 | недостатній price-motion veto |
| bleed motion gate | NRR-030 | PASS | 11 | bleed-up short veto |

### Підсумок По Причинах Блокування

| why family | count |
| --- | --- |
| regime_confidence_below_min | 254 |
| uptrend_blocks_short | 95 |
| flash_up_blocks_short | 29 |
| downtrend_blocks_long | 14 |
| price_motion_flash_insufficient | 12 |
| bleed_up_blocks_short | 11 |
| price_motion_bleed_insufficient | 1 |
| flash_down_blocks_long | 1 |

### Підсумок По Монетах

| symbol | reject count |
| --- | --- |
| SOLUSDT | 235 |
| ETHUSDT | 90 |
| XRPUSDT | 68 |
| BNBUSDT | 21 |
| BTCUSDT | 3 |

### Підсумок По Режимах

| regime | reject count |
| --- | --- |
| TREND_DOWN | 199 |
| MEAN_REVERSION | 129 |
| TREND_UP | 35 |
| HIGH_VOLATILITY | 28 |
| LOW_VOLATILITY | 26 |

### Найбільші Поверхні Блокування Symbol / Regime

| symbol | regime | reject count |
| --- | --- | --- |
| SOLUSDT | TREND_DOWN | 111 |
| SOLUSDT | MEAN_REVERSION | 91 |
| ETHUSDT | TREND_DOWN | 68 |
| XRPUSDT | MEAN_REVERSION | 29 |
| SOLUSDT | HIGH_VOLATILITY | 21 |
| ETHUSDT | TREND_UP | 18 |
| XRPUSDT | TREND_DOWN | 18 |
| XRPUSDT | LOW_VOLATILITY | 16 |
| SOLUSDT | TREND_UP | 12 |
| BNBUSDT | LOW_VOLATILITY | 10 |
| BNBUSDT | MEAN_REVERSION | 9 |

## Policy Sidecar

### Підсумок По Подіях

| event_type | count |
| --- | --- |
| POSITION_POLICY_SIDECAR_SUPPRESSED | 389891 |
| POSITION_POLICY_MICROSTRUCTURE_PRESSURE_EVALUATED | 390305 |
| POSITION_POLICY_SIDECAR_EVALUATED | 1585 |
| POSITION_POLICY_SIDECAR_SCORES | 1585 |
| POSITION_POLICY_SIDECAR_RECOMMENDED | 112 |
| POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE | 112 |
| POSITION_POLICY_SIDECAR_CLOSE_REQUESTED | 112 |
| POSITION_POLICY_SIDECAR_MODE_ACTIVE | 2 |

### Причини Suppression

| suppression_reason | count |
| --- | --- |
| features_snapshot_missing_or_stale | 139503 |
| no_manage_flow_for_symbol | 108287 |
| manage_flow_has_no_active_lifecycle | 64177 |
| authoritative_close_reconciled | 32580 |
| regime_snapshot_missing_or_stale | 24880 |
| portfolio_snapshot_missing_or_stale | 14374 |
| startup_grace_active | 4376 |
| recommendation_duplicate_same_state | 1165 |
| warmup_incomplete | 523 |
| post_fill_grace_active | 24 |
| manage_flow_close_in_progress | 2 |

### Suppression По Символах

| symbol | suppression count |
| --- | --- |
| DOGEUSDT | 56166 |
| SOLUSDT | 56161 |
| ETHUSDT | 56096 |
| BTCUSDT | 55971 |
| XRPUSDT | 55305 |
| BNBUSDT | 55270 |
| 1000PEPEUSDT | 54922 |

### Recommendation / Close-Request Surface

| symbol | recommended | close_requested |
| --- | --- | --- |
| BNBUSDT | 36 | 36 |
| BTCUSDT | 33 | 33 |
| XRPUSDT | 28 | 28 |
| ETHUSDT | 15 | 15 |

| reason_code | count |
| --- | --- |
| recommend_soft_close_threshold_met | 112 |
| trigger:regime_detected | 110 |
| trigger:features_calculated | 2 |

Інтерпретація:

- FACT: усі observed close-requested / recommended rows у цьому runtime slice містять reason code recommend_soft_close_threshold_met.
- FACT: payload-и мають evaluation_mode=phase1_recommendation_only, тому ці події слід читати як recommendation layer, а не як самодостатній доказ примусового виконання close.
- FACT: домінуючі suppression-ы пов'язані зі stale snapshot, відсутністю lifecycle owner та вже reconciled close.
- INFERENCE: sidecar у поточному runtime значно частіше не міг діяти через data/lifecycle constraints, ніж реально штовхав виконувані close-и.

## Невідоме Та Fail-Closed Межі

- UNPROVEN: фінальна ціна виходу, фінальна причина закриття й фінальний PnL для канонічного BNBUSDT MEAN_REVERSION long, який пізніше зник.
- UNPROVEN: фінальний PnL і повний fee burden для probable ghost XRPUSDT 6991.1 long після -1007 adapter timeout.
- UNPROVEN: mark-to-market або realized result для останнього XRPUSDT TREND_DOWN long, який залишився open / unclosed на runtime tail.
- UNPROVEN: чи хоч одна sidecar recommendation прямо спричинила close у межах поточного runtime slice; наявні докази підтверджують рекомендації, але не authoritative downstream execution для цих рядків.

## Валідація

- Validation 1: one-pass parse logs/order_log_v1.jsonl для ORDER_PLACED / ORDER_FILLED / DECISION_INTENT_REJECTED / ORDER_TIMEOUT / ORDER_CANCELLED / ORDER_REJECTED і реконструкція епізодів.
- Validation 2: one-pass parse logs/trade_lifecycle.jsonl для POSITION_DISAPPEARANCE_ATTRIBUTED і POSITION_POLICY_* count / suppression reason.
- Validation 3: cross-check канонічних episode outcome проти disappearance records там, де точно збігаються symbol, quantity та average price.
- Validation 4: fail-closed виключення всіх епізодів, де close лише припускається з portfolio state, disappearance або sidecar state без канонічного close fill.

## Шляхи До Доказів

- logs/order_log_v1.jsonl
- logs/trade_lifecycle.jsonl
- config/aurora/domains.yaml
