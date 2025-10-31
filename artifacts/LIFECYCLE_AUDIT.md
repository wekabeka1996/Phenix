# LIFECYCLE_AUDIT.md - Аудит тра� � ировки жизненного цикла ордера

## 1. Текущая тра� � ировка

### Генерация RID/Corr_ID
- **Где генерирует� я**: `vfoundation/core/protocol.py:15` - `rid: str = Field(default_factory=lambda: str(uuid.uuid4()))`
- **Передача между доменами**: RID копирует� я из входящего Message в и� ходящие (`rid=msg.rid`)
- **Примеры точек генерации**:
  - Начальный ASK от decision_making
  - EVT от market_data/feature_engineering
  - CMD от risk_management

### Логирование моментов жизненного цикла

#### TRADE_INTENT
- **Где**: `apps/reference/domains/execution_position/aurora_log_adapter.py:log_trade_intent()`
- **Когда**: По� ле DEC:OPEN от execution_position FSM
- **Поля**: rid, symbol, side, probability, size_usd, price, quantity, risk_score, features

#### CMD:OPEN
- **Где**: `apps/reference/domains/execution_position/fsm.py:handle()` → `open_flow.handle(msg)`
- **Когда**: Приходит CMD:OPEN от decision_making
- **Поля**: symbol, side, qty, price, order_type, tif, idempotent_key

#### DEC:OPEN
- **Где**: `apps/reference/domains/execution_position/fsm_open.py:handle()`
- **Когда**: По� ле прохождения guards (min_notional, cooldown, qty/price steps)
- **Поля**: symbol, side, qty, order_type, price?, tif?, idempotent_key

#### Exchange ACK
- **Где**: `apps/reference/domains/execution_position/fsm.py:_execute_decision()`
- **Когда**: По� ле у� пешного `adapter.place_market_entry()`
- **Поля**: order_id из Binance response, но не логирует� я явно �  RID

#### Partial/Full FILL
- **Где**: `apps/reference/domains/account_observer.py` → EVT:FILL/PARTIAL_FILL
- **Когда**: При получении trade updates от Binance WebSocket
- **Поля**: symbol, side, qty, price, order_id, но корреляция �  RID через order_id?

#### По� тановка SL/TP
- **Где**: `apps/reference/domains/execution_position/fsm.py:_execute_decision()`
- **Когда**: По� ле entry order, `adapter.place_stop_market_close_position()` и `adapter.place_take_profit_market_close_position()`
- **Поля**: sl_id, tp_id генерируют� я через `generate_client_order_id()`, но не � вязывают� я �  entry order_id

### Схема корреляции (Mermaid)

```mermaid
sequenceDiagram
    participant DM as decision_making
    participant EP as execution_position
    participant BA as BinanceAdapter
    participant AO as account_observer

    Note over DM,AO: RID = uuid4() генерирует� я в Message.__init__

    DM->>EP: CMD:OPEN (rid, symbol, side, qty, ...)
    EP->>EP: OpenFlowFSM guards check
    EP->>DM: DEC:OPEN (rid, symbol, side, qty, ...)
    EP->>EP: aurora_log_adapter.log_trade_intent(rid, ...)

    EP->>BA: place_market_entry() async
    BA->>EP: response with order_id
    Note over EP: Exchange ACK - order_id получен, но не логирует� я �  RID

    AO->>EP: EVT:FILL/PARTIAL_FILL (order_id, qty, price, ...)
    Note over AO,EP: Корреляция через order_id, но RID не передает� я в EVT

    EP->>BA: place_stop_market_close_position() async
    EP->>BA: place_take_profit_market_close_position() async
    BA->>EP: SL/TP responses with sl_id, tp_id
    Note over EP: SL/TP order_ids генерируют� я, но не � вязывают� я �  entry order_id
```

## 2. Пробелы и дубли

### От� ут� твующие звенья
1. **Exchange ACK**: Получение order_id от Binance не логирует� я �  RID. Только в _execute_decision LOG.info, но без � труктурированного лога.
2. **OCO Group ID**: SL и TP orders не � вязывают� я �  entry order_id через OCO group. Binance поддерживает OCO, но код и� пользует отдельные STOP_MARKET и TAKE_PROFIT_MARKET.
3. **Parent ClientOrderId**: SL/TP orders не имеют parent_client_order_id, указывающего на entry order.
4. **Partial FILL correlation**: EVT:FILL от account_observer � одержит order_id, но не RID оригинального CMD:OPEN.
5. **Retry/Fallback correlation**: При retry TP (из-за -2021), новый order_id не � вязывает� я �  оригинальным.

### Поля е� ть, но не прокидывают� я
1. **idempotent_key**: Передает� я из CMD:OPEN в DEC:OPEN, но не в SL/TP orders.
2. **span_id/parent_span_id**: Определены в Message, но не и� пользуют� я для tracing.
3. **why_explain_ref**: Для детального объя� нения, но не заполняет� я в execution logs.

## 3. План AUR-004 (additive-only correlation)

### Предлагаемые поля/� вязи
```python
# В Message.pld для DEC:OPEN и EVT
{
    "corr_id": "uuid4()",  # Новый correlation ID для в� ей цепочки
    "parent_client_order_id": null,  # Для SL/TP - указывает на entry
    "oco_group_id": "uuid4()",  # Группа для entry + SL + TP
    "link_ack_id": "order_id от exchange",  # Связь DEC:OPEN ↔ ACK
    "link_fill_id": "order_id",  # Для EVT:FILL correlation
}
```

### Точки корреляции (hooks)
1. **В OpenFlowFSM.handle()**: При генерации DEC:OPEN добавить `corr_id`, `oco_group_id`
2. **В _execute_decision()**: По� ле place_market_entry � охранить `entry_order_id`, передать в SL/TP как `parent_client_order_id`
3. **В account_observer**: При генерации EVT:FILL добавить `corr_id` из lookup по order_id
4. **В aurora_log_adapter**: Логировать corr_id вме� то/вме� те �  rid

### Согла� ование �  L1-ORDER-LOGGER
- Целевые поля: corr_id, oco_group_id, parent_client_order_id, link_ack_id
- Избегать дублирования: и� пользовать � уще� твующие rid как fallback, corr_id как primary для tracing

## 4. L3-METRICS-SUMMARY (дизайн)

### Мини-набор метрик
- **open_success_rate**: (у� пешные DEC:OPEN) / (в� е CMD:OPEN) * 100
- **mean_time_to_open**: Среднее время от CMD:OPEN до DEC:OPEN (м� )
- **defer_rate**: (отложенные CMD:OPEN) / (в� е CMD:OPEN) * 100
- **block_rate**: (заблокированные CMD:OPEN) / (в� е CMD:OPEN) * 100
- **retry_count**: Количе� тво retry при размещении orders
- **qos_cooldown_hits**: Количе� тво отклонений из-за cooldown

### И� точники метрик
- **open_success_rate**: Из OpenFlowFSM._metrics["fsm_open_decisions_total"] / общее CMD:OPEN (нужен � четчик входящих)
- **mean_time_to_open**: Timestamp CMD:OPEN - timestamp DEC:OPEN, агрегировать в metrics_collector
- **defer_rate/block_rate**: Из QoS логики в decision_making (е� ли е� ть)
- **retry_count**: В _execute_decision при retry TP из-за -2021
- **qos_cooldown_hits**: Из OpenFlowFSM guards

### JSON-репорт: reports/summary_gate_status.json
```json
{
  "timestamp": "2025-10-31T12:00:00Z",
  "period_hours": 24,
  "metrics": {
    "open_success_rate": 95.2,
    "mean_time_to_open_ms": 45.3,
    "defer_rate": 2.1,
    "block_rate": 1.8,
    "retry_count": 12,
    "qos_cooldown_hits": 8
  },
  "breakdown_by_symbol": {
    "BTCUSDT": {
      "open_success_rate": 96.1,
      "cmd_open_count": 150,
      "dec_open_count": 144
    },
    "ETHUSDT": {
      "open_success_rate": 94.3,
      "cmd_open_count": 120,
      "dec_open_count": 113
    }
  },
  "alerts": [
    "ETHUSDT defer_rate > 5% threshold"
  ]
}
```

Агрегация в `tools/metrics_summary.py`:
- Читать из Prometheus /metrics/json
- Или из WAL логов
- Группировать по symbol, � читать проценты
- Запи� ывать JSON файл

## 5. Спи� ок файлов для будущих правок

### О� новные файлы для AUR-004 correlation:
- `vfoundation/core/protocol.py`: Добавить поля corr_id, oco_group_id в Message
- `apps/reference/domains/execution_position/fsm_open.py`: Генерировать corr_id/oco_group_id в DEC:OPEN
- `apps/reference/domains/execution_position/fsm.py`: Передать parent_client_order_id в SL/TP orders
- `apps/reference/domains/account_observer.py`: Добавить corr_id lookup в EVT:FILL
- `apps/reference/domains/execution_position/aurora_log_adapter.py`: Логировать corr_id

### Файлы для L3-METRICS-SUMMARY:
- `tools/metrics_summary.py`: Создать новый файл для агрегации и генерации JSON
- `apps/reference/domains/execution_position/fsm_open.py`: Добавить timestamp tracking для mean_time_to_open
- `apps/reference/domains/execution_position/metrics_collector.py`: Ра� ширить метрики для retry_count, qos_hits
- `vfoundation/obs/debug_api.py`: Добавить endpoints для чтения метрик в tools/

### Сопут� твующие файлы:
- `docs/ORDER_LIFECYCLE_CORRELATION.md`: Документация новой � хемы correlation
- `tests/test_order_lifecycle_correlation.py`: Те� ты для проверки corr_id propagation
- `tests/test_metrics_summary.py`: Те� ты для JSON репорта</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\artifacts\LIFECYCLE_AUDIT.md
