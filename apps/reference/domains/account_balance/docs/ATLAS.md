# Атлас домену Account Balance

## 1. Огляд (Scope & Purpose)
Домен **account_balance** відповідає за моніторинг стану рахунку користувача на біржі (Binance Futures). Він є "джерелом істини" (Source of Truth) для залишків коштів (balances) та відкритих позицій (positions) у системі.

**Межі відповідальності:**
- Періодичне опитування (polling) Binance API через `BinanceAdapter`.
- Перетворення сирих даних API у внутрішні формати подій.
- Емісія подій про оновлення балансу та позицій у шину подій FSM.

## 2. Карта залежностей (Dependencies)
```mermaid
graph TD
    subgraph "External"
        B[Binance API]
    end
    subgraph "Domain: account_balance"
        AC[AccountConnector]
    end
    subgraph "Shared Infrastructure"
        BA[BinanceAdapter]
        FSM[FSMCore]
    end

    AC -->|викликає| BA
    BA -->|HTTP| B
    AC -->|емітує події| FSM
```

- **Вхідні залежності:** `AuroraConfig` (для налаштувань API та інтервалів).
- **Вихідні залежності:** `BinanceAdapter` (для зв'язку з біржею), `FSMCore` (для публікації подій).

## 3. Карта файлів (File Map)
- `account_connector.py`: Основний оркестратор домену. Містить клас `AccountConnector`, який керує фоновим потоком моніторингу.
- `docs/`: Технічна документація домену.
- `Readme/`: (Застаріла) початкова документація.

## 4. Карта подій (Event Map)

### Вихідні події (Outbound Events)
| Назва події | Опис | Призначення |
|-------------|------|-------------|
| `EVT:BALANCE_UPDATE_RECEIVED` | Оновлення залишків по активах | Для `risk_management` та `strategies` |
| `EVT:ACCOUNT_UPDATE_RECEIVED` | Оновлення відкритих позицій та загального балансу | Для `execution_position` та `position_tracking` |

### Вхідні події (Inbound Events)
- *Домен не споживає подій.* Він ініціює дані самостійно через таймер.

## 5. Діаграма послідовності (Sequence Diagram)
```mermaid
sequenceDiagram
    participant T as Monitor Thread
    participant AC as AccountConnector
    participant BA as BinanceAdapter
    participant FSM as FSMCore

    loop Every update_interval
        T->>AC: _fetch_and_emit_account_data()
        AC->>BA: get_account_balance()
        BA-->>AC: balance_data
        AC->>FSM: emit EVT:BALANCE_UPDATE_RECEIVED
        
        AC->>BA: get_open_positions()
        BA-->>AC: positions_data
        AC->>FSM: emit EVT:ACCOUNT_UPDATE_RECEIVED
    end
```
