from __future__ import annotations

from pathlib import Path

import pytest

from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import AuroraConfig


def _raw_config_dict() -> dict:
    cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()
    return cfg.model_dump(mode="python")


def test_missing_llm_strategy_config_fails_closed() -> None:
    raw = _raw_config_dict()
    # Trigger contract path.
    raw["trading"]["llm_orchestration"]["symbols_llm"] = ["BNBUSDT"]
    raw["trading"]["llm_orchestration"]["mode"] = "hybrid_advisory"
    raw["trading"]["llm_orchestration"]["intent_policy"]["max_notional_usd"] = 100.0
    raw["trading"]["llm_orchestration"]["intent_policy"]["max_qty"] = 2.0
    raw["trading"]["llm_orchestration"]["intent_policy"]["max_price_deviation_bps"] = 20.0
    raw["strategies"].pop("llm_microstructure", None)

    with pytest.raises(ValueError, match="strategy_config_missing\\(llm_microstructure\\)"):
        AuroraConfig.model_validate(raw)


def test_llm_symbol_ownership_mismatch_fails_closed() -> None:
    raw = _raw_config_dict()
    raw["trading"]["llm_orchestration"]["symbols_llm"] = ["BNBUSDT"]
    raw["trading"]["llm_orchestration"]["mode"] = "hybrid_advisory"
    raw["trading"]["llm_orchestration"]["intent_policy"]["max_notional_usd"] = 100.0
    raw["trading"]["llm_orchestration"]["intent_policy"]["max_qty"] = 2.0
    raw["trading"]["llm_orchestration"]["intent_policy"]["max_price_deviation_bps"] = 20.0
    raw["strategies_registry"]["assignments"]["BNBUSDT"] = ["aurora"]

    with pytest.raises(ValueError, match="symbol ownership invalid for BNBUSDT"):
        AuroraConfig.model_validate(raw)
