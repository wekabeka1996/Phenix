import sys
from pydantic import ValidationError
from apps.reference.config.strategies.aurora import StrategyExecutionConfig

print(f"StrategyExecutionConfig module: {StrategyExecutionConfig.__module__}")
print(f"StrategyExecutionConfig fields: {StrategyExecutionConfig.model_fields.keys()}")

try:
    StrategyExecutionConfig(entry_order_type="MARKET")
except ValidationError as e:
    print(f"ValidationError: {e}")
except Exception as e:
    print(f"Other error: {e}")
