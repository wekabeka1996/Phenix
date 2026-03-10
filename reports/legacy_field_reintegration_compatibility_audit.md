# Legacy Field Reintegration Compatibility Audit

## Scope

Цей аудит оцінює не історичну цінність legacy/advanced полів, а сумісність їх повторної інтеграції з поточним checked-out workspace. Цільовий baseline для reintegration - поточний стан гілки/робочого дерева; `stable_11_11` використано лише як джерело legacy semantics, старих schema-contracts, runtime wiring і historical tests.

У фокусі тільки такі блоки:

- `execution_position.bracket_health_check.*`
- `execution_position.pending_entry_ttl.advanced_stale_cancel.*`
- `execution_position.pending_entry_ttl.supersede_reprice_guard.*`
- `execution_position.quiet_hours.*`
- `feature_engineering.absorption.dp_cap_pct`
- `feature_engineering.bar_ta.*`
- `feature_engineering.legacy_features_log.*`
- `shadow_telemetry.*`

Аудит відповідає на практичне питання: чи можна повернути ці поля і їх стару логіку без schema breakage, runtime conflicts, safety degradation, event drift, test breakage та operational risk. Якщо ні, то що саме треба змінити перед reintegration.

## Method

Аудит виконано по current-first методології:

1. Поточний schema/load baseline відтрасовано через `apps/reference/config_loader.py`, `apps/reference/domain_config.py`, `apps/reference/config_models.py`, `config/aurora/*.yaml`.
2. Поточні runtime owners визначено через актуальні модулі `execution_position`, `feature_engineering`, `decision_making`, `main`.
3. Legacy source реконструйовано через `git show stable_11_11:...` для тих самих schema/runtime/test paths.
4. Baseline tests прогнано на current workspace, щоб відрізнити вже наявні проблеми від потенційних reintegration regressions.
5. Кожен висновок нижче зроблено тільки там, де є code/config/test evidence. Якщо доказів недостатньо, це прямо позначено як `uncertain`.

Baseline evidence з current workspace:

- `tests/integration/test_ep01_3_pending_entry_ttl.py`: 14 passed, 1 failed; failure вже існує зараз і пов'язаний з `UnicodeDecodeError` при читанні `domains.yaml` без явного UTF-8 на Windows, а не з legacy logic.
- `tests/units/test_quiet_hours.py`: passed; покриває тільки helper `_in_quiet()`, не активний runtime gate.
- `tests/test_tpsl_placement.py`: passed; підтверджує, що current bracket placement/gating належить `OrderGuardian` та суміжним runtime owners.
- `tests/unit/feature_integrity/test_r1r2_features.py`: passed; підтверджує, що SSOT для absorption cap зараз є `feature_engineering.absorption.proxy.dp_cap_pct`.

## Current architecture constraints

Поточна система має жорсткі контракти, які прямо обмежують raw restore legacy полів.

Current config loading path:

- `apps/reference/config_loader.py` збирає конфіг тільки через canonical path: `system.yaml` + `trading.yaml` + `regime.yaml` + `domains.yaml`.
- `domains.yaml` вливається в `config.domains`; `trading.domains` explicitly rejected через `ConfigContractError`.
- Додатково `feature_engineering` в `trading.yaml` також explicitly rejected, тобто domain-level конфіг не може жити в старих або дубльованих шляхах.
- `apps/reference/domain_config.py` (`DomainConfigResolver`) fail-closed, якщо `config.domains` відсутній або неповний.

Current schema constraints:

- Root/domain models в `apps/reference/config_models.py` побудовані на strict Pydantic-моделях з `extra='forbid'`.
- Поточний `DomainsConfig` не містить `shadow_telemetry`.
- Поточний `ExecutionPositionDomainConfig` не містить `bracket_health_check` і `quiet_hours`.
- Поточний `PendingEntryTTLConfig` не містить `advanced_stale_cancel` і `supersede_reprice_guard`.
- Поточний `FeatureEngineeringDomainConfig` не містить `bar_ta` і `legacy_features_log`.
- Поточний `AbsorptionConfig` очікує cap тільки в `absorption.proxy.dp_cap_pct`; старий flat-path `absorption.dp_cap_pct` відсутній.
- Поточний `OpsConfig` не має живого поля `quiet_hours_utc`, хоча tooling/tests все ще містять застарілі згадки.

Current runtime constraints:

- `execution_position` більше не є старим monolithic FSM-path з `stable_11_11`; відповідальність розкладена між `fsm.py`, `event_handlers.py`, `open_executor.py`, `entry_manager.py`, `bracket_manager.py`, `order_guardian.py`, `exposure_manager.py`.
- Pending entry lifecycle зараз контролюють `PendingEntryTTLConfig`, `EPEventHandlers.on_regime_detected()`, `OpenExecutor._handle_supersede()`, `EntryManager.cancel_pending_entries_for_symbol()`, timeout scheduling та queued supersede flow.
- Bracket lifecycle зараз контролюють `BracketManager` + `OrderGuardian`; це current ownership boundary для TP/SL registration, cleanup, orphan cleanup, symbol reconciliation і placement gating.
- `feature_engineering` не має current FE-wide `bar_ta` state machine; indicator ownership частково мігрувала в strategy-local configs/runtime.
- `_log_features_to_file()` у `feature_engineering.py` досі викликається, але schema-controlled knobs для цього вже відсутні.
- Tracked current `main.py` не містить wiring для `shadow_telemetry`; у workspace присутні відповідні файли, але вони не є підтвердженим tracked current contract. Це `uncertain` overlap, а не SSOT.

Current execution/risk/event invariants:

- Немає допустимого dual-source-of-truth між `domains.yaml`, `trading.yaml`, tooling maps або runtime defaults.
- Bracket placement не повинен дублюватися паралельними watchdog/reconciler loops поза `BracketManager`/`OrderGuardian`.
- Pending-entry cancel semantics не повинні створювати duplicate cancel reasons, подвійний event emission або конфлікт між regime-driven і supersede-driven paths.
- Feature payload/readiness semantics не повинні змінюватися неявно через повернення FE-wide legacy producers.
- Fail-closed schema validation важливіша за backward-compat convenience: silent config acceptance без runtime effect неприпустимий.

## Executive summary

У поточну систему не можна безпечно повернути жоден із цільових блоків у старому вигляді `as is`.

Практичний висновок по групах:

- Можна повертати тільки через adapter/runtime rewrite: `execution_position.bracket_health_check`, `execution_position.pending_entry_ttl.advanced_stale_cancel`, `execution_position.pending_entry_ttl.supersede_reprice_guard`, `feature_engineering.legacy_features_log`, `shadow_telemetry`.
- Треба мігрувати в current field, а не відновлювати старий path: `feature_engineering.absorption.dp_cap_pct` -> `feature_engineering.absorption.proxy.dp_cap_pct`.
- Не варто повертати у старому path/ownership: `execution_position.quiet_hours`.
- Потрібен redesign, а не restore: `feature_engineering.bar_ta`.

Найкритичніші ризики raw restore:

- `extra='forbid'` validation failures для більшості старих YAML blocks.
- duplicate cancel logic між legacy stale/supersede guards і current pending-entry TTL flow.
- duplicate або race-prone bracket actions поза current `BracketManager`/`OrderGuardian` ownership boundary.
- silent no-op конфіги для helper-only або partially present paths.
- drift між schema SSOT і runtime behavior, особливо для `legacy_features_log` і `shadow_telemetry`.

## Compatibility matrix

| Field block | Stable role | Current equivalent | Schema compatible | Runtime compatible | Risk level | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| `execution_position.bracket_health_check.*` | Watchdog для перевірки/відновлення bracket health після входу | `BracketManager` + `OrderGuardian` cleanup/reconcile, але без current re-place-missing-brackets loop | No | Partial | High | `restore_with_adapter` |
| `execution_position.pending_entry_ttl.advanced_stale_cancel.*` | Розумне stale-cancel рішення через regime/age/drift gates | `cancel_on_regime_change` + `regime_change_cancel_mode`, але без age/drift gates | No | Partial | High | `restore_with_adapter` |
| `execution_position.pending_entry_ttl.supersede_reprice_guard.*` | Guard проти churn при same-side supersede/reprice | `cancel_on_supersede` + queued supersede timeout | No | Partial | High | `restore_with_adapter` |
| `execution_position.quiet_hours.*` | Time-window gate для блокування нових входів/ордерів | Helper `_in_quiet()` + stale tests/tool maps, без live gate owner | No | No | Medium | `do_not_restore` |
| `feature_engineering.absorption.dp_cap_pct` | Cap для normalization компонента absorption | `feature_engineering.absorption.proxy.dp_cap_pct` | No | Yes, через current field | Medium | `migrate_to_current_field` |
| `feature_engineering.bar_ta.*` | FE-wide bar-based TA state/config | Частково strategy-local indicator params, не FE-wide producer | No | No | High | `redesign_required` |
| `feature_engineering.legacy_features_log.*` | Shadow/data logging з режимами `off` / `sample` / `full` | `_log_features_to_file()` існує, але без current schema control | No | Partial | Medium | `restore_with_adapter` |
| `shadow_telemetry.*` | Ізольований shadow ingress/bridge для LLM intents | `decision_making` має latent telemetry probe; service files є у workspace, але tracked main wiring/schema відсутні | No | Partial | High | `restore_with_adapter` |

## Detailed analysis by block

### execution_position.bracket_health_check

Stable implementation summary:

- У `stable_11_11` цей блок був schema-backed (`config_models.py`), жив у `domains.yaml` і запускав окремий `_run_bracket_health_check(cfg)` loop у legacy `execution_position/fsm.py`.
- Семантика була safety/watchdog-oriented: після відкриття позиції перевіряти, чи bracket orders (SL/TP) існують і чи не треба втручання.

Current architecture overlap:

- У current runtime bracket lifecycle вже рознесений по `bracket_manager.py` і `order_guardian.py`.
- `OrderGuardian` зараз відповідає за registration, orphan cleanup, symbol reconciliation та cleanup of other brackets.
- Current code не має підтвердженого loop-а, який би регулярно добудовував відсутні brackets для already-open position.

Conflict analysis:

- Raw restore старого loop-а поверх current owners створює другий control-plane для bracket lifecycle.
- Є прямий ризик конфлікту з deferred/current placement semantics: старий watchdog може вважати bracket "відсутнім" у той момент, коли current `BracketManager` ще обробляє placement або guardian registration.
- Такий restore не поважає current ownership boundary і може породити duplicate place/cancel або racing registration.

Schema impact:

- Поточний `ExecutionPositionDomainConfig` не приймає `bracket_health_check`; YAML з цим блоком впаде на strict validation.
- Для reintegration потрібен новий config model в `apps/reference/config_models.py` і explicit field в `ExecutionPositionDomainConfig`.

Runtime impact:

- Старий код не можна просто вставити назад у current `fsm.py`, бо current runtime більше не збігається зі stable event/lifecycle ownership.
- Потрібен adapter, який використовує current `BracketManager`/`OrderGuardian` APIs і не обходить їх.
- Потрібні явні guardrails проти повторної постановки TP/SL, якщо bracket placement already in flight.

Safety impact:

- Без адаптації можливе safety degradation: duplicate bracket placement, inconsistent linkage, або невірне трактування transient state як аварії.
- Це особливо небезпечно, бо bracket logic є частиною current risk posture, а не просто observability.

Test impact:

- Найімовірніший regression surface: `tests/test_tpsl_placement.py`.
- До reintegration потрібні integration tests на:
  - no duplicate TP/SL placement при активному health check;
  - no race with deferred/current bracket placement;
  - no cleanup/place conflict між watchdog і guardian reconcile paths.

Recommended integration path:

- Додати schema block у `ExecutionPositionDomainConfig`, але runtime owner зробити не legacy FSM loop, а adapter поверх `BracketManager`/`OrderGuardian`.
- Увести feature flag або dry-run/shadow mode, де health check спочатку тільки рахує miss/recover candidates і емить telemetry без placement side effects.
- Перевести actual repair у current manager API після появи tests на duplicate protection.

Final recommendation:

`restore_with_adapter`

### execution_position.pending_entry_ttl.advanced_stale_cancel

Stable implementation summary:

- У `stable_11_11` блок був schema-backed nested config під `pending_entry_ttl`.
- Runtime логіка `_evaluate_advanced_stale_cancel` використовувала regime gate, min age gate та drift gate відносно ATR/features.
- Це був selective cancel, а не простий unconditional regime-change cancel.

Current architecture overlap:

- Current `PendingEntryTTLConfig` містить тільки `cancel_on_regime_change`, `regime_change_cancel_mode`, `cancel_on_supersede`, `cancel_on_panic`, timeout controls.
- `EPEventHandlers.on_regime_detected()` зараз реалізує простіший regime-change path: або дати TTL дожити, або скасувати pending entries.
- Живих `_pending_entry_meta` і `_last_features_cache` у current execution_position не знайдено.

Conflict analysis:

- Raw restore старої логіки неможливий без state, якого більше немає в current runtime.
- Якщо додати старий regime/age/drift cancel паралельно до current `on_regime_detected()`, вийде duplicate cancel policy.
- Є ризик, що current path скасує ордер раніше, ніж legacy gates встигнуть оцінитися, або навпаки змінить semantics `let_ttl_expire`.

Schema impact:

- Поточний `PendingEntryTTLConfig` не приймає `advanced_stale_cancel`; legacy YAML зараз падає на validation.
- Для reintegration потрібні новий nested model, validators і чітке правило взаємодії з `cancel_on_regime_change`/`regime_change_cancel_mode`.

Runtime impact:

- Потрібно або відновити per-order metadata та feature cache в current execution path, або побудувати новий adapter на основі вже наявних runtime sources.
- Integration point має бути в current event/lifecycle owners, а не у відновленому stable monolith.
- Найлогічніше місце для adapter-а: `EPEventHandlers` + `EntryManager`, з явним доступом до pending-entry age та актуальних features.

Safety impact:

- Неправильна інтеграція може призвести до conflicting cancel logic і непередбачуваного order lifecycle.
- Особливо ризиковий сценарій: partial schema restore без runtime wiring, коли користувач бачить accepted config, але логіка не працює або працює не там.

Test impact:

- Потенційно ламаються current pending-entry integration tests, якщо зміниться режим cancel on regime change.
- До reintegration потрібні:
  - config validation tests для нового nested block;
  - integration tests на regime gate, age gate, drift gate;
  - tests на взаємодію з `regime_change_cancel_mode='let_ttl_expire'`;
  - tests на відсутність duplicate cancel events/reasons.

Recommended integration path:

- Не повертати старий код `as is`.
- Додати schema block у `PendingEntryTTLConfig`.
- Реалізувати adapter в current pending-entry flow, де advanced stale cancel або замінює, або підпорядковує current regime-change path за чітким precedence rule.
- За замовчуванням тримати вимкненим через feature flag.

Final recommendation:

`restore_with_adapter`

### execution_position.pending_entry_ttl.supersede_reprice_guard

Stable implementation summary:

- У `stable_11_11` цей блок задавав threshold-и для того, чи виправдано cancel/reprice на тому ж боці.
- Логіка `_evaluate_supersede_reprice_guard` оцінювала price improvement через bps/ATR і могла працювати в shadow або enforce mode.

Current architecture overlap:

- Current runtime вже має живий queued supersede path через `OpenExecutor._handle_supersede()`, `EntryManager`, `ExposureManager` і `supersede_cancel_timeout_sec`.
- У current config є тільки coarse-grained `cancel_on_supersede`; guard, який би відсікав дрібні reprice, відсутній.

Conflict analysis:

- Raw restore поверх current supersede queue створює другий policy layer без узгодженого precedence.
- Старий guard залежав від metadata/features, яких current execution path напряму не тримає в stable shape.
- Якщо вставити guard не в той layer, можна або випадково блокувати валідний supersede, або все одно робити cancel, але вже з розсинхронізованими причинами та metrics.

Schema impact:

- Поточний `PendingEntryTTLConfig` не приймає `supersede_reprice_guard`.
- Потрібен nested model і чітка типізація shadow/enforce semantics.

Runtime impact:

- Guard повинен бути інтегрований у current `_handle_supersede()` decision point, а не як паралельний watcher.
- Для роботи потрібен доступ до current pending order state, target price і, якщо ATR-based threshold лишається, до поточних features/volatility inputs.

Safety impact:

- Неправильне повернення може погіршити current order-lifecycle stability: queued supersede зависне або почне churn-ити без фактичного покращення.
- Є ризик false confidence, якщо guard конфігурується, але runtime не має даних для повної оцінки.

Test impact:

- Потрібні integration tests на:
  - no cancel when improvement below threshold;
  - cancel and queue release when threshold exceeded;
  - no duplicate cancel intents при повторних same-side updates;
  - shadow-vs-enforce semantics, якщо режим буде підтримано.

Recommended integration path:

- Додати schema block у `PendingEntryTTLConfig`.
- Реалізувати current-path adapter у `OpenExecutor._handle_supersede()` і суміжних managers.
- Забезпечити fallback policy, якщо необхідних runtime inputs немає; fail-open/fail-closed вибір треба задокументувати і протестувати.

Final recommendation:

`restore_with_adapter`

### execution_position.quiet_hours

Stable implementation summary:

- У `stable_11_11` це був активний gate для блокування entry/order activity в задані часові вікна.
- У legacy описі є також historical mapping до `OpsConfig.quiet_hours_utc`.

Current architecture overlap:

- У current `fsm.py` залишився тільки helper `_in_quiet()`.
- `tests/units/test_quiet_hours.py` досі проходить, але тестує тільки helper semantics.
- Поточний `OpsConfig` не містить `quiet_hours_utc`.
- Tooling/docs містять застарілі згадки про `quiet_hours_utc`, тобто є явний drift між code SSOT і ancillary artifacts.

Conflict analysis:

- Відновлення старого `execution_position.quiet_hours` path створює новий canonical owner там, де current system не має live gate owner взагалі.
- Відновлення `OpsConfig.quiet_hours_utc` теж створить інший canonical owner і погіршить drift, якщо одночасно лишити domain-level path.
- Тут проблема не лише в schema, а в відсутності узгодженого place of truth.

Schema impact:

- Поточна schema не приймає цей блок ні в `execution_position`, ні в `ops`.
- Будь-яке повернення без попереднього architectural choice зламає SSOT або поверне dual config paths.

Runtime impact:

- Helper `_in_quiet()` сам по собі не вмикає gate.
- Якщо додати тільки schema, вийде silent accepted config без runtime effect.
- Якщо повернути старий gate без owner redesign, незрозуміло, хто має право блокувати: entry intent creation, open executor, чи exchange submission layer.

Safety impact:

- Найнебезпечніший сценарій тут не помилкове спрацювання, а false confidence: користувач думає, що quiet-hours enforce-яться, але gate фактично ніде не стоїть.

Test impact:

- Поточні helper tests не дадуть гарантії реальної роботи.
- До будь-якої інтеграції потрібні справжні end-to-end tests на blocked entries/orders у quiet windows та allow behavior поза ними.

Recommended integration path:

- Не відновлювати legacy path як є.
- Спочатку визначити один canonical owner: або `ops`, або domain gate, але не обидва.
- Після цього спроєктувати один runtime entry gate з явним місцем у current architecture і тільки тоді вводити schema path.

Final recommendation:

`do_not_restore`

### feature_engineering.absorption.dp_cap_pct

Stable implementation summary:

- У `stable_11_11` `dp_cap_pct` жив безпосередньо під `feature_engineering.absorption`.
- Він контролював clipping/normalization для absorption calculation.

Current architecture overlap:

- У current schema і runtime цей параметр живе в `feature_engineering.absorption.proxy.dp_cap_pct`.
- `apps/reference/domains/feature_engineering/types.py` fail-closed читає саме цей path.
- `tests/unit/feature_integrity/test_r1r2_features.py` підтверджує current SSOT.

Conflict analysis:

- Повернення старого flat-path створить dual-source-of-truth для одного й того ж runtime signal.
- Якщо одночасно підтримувати старий і новий path без нормалізації на loader/model-рівні, виникне hidden drift між тим, що задав користувач, і тим, що реально читає runtime.

Schema impact:

- Старий path зараз невалідний.
- Але правильний шлях тут не restore старої schema, а migration/aliasing у current field.

Runtime impact:

- Runtime уже сумісний з самою semantics cap, але не з legacy path.
- Якщо потрібна backward compatibility для старих YAML, її варто робити як one-way migration shim: old key accepted -> normalized into `absorption.proxy.dp_cap_pct`.

Safety impact:

- Ризик не стільки safety-runtime, скільки contract drift: accepted legacy key може не впливати на current calculation, якщо normalization не зробити централізовано.

Test impact:

- Прямий restore старого path може зламати або розмити current feature-integrity contract tests.
- Обов'язкові тести:
  - validation/migration tests для old -> new alias;
  - precedence tests, якщо тимчасово допускається одночасна присутність old/new key;
  - regression test, що runtime читає тільки normalized current field.

Recommended integration path:

- Не повертати `absorption.dp_cap_pct` як окремий current runtime field.
- Якщо потрібна backward compatibility, додати migration shim на config/model layer, який перетворює старий key в `absorption.proxy.dp_cap_pct` і не залишає обидва поля живими одночасно.

Final recommendation:

`migrate_to_current_field`

### feature_engineering.bar_ta

Stable implementation summary:

- У `stable_11_11` `bar_ta.*` був окремим FE-wide config block з періодами RSI/BB/Stochastic/SMA.
- Runtime мав `_update_bar_ta_state()` і підтримував окремий state machine/buffer ownership у `feature_engineering.py`.

Current architecture overlap:

- Current `FeatureEngineeringDomainConfig` не містить `bar_ta`.
- У current FE runtime немає `_update_bar_ta_state()` або `bar_ta` state.
- Частина indicator semantics тепер живе strategy-local, наприклад у mean-reversion strategy configs/runtime (`bb_window`, `bb_num_std`, `rsi_window`, `atr_window`).

Conflict analysis:

- Raw restore повертає в FE-wide layer те, що current architecture частково вже делегувала strategy-level owners.
- Це змінить payload semantics, feature readiness timing і, потенційно, обчислювальні витрати.
- Тут конфлікт не з одним конкретним guard, а з новою межею відповідальності між generic FE і strategy-specific indicators.

Schema impact:

- Поточна schema block не приймає.
- Просте додавання back old model ще не вирішує головної проблеми: де тепер має жити indicator ownership.

Runtime impact:

- Повернення old FE producer змінить current feature set і може створити нові обов'язкові prerequisites на `BAR_CLOSED`.
- Також це може дублювати обчислення тих самих індикаторів, які strategy layer вже рахує для себе.

Safety impact:

- Прямий safety-risk тут нижчий, ніж у execution blocks, але operational risk високий: performance regressions, payload drift, model/readiness regressions, downstream feature consumers із новими неочікуваними полями.

Test impact:

- Потрібні нові contract tests на feature payload, readiness, event cadence і відсутність дублюючих indicator producers.
- Без цього merge поверне непрогнозований feature drift.

Recommended integration path:

- Не робити raw restore.
- Спочатку вирішити архітектурно, які TA indicators мають бути FE-wide, а які strategy-local.
- Якщо частина semantics справді потрібна глобально, реалізувати новий current-native design з явним contract for payload/readiness, а не відновлювати stable implementation дослівно.

Final recommendation:

`redesign_required`

### feature_engineering.legacy_features_log

Stable implementation summary:

- У `stable_11_11` це був керований config block з режимами `off`, `sample`, `full` та `sample_every_n`.
- Runtime логував feature snapshots у файл не завжди, а згідно з mode/sample policy.

Current architecture overlap:

- У current `feature_engineering.py` `_log_features_to_file()` усе ще існує й викликається.
- Але current schema не містить `legacy_features_log`, тобто behavior залишився без публічного contract-controlled knob.

Conflict analysis:

- Це вже зараз є drift: runtime side effect живий, schema control відсутній.
- Raw restore старого блоку може бути близьким до current behavior, але без адаптації неясно, чи current log sink точно збігається з old semantics `off/sample/full`.

Schema impact:

- Поточна schema block не приймає.
- Для безпечного restore треба повернути config model і чітко зв'язати його з current `_log_features_to_file()` call path.

Runtime impact:

- Тут найменший structural gap серед усіх блоків: runtime hook уже існує.
- Але потрібен adapter, щоб current unconditional logging став schema-driven і fail-closed відносно mode/sample semantics.

Safety impact:

- Trading safety-risk низький, але operational/observability risk реальний: зайві логи, неконтрольований обсяг файлів, хибне уявлення про sampling/off behavior.

Test impact:

- Потрібні tests на:
  - `off` справді не пише;
  - `sample` пише тільки кожен `n`-й snapshot;
  - `full` пише кожен snapshot;
  - invalid modes не проходять validation.

Recommended integration path:

- Додати `LegacyFeaturesLogConfig` у `FeatureEngineeringDomainConfig`.
- Підключити current `_log_features_to_file()` до schema-driven policy.
- Зафіксувати один canonical output path і telemetry about dropped/sample decisions.

Final recommendation:

`restore_with_adapter`

### shadow_telemetry

Stable implementation summary:

- У `stable_11_11` це був великий окремий domain/service block з own schema, startup wiring у `main.py`, bridge components, ingress validation, allowlists/auth і dedicated tests.

Current architecture overlap:

- У current tracked schema `DomainsConfig` не має `shadow_telemetry`.
- У current tracked `main.py` немає підтвердженого startup wiring для bridges/publishers.
- У current `decision_making.py` лишився latent probe: при `require_telemetry` код шукає `config.domains.shadow_telemetry` через `getattr`.
- У workspace присутні файли `apps/reference/domains/shadow_telemetry/*`, але їх tracked status і включення в current product contract не підтверджені. Це `uncertain` overlap, а не достатній доказ сумісності.

Conflict analysis:

- Schema/runtime зараз розійшлися: decision-making ще знає про можливий telemetry dependency, але config contract її не дозволяє.
- Raw restore тільки schema або тільки service files створить partial subsystem: accepted config без wiring або wiring без validated config.
- Через відсутність source tests у current tree немає доказу, що цей subsystem сумісний з поточними contracts/auth/event bus.

Schema impact:

- Без додавання `shadow_telemetry` в `DomainsConfig` будь-який YAML block впаде на validation.
- Потрібен повний model set, а не лише один прапорець `enabled`.

Runtime impact:

- Недостатньо просто повернути файли: потрібне tracked startup wiring у `main.py`, bridge registration, config plumbing і перевірка взаємодії з `decision_making`.
- Вмикати це як live-trading control-plane одразу не можна; спочатку тільки shadow ingress/logging mode.

Safety impact:

- Це високий operational risk: partial subsystem здатен створити false confidence щодо LLM intent gating, auth, idempotency та bridge isolation.
- Якщо fail-closed behavior не відновити повністю, можна отримати або silent drop, або неконтрольовану активацію неповністю валідованого ingress path.

Test impact:

- Source tests із `stable_11_11` у current tree відсутні; лишилися тільки `.pyc`, що не є придатним доказом.
- До reintegration обов'язкові:
  - config validation tests;
  - bridge startup tests;
  - IPC ingress tests;
  - fail-closed tests на auth/allowlist/idempotency;
  - tests, що main-process restore не впливає на normal event flow when disabled.

Recommended integration path:

- Повернути тільки через adapter і тільки як tracked, schema-backed, test-backed subsystem.
- Спочатку відновити full schema contract у `apps/reference/config_models.py`, потім current `main.py` wiring, потім tests.
- Rollout тільки у shadow-only mode без live order effects, доки не буде повного regression contour.

Final recommendation:

`restore_with_adapter`

## Exact breakage risks

Нижче перелік конкретних поломок, які підтверджено або високовірогідно випливають з current architecture.

Validation failures:

- Будь-який raw YAML restore для `bracket_health_check`, `advanced_stale_cancel`, `supersede_reprice_guard`, `quiet_hours`, `bar_ta`, `legacy_features_log`, `shadow_telemetry` зараз упаде на strict schema validation через `extra='forbid'`.
- Старий `absorption.dp_cap_pct` також невалідний без migration shim.

Duplicate logic:

- `advanced_stale_cancel` може дублювати current `cancel_on_regime_change` flow.
- `supersede_reprice_guard` може дублювати або перехоплювати current queued supersede path.
- `bracket_health_check` може дублювати current bracket placement/reconcile responsibilities.

Silent no-op config:

- `quiet_hours` має helper-only overlap; schema-only restore без нового gate owner дасть accepted-but-ineffective config.
- `legacy_features_log` може приймати mode, але лишитися disconnected від current sink, якщо не перепідключити runtime.
- `shadow_telemetry` без tracked `main.py` wiring створить partial accepted config без реального service lifecycle.

Event conflicts:

- `advanced_stale_cancel` конфліктує з regime-change events, якщо не визначити precedence з `regime_change_cancel_mode`.
- `supersede_reprice_guard` конфліктує з current supersede timeout/queue semantics.
- `bar_ta` може змінити feature-emission cadence і readiness semantics на `BAR_CLOSED`.

Order lifecycle conflicts:

- `bracket_health_check` може втручатися в позицію до завершення current bracket placement/register flow.
- `advanced_stale_cancel` і `supersede_reprice_guard` можуть породжувати подвійні cancel requests або змінювати причину/час cancel.

Performance regressions:

- FE-wide `bar_ta` додає state/buffer maintenance та повторні індикаторні обчислення.
- Некерований `legacy_features_log` збільшує disk I/O.
- `shadow_telemetry` додає ingress/bridge path і журналювання, що треба оцінювати окремо.

Observability drift:

- Якщо schema повернути без current telemetry/metrics wiring, користувач побачить конфіг, але не отримає узгоджених counters/events.
- Особливо це стосується `advanced_stale_cancel`, `supersede_reprice_guard`, `legacy_features_log`, `shadow_telemetry`.

Safety regressions:

- Найвищий ризик у raw restore `bracket_health_check`, бо це може змінити current fail-safe TP/SL lifecycle.
- `advanced_stale_cancel` і `supersede_reprice_guard` здатні погіршити fail-closed behavior pending-entry management.
- `shadow_telemetry` без повного auth/idempotency contour погіршує operational safety perimeter.

## Required changes before reintegration

Config models:

- Додати в `apps/reference/config_models.py` нові/повернуті моделі тільки для блоків, що рекомендовані не як raw restore, а як controlled reintegration:
  - `BracketHealthCheckConfig` -> `ExecutionPositionDomainConfig`
  - `AdvancedStaleCancelConfig` -> `PendingEntryTTLConfig`
  - `SupersedeRepriceGuardConfig` -> `PendingEntryTTLConfig`
  - `LegacyFeaturesLogConfig` -> `FeatureEngineeringDomainConfig`
  - `ShadowTelemetry...Config` -> `DomainsConfig`
- Для `quiet_hours` спочатку прийняти architectural decision про canonical owner; не додавати старий block у schema до цього.
- Для `absorption.dp_cap_pct` не повертати старе runtime field; за потреби додати migration alias/shim, який нормалізує в `absorption.proxy.dp_cap_pct`.
- Для `bar_ta` спочатку зробити redesign spec; не додавати old model без нового owner contract.

YAML paths:

- Canonical owner для всіх domain blocks - тільки `config/aurora/domains.yaml`.
- Не вводити дублікати під `trading.*`, `ops.*` або tooling-only maps.
- Якщо `quiet_hours` колись повертати, спочатку обрати один canonical path і прибрати альтернативний.

Runtime wiring:

- `bracket_health_check`: adapter поверх `BracketManager`/`OrderGuardian`, без legacy bypass.
- `advanced_stale_cancel`: integration в current pending-entry flow (`EPEventHandlers`/`EntryManager`) з явним state/data contract.
- `supersede_reprice_guard`: integration в current supersede decision point (`OpenExecutor._handle_supersede()`).
- `legacy_features_log`: зробити current `_log_features_to_file()` schema-driven.
- `shadow_telemetry`: повернути tracked `main.py` wiring, bridge lifecycle і decision-making integration; workspace-only files недостатньо.
- `bar_ta`: новий runtime layer/design, якщо після redesign буде підтверджена потреба.

Tests:

- Додати config validation tests для кожного повернутого schema block або alias.
- Додати execution integration tests на regime-change cancel, queued supersede, no duplicate TP/SL placement.
- Додати FE tests на payload stability, readiness та `legacy_features_log` mode semantics.
- Додати shadow telemetry tests на config acceptance, bridge startup, IPC ingress, auth/allowlist/idempotency fail-closed behavior.
- Окремо усунути current Windows encoding issue у `tests/integration/test_ep01_3_pending_entry_ttl.py`, щоб baseline suite не шуміла хибним failure.

Docs:

- Оновити config maps/passports/docs тільки після того, як schema і runtime реально узгоджені.
- Прибрати stale references на `quiet_hours_utc`, `panic_ttl_sec`, `allowlist_symbols`, якщо вони не повертаються як active contract.

Feature flags:

- `bracket_health_check`, `advanced_stale_cancel`, `supersede_reprice_guard`, `legacy_features_log`, `shadow_telemetry` мають входити тільки через feature flag або shadow mode.
- `bar_ta` не вмикати feature flag-ом до redesign spec, інакше це сховає structural drift, а не вирішить його.

Migration shims:

- `absorption.dp_cap_pct` -> one-way normalization у `absorption.proxy.dp_cap_pct`.
- Якщо потрібна тимчасова backward compatibility для інших blocks, shim має лише переводити old config у current canonical model, а не створювати два паралельні runtime fields.

## Minimal safe rollout plan

1. Першим кроком можна безпечно зробити тільки low-blast-radius роботу:
   - закрити current baseline noise (`UTF-8` issue в pending-entry config test);
   - додати migration shim для `feature_engineering.absorption.dp_cap_pct`;
   - повернути schema-driven control для `feature_engineering.legacy_features_log`, бо runtime hook уже існує.

2. За feature flag або shadow mode треба ховати:
   - `execution_position.bracket_health_check`
   - `execution_position.pending_entry_ttl.advanced_stale_cancel`
   - `execution_position.pending_entry_ttl.supersede_reprice_guard`
   - `feature_engineering.legacy_features_log` під час первинного rollout
   - `shadow_telemetry` виключно як shadow-only subsystem

3. До merge обов'язково протестувати:
   - strict config validation на всі нові blocks/aliases;
   - execution integrations для regime-change cancel, supersede guard і no duplicate TP/SL placement;
   - FE payload/readiness stability;
   - `legacy_features_log` mode semantics;
   - `shadow_telemetry` startup/auth/idempotency/disabled-mode isolation.

4. Не можна вмикати одразу в live-like режимі:
   - raw `bracket_health_check`, бо він найближче підходить до safety-critical order lifecycle;
   - `bar_ta`, поки не буде redesign і підтвердженого owner contract;
   - `quiet_hours` у старому path;
   - `shadow_telemetry` з будь-яким live side effect до повного test contour.

## Final conclusion

У поточну систему не можна безпечно повернути жоден із цільових legacy blocks у старому вигляді.

Що можна повертати вже зараз:

- Частково і контрольовано: `feature_engineering.legacy_features_log` через schema/runtime adapter.
- Через migration, а не restore: `feature_engineering.absorption.dp_cap_pct` як alias у `feature_engineering.absorption.proxy.dp_cap_pct`.

Що можна повертати тільки частково і тільки через adapter:

- `execution_position.bracket_health_check`
- `execution_position.pending_entry_ttl.advanced_stale_cancel`
- `execution_position.pending_entry_ttl.supersede_reprice_guard`
- `shadow_telemetry`

Що краще не повертати в старому вигляді:

- `execution_position.quiet_hours`, бо current system не має одного узгодженого owner path/gate.

Де потрібен redesign замість restore:

- `feature_engineering.bar_ta`, бо current architecture вже змінила межу відповідальності між FE-wide і strategy-local indicator ownership.

Отже, practical answer такий: safe raw restore немає; є лише selective reintegration через migration shims, current-native adapters і phased rollout з тестами та feature flags. Будь-яка спроба просто повернути старі поля та їх stable runtime майже гарантовано створить schema breakage, runtime duplication або drift між SSOT і реальною поведінкою системи.
