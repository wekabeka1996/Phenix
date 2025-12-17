# TASK18A — DomainConfigResolver / `domain_config.py` usage (“middleman”)

Команда(и):
- `rg -n "DomainConfigResolver|domain_config" apps/reference`
- `rg -n "DomainConfigResolver\\(" apps/reference -S`

## Resolver визначений тут
- `apps/reference/domain_config.py:46` (`class DomainConfigResolver`)

## Dict-compat factory (сигнал “middleman”)
- `apps/reference/domain_config.py:275`
```py
def create_resolver_from_dict(config_dict: dict) -> DomainConfigResolver:
    aurora_config = AuroraConfig(**config_dict)
    return DomainConfigResolver(aurora_config)
```

## Використання по доменах

### `risk_management`
- `apps/reference/domains/risk_management/risk_management.py:64-66`
```py
from apps.reference.domain_config import DomainConfigResolver
self.resolver = DomainConfigResolver(config)
self.domain_config = self.resolver.get_risk_management()
```

### `decision_making`
- `apps/reference/domains/decision_making/decision_making.py:237-239`
```py
resolver = DomainConfigResolver(self.config)
dm_cfg = resolver.get_decision_making()
qos_cfg = dm_cfg.qos
```

### `execution_position` (exposure_guard)
- `apps/reference/domains/execution_position/exposure_guard.py:91-93`
```py
resolver = DomainConfigResolver(config)
eg_config = resolver.get_exposure_guard()
```

### `feature_engineering` wrapper
- `apps/reference/domains/feature_engineering/types.py:139-142`
```py
if isinstance(config, AuroraConfig):
    resolver = DomainConfigResolver(config)
    return resolver.get_feature_engineering()
```

