# Config Inventory Map (v0.2)

> TASK 7.7: єдиний SSOT для AuroraTrader — `config/domains/*.yaml`, `config/instruments.yaml`, `config/overrides.yaml`, `config/modes.yaml`. Монофайл `config/aurora/trading.yaml` та пов’язані YAML переміщено до `config/archive/v1/` і більше не читаються рантаймом чи тестами (залишаються лише як історичний snapshot).

## Перелік конфіг-файлів
- `config/instruments.yaml` — паспортні дані монет (precision, limits, tp/sl дефолти), споживається `resolve_instrument_profile`.
- `config/overrides.yaml` — символ/профільні overrides (limits, tp_sl, risk) для резольверів.
- `config/symbols.yaml` — архівований, дублював instruments.yaml (залишено для історії, не підключається).
- `config/domains/execution.yaml` — execution-домен (exposure, manage, brackets, watchdog, guardian, auto flags).
- `config/domains/risk.yaml` — risk-домен (daily_limits, soft_limits, score_weights, thresholds).
- `config/domains/decision.yaml` — decision-домен (signals, qos, behavior_fsm, cooldown).
- `config/domains/sizing.yaml` — sizing-домен (min_notional_usd, kelly, modifiers, liquidity капи).
- `config/domains/features.yaml` — feature engineering (EMA/volume/volatility windows, liquidity, macro_sync).
- `config/domains/regimes.yaml` — regime detector (models, regimes, hotreload whitelist).
- `config/domains/tca.yaml` — TCA / execution preferences (максимальні slippage/latency).
- `config/modes.yaml` — профілі trading_mode + domain_mode mapping.
- `config/core.yaml` — ARCHIVED; дублював базові системні налаштування.
- `config/archive/v1/system.yaml` — legacy системний YAML (не використовується, лише reference).
- `config/archive/v1/trading.yaml` — legacy монолітний торговий YAML (quarantined snapshot).
- `configs/master_config_v1.yaml` та `configs/frozen/*.yaml` — історичні master-файли (reference-only, не завантажуються AuroraConfig).
- `vfoundation/configs/adapter.yaml`, `vfoundation/configs/idempotency.yaml` — internal configs бібліотеки vFoundation (залишаються активними).

## Використання конфігів доменами
| Файл конфігу | Домени/модулі-споживачі | Основні резольвери/лоадери | Примітки |
| --- | --- | --- | --- |
| `config/instruments.yaml` | `execution_position`, `decision_making`, `risk_management` | `resolve_instrument_profile` | Паспортні дані + limits, джерело для `InstrumentProfile.source="config_v2"`. |
| `config/overrides.yaml` | ті самі домени, що вище | `resolve_instrument_profile`, `resolve_exposure_policy`, domain-specific overrides | Символьно-профільні налаштування (limits, tp/sl, risk). |
| `config/domains/execution.yaml` | `execution_position` | `resolve_exposure_policy`, `resolve_execution_manage_config`, `resolve_brackets_config` | Управління execution: exposure, manage, guardian, brackets. |
| `config/domains/risk.yaml` | `risk_management`, `decision_making` | `resolve_daily_risk_state`, `resolve_risk_soft_limits`, `resolve_trading_allowed_thresholds` | Daily limits, soft limits, scoring ваги. |
| `config/domains/decision.yaml` | `decision_making` | `resolve_decision_policy`, `compute_effective_trading_modes` | Сигнали, QoS, behavior FSM. |
| `config/domains/sizing.yaml` | `decision_making`, `execution_position` | `resolve_sizing_policy` | Position sizing, liquidity, kelly. |
| `config/domains/features.yaml` | `feature_engineering`, `market_data` | `resolve_feature_engineering_config` | Вікна, enable_new_metrics, macro_sync. |
| `config/domains/regimes.yaml` | `regime_detector`, `risk_management` | `resolve_regime_detector_config` | Конфіг HMM, whitelist hotreload. |
| `config/domains/tca.yaml` | `execution_position`, `adapters` | (pending resolver) | Стан переходу; використовується у TCA утилітах. |
| `config/modes.yaml` | всі домени, bootstrap | `compute_effective_trading_modes`, `get_domain_mode_from_mapping` | Профілі trading_mode та domain modes. |
| `config/archive/v1/system.yaml` | **архів** | `ConfigLoader` читає лише якщо явно вказано `config_root` | Зберігається для довідки, не підключається за замовчуванням. |
| `config/archive/v1/trading.yaml` | **архів** | лише manual diff/analysis | Використовується для історичних audітів, тестові копії видалені. |
| `configs/master_config_v1*.yaml` | docs/audits | `tools/verify_config.py` (offline) | Контрактна документація, не рантайм. |
| `vfoundation/configs/*.yaml` | `vfoundation` helpers | `vfoundation.config` | Active для бібліотеки (rate-limit/idempotency). |

## Legacy / Active / Deprecated
- `config/instruments.yaml`, `config/overrides.yaml`, `config/domains/*.yaml`, `config/modes.yaml` — **active** (SSOT для всіх доменів, читаються резольверами config v2).
- `config/core.yaml`, `config/symbols.yaml` — **archived** (збігаються з legacy структурами, лишені для історії).
- `config/archive/v1/system.yaml`, `config/archive/v1/trading.yaml` — **legacy snapshots** (не використовуються рантаймом/тестами, доступні лише для ручного аудиту).
- `configs/master_config_v1*.yaml` — **reference-only** (джерело історичних frozen контентів, не завантажуються AuroraConfig).
- `tests/config/aurora/*` — **removed from runtime path**; тести більше не підміняють `config_root`, натомість працюють через `load_config()` → config v2.
- `vfoundation/configs/adapter.yaml`, `vfoundation/configs/idempotency.yaml` — **active** (частина бібліотеки vFoundation; поза обсягом config v2).

## Виявлені дублікати та конфлікти (чернетка)
- `risk.trading_allowed_thresholds` з `trading.yaml` повторюється з `system.yaml` (обидва задають drawdown/stop-loss limits); потрібно узгодити, де еталон.
- `decision` thresholds (open/close) дублюються між `trading.yaml` та `trading_v0.2.yaml` (legacy має окремі значення), що може спричинити різні поведінки при `trading_mode` switch.
- `instruments` та `feature_engineering` блоки в `trading.yaml` й `trading_v0.2.yaml` мають схожі ключі, але можуть не синхронізуватися під час оновлень.
- `tp_sl` параметри з `trading.yaml` частково повторюються у `configs/master_config_v1.yaml`, а також у `tp_sl_overrides` (в `CONFIG_REFERENCE` підкреслено, що overrides різні). Підозріло для exposure + risk guards.
- `exposure` та `leverage` значення іноді фіксуються як hardcode у `system.yaml`, `trading.yaml` і `vfoundation/configs/adapter.yaml` (adaptors/resolution mix); потребує узгодження джерела правди.

## Автоматизований інвентар

Існує скрипт `tools/config_inventory.py`, який автоматично збирає всі ключі з основних YAML-конфігів у плоский вигляд (наприклад, `trading.execution.manage.quick_profit.target_usd`).

### Куди записується JSON
Скрипт зберігає результат у `docs/config_analysis/config_inventory_raw.json` як машинно-читаний артефакт.

### Як запускати
Запустіть команду:
```
python -m tools.config_inventory
```
або
```
python tools/config_inventory.py
```

Це побудує інвентар, запише JSON і виведе коротке резюме в консоль (кількість файлів, кількість ключів на файл).
