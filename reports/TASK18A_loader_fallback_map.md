# TASK18A — `apps/reference/config_loader.py` fallbacks / legacy map

Команда(и):
- `rg -n "deep_merge|deprecated|fallback|warn|WARNING|compat|legacy" apps/reference/config_loader.py`
- `rg -n "mean_reversion_1m" apps/reference/config_loader.py`

## Карта патернів

| pattern | file:line | behavior | strict impact |
|---|---:|---|---|
| `deep_merge()` об’єднання кількох YAML | `apps/reference/config_loader.py:20` + `apps/reference/config_loader.py:408` | merge `system.yaml` → `trading.yaml` → `regime.yaml` | OK (це “compose”, але слід не плутати з fallback) |
| “domains.yaml not found … fallback” log | `apps/reference/config_loader.py:317-322` | лог каже про fallback на `trading.domains` | misleading: нижче код **FAIL FAST** без fallback |
| Canonical domains, no fallback | `apps/reference/config_loader.py:415-435` | якщо `domains.yaml` порожній/немає → `ValueError` | OK (fail-closed) |
| Deprecated `trading.domains` detection | `apps/reference/config_loader.py:437-451` | strict → `ValueError`, non-strict → `LOG.warning` | non-strict гілка = м’який режим (не SSOT) |
| Deprecated `trading.instruments` detection | `apps/reference/config_loader.py:494-515` | strict → `ValueError`, non-strict → `LOG.warning` | non-strict гілка = м’який режим (не SSOT) |
| Deprecated `features.yaml` presence | `apps/reference/config_loader.py:333-345` | strict → `ValueError`, non-strict → `LOG.warning` | non-strict гілка = м’який режим (two-sources risk) |
| Deprecated `trading.mean_reversion_1m` | `apps/reference/config_loader.py:353-366` | strict → `ValueError`, non-strict → `LOG.warning` | OK (в strict забороняє дублікати) |
| Strategy profile injection at root | `apps/reference/config_loader.py:612-615` | `merged_config[strategy_id] = config_data` | створює root-level keys (вимагає явної підтримки в schema) |
| Back-compat root `execution` mapping | `apps/reference/config_loader.py:697-704` | якщо нема `execution`, копіює з `trading.execution` | root-level alias = legacy surface |
| Runtime metadata injection (`_config_*`) | `apps/reference/config_loader.py:708-709` | додає `_config_name`, `_config_dir` у dict перед parse | extra keys на root рівні (зараз тримається через `extra='allow'`) |

