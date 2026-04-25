from pathlib import Path

import yaml


def test_max_risk_score_uses_current_contract_shape() -> None:
    """
    max_risk_score is a required-nullable per-asset block in the current schema.
    Active configs must carry either explicit null or a structured override object.
    """
    aurora_path = Path("config/aurora/strategies/aurora.yaml")
    payload = yaml.safe_load(aurora_path.read_text(encoding="utf-8"))
    assets = payload["aurora"]["assets"]

    for symbol, asset_cfg in assets.items():
        assert "max_risk_score" in asset_cfg, f"max_risk_score missing for {symbol}"
        max_risk_score = asset_cfg["max_risk_score"]
        assert max_risk_score is None or isinstance(max_risk_score, dict), (
            f"max_risk_score for {symbol} must be null or mapping, got {type(max_risk_score).__name__}"
        )
