# AGENT_REPORT_V1

**task**: AURORA_TIMER_GOVERNANCE_T6C0_TRADE_FLOW_FRESHNESS_CORRIDOR
**verdict**: TRADE_FLOW_CORRIDOR_REPRODUCED
**report_path**: AURORA_TIMER_GOVERNANCE_T6C0_TRADE_FLOW_FRESHNESS_CORRIDOR_REPORT.md

---

## problem
В ходе аудита таймер-менеджмента T6A был выявлен критический зазор в обеспечении свежести рыночных данных (Trade-Flow Freshness Gap). Поток котировок `bookTicker` и поток сделок `aggTrade`/`trade` поступают независимо в рамках единого WebSocket-соединения Binance.

Если поток сделок зависает или отключается биржей (что является известной аномалией реконнектов Binance), а поток котировок продолжает функционировать:
1. `bookTicker` исправно обновляет локальное системное время и котировки.
2. Внутреннее скользящее окно `WebSocketAggregator` со временем очистки `window_seconds=60` вымывает старые сделки, обнуляя объемы торгов (`buy_volume`/`sell_volume`) и счетчики сделок.
3. Тем не менее, тики продолжают отправляться даунстрим, поскольку список последних цен (`prices` deque) не очищается и хранит предыдущие значения сделок.
4. Сторожевой таймер воркера `trade_silence_reconnect_sec = 120` инициирует аварийное закрытие и реконнект только спустя 120 секунд тишины сделок.
5. Это создает скрытый 60-секундный коридор уязвимости (между 60-й и 120-й сек), в течение которого система отправляет свежие котировочные тики с нулевыми торговыми объемами. `BarAggregator` принимает их и упаковывает в kline-бары с объемами `0.0`.
6. Даунстрим-гейты свежести (в `DecisionMaking` и `RegimeDetector`), проверяющие свежесть исключительно по меткам времени (`ts_ms` / `bar_close_ts`), валидируют эти бары как абсолютно свежие. Стратегии получают искаженные деградировавшие признаки (например, TFI = 0), что может повлечь ошибочные торговые решения.

---

## facts
- **WebSocketAggregator window**: 60 секунд (`window_seconds=60` по умолчанию). Используется для скользящего вымывания сделок из `trades_window` в `_cleanup_window`.
- **trade_silence_reconnect_sec**: 120.0 секунд (задано в [config/aurora/system.yaml](config/aurora/system.yaml#L13) и проверяется в `worker.py`).
- **quote-fresh / trade-stale behavior**: `_cleanup_window` выравнивает время очистки по `max(last_book_ts_ms, last_trade_ts_ms)`. Когда `last_book_ts_ms` уходит вперед более чем на 60 секунд от последней сделки, все сделки удаляются. Функция `get_market_tick` возвращает валидный словарь tick со свежим `ts` (из `bookTicker`), но со всеми нулевыми объемами и числом сделок.
- **BarAggregator behavior**: `BarAggregator.on_tick(...)` принимает поступающие тики со свежим временем и объемом `Decimal("0")` и строит бары, которые успешно закрываются по временной границе kline с нулевым объемом `volume=Decimal("0.0")` и свежей временной меткой.
- **downstream stale guard behavior**: Класс [ReadinessGates.features_ready](apps/reference/domains/decision_making/gates/readiness_gates.py#L310) проверяет актуальность по лагу времени события `now_ms - bar_close_ts <= bar_ttl_ms` (10000 мс). Поскольку время закрытия бара генерируется на базе свежего `bookTicker` тика, лаг равен близкому к нулю значению. Гейты считают данные свежими и готовыми к торгам, никак не анализируя деградацию торговых объемов.

---

## test_results
Новые комплексные тесты успешно воспроизводят описанное поведение во всех цепочках:
- **Test 1 (`test_t6c0_trade_window_expires_to_zero_flow_while_quote_remains_fresh`)**: Подтвердил, что при затишье сделок свыше 60 секунд объемы и количества сделок в `WebSocketAggregator` корректно обнуляются, в то время как временная метка и серединная котировка `mid` обновляются по свежему `bookTicker`.
- **Test 2 (`test_t6c0_corridor_exists_before_trade_silence_reconnect_sec`)**: Контекстно доказал существование 60-секундного зазора уязвимости между окончанием скользящего окна (`60s`) и срабатыванием watchdog реконнекта (`120s`).
- **Test 3 (`test_t6c0_bar_aggregator_accepts_quote_fresh_zero_flow_tick`)**: Продемонстрировал, что `BarAggregator` беспрепятственно принимает тики с нулевыми объемами и завершает bars kline с `volume = Decimal("0.0")` со свежей временной шкалой.
- **Test 4 (`test_t6c0_downstream_stale_bar_guard_fails_to_catch_trade_flow_staleness`)**: Доказал на уровне продакшен-кода `ReadinessGates`, что лаг-гейты пропускают деградировавшие признаки с нулевыми объемами как готовые к торгам (`is_ready == True`).

---

## classification
- **trade_flow_freshness_gap**: `TRADE_FLOW_FRESHNESS_GAP_CONFIRMED`
- **severity**: `P1_HIGH` (Критический зазор качества данных / сигналов торговой логики, способный приводить к ложным расчетам TFI и индикаторов поглощения, хотя прямой экономический ущерб не гарантирован).
- **proof_level**: `FULL_REPROPRODUCER_PROOF` (Прямое воспроизведение через юнит-тесты на основе живой логики `WebSocketAggregator`, `BarAggregator` и `ReadinessGates`).

---

## root_cause_vs_symptom
- **symptom**: Стратегии принимают решения на барах с аномальными нулевыми сделками/объемами на живом рынке, считая при этом систему полностью готовой и здоровой.
- **root cause**: Асинхронность потока сделок и котировок Binance, при которой поток сделок может "молча" зависнуть без разрыва сетевого вебсокета, в сочетании с избыточной длительностью watchdog таймаута затишья сделок относительно размера окна агрегации.
- **contributing factor**: Фиксированные параметры `window_seconds = 60` и `trade_silence_reconnect_sec = 120.0` жестко зашиты и рассогласованы во времени на 60 секунд.
- **masking factor**: Активный поток `bookTicker` непрерывно обновляет время последней сетевой активности `_last_ws_text_mono`, маскируя зависание сделок от сетевых тайм-аутов (`ws_receive_timeout_sec = 60.0`).

---

## implementation
- **files changed**:
  - `tests/domains/market_data/test_trade_flow_freshness_corridor.py` (добавлен новый тестовый сценарий)
- **tests added**:
  - `test_t6c0_trade_window_expires_to_zero_flow_while_quote_remains_fresh`
  - `test_t6c0_corridor_exists_before_trade_silence_reconnect_sec`
  - `test_t6c0_bar_aggregator_accepts_quote_fresh_zero_flow_tick`
  - `test_t6c0_downstream_stale_bar_guard_fails_to_catch_trade_flow_staleness`
- **runtime behavior changed**: `NONE` (Strictly non-invasive reproducer tests and forensics).
- **config changes**: `NONE`

---

## unproven
- **economic impact**: Точный финансовый эффект или PnL-ущерб от искажения признаков TFI/OBI в живых торгах.
- **live frequency**: Частота возникновения специфических зависаний потока сделок Binance в продуктивной среде.
- **strategy sensitivity**: Степень влияния переключения объемов в ноль на успешность маркет-мейкинга для конкретных моделей alpha-диапазона.
- **exact decision impact**: Влияние на отправку лимитных ордеров / проскальзывание.

---

## recommended_next_package
Рекомендуется запустить следующий пакет:
- **`T6C1 — Trade-Flow Freshness Policy Design`**
  - Оценить варианты защитных политик:
    1. Синхронизация watchdog: Снизить `trade_silence_reconnect_sec` до `ws_receive_timeout_sec` (60.0) или напрямую выровнять с `window_seconds` (хотя частые реконнекты на низколиквидных парах могут быть нежелательны).
    2. Флаг деградации: Добавить в метаданные баров kline логический признак `trade_flow_stale=true`, если с момента последней сделки прошло больше `X` секунд.
    3. feature-level fallback в FeatureEngineering.
    4. DecisionMaking penalty / block: точечные блокировки открытия новых позиций только по стратегиям, рассчитывающим дельту объемов, сохраняя при этом работу котировочных аварийных закрытий.

---

## validation
- **pytest tests/domains/market_data/test_trade_flow_freshness_corridor.py -q**:
  ```text
  tests\domains\market_data\test_trade_flow_freshness_corridor.py ....     [100%]
  ============================== 4 passed in 1.34s ==============================
  ```
- **related market_data tests (58 passed)**:
  ```text
  tests\domains\market_data\test_stream_contract.py ........               [ 13%]
  tests\domains\market_data\test_md_domain_structural_guardrails.py ...... [ 24%]
  ...........                                                              [ 43%]
  tests\domains\market_data\test_task31_ws_aggregator_trade_qty_preserved.py . [ 44%]
  ...                                                                      [ 50%]
  tests\domains\market_data\test_bar_aggregator_ssot.py .............      [ 72%]
  tests\domains\market_data\test_task30_anchor_ts_propagation.py ..        [ 75%]
  tests\domains\market_data\test_trade_flow_freshness_corridor.py ....     [ 82%]
  tests\domains\market_data\test_bar_aggregator_warmup_import.py ......    [ 93%]
  tests\domains\market_data\test_worker_heartbeat_cadence_governance.py .. [ 96%]
  ..                                                                       [100%]
  ============================= 58 passed in 2.94s ==============================
  ```
- **git diff --stat**:
  ```text
  .../test_trade_flow_freshness_corridor.py          | 240 +++++++++++++++++++++
  1 file changed, 240 insertions(+)
  ```
- **git diff --name-only**:
  ```text
  tests/domains/market_data/test_trade_flow_freshness_corridor.py
  ```
