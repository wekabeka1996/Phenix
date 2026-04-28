import sys
from pydantic import ValidationError
from apps.reference.config.strategies.mean_reversion import MRAssetConfig
from apps.reference.config.domains.decision_making import ExecutionGateConfig

print(f"ExecutionGateConfig module: {ExecutionGateConfig.__module__}")
print(f"ExecutionGateConfig fields: {ExecutionGateConfig.model_fields.keys()}")

try:
    # This is what failing in the test
    MRAssetConfig(
        enabled=True,
        leverage=None,
        strategy=None,
        liquidity_gate=None,
        allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        position_mode="STRICT",
    )
    print("MRAssetConfig initialized successfully")
except ValidationError as e:
    print(f"ValidationError: {e}")
except Exception as e:
    print(f"Other error: {e}")
