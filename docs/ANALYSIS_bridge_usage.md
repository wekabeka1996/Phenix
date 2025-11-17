# Bridge Usage Analysis

## 1. Вступ
- Перевірено репозиторій на предмет будь-якого використання каталогу `bridge/` у виробничому pipeline Aurora/vFoundation: імпорти, виклики класів, підпроцеси, згадки у документації та журнальних записах.
- Мета — визначити, чи bridge-скрипти мають прямі залежності в коді або їх можна вважати окремими утилітами/архівними артефактами.

## 2. Перелік файлів у bridge/
- `bridge_feature_collection.py`: `LiveBridgeCollector` (залежить від `BinanceWebSocketApiManager`, обчислює obi/tfi/delta_price, записує JSONL). Є `main()` який викликає `get_trading_symbols()` у `vfoundation.config_symbols`.
- `live_feature_collector.py`: `LiveFeatureCollector` (також робить WebSocket стріми, обраховує obi/tfi/delta_price, має `collect_features()` `main()`, друкує статистику). Без зовнішніх залежностей окрім `vfoundation.config_symbols`.

## 3. Аналіз імпортів
- Перевірка `rg -n "import bridge"`/`rg -n "from bridge"` дублікатів не виявила жодного імпорту з `bridge/`. Назви модулів/класів не імпортуються ані у `apps/reference`, ані у `vfoundation`, ані в `tests`.

## 4. Аналіз використання
- Пошук символів `LiveBridgeCollector`, `LiveFeatureCollector` показав лише присутність у власних файлах (рядки `class LiveBridgeCollector` і `main()`), без інших викликів.
- Немає subprocess/cli викликів bridge-скриптів у `tools/`, `scripts/`, `docs/` або тестах.
- Журнали (`JOURNAL.md`, `docs_arhive/AUDIT_FINAL_REPORT.md` тощо) згадують bridge як чистий/дослідницький артефакт, але без посилань на вживання в pipeline (часто у вигляді «clean» заметок).

## 5. Інтеграція з pipeline
- FSM і домени (`market_data`, `feature_engineering`, `risk_management`, `decision_making`, `execution_position`, `adapters`, `utils`, `telemetry`) не імпортують `bridge` модулі і не споживають їхнє API.
- `MarketDataConnector` жодного разу не викликає класи bridge/; фічі, які обчислюються там, існують також у `apps/reference/domains/feature_engineering`.
- Bridge-класи ніде не пишуть свої результати в загальний pipeline (тільки локальні JSONL або stdout).

## 6. Висновок
- **Не використовується** — bridge-модулі не імпортуються, не вбудовані в FSM, не споживаються domain logic.
- **Приховані залежності** відсутні: всі виклики/пошуки повертають нулі.
- **Рекомендація**: зафіксувати як research tool/experimental utility, не включати до production deployment, або перемістити до `docs_arhive`/`tools` з позначкою «offline collector». If needed for analysis, keep alive but detach from pipeline; otherwise архівувати.  
