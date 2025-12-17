# TASK18A — `config_helpers.py` як string-path traversal

Команда(и):
- `rg -n "config_helpers|get_config_value|get_config_" apps/reference`
- `rg -n "from apps\\.reference\\.config_helpers|import .*config_helpers|config_helpers\\." apps/reference -S`

## Файл існує
- `apps/reference/config_helpers.py` (string-path traversal + `default=` параметр)

Ключові місця:
- `apps/reference/config_helpers.py:39`
```py
def get_config_value(config: Any, domain_name: str, path: str, default: Any = None) -> Any:
    ...
    for part in path.split('.'):
        ...
    return default
```

## Хто імпортує / викликає

`apps/reference` importers: **не знайдено** (0).

Примітка: `rg ... "get_config_"` також знаходить локальні методи `_get_config_value` в інших модулях (не `config_helpers.py`).

