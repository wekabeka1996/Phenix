# TASK28 — Звіт про готовність режиму RegimeDetector End-to-End та гібридного режиму

## 1) Додано новий інтеграційний тест (без fallback-ів, з відкладеним через warmup)

### Тест
- `tests/integration/test_regime_detector_event_flow.py`:
  - `test_decision_making_does_not_defer_for_regime_after_warmup_ready`
  - додаткове покриття для підписки та поведінки відкладення через warmup

### Що доводить
- RegimeDetector підписаний і видає `EVT:REGIME_DETECTED`.
- DecisionMaking **не** створює відкладень (warmup/regime-missing), коли `RegimeDetector` має `warmup.full_ready=true`.
- Перевірено заборонені відкладення: `NRR-ARMING-NOT-READY`, `NRR-ARMING-WARMUP-MISSING`, `NRR-REGIME-MISSING`.

### Результат
- Запуск: `.venv/bin/pytest -q tests/integration/test_regime_detector_event_flow.py`
- Результат: **3 passed**

## 1.1) Новий тест контракту конфігу для гібридного режиму (mapping режимів + креденшіали)

### Тест
- `tests/config/test_task28_hybrid_mode_config_contract.py`:
  - `test_hybrid_mode_config_contract_mapping_and_credentials_present`

### Що доводить
- `trading_mode == hybrid_live_data_testnet_exec` і мапінг `trading.domain_configuration` відповідає очікуваній гібридній схемі.
- `decision_making.arming.require_regime_warmup == true` (fail-closed до готовності RegimeDetector).
- Присутні креденшіали для testnet API та змінні середовища розв'язані (немає незмінених `${VAR}`).

### Результат
- Запуск: `.venv/bin/pytest -q tests/integration/test_regime_detector_event_flow.py tests/config/test_task28_hybrid_mode_config_contract.py`
- Результат: **4 passed**

## 2) Скан конфігурацій (hybrid live-features + testnet-execution)

### Ефективні режими (з мапінгу конфігів)
- `config/aurora/system.yaml:4` встановлює `trading_mode: hybrid_live_data_testnet_exec`.
- `config/aurora/trading.yaml:244` визначає `domain_configuration`:
  - `market_data: live` (`config/aurora/trading.yaml:245`)
  - `feature_engineering: live` (`config/aurora/trading.yaml:247`)
  - `decision_making: live` (`config/aurora/trading.yaml:249`)
  - `risk_management: testnet` (`config/aurora/trading.yaml:251`)
  - `execution_position: testnet` (`config/aurora/trading.yaml:253`)
- `config/aurora/trading.yaml:257` визначає джерела risk mgmt:
  - `portfolio_state: testnet` (`config/aurora/trading.yaml:258`)
  - `market_data: live` (`config/aurora/trading.yaml:259`)

### Політика warmup тепер жорстка (fail-closed до готовності RegimeDetector)
- `config/aurora/domains.yaml:43` встановлює `decision_making.arming.require_regime_warmup: true`.

### TTL / прострочення
- `config/aurora/system.yaml:19` встановлює `system.market_data.tick_ttl_ms: 2000`.
  - RegimeDetector відмічає застарілі фічі як `UNCERTAIN` (data-quality gate) і DecisionMaking блокує по `allowed_regimes`, коли це присутнє.

### Базова валідація інструментом конфігурацій (тільки структура)
- Запуск: `.venv/bin/python tools/validate_configs.py`
- Результат: **exit 0** (структура YAML для trading/system/regime OK; обов'язкові env змінні присутні)

## 3) Вердикт готовності для гібридного режиму

### ✅ Готово (концептуально + wiring)
- Мапінг доменів відповідає «live features + testnet execution» (`config/aurora/trading.yaml:244`).
- RegimeDetector тепер бере участь у runtime event bus і DecisionMaking може бути налаштований чекати warmup (немає intent-ів на торг до готовності).

### ⚠️ Не повністю готово для запуску «fail-closed» без операційних перевірок
1) **Розв'язання середовища залежить від `python-dotenv` / експортованих env змінних**
   - Перевірено у віртуальному оточенні через `tests/config/test_task28_hybrid_mode_config_contract.py` (немає незмінених `${VAR}` у потрібних креденшах).
   - Якщо запускати поза venv / без dotenv, `${VAR}` може залишатись не розв'язаним і виглядати «truthy».
2) **ExecutionPosition має fallback у вигляді `shadow_mode`**
   - `apps/reference/domains/execution_position/fsm.py:897`–`apps/reference/domains/execution_position/fsm.py:905` встановлює `self.shadow_mode = True` при відсутності API-кредієнтів замість жорсткого фейлу.
   - Це порушує принцип «no fallbacks» і може приховати некоректну конфігурацію.
3) **Kill-switch налаштований, але не застосований**
   - `ops.panic_killswitch: true` встановлено в конфігах (`config/aurora/system.yaml:23`, `config/aurora/trading.yaml:164`), але grep по репозиторію не виявляє його примусового застосування у runtime доменах.

### Мінімальний чекліст «go / no-go» для гібридного запуску
- Запустити у venv: `.venv/bin/python -c "from apps.reference.config_loader import get_config; c=get_config(); print(c.binance_api.live.api_key[:4], c.binance_api.testnet.api_key[:4])"`.
- Перевірити, що `market_data` використовує `live`, а `execution_position` — `testnet` (ефективний мапінг).
- Переконатися, що ExecPos **не** у `shadow_mode` (API ключі присутні, URL вказаний на testnet).
- Вирішити, чи слід імплементувати kill-switch або явно його вимкнути (зараз він налаштований, але не активний).

---

Звіт перекладено українською та збережено як цей файл.
