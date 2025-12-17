# TASK18A — Dict-Relapse у `apps/reference/main.py` (`config.to_dict()` hits)

Команда(и):
- `rg -n "to_dict\\(" apps/reference/main.py`

## Hits (10)

### AlertManager
- `apps/reference/main.py:1430`
```py
# Initialize Alert Manager
alert_manager = AlertManager(config=config.to_dict(), logger=LOG)
LOG.info("✅ Alert Manager initialized")
```

### Hybrid preflight (`check_hybrid_coherence`)
- `apps/reference/main.py:1443`
```py
# FSMP-P3-T01: Pre-flight check for hybrid coherence
is_coherent, reasons = check_hybrid_coherence(config.to_dict())
if not is_coherent:
```

### AuroraBridge
- `apps/reference/main.py:1482`
```py
# Initialize AuroraBridge (handles TRADE_INTENT_PROPOSED → CMD:OPEN with freshness gate)
bridge = AuroraBridge(fsm=fsm, config=config.to_dict(), logger=LOG)
```

### AccountConnector
- `apps/reference/main.py:1516`
```py
# Account Connector (source of account balance and positions)
account_balance = AccountConnector(fsm=fsm, config=config.to_dict())
```

### AccountObserver
- `apps/reference/main.py:1523`
```py
account_observer = AccountObserver(
    fsm=fsm, config=config.to_dict(), environment=risk_portfolio_source)
```

### MarketData feature-flag access via dict traversal
- `apps/reference/main.py:1527`
```py
# Feature flag: trading.market_data.use_multiprocessing (default: False for safety)
market_data_cfg = config.to_dict().get("trading", {}).get("market_data", {})
use_multiprocessing = market_data_cfg.get("use_multiprocessing", False)
```

### PositionTracking
- `apps/reference/main.py:1551`
```py
# Position Tracking (tracks portfolio state)
position_tracking = PositionTracking(fsm=fsm, config=config.to_dict())
```

### ExecPosFSM
- `apps/reference/main.py:1555`
```py
global execution_position
execution_position = ExecPosFSM(config=config.to_dict(), fsm=fsm)
LOG.info("✅ Execution position FSM initialized")
```

### RegimeDetector
- `apps/reference/main.py:1703`
```py
# Emits EVT:REGIME_DETECTED which decision_making uses for regime-aware sizing
regime_detector = RegimeDetector(config=config.to_dict(), fsm=fsm)
LOG.info("✅ RegimeDetector initialized and subscribed to EVT:FEATURES_CALCULATED")
```

### Alert checks loop (dict cast)
- `apps/reference/main.py:1791`
```py
from typing import cast
config_dict_arg = cast(dict[Any, Any], config.to_dict(
) if hasattr(config, 'to_dict') else config)
_perform_alert_checks(alert_manager, wal_dir, config_dict_arg)
```

