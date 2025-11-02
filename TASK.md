Роль: Сбор контекста и доказательств. Ничего не изменяй в коде, только анализируй и собирай.
Ограничение: Не вмешивайся в домены, которыми занимаются другие агенты.

Задача (скопируй в Copilot):

Заголовок: Сбор доказательств работоспособности гибридного режима и ордерного контура
Цель: Подтвердить факт работоспособности всей цепочки (Live data → Features/Signals → Risk → Decision/QoS → Exec Testnet c TP/SL → Корреляция → Логи/Метрики) на текущем коммите.
Преусловия: Проект установлен, .env корректен, USE_TESTNET=true.
Действия:

Извлеки и приложи текущее содержимое ключевых конфигов:

configs/aurora/system.yaml

configs/aurora/trading.yaml

schemas/config/trading_schema.json

Приложи последние 300 строк:

logs/aurora_events.jsonl

logs/order_log_v1.jsonl

logs/orders_{success,failed,denied}.jsonl (если есть)

Снимок Prometheus /metrics (HTTP к локальному эндпоинту), сохрани в reports/metrics_snapshot.txt.

Сформируй компактную таблицу (Markdown) по метрикам:

aurora_hybrid_coherent{mode="hybrid_testnet"}

aurora_hybrid_incoherent_reasons_total{reason=...}

open_success_rate, mean_time_to_open_ms

defer_rate, block_rate, retry_count, qos_cooldown_hits

order_timeout_total{type="ack"|"fill"}

Найди в логах минимум один успешный цикл для любого символа: CMD:OPEN → ORDER_PLACED/ACK → ORDER_STATE_CHANGED(FILL) с TP/SL. Вырежи связанный corr_id и приложи связанный фрагмент логов (RID/corr_id/oco_group_id/link_ack_id/link_fill_id).

Проверь XAI why-поля: найди не менее 5 последних записей по triage/QoS/risk/exec с why ≤ 80 символов. Выпиши их в таблицу.

Сконсолидируй отчет:

reports/ACCEPTANCE_CTX.md с разделами: Config, Metrics, Evidence (логи), XAI, Вывод.
Артефакты (верни):

reports/metrics_snapshot.txt

reports/ACCEPTANCE_CTX.md

Вырезки логов с привязкой по corr_id.
