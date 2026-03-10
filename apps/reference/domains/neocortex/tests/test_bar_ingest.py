import json
from pathlib import Path

import pytest
import yaml

from apps.reference.domains.neocortex.config_models import NeocortexConfig
from apps.reference.domains.neocortex.logic.ingest.parser import FeatureParser
from apps.reference.domains.neocortex.logic.ingest.parsers.feature_parser import parse_feature_log_line


def test_bar_feature_log_nested_json_is_flattened_and_parsed(tmp_path: Path) -> None:
    config_dir = Path(__file__).resolve().parents[1] / "config"

    with open(config_dir / "ingest.yaml") as f:
        ingest_data = yaml.safe_load(f)
    with open(config_dir / "neuro.yaml") as f:
        neuro_data = yaml.safe_load(f)

    system_data = {
        "data_dir": str(tmp_path / "data"),
        "checkpoint_dir": str(tmp_path / "data" / "checkpoints"),
        "brain_workers": 1,
        "queue_maxsize": 1000,
        "log_level": "INFO",
        "log_to_file": False,
        "rng_seed": 42,
    }

    cfg = NeocortexConfig(system=system_data, ingest=ingest_data, neuro=neuro_data)
    parser = FeatureParser(cfg.ingest)

    nested_features = {
        "price": "90450.0",
        "obi": "-0.12",
        "tfi": "0.34",
        "delta_price": "1.5",
        "ema_bias": "0.55",
        "volume_spike": "0.10",
        "volatility_state": "0.5",
        "depth_imbalance": "0.9",
        "spread_bps": "0.01",
        "macro_sync": "0.88",
        "macro_resid": "0.5",
        "volume_zscore": "0.95",
        "large_trade_imbalance": "0.24",
        "volatility": {
            "bar_range": "12.3",
            "bar_body": "3.2",
            "true_range": "15.0",
            "atr_14": None,  # warmup
            "range_pct": "0.001",
            "atr_pct": "0.0008",
        },
        "liquidity": {"obi_close": "0.77"},
    }

    log_line = (
        "2026-01-09 12:58:42,585 - FeatureEngineering - INFO - "
        f"Calculated features for BTCUSDT: {json.dumps(nested_features)}"
    )
    entry = parse_feature_log_line(log_line)
    assert entry is not None

    assert "volatility_atr_14" in entry.features
    assert entry.features["volatility_atr_14"] == 0.0
    assert entry.features["liquidity_obi_close"] == 0.77

    obs = parser.parse({"timestamp": entry.timestamp, "symbol": entry.symbol, "features": entry.features})
    assert obs.features_vector.shape == (len(cfg.ingest.feature_list),)

    idx_atr = parser.feature_indices["volatility_atr_14"]
    idx_liq = parser.feature_indices["liquidity_obi_close"]
    assert float(obs.features_vector[idx_atr]) == 0.0
    assert float(obs.features_vector[idx_liq]) == pytest.approx(0.77, abs=1e-6)

