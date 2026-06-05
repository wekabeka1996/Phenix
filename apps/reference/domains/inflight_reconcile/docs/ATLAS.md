# Атлас домену In-Flight Reconcile

## 1. Огляд (Scope & Purpose)
Домен **inflight_reconcile** виконує роль "санітара" для торгових ордерів, що знаходяться у процесі виконання (in-flight). Його головна задача — запобігти вічному блокуванню системи через ордери, статус яких не був оновлений через стандартні канали (WebSocket).

**Межі відповідальності:**
- Відстеження часу життя (TTL) активних ордерів.
- Активна звірка статусу ордерів через REST API після закінчення TTL.
- Примусове очищення локального стану "in-flight" для розблокування нових операцій.

## 2. Карта залежностей (Dependencies)
```mermaid
graph TD
    subgraph "External"
        B[Binance REST API]
    end
    subgraph "Domain: inflight_reconcile"
        IFR[InFlightReconciler]
        IFE[InFlightEntry]
    end
    subgraph "Inbound"
        EP[execution_position]
    end

    EP -->|register order| IFR
    IFR -->|get_order_status| B
    IFR -->|clear in-flight| EP
```

- **Вхідні:** Реєстрація ордерів від `execution_position`.
- **Вихідні:** Запити статусу до `BinanceAdapter`.

## 3. Карта файлів (File Map)
- `reconciler.py`: Основна логіка відстеження та цикл звірки.
- `config.py`: Параметри TTL та інтервалів перевірки.

## 4. Карта подій (Event Map)
*Домен працює переважно через прямі виклики методів (Method Injection) з `execution_position`, але результати звірки можуть впливати на стан FSM.*

## 5. Діаграма послідовності (Reconciliation Flow)
```mermaid
sequenceDiagram
    participant EP as Execution Position
    participant IFR as InFlightReconciler
    participant B as Binance API

    EP->>IFR: register(rid, symbol)
    Note over IFR: Wait for TTL (e.g. 60s)
    loop Every reconcile_interval
        IFR->>IFR: get_expired_entries()
        IFR->>B: get_order_status(rid)
        B-->>IFR: status: FILLED
        IFR->>IFR: mark_terminal & clear
    end
```
