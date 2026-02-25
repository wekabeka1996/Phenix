# Контракти подій домену Data Recorder

## Вхідні події (Consumed)

### 1. EVT:FEATURES_CALCULATED
- **Схема**: Має містити `symbol`, `ts`, `tf_sec`, `bar` (OHLCV) та `features` (dict).
- **Використання**: Основне джерело даних для рядка CSV.

### 2. EVT:REGIME_DETECTED
- **Схема**: Має містити `symbol`, `ts`, `regime` (string) та `confidence` (float).
- **Використання**: Додаткове поле для збагачення OHLCV даних фазою ринку.

## Вихідні дані (Storage Contract)
Рекордер не емітує подій, але гарантує запис у форматі CSV:
- **Encoding**: UTF-8.
- **Separator**: Кома (`,`).
- **Header**: Записується при створенні нового файлу.
