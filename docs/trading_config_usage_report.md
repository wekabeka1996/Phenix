# Інвентаризація використання конфігурації trading.yaml

## Вступ

Цей звіт містить детальну карту того, як поля з конфігураційного файлу `trading.yaml` використовуються в кодовій базі проекту QuantumTraderX. Аналіз проведено шляхом пошуку всіх місць читання конфігурації через YAML-лоадери, конфіг-класи, DI-контейнери та інші механізми.

Звіт охоплює наступні групи ключів:
1. Режими та оточення (trading.mode, domain_configuration.*.trading_mode)
2. Ризик та денні ліміти (risk_budgets.*, risk.max_daily_drawdown_limit тощо)
3. Інструменти (instruments[<symbol>].position_sizing.*, instruments[<symbol>].kelly.* тощо)
4. Execution / brackets / order params (execution.manage.brackets.*, execution.order_params.*)
5. QoS / cooldown / exposure (instruments[<symbol>].cooldown_sec, instruments[<symbol>].qos.* тощо)
6. Signals / features / models (feature_engineering.*, models.*, signal_weights)

Для кожного поля вказується:
- Шлях до ключа конфігурації
- Файл, клас, функція та рядок використання
- Очікуваний тип даних
- Нотатки про використання та можливі проблеми

## 1. Режими та оточення

| config_key_path | file | location | expected_type | notes |
|----------------|------|----------|---------------|-------|
| trading.mode | apps/reference/domains/execution_position/fsm.py | ExecPosFSM._on_trade_intent (line 1125) | str | Використовується для вибору між live/testnet режимами. Очікувані значення: 'testnet', 'production', 'hybrid_live_data_testnet_exec' |
| trading.mode | apps/reference/domains/execution_position/fsm.py | ExecPosFSM._on_trade_intent (line 1134) | str | Аналогічно до попереднього |
| trading.mode | tools/validate_configs.py | validate_trading_config (line 46) | str | Валідація: має бути 'testnet' або 'production' |
| trading.mode | tools/validate_configs.py | validate_trading_config (line 49) | str | Помилка якщо невірне значення |
| trading.mode | tests/test_config_backward_compat.py | test_backward_compat (line 47) | str | Тест: має бути 'testnet' |
| trading.mode | apps/reference/domains/decision_making/decision_making.py | DecisionMakingFSM.__init__ (line 1953) | str | Використовується для вибору джерела даних |
| trading.mode | apps/reference/domains/decision_making/decision_making.py | DecisionMakingFSM.__init__ (line 1956) | str | Фолбек до trading.mode |
| trading.mode | apps/reference/config_models.py | ensure_trading_mode_consistency (line 310) | str | Забезпечення консистентності між trading.mode та trading_mode |
| trading.domain_configuration.execution_position.trading_mode | apps/reference/domains/execution_position/fsm.py | ExecPosFSM._on_trade_intent (line 1137) | str | Доменно-специфічний режим для execution_position. Має пріоритет над глобальним trading.mode |
| trading.domain_configuration.execution_position.trading_mode | tests/integration/test_hybrid_metrics_export.py | test_hybrid_incoherent_metrics_export (line 23) | str | Тестове значення 'testnet' |
| trading.domain_configuration.execution_position.trading_mode | tests/integration/test_hybrid_metrics_export.py | test_hybrid_incoherent_metrics_export (line 60) | str | Тестове значення 'testnet' |
| trading.domain_configuration.execution_position.trading_mode | tests/domains/conftest.py | create_test_config (line 63) | str | Тестове значення 'live' |
| trading.domain_configuration.risk_management.trading_mode | apps/reference/main.py | initialize_domains (line 954) | str | Використовується для вибору джерела даних ризику |

**Примітки до розділу:**
- Одночасно враховуються trading.mode та domain_configuration.*.trading_mode
- domain_configuration має пріоритет над глобальним режимом
- Для гібридного режиму потрібна консистентність між глобальним та доменними режимами

## 2. Ризик та денні ліміти

| config_key_path | file | location | expected_type | notes |
|----------------|------|----------|---------------|-------|
| risk_budgets.trade_cvar95_max_bps | tests/unit/test_qos_nrr012.py | test_symbol_cooldown_nrr017 (line 54) | float | Максимальний CVaR в bps для трейду. Шкала: 0-100 (наприклад, 100 = 1%) |
| risk_budgets.trade_cvar95_max_bps | tests/unit/test_qos_nrr012.py | test_exposure_block_cooldown_nrr018 (line 126) | float | Аналогічно |
| risk_budgets.trade_cvar95_max_bps | tests/unit/test_qos_nrr012.py | test_combined_cooldowns_nrr019 (line 194) | float | Аналогічно |
| risk_budgets.trade_cvar95_max_bps | tests/domains/test_sizing_matrix.py | test_sizing_matrix_basic (line 69) | float | Використовується в матриці розмірів позицій |
| risk_budgets.trade_cvar95_max_bps | tests/domains/test_sizing_matrix.py | test_sizing_matrix_with_regime (line 95) | float | Аналогічно |
| risk_budgets.trade_cvar95_max_bps | tests/domains/test_regime_threshold_effect.py | test_regime_thresholds (line 48) | float | Впливає на пороги режимів |
| risk_budgets.ETHUSDT.max_position_size_usd | tests/domains/test_position_tracking_wal_integration.py | test_position_tracking_wal_integration (line 53) | float | Максимальний розмір позиції для ETHUSDT в USD |
| risk_budgets | tests/domains/test_portfolio_equity_flow.py | test_portfolio_equity_flow (line 100) | dict | Порожній словник для тестів |
| risk_budgets | tests/test_decision_making_qos.py | test_decision_making_with_qos (line 39) | dict | Порожній словник для тестів |
| risk_budgets | tests/domains/test_decision_making_trade_intent_validation.py | create_minimal_config (line 17) | dict | Порожній словник для мінімальної конфігурації |
| risk_budgets | tests/domains/test_decision_making_side_bias.py | test_side_bias_calculation (line 39) | dict | Містить налаштування для тестів |
| risk_budgets | tests/domains/test_decision_making_logic_branches.py | create_test_config (line 34) | dict | Порожній словник |
| risk_budgets | tests/domains/test_decision_making_equity_validation.py | create_test_config (line 29) | dict | Порожній словник |
| risk_budgets | tests/domains/test_decision_making_config_validation.py | test_halts_if_risk_budgets_config_is_missing (line 29) | dict | Обов'язковий ключ, відсутність спричиняє помилку |
| risk_budgets.trade_cvar95_max_bps | tests/domains/test_decision_making_bar_gating.py | test_bar_gating_with_regime (line 57) | float | Використовується в gating барів |
| risk_budgets | tests/domains/test_decision_making.py | test_decision_making_full_flow (line 60) | dict | Містить налаштування для повного флоу |
| risk_budgets | tests/domains/test_config_loader.py | test_config_loader (line 43) | dict | Тестування завантаження конфігурації |
| risk_budgets.trade_cvar95_max_bps | tests/domains/test_action_determinism.py | test_action_determinism (line 45) | float | Впливає на детермінізм дій |
| risk.max_daily_drawdown_limit | tests/units/test_risk_score_not_null.py | test_risk_score_not_null (line 25) | str/float | Ліміт денного дроудауну. Шкала: 0-1 (наприклад, 0.10 = 10%) |
| risk.max_daily_drawdown_limit | tests/units/test_risk_score_not_null.py | test_risk_score_not_null (line 81) | str/float | Аналогічно |
| risk.max_daily_drawdown_limit | tests/unit/test_risk_gate_reasons.py | test_risk_gate_reasons (line 37) | str/float | Використовується в логіці risk gate |
| risk.max_daily_drawdown_limit | tests/unit/test_risk_gate_reasons.py | test_risk_gate_reasons (line 104) | str/float | Тестове значення 0.05 (5%) |
| risk.max_daily_drawdown_limit | tests/unit/test_risk_gate_reasons.py | test_risk_gate_reasons (line 152) | str/float | Тестове значення 0.10 (10%) |
| risk.max_daily_drawdown_limit | tests/unit/test_risk_gate_reasons.py | test_risk_gate_reasons (line 196) | str/float | Тестове значення 0.10 (10%) |
| risk.max_daily_drawdown_limit | tests/unit/test_risk_gate_reasons.py | test_risk_gate_reasons (line 242) | str/float | Тестове значення 0.10 (10%) |
| risk.max_daily_drawdown_limit | tests/integration/test_e2e_lifecycle.py | test_e2e_lifecycle (line 74) | str/float | Тестове значення 0.10 (10%) |
| risk.max_daily_drawdown_limit | tests/integration/test_features_pipeline_trace.py | test_features_pipeline_trace (line 128) | float | Тестове значення 0.05 (5%) |
| risk.max_daily_drawdown_limit | tests/integration/test_hotloop_defer_then_open.py | test_hotloop_defer_then_open (line 146) | str/float | Тестове значення 0.01 (1%) |
| risk.max_daily_drawdown_limit | tests/integration/test_hotloop_defer_then_open.py | test_hotloop_defer_then_open (line 250) | str/float | Тестове значення 0.10 (10%) |
| risk.max_daily_drawdown_limit | tests/integration/test_e2e_smoke.py | test_e2e_smoke (line 74) | str/float | Тестове значення 0.10 (10%) |
| risk.max_daily_drawdown_limit | tests/integration/test_e2e_smoke.py | test_e2e_smoke (line 213) | str/float | Тестове значення 0.10 (10%) |
| risk.max_daily_drawdown_limit | tests/domains/conftest.py | create_test_config (line 49) | float | Тестове значення 0.05 (5%) |
| risk.max_daily_drawdown_limit | apps/reference/domains/risk_management/risk_management.py | RiskManagementFSM._check_daily_limits (line 204) | str/float | Читання системного ризику |
| risk.max_daily_drawdown_limit | apps/reference/domains/risk_management/risk_management.py | RiskManagementFSM._check_daily_limits (line 207) | str/float | Читання з risk конфігурації |

**Примітки до розділу:**
- risk_budgets.trade_cvar95_max_bps використовується в багатьох місцях, завжди як float в шкалі 0-100 (bps)
- risk.max_daily_drawdown_limit має змішані типи (str/float), але семантично завжди в шкалі 0-1
- Немає дублювання між max_daily_drawdown_limit та іншими полями

## 3. Інструменти (instruments.*)

| config_key_path | file | location | expected_type | notes |
|----------------|------|----------|---------------|-------|
| instruments[<symbol>].position_sizing.min_position_size_usd | test_dynamic_sl_bps.py | create_config (line 34) | float | Мінімальний розмір позиції в USD |
| instruments[<symbol>].position_sizing.liquidity_based_cap_usd | test_dynamic_sl_bps.py | create_config (line 34) | float | Кап на основі ліквідності в USD |
| instruments[<symbol>].position_sizing.min_position_size_usd | tests/unit/test_qos_nrr012.py | test_symbol_cooldown_nrr017 (line 49) | float | Мінімальний розмір позиції |
| instruments[<symbol>].position_sizing.liquidity_based_cap_usd | tests/unit/test_qos_nrr012.py | test_symbol_cooldown_nrr017 (line 49) | float | Кап ліквідності |
| instruments[<symbol>].position_sizing.min_position_size_usd | tests/unit/test_qos_nrr012.py | test_exposure_block_cooldown_nrr018 (line 121) | float | Аналогічно |
| instruments[<symbol>].position_sizing.liquidity_based_cap_usd | tests/unit/test_qos_nrr012.py | test_exposure_block_cooldown_nrr018 (line 121) | float | Аналогічно |
| instruments[<symbol>].position_sizing.min_position_size_usd | tests/unit/test_qos_nrr012.py | test_combined_cooldowns_nrr019 (line 189) | float | Аналогічно |
| instruments[<symbol>].position_sizing.liquidity_based_cap_usd | tests/unit/test_qos_nrr012.py | test_combined_cooldowns_nrr019 (line 189) | float | Аналогічно |
| instruments[<symbol>].position_sizing.min_position_size_usd | tests/integration/test_qos_symbol_cooldown_nrr017.py | create_config (line 17) | float | Мінімальний розмір позиції |
| instruments[<symbol>].position_sizing.liquidity_based_cap_usd | tests/integration/test_qos_symbol_cooldown_nrr017.py | create_config (line 17) | float | Кап ліквідності |
| instruments[<symbol>].position_sizing.min_position_size_usd | tests/integration/test_hotloop_defer_then_open.py | create_config (line 75) | float | Мінімальний розмір позиції |
| instruments[<symbol>].position_sizing.liquidity_based_cap_usd | tests/integration/test_hotloop_defer_then_open.py | create_config (line 75) | float | Кап ліквідності |
| instruments[<symbol>].position_sizing.min_position_size_usd | tests/integration/test_hotloop_defer_then_open.py | create_config (line 153) | float | Аналогічно |
| instruments[<symbol>].position_sizing.liquidity_based_cap_usd | tests/integration/test_hotloop_defer_then_open.py | create_config (line 153) | float | Аналогічно |
| instruments[<symbol>].position_sizing.min_position_size_usd | tests/integration/test_hotloop_defer_then_open.py | create_config (line 256) | float | Аналогічно |
| instruments[<symbol>].position_sizing.liquidity_based_cap_usd | tests/integration/test_hotloop_defer_then_open.py | create_config (line 256) | float | Аналогічно |
| instruments[<symbol>].position_sizing | tests/integration/test_features_pipeline_trace.py | create_config (line 86) | dict | Словник з налаштуваннями позиціонування |
| instruments[<symbol>].position_sizing | tests/integration/test_features_pipeline_trace.py | create_config (line 104) | dict | Аналогічно |
| instruments[<symbol>].position_sizing | tests/integration/test_features_full_chain_happy.py | create_config (line 40) | dict | Словник налаштувань |
| instruments[<symbol>].position_sizing | tests/test_decision_making_qos.py | create_config (line 32) | dict | Словник налаштувань |
| instruments[<symbol>].position_sizing | tests/integration/test_features_deferred_reasons.py | create_config (line 26) | dict | Словник налаштувань |
| instruments[<symbol>].position_sizing | tests/integration/test_features_and_risk_join.py | create_config (line 25) | dict | Словник налаштувань |
| instruments[<symbol>].position_sizing | tests/integration/test_e2e_smoke.py | test_e2e_smoke (line 111) | dict | Словник налаштувань |
| instruments[<symbol>].position_sizing | tests/integration/test_e2e_smoke.py | create_config (line 189) | dict | Словник налаштувань |
| instruments[<symbol>].position_sizing | tests/integration/test_e2e_lifecycle.py | create_config (line 50) | dict | Словник налаштувань |
| instruments[<symbol>].position_sizing | tests/test_config_auto_trading.py | test_config_auto_trading (line 29) | dict | Читання position_sizing з decision_config |
| instruments[<symbol>] | apps/reference/config_symbols.py | get_symbol_config (line 100) | dict | Читання конфігурації символу |
| instruments[<symbol>] | apps/reference/config_symbols.py | get_symbol_config (line 116) | dict | Фолбек до конфігурації символу |

**Примітки до розділу:**
- position_sizing використовується широко в тестах, завжди як dict з min_position_size_usd та liquidity_based_cap_usd
- Немає жорстких очікувань що під-ключі завжди існують (використовуються get() з defaults)
- Немає окремих гілок логіки для ETHUSDT порівняно з іншими символами

## 4. Execution / brackets / order params

| config_key_path | file | location | expected_type | notes |
|----------------|------|----------|---------------|-------|
| trading.execution.manage.* | apps/reference/domains/execution_position/manage_config.py | resolve_execution_manage_config (line 170) | dataclass | Central resolver for auto-manage, orphan monitor, quick profit, trailing, emergency, and bracket metadata |
| trading.execution.manage.brackets.* | apps/reference/domains/execution_position/brackets_config.py | resolve_brackets_config (line 91) | dict | SSOT для TP/SL/offset, включає legacy fallback + логування |
| trading.execution.manage.brackets.* | apps/reference/domains/execution_position/fsm.py | ExecPosFSM._execute_decision (around line 1990) | dict | Викликає resolve_brackets_config для DEC:OPEN превʼю |
| trading.execution.manage.brackets.* | apps/reference/domains/execution_position/fsm_manage.py | ManageFlowFSM._place_brackets (around line 430) | dict | Використовує ResolvedBrackets для цін TP/SL |
| trading.execution.manage.brackets.* | apps/reference/domains/decision_making/decision_making.py | DecisionMaking._build_trade_intent (around line 1530) | dict | Kelly payoff ratio отримує tp/sl через резольвер |
| trading.execution.manage.brackets.* | tests/domains/execution_position/test_brackets_config.py | resolve_brackets_config tests | dict | Покриває canonical, legacy та default кейси |
| trading.execution.manage.brackets.* | tests/test_order_40usd.py | calculate_order | dict | Демонстрація TP/SL via resolve_brackets_config |
| trading.execution.manage.brackets.* | tests/test_testnet_checks.py | test_sl_bps_default_warning | dict | Перевірка конфігів через резольвер |
| trading.execution.manage.brackets.stop_loss_bps | apps/reference/config_models.py | BracketsConfig (line 134) | int | Контракт зберігає поле для зворотної сумісності |

**Примітки до розділу:**
- ManageFlowFSM now consumes manage metadata exclusively via `manage_config.resolve_execution_manage_config`; direct `trading.execution.manage.*` traversal is prohibited.
- ExecPosFSM також використовує `manage_config.resolve_execution_manage_config` для orphan_monitor/order_guardian/watchdog TTL; прямі читання конфігу видалені.
- Усі бойові шляхи читають TP/SL через resolve_brackets_config; пряме читання YAML заборонене.
- Legacy ключі (`stop_loss_bps`, `take_profit_*_ratio`) підтримуються лише у резольвері; використання логуються.
- Для майбутніх змін структури потрібно оновлювати resolve_brackets_config + супутні тести, інакше споживачі зламаються.
- callbackRate надалі зберігається як float (попередньо було string) для узгодженості з API.

## 5. QoS / cooldown / exposure

| config_key_path | file | location | expected_type | notes |
|----------------|------|----------|---------------|-------|
| trading.instruments[<symbol>].trade_cooldown_sec | apps/reference/utils/trade_cooldowns.py | get_trade_cooldown_sec_for_symbol (line 40) | float | Канонічний кулдаун між реальними трейдами |
| trading.instruments[<symbol>].cooldown_sec | apps/reference/utils/trade_cooldowns.py | get_trade_cooldown_sec_for_symbol (line 48) | float | Legacy fallback; лог warning під час використання |
| trading.execution.cooldown_ms | apps/reference/domains/execution_position/fsm.py | ExecPosFSM._get_or_create_flows (line 1367) | float | Глобальний fallback (мс) для trade cooldown, якщо інструмент не задає значення |
| instruments[<symbol>].qos.symbol_cooldown_sec | apps/reference/domains/decision_making/decision_making.py | DecisionMakingFSM.__init__ (line 244) | float | Кулдаун символу в QoS |
| instruments[<symbol>].qos.symbol_intent_cooldown_sec | apps/reference/domains/decision_making/decision_making.py | DecisionMakingFSM.__init__ (line 244) | int | Новий канонічний QoS-кулдаун; symbol_cooldown_sec використовується як fallback |
| exposure_block_cooldown_sec | tests/unit/test_qos_nrr012.py | test_symbol_cooldown_nrr017 (line 44) | int | Кулдаун блокування експозиції в секундах |
| exposure_block_cooldown_sec | tests/unit/test_qos_nrr012.py | test_exposure_block_cooldown_nrr018 (line 116) | int | Аналогічно |
| exposure_block_cooldown_sec | tests/unit/test_qos_nrr012.py | test_combined_cooldowns_nrr019 (line 184) | int | Аналогічно |
| symbol_cooldown_sec | tests/unit/test_qos_nrr012.py | test_symbol_cooldown_nrr017 (line 45) | int | Кулдаун символу в секундах |
| symbol_cooldown_sec | tests/unit/test_qos_nrr012.py | test_exposure_block_cooldown_nrr018 (line 117) | int | Аналогічно |
| symbol_cooldown_sec | tests/unit/test_qos_nrr012.py | test_combined_cooldowns_nrr019 (line 185) | int | Аналогічно |
| max_intents_per_minute_per_symbol | tests/unit/test_qos_nrr012.py | test_symbol_cooldown_nrr017 (line 44) | int | Макс інтентів за хвилину на символ |
| max_intents_per_minute_per_symbol | tests/unit/test_qos_nrr012.py | test_exposure_block_cooldown_nrr018 (line 116) | int | Аналогічно |
| max_intents_per_minute_per_symbol | tests/unit/test_qos_nrr012.py | test_combined_cooldowns_nrr019 (line 184) | int | Аналогічно |

**Примітки до розділу:**
- trade_cooldown_sec є канонічним полем; під час fallback логуються попередження про використання cooldown_sec
- За відсутності trade/cooldown_sec FSM повертається до trading.execution.cooldown_ms (мс → сек)
- qos.symbol_intent_cooldown_sec залишається окремим шаром (intent-level)
- Є кілька різних cooldown параметрів з подібною семантикою

## 6. Signals / features / models

| config_key_path | file | location | expected_type | notes |
|----------------|------|----------|---------------|-------|
| feature_engineering | apps/reference/main.py | main (line 7) | dict | Коментар про домен feature_engineering |
| feature_engineering | apps/reference/main.py | main (line 31) | module | Імпорт модуля |
| feature_engineering | apps/reference/main.py | main (line 647) | str | Шлях до логу |
| feature_engineering | apps/reference/main.py | main (line 655) | str | Назва домену |
| feature_engineering | apps/reference/main.py | main (line 657) | handler | Обробник домену |
| feature_engineering | apps/reference/main.py | main (line 769) | class | Ініціалізація FeatureEngineering |
| feature_engineering | apps/reference/main.py | main (line 780) | domain | Реєстрація домену |
| feature_engineering | apps/reference/main.py | main (line 948) | class | Ініціалізація в тестовому режимі |
| feature_engineering | apps/reference/main.py | main (line 1143) | comment | Закоментована реєстрація |
| feature_engineering | apps/reference/main.py | main (line 1205) | method | Запуск домену |
| feature_engineering | apps/reference/main.py | main (line 1274) | str | Назва домену в логі |
| models.sma_trend | apps/reference/domains/regime_detector/regime_detector.py | RegimeDetectorFSM.__init__ (line 77) | dict | Конфігурація SMA trend моделі |
| models.volatility | apps/reference/domains/regime_detector/regime_detector.py | RegimeDetectorFSM.__init__ (line 131) | dict | Конфігурація volatility моделі |
| models.sideways | apps/reference/domains/regime_detector/regime_detector.py | RegimeDetectorFSM.__init__ (line 223) | dict | Конфігурація sideways моделі |
| models.sma_trend.fast_period | apps/reference/domains/regime_detector/config.py | migrate_legacy_sma_config (line 177) | int | Період швидкої SMA |
| models.sma_trend.slow_period | apps/reference/domains/regime_detector/config.py | migrate_legacy_sma_config (line 178) | int | Період повільної SMA |
| models.sma_trend | apps/reference/domains/regime_detector/config.py | migrate_legacy_sma_config (line 188) | dict | Створення SmaTrendConfig |
| models.volatility | apps/reference/domains/regime_detector/config.py | migrate_legacy_sma_config (line 193) | dict | Створення VolatilityConfig |
| models.sideways | apps/reference/domains/regime_detector/config.py | migrate_legacy_sma_config (line 213) | dict | Створення SidewaysConfig |
| models.sma_trend | apps/reference/domains/regime_detector/config.py | migrate_config (line 230) | dict | Міграція конфігурації |
| models.volatility | apps/reference/domains/regime_detector/config.py | migrate_config (line 233) | dict | Міграція конфігурації |
| models.sideways | apps/reference/domains/regime_detector/config.py | migrate_config (line 236) | dict | Міграція конфігурації |
| signal_weights | tests/test_decision_making_qos.py | create_config (line 36) | dict | Вага сигналів для тестів |
| signal_weights | tests/test_features_and_signals_live.py | test_signal_weights_loaded (line 227) | dict | Тест завантаження ваг сигналів |
| signal_weights | tests/test_features_and_signals_live.py | test_signal_weights_loaded (line 240) | dict | Читання signal_weights |
| signal_weights | tests/test_features_and_signals_live.py | test_signal_weights_loaded (line 241) | dict | Фолбек до dict |
| signal_weights | tests/test_features_and_signals_live.py | test_signal_weights_loaded (line 247) | dict | Логування ваг |
| signal_weights | tests/test_features_and_signals_live.py | test_signal_weights_loaded (line 255) | dict | Перевірка наявності |
| signal_weights | tests/test_features_and_signals_live.py | test_signal_weights_loaded (line 256) | dict | Читання з _config |
| signal_weights | tests/test_features_and_signals_live.py | test_signal_weights_loaded (line 257) | dict | Ассерт наявності |
| signal_weights | tests/test_features_and_signals_live.py | test_signal_weights_loaded (line 265) | dict | Читання актуальних ваг |

**Примітки до розділу:**
- feature_engineering використовується широко в main.py для ініціалізації домену
- models.* використовуються в regime_detector для різних моделей (sma_trend, volatility, sideways)
- signal_weights використовуються в decision_making для вагування сигналів
- Очікувані ключі включають obi, tfi, delta_price, ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync
- enable_new_metrics та compute_all впливають на включення нових метрик

## Виявлені проблеми

### Дубліруючі поля з однаковою семантикою:
- risk_budgets.trade_cvar95_max_bps використовується в багатьох місцях з однаковою семантикою
- Кілька cooldown полів: cooldown_sec, symbol_cooldown_sec, exposure_block_cooldown_sec, qos.symbol_cooldown_sec

### Змішані шкали відсотків:
- risk.max_daily_drawdown_limit використовується як string та float, але завжди в шкалі 0-1 (legacy; daily_limits.* перейшли на 0-100)
- risk_budgets.trade_cvar95_max_bps завжди в шкалі 0-100 (bps)

### Поля, які не використовуються в коді:
- trading.data_sources.* - не знайдено використання в коді
- risk.daily.max_drawdown_pct - здається дублюючим max_daily_drawdown_limit
- risk.daily.max_realized_loss_usd - не знайдено використання
- risk.max_portfolio_risk_pct, risk.max_single_position_risk_pct, risk.max_daily_loss_pct - не знайдено використання
- instruments[<symbol>].cooldown_sec - позначено як legacy; використовується лише як fallback (лог warning)
- instruments[<symbol>].kelly.* - не знайдено використання
- instruments[<symbol>].behavior_fsm.* - не знайдено використання
- execution.manage.brackets.sl.* - не знайдено використання
- execution.manage.brackets.tp.* - не знайдено використання
- execution.order_params.* (крім TRAILING_STOP_MARKET.callbackRate) - не знайдено використання</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\docs\trading_config_usage_report.md
