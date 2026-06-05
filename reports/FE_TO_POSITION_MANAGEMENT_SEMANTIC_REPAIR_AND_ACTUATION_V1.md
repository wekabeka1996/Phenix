# FE_TO_POSITION_MANAGEMENT_SEMANTIC_REPAIR_AND_ACTUATION_V1

## Обсяг

Імплементаційний пакет для доведеного семантичного розриву між FeatureEngineering та post-entry position management.

Межі пакета, які збережено:

- Без ретюнінгу entry-gates.
- Без змін strategy allowlist або regime thresholds.
- Без глобальних змін математики TP/SL.
- Без нового прямого exchange-order path.
- Існуючий шов `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST -> CMD:CLOSE` лишається єдиним behavior-changing authority path.

## Факти

- ФАКТ: `execution_position` тепер має канонічний normalization seam `microstructure_snapshot_v1` у [apps/reference/domains/execution_position/microstructure_snapshot.py](../apps/reference/domains/execution_position/microstructure_snapshot.py).
- ФАКТ: `EPEventHandlers.on_features_calculated()` тепер додає канонічний snapshot у `_last_features_cache` і явно утримує повільні bar-semantic поля на кшталт `atr_14`, коли пізніші FE payload-и їх не містять.
- ФАКТ: ATR-споживачі в `ExecPosFSM`, `_evaluate_supersede_reprice_guard()` та `_evaluate_advanced_stale_cancel()`, тепер спочатку читають канонічну snapshot-семантику, а raw legacy fields використовують лише як fallback.
- ФАКТ: `ExecPosFSM` тепер пасивно спостерігає `CMD:PROCESS_STRATEGY`, тому nested FE bar semantics, які вже емiтяться там, включно з `volatility.atr_14`, доходять до post-entry consumers без введення нового routing path.
- ФАКТ: `PositionPolicySidecar` тепер споживає канонічний snapshot як primary source для microstructure pressure, а legacy alias fields збережено лише як optional fallback input.
- ФАКТ: `PositionPolicySidecar` тепер емiтить `EVT:POSITION_POLICY_MICROSTRUCTURE_PRESSURE_EVALUATED` з bounded pressure details, видимістю missing fields, retained fields та authority state.
- ФАКТ: `position_policy_sidecar.microstructure_exit_v1` тепер є typed SSOT subtree у [apps/reference/config_models.py](../apps/reference/config_models.py) та [config/aurora/domains.yaml](../config/aurora/domains.yaml).
- ФАКТ: soft-close authority тепер явно обмежена execution domain mode. Поточний production SSOT у [config/aurora/domains.yaml](../config/aurora/domains.yaml) авторизує лише `testnet`, що покриває `full_testnet` і `hybrid_live_data_testnet_exec`, бо hybrid резолвить `execution_position -> testnet`.
- ФАКТ: live/prod за замовчуванням лишається observe-only навіть якщо sidecar mode дорівнює `enable`, доки `authoritative_domain_modes` явно не розширено в SSOT.
- ФАКТ: contract surface оновлено у verb registry, execution_position domain dictionary, JSON schema family та default critical events shadow journal.

## Висновки

- ВИСНОВОК: найменш інвазивний root fix полягав не у вигадуванні synthetic ATR в `EVT:FEATURES_CALCULATED`, а в одноразовій нормалізації FE payload на execution boundary плюс пасивному спостереженні вже наявного richer `CMD:PROCESS_STRATEGY` bar payload.
- ВИСНОВОК: явне утримання попередньої ATR/OBI-close семантики в canonical snapshot безпечніше, ніж неявно перераховувати або фабрикувати ці значення з пізніших tick payload-ів.
- ВИСНОВОК: нова microstructure pressure подія дає достатню runtime-evidence surface для подальшого аудиту того, чи реально exercising bounded soft-close authority у testnet/hybrid slices перед будь-яким майбутнім розширенням.

## Не доведено

- НЕ ДОВЕДЕНО: retained runtime logs ще не переаудитовано, щоб довести реальне exercise `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST` через новий FE-semantic path у свіжому testnet/hybrid runtime slice.
- НЕ ДОВЕДЕНО: нову observability-подію microstructure pressure ще не проаналізовано на новому shadow/testnet forensic window.
- НЕ ДОВЕДЕНО: будь-яке розширення authority для live/prod поза поточним `authoritative_domain_modes: ["testnet"]`.

## Змінені файли

- [apps/reference/domains/execution_position/microstructure_snapshot.py](../apps/reference/domains/execution_position/microstructure_snapshot.py)
- [apps/reference/domains/execution_position/event_handlers.py](../apps/reference/domains/execution_position/event_handlers.py)
- [apps/reference/domains/execution_position/fsm.py](../apps/reference/domains/execution_position/fsm.py)
- [apps/reference/domains/execution_position/position_policy_sidecar.py](../apps/reference/domains/execution_position/position_policy_sidecar.py)
- [apps/reference/config_models.py](../apps/reference/config_models.py)
- [config/aurora/domains.yaml](../config/aurora/domains.yaml)
- [apps/reference/dictionaries/verb_registry_v1.yaml](../apps/reference/dictionaries/verb_registry_v1.yaml)
- [apps/reference/domains/execution_position/domain_dict.json](../apps/reference/domains/execution_position/domain_dict.json)
- [apps/reference/domains/execution_position/schemas/position_policy_microstructure_pressure_evaluated_v1.json](../apps/reference/domains/execution_position/schemas/position_policy_microstructure_pressure_evaluated_v1.json)
- [apps/reference/telemetry/shadow_journal.py](../apps/reference/telemetry/shadow_journal.py)
- focused tests у [tests/domains/execution_position](../tests/domains/execution_position), [tests/config](../tests/config) та [tests/contracts](../tests/contracts)

## Валідація

Виконано й пройдено:

- `python -m pytest tests/domains/execution_position/test_microstructure_snapshot.py`
- `python -m pytest tests/domains/execution_position/test_execpos_microstructure_atr_guards.py`
- `python -m pytest tests/domains/execution_position/test_position_policy_sidecar.py`
- `python -m pytest tests/domains/execution_position/test_position_policy_sidecar_recommendation_dedup.py`
- `python -m pytest tests/contracts/test_position_policy_sidecar_contracts.py`
- `python -m pytest tests/config/test_position_policy_sidecar_config_contract.py`

Фінальний focused package run:

- `python -m pytest tests/domains/execution_position/test_microstructure_snapshot.py tests/domains/execution_position/test_execpos_microstructure_atr_guards.py tests/domains/execution_position/test_position_policy_sidecar.py tests/domains/execution_position/test_position_policy_sidecar_recommendation_dedup.py tests/contracts/test_position_policy_sidecar_contracts.py tests/config/test_position_policy_sidecar_config_contract.py`
- Результат: `51 passed`

## Залишкові ризики

- Залишковий ризик: FE tick-level payload-и все ще не емiтять nested ATR нативно; пакет спирається на canonical boundary normalization плюс пасивне спостереження richer bar-semantic `CMD:PROCESS_STRATEGY` payload-ів.
- Залишковий ризик: legacy tests та fixtures, які подають прямі `testnet/live/backtest` literals замість profile names, вимагали явної обробки на sidecar authority-resolution seam.
- Залишковий ризик: якщо в майбутньому `authoritative_domain_modes` буде розширено, runtime-admission слід підтверджувати свіжим testnet forensic evidence, а не лише документацією.