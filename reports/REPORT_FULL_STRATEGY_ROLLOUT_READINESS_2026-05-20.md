# Звіт По Готовності Full Strategy Rollout

## 1. Скоуп

Мета цього пакета змін:

- увімкнути всі стратегії для всього поточного 7-symbol universe;
- увімкнути всі доступні режими для кожної стратегії;
- увімкнути pyramiding через `position_mode: DYNAMIC`;
- вимкнути NRR-026..030 через конфіг SSOT, без прихованих code-path fallback;
- прогнати вузьку Pydantic/pytest валідацію та дати verdict по готовності.

Поточний universe після валідації:

- `1000PEPEUSDT`
- `BNBUSDT`
- `BTCUSDT`
- `DOGEUSDT`
- `ETHUSDT`
- `SOLUSDT`
- `XRPUSDT`

## 2. Підтверджені Зміни

### 2.1 Strategy Registry

У `config/aurora/strategies.yaml` кожен із 7 символів тепер має повний registry assignment:

- `aurora`
- `mean_reversion`
- `md_amr`
- `llm_microstructure`

Арбітраж залишився `priority`, тобто контракт конфлікт-резолюції не ламався, а лише розширився на повний rollout.

### 2.2 Aurora Profile

У `config/aurora/strategies/aurora.yaml`:

- для всіх 7 symbol asset blocks виставлено `position_mode: DYNAMIC`;
- для всіх 7 symbol asset blocks дозволено повний 9-regime allowlist;
- `1000PEPEUSDT` переведено в `enabled: true`;
- внутрішній `aurora.decision.symbols_to_track` розширено до 7 символів.

### 2.3 Mean Reversion Profile

У `config/aurora/strategies/mean_reversion.yaml`:

- `BTCUSDT`, `XRPUSDT`, `ETHUSDT`, `SOLUSDT` переведені в `enabled: true`;
- для всіх MR asset blocks встановлено `position_mode: DYNAMIC`;
- додані відсутні asset blocks для `BNBUSDT` і `1000PEPEUSDT`;
- allowlist залишено в межах валідних MR режимів: `FLAT_LOW`, `FLAT_NORMAL`, `FLAT_HIGH`, `MEAN_REVERSION`.

### 2.4 MD-AMR Profile

У `config/aurora/strategies/md_amr.yaml`:

- для всіх asset blocks встановлено `position_mode: DYNAMIC`;
- allowlist розширено до повного валідного 9-regime набору;
- додано відсутній `1000PEPEUSDT` asset block з явним `exit` контрактом, щоб пройти strict Pydantic validation.

### 2.5 LLM Ownership

У `config/aurora/trading.yaml`:

- `trading.llm_orchestration.symbols_llm` розширено до всіх 7 символів;
- `trading.llm_orchestration.allowlist_symbols` розширено до всіх 7 символів.

Важлива межа: `llm_microstructure` все ще залишається external-intent bridge, а не звичайною in-process strategy engine. Це означає, що registry activation для LLM існує, але її runtime semantics відрізняються від `aurora`, `mean_reversion` і `md_amr`.

### 2.6 NRR-026..030

Дослідження джерел reject-кодів показало:

- `NRR-026` формується через regime-confidence / insufficient trend confirmation path у `directional_sanity`;
- `NRR-027` формується через hard directional veto у `directional_sanity`;
- `NRR-028`, `NRR-029`, `NRR-030` формуються через `price_motion_sanity`.

Фактичне конфіг-вимкнення зроблено так:

- `domains.decision_making.directional_sanity.enabled: false`
- `domains.decision_making.directional_sanity.min_regime_confidence: 0.0`
- `domains.decision_making.price_motion_sanity.enabled: false`

Висновок: окремий code change для toggles не знадобився. Потрібні перемикачі вже існували в SSOT-конфігу; я використав їх напряму.

## 3. Доведені Факти

### 3.1 Pydantic / ConfigLoader

Успішно пройшов вузький smoke-check:

```text
python -c "from pathlib import Path; from apps.reference.config_loader import ConfigLoader; cfg = ConfigLoader(config_dir=Path('config/aurora')).load_config(); print('OK', sorted(cfg.strategies_registry.assignments.keys()), cfg.domains.decision_making.directional_sanity.enabled, cfg.domains.decision_making.price_motion_sanity.enabled)"
```

Підтверджений результат:

- ConfigLoader завантажує canonical `config/aurora` без ValidationError;
- active symbol universe = 7 символів;
- `directional_sanity.enabled == False`;
- `price_motion_sanity.enabled == False`.

### 3.2 Pytest

Успішно пройдено вузький тестовий набір:

```text
python -m pytest -q tests/config/test_full_strategy_rollout_config.py tests/config/test_llm_strategy_contract_fail_closed.py tests/domains/decision_making/test_position_mode_pyramiding_v1.py
```

Результат:

- `8 passed in 0.77s`

Що саме покрито цими тестами:

- новий canonical rollout baseline;
- fail-closed LLM ownership contract;
- runtime semantics `position_mode` / anti-pyramiding.

## 4. Не Доведено Цим Пакетом

- Не доведено, що цей rollout є прибутковим на testnet або replay.
- Не доведено, що такий universe не погіршить churn, deferred-intent rate або execution noise.
- Не доведено, що повний 4-strategy rollout не створить операційну конкуренцію за intent window, навіть з арбітражем.
- Не доведено, що весь репозиторний pytest suite зелений після зміни baseline-конфігу.

## 5. Ризики І Обмеження

- `position_mode: DYNAMIC` знімає same-side anti-pyramiding block, але не вимикає `order_in_flight` guard. Тобто concurrent intent pressure все ще може переходити в defer, а не в паралельне відкриття.
- Увімкнення всіх regime allowlists свідомо прибирає попередні forensic embargo/hotfix обмеження. Це технічно відповідає задачі, але економічно є агресивним режимом.
- `llm_microstructure` тепер ownership-allowlisted на весь universe, але це окремий external ingress path. Його не слід трактувати як звичайний внутрішній arbitration participant навіть при повному registry assignment.
- Частина broader config tests у репозиторії може бути прив'язана до старого conservative baseline і потребувати rebasing, якщо запускати не вузький набір, а ширший suite.

## 6. Verdict

### Технічний verdict

`READY FOR CONFIG/PYDANTIC BASELINE`

Під цим мається на увазі:

- canonical SSOT-конфіг узгоджений;
- Pydantic/ConfigLoader проходить;
- вузький regression pytest зелений;
- NRR-026..030 реально вимкнені через конфіг, а не прихованим кодовим bypass.

### Операційний verdict

`READY WITH HIGH STRATEGY-RISK`

Причина:

- ви свідомо ввімкнули максимальний universe, повний regime coverage, DYNAMIC pyramiding і прибрали directional/price-motion safety denies;
- це технічно коректний rollout, але не економічно доведений rollout.

## 7. Змінені Файли

- `config/aurora/strategies.yaml`
- `config/aurora/strategies/aurora.yaml`
- `config/aurora/strategies/mean_reversion.yaml`
- `config/aurora/strategies/md_amr.yaml`
- `config/aurora/trading.yaml`
- `config/aurora/domains.yaml`
- `tests/config/test_full_strategy_rollout_config.py`
- `tests/config/test_llm_strategy_contract_fail_closed.py`