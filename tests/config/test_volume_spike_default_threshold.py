from collections import deque
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
from apps.reference.domains.feature_engineering.types import HotState


def test_default_config_enables_low_volume_neutral_for_volume_spike():
    domains_path = Path(__file__).resolve().parents[2] / "config" / "aurora" / "domains.yaml"
    with open(domains_path, "r") as f:
        domains_cfg = yaml.safe_load(f) or {}

    min_vol = (
        domains_cfg.get("feature_engineering", {})
        .get("volume", {})
        .get("min_window_volume_usd", 0.0)
    )
    assert float(min_vol) > 0.0

    cfg = MagicMock()
    cfg.neutral_value = Decimal("0.5")
    cfg.volume_spike_cap = Decimal("3.0")
    cfg.min_window_volume_usd = float(min_vol)
    cfg.volume_sma_length = 5
    cfg.volume_window_ms = 60_000
    cfg.volume_input_mode = "integrate"

    engine = FeatureCalculationEngine(cfg)

    state = HotState(
        ema_short=Decimal("100.0"),
        ema_long=Decimal("99.0"),
        ema_short_alpha=0.2,
        ema_long_alpha=0.1,
        vol_window_start_ts=None,
        vol_current_ts=0,
        vol_window_trades=float(min_vol) - 1.0,
        vol_hist=deque(maxlen=5),
        vol_stats=(3, 500.0, 100.0),
        range_window_start_ts=None,
        range_min=None,
        range_max=None,
        range_hist=deque(maxlen=5),
        range_stats=(0, 0.0, 0.0),
        returns_buffer=deque(maxlen=100),
        prev_price=None,
    )

    assert engine.compute_volume_spike(state) == Decimal("0.5")

