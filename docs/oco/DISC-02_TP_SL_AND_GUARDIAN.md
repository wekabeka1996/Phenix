# DISC-02 TP/SL та OrderGuardian

## Місця створення TP/SL (таблиця: файл → функція → тип брекету)

| Файл (функція) | Тип/контекст | Що відбувається та які прапорці ставляться |
| --- | --- | --- |
| `apps/reference/domains/execution_position/fsm_manage.py#L360` `_place_brackets_legacy` | персональний TP/SL для кожного entry | `resolve_brackets_config` дає стоп/профіт за bps, проходяться перевірки (mark price, offset, tick size) і `STOP_MARKET`/`LIMIT` оформлюються через `_emit_place_order` (`apps/reference/domains/execution_position/fsm_manage.py#L1078`). payload завжди `reduceOnly=True`, `workingType=MARK_PRICE`, `priceProtect`/`newClientOrderId` з `rid`, а `side` залежить від position (SL на true-side, TP — протилежний). Ризик: як тільки entry дублюється (scale-in, manual cancel), цей локальний бракет може залишитись без загального контролю, тому `OrderGuardian.cleanup_orphans` також викликається при `position_amt == 0` (`apps/reference/services/order_guardian.py#L1471`). |
| `apps/reference/domains/execution_position/fsm_manage.py#L553` `_place_or_update_bracket_set_from_levels` | агрегований OCO для всього `(symbol, side)` | Коли `aggregated_oco.enabled`, `compute_aggregated_brackets` (риски/tick size з `vfoundation/apps/reference/domains/execution_position/bracket_aggregator.py#L1`) генерує нові `tp_price/sl_price`, `_emit_place_order` ставить пару `STOP_MARKET`/`LIMIT` з `reduceOnly=True`, `qty=position_qty`, `closePosition` не використовується, але метадані капсуються в `BracketSetMeta` через `OrderGuardian.register_bracket_set` (`apps/reference/services/order_guardian.py#L223`). Усі клієнтські ID формуються з `rid` + timestamp (`_maybe_register_bracket_set`) і гарантують, що `OrderGuardian` знає, які ордери належать агрегату (`apps/reference/domains/execution_position/fsm_manage.py#L628`). |
| `apps/reference/domains/execution_position/fsm.py#L2230` (DEC:CLOSE) | закриття/авто-валидація | `DEC:CLOSE` спочатку просить `OrderGuardian.close_entry` (або скасовує записані SL/TP) для звʼязаних брекетів (`apps/reference/services/order_guardian.py#L1405`), потім пускає `adapter.place_market_reduce_only` з `reduce_only=True`/`client_id=GENERATED`. Додатково викликається `OrderGuardian.cleanup_orphans` (`apps/reference/services/order_guardian.py#L1471`) для очистки reduceOnly/`closePosition` ордерів по символу. Якщо нема `parent_order_id`, реакція — скасувати `_symbol_brackets` всередині FSM та підтвердити via `OrderGuardian.cleanup_other_brackets_for_symbol` (`apps/reference/services/order_guardian.py#L1688`). |

## Поточна роль OrderGuardian

- **Трекінг entry/brackets:** `register_entry` + `register_bracket[s]` зберігають керовані `client_order_id → order_id`, кількість виконань (`on_fill`) та metadata (`apps/reference/services/order_guardian.py#L828`, `#L921`, `#L301`). |
- **Роль у дозвонах:** `should_place_brackets` опитує `/open_positions` і запобігає батчам без активної позиції або якщо entry вже `close_position=True` (`apps/reference/services/order_guardian.py#L1271`). |
- **Агрегований OCO:** `register_bracket_set`/`get_active_bracket_set` + `rehydrate_bracket_set_for_position` тримають `BracketSetMeta` (`symbol, side, sl_order_id, tp_order_id, version`) та дають гарантію по одній парі на сторону (`apps/reference/services/order_guardian.py#L223`, `#L269`). `AggregatedOcoGuardianConfig` (TTL, allow_unprotected) керує `ensure_single_bracket_set_for_position`, який захищає щойно поставлені ордери, не дозволяє прибирати останній SL якщо `position_amt > 0` і видаляє `bracket_set` при повному закритті (`apps/reference/services/order_guardian.py#L135`, `#L432`). |
- **Диск/восстановлення:** `_startup_relink_known_symbols` + `link_existing_from_rest` пов’язують існуючі `reduceOnly/closePosition` ордери зі стором після рестарту (`apps/reference/services/order_guardian.py#L1140`, `#L1173`). |
- **Синхронізація/чистка:** `cleanup_before_close`/`close_entry` обробляють DEC:CLOSE, `cleanup_orphans` скидає всі ордери при `position_amt == 0`, `cleanup_other_brackets_for_symbol` виконує `ensure_single_bracket_set_for_position` для символу навіть зі `position_amt > 0`, `reconcile_symbol` викликає їх у полігоні (`apps/reference/services/order_guardian.py#L1324`, `#L1405`, `#L1471`, `#L1688`, `#L1910`). |
- **Документована поведінка:** `apps/reference/domains/execution_position/Readme/CONTRACT_aggregated_oco_v1.md#L1` описує інваріанти (одна пара на символ/сторону, `reduceOnly || closePosition`, canonical sides, DR-перезапуск тощо) і `AGG_OCO_*` сповіщення для моніторингу.

## Сценарії

### Перший вхід / відкриття позиції

- `ManageFlow` (legacy або aggregated залежно від config) рахує TP/SL (`_calculate_bracket_prices` або `compute_aggregated_brackets`), викликає `_place_brackets` → `_emit_place_order` і реєструє метадані у `OrderGuardian` (`apps/reference/domains/execution_position/fsm_manage.py#L357`, `#L553`, `#L1078`). |
- При `aggregated_oco.enabled` після подвійного ACK викликається `register_bracket_set`, туди потрапляють активні `sl_order_id/tp_order_id`, `side=LONG|SHORT` і TTL/версія (`apps/reference/domains/execution_position/fsm_manage.py#L628`, `apps/reference/services/order_guardian.py#L223`). |
- Документація `CONTRACT_aggregated_oco_v1` описує інваріанти для першого entry і посилання на `tests/domains/execution_position/test_aggregated_oco_scale_in_legacy.py#L1` як перший сценарій (`apps/reference/domains/execution_position/Readme/CONTRACT_aggregated_oco_v1.md#L1`). |

### Scale-in

- При додаткових вікнах `_handle_aggregated_fill_event` (тільки для aggregated) відраховує `fill_qty`, при `recalc_on_scale_in=true` спрацьовує `_recalc_aggregated_brackets` → `_place_brackets_aggregated`, що знищує попередню пару через `OrderGuardian.ensure_single_bracket_set_for_position` (`apps/reference/domains/execution_position/fsm_manage.py#L851`, `#L1160`, `apps/reference/services/order_guardian.py#L432`). |
- `OrderGuardian` логів `AGG_OCO_BRACKET_GUARD` або `cleanup_extras`, забезпечуючи один SL/TP та не дозволяючи зайвим `reduceOnly`-ордером залишитися, навіть коли рецалк спрацьовує раніше ніж Binance повідомляє нові бракет-ідентифікатори. |
- `tests/domains/execution_position/test_aggregated_oco_scale_in_legacy.py#L1` підтверджує, що новий `bracket_set_id` створюється, а старий очищається. |

### Часткове закриття

- `DEC` із `PARTIAL_FILL/TRADE_EXECUTED` у агрегованому режимі викликає `_handle_aggregated_fill_event`; якщо `recalc_on_partial_close=true` або `allow_unprotected_position=false` (і SL пропав), FSM знову `recalc`-ить та переставляє TP/SL (`apps/reference/domains/execution_position/fsm_manage.py#L851`, `#L894`). |
- `OrderGuardian.ensure_single_bracket_set_for_position` (TTL/`allow_unprotected_position`) фільтрує extra ордери та логірує `decision=name` через `AGG_OCO_BRACKET_GUARD`, не скидаючи останній SL без причини (`apps/reference/services/order_guardian.py#L432`). |
- `tests/domains/execution_position/test_aggregated_oco_partial_close_legacy.py#L1` показує, що позиція або перераховує TP/SL, або тримає їх інтактними в залежності від `recalc_on_partial_close`. |

### Повне закриття

- `DEC:CLOSE` ставить прапорець `_closing_position`, просить `OrderGuardian.close_entry`/`cleanup_orphans` прибрати tracked SL/TP (`apps/reference/domains/execution_position/fsm.py#L2230`, `apps/reference/services/order_guardian.py#L1405`, `#L1471`). |
- Після скасування FSM будує reduce-only market через `place_market_reduce_only`, куди передає залишкову кількість, а `OrderGuardian` викидає `BracketSetMeta` (`apps/reference/domains/execution_position/fsm.py#L2230`, `apps/reference/services/order_guardian.py#L1405`, `#L432`). |
- `tests/domains/execution_position/test_aggregated_oco_dr_restart.py#L1` і `OrderGuardian.link_existing_from_rest` (`apps/reference/services/order_guardian.py#L1173`) гарантують, що після рестарту ADR/SL не губляться: metadata реанімується за відкритими ордерами, cleanup запускається лише якщо позиція нульова. |

## Список персональних TP/SL (legacy) + ризики

- `ManageFlow._place_brackets_legacy` (`apps/reference/domains/execution_position/fsm_manage.py#L360`) — це місце, де для кожного entry одночасно створюється SL (`STOP_MARKET`), TP (`LIMIT`), обидва з `reduceOnly=True`, `workingType=MARK_PRICE`/`priceProtect` з конфига, `qty=str(position_qty)` і `client_id = {rid}_{position_open_ts}_{sl|tp}`. |
- `OrderGuardian.register_entry`/`register_bracket` відстежують, які `client_order_id` належать конкретному entry і коли виконано (`apps/reference/services/order_guardian.py#L828`, `#L921`). Але без aggregated guard можлива ситуація, коли кілька entry залишають стариі SL/TP: `cleanup_orphans` вмикається тільки після `position_amt == 0`, тому між scale-in і cleanup може бути короткий window з двома наборами. |
- Legacy риски: таймінг (запит `cleanup_orphans` ≈ `app/reference/services/order_guardian.py#L1471` лише при відсутній позиції), відсутність TTL/guard (коли Binance видаляє SL, ManageFlow може не знати), і немає гарантії `one bracket per side` — мудь `OrderGuardian.cleanup_other_brackets_for_symbol` (`apps/reference/services/order_guardian.py#L1688`) запускає manual clean-up тільки при явній команді. |

## Список точок aggregated OCO (як вони зараз виглядають)

- **`ManageFlowFSM`** — `_place_brackets_aggregated` → `_place_or_update_bracket_set_from_levels` (`apps/reference/domains/execution_position/fsm_manage.py#L553`) крутить `bracket_aggregator.compute_aggregated_brackets` (`vfoundation/apps/reference/domains/execution_position/bracket_aggregator.py#L1`) з `sl_pct/tp_rr` та обмеженнями по `tick_size/min_price` із конфіга (`apps/reference/domains/execution_position/manage_config.py#L342`). |
- **`OrderGuardian.register_bracket_set`** (/`clear_bracket_set_for_position`) фіксує актуальну пару `sl_order_id/tp_order_id` за canonical `symbol/side`, інкрементує версію, і TTL (`AggregatedOcoGuardianConfig`) захищає нові ордери від негайних cleanup`ів (`apps/reference/services/order_guardian.py#L135`, `#L223`, `#L432`). |
- **`OrderGuardian.ensure_single_bracket_set_for_position`** (з `position_amt`, `open_orders`, `ttl`, `allow_unprotected_position`) перекидає `cleanup_extras`, `fail_closed_guard`, `cleanup_zero_position` і зносить занадто старі набори згідно з `aggregated_oco.recalc` (`apps/reference/services/order_guardian.py#L432`). |
- **`OrderGuardian` poll/relink** (`_poll_loop`, `link_existing_from_rest`, `cleanup_orphans`) щосекунди/по запуску синхронізує інформацію з `/openOrders` і `/positionRisk`, не даючи “ghost” SL/TP висіти (`apps/reference/services/order_guardian.py#L1140`, `#L1173`, `#L1471`). |
- **Конфіг** `execution.manage.brackets.aggregated_oco` (`apps/reference/domains/execution_position/manage_config.py#L342`) керує `recalc_on_scale_in`, `recalc_on_partial_close`, `ttl_protect_new_bracket_ms`, `allow_unprotected_position`, що прямо впливає на `ManageFlow`/`OrderGuardian` комбінації. |
- **Тести** `tests/domains/execution_position/test_aggregated_oco_*` і `tests/domains/execution_position/test_order_guardian_aggregated_cleanup.py#L1` покривають: перший entry, scale-in, partial close речалк, restart/DR, cleanup надлишкових брекетів, і гарантують, що `AGG_OCO_BRACKET_SET_CHANGED`/`AGG_OCO_BRACKET_GUARD` події виникають у потрібні моменти (`apps/reference/domains/execution_position/Readme/CONTRACT_aggregated_oco_v1.md#L1`).
