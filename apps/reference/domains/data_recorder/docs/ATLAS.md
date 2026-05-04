# Атлас домену Data Recorder

## 1. Огляд (Scope & Purpose)
Домен **data_recorder** відповідає за збереження уніфікованих знімків ринкових даних (барів), розрахованих ознак (features) та режимів ринку (regimes) у CSV-файли. Ці дані використовуються для подальшого бектестування та аналізу.

**Межі відповідальності:**
- Слухання подій ознак та режимів.
- Синхронізація (join) потоків даних за символом та часом (timestamp).
- Буферизація та періодичне скидання (flush) даних на диск.

## 2. Карта залежностей (Dependencies)
```mermaid
graph TD
    subgraph "Inbound"
        FE[feature_engineering]
        RD[regime_detector]
    end
    subgraph "Domain: data_recorder"
        CR[CsvRecorder]
        BUF[Buffer]
    end
    subgraph "Storage"
        DISK[(data/recorder/)]
    end

    FE -->|EVT:FEATURES_CALCULATED| CR
    RD -->|EVT:REGIME_DETECTED| CR
    CR --> BUF
    BUF -->|periodic flush| DISK
```

- **Вхідні:** `EVT:FEATURES_CALCULATED`, `EVT:REGIME_DETECTED`.
- **Вихідні:** CSV-файли в директорії `data/recorder/`.

## 3. Карта файлів (File Map)
- `recorder.py`: Основний клас `CsvRecorder`, що реалізує логіку збору та запису даних.

## 4. Карта подій (Event Map)

### Вхідні події (Inbound Events)
| Назва події | Джерело | Опис |
|-------------|---------|------|
| `EVT:FEATURES_CALCULATED` | `feature_engineering` | Надає OHLCV дані та розраховані ознаки. |
| `EVT:REGIME_DETECTED` | `regime_detector` | Надає поточну фазу ринку (режим). |

## 5. Діаграма послідовності (Sync Logic)
```mermaid
sequenceDiagram
    participant FE as Feature Eng
    participant RD as Regime Det
    participant CR as CsvRecorder
    participant D as Disk

    FE->>CR: on_features (symbol, ts)
    Note over CR: Buffer Features
    RD->>CR: on_regime (symbol, ts)
    Note over CR: Match & Join in Buffer
    loop Flush Loop
        CR->>D: Write unified row to CSV
    end
```
