"""
Regression test: md_amr handler must inject top-level ``atr`` into features
before calling ``build_market_input``.

Feature Engineering emits ATR nested at ``features["volatility"]["atr_14"]``,
but ``build_market_input`` expects a top-level ``features["atr"]``.
mean_reversion_handler already does this injection; md_amr was missing it,
causing 100% DECISION_REJECT on XRPUSDT/BNBUSDT with
"objective field missing or invalid: atr".
"""

from __future__ import annotations

import pytest
from apps.reference.domains.objective_engine.adapters import (
    build_market_input,
    _to_float,
)


# ---------------------------------------------------------------------------
# Canonical FE features dict (as emitted by feature_engineering.py)
# ---------------------------------------------------------------------------

def _fe_features(*, atr_14: float = 0.0035) -> dict:
    """Reproduce the exact shape of features from CMD:PROCESS_STRATEGY."""
    return {
        "obi": "0.12",
        "tfi": "0.05",
        "delta_price": "0.001",
        "absorption": "0.0",
        "price": "0.62",
        "liquidity_kappa": "1.2",
        "ema_bias": "0.01",
        "volume_spike": "0.3",
        "volatility_state": "0.45",
        "depth_imbalance": "0.1",
        "spread_bps": "2.5",
        "volatility": {
            "bar_range": "0.005",
            "bar_body": "0.003",
            "true_range": "0.004",
            "atr_14": atr_14,
            "range_pct": 0.008,
            "atr_pct": 0.006,
            "atr_ready": True,
        },
    }


class TestBuildMarketInputWithoutTopLevelAtr:
    """FE features have NO top-level 'atr' — build_market_input must fail."""

    def test_raw_fe_features_missing_atr_raises(self) -> None:
        features = _fe_features()
        assert "atr" not in features  # sanity
        with pytest.raises(ValueError, match="atr"):
            build_market_input(features=features)


class TestBuildMarketInputAfterAtrInjection:
    """After handler injects signal.atr, build_market_input succeeds."""

    def test_injected_atr_resolves(self) -> None:
        features = _fe_features(atr_14=0.0042)
        # Simulate what md_amr handler now does:
        features.setdefault("atr", 0.0042)
        result = build_market_input(features=features)
        assert abs(result.atr - 0.0042) < 1e-9

    def test_setdefault_does_not_overwrite_existing(self) -> None:
        features = _fe_features()
        features["atr"] = 0.005  # already present (mean_reversion pattern)
        features.setdefault("atr", 999.0)  # should NOT overwrite
        result = build_market_input(features=features)
        assert abs(result.atr - 0.005) < 1e-9

    def test_all_fields_resolve_with_fe_features(self) -> None:
        features = _fe_features()
        features.setdefault("atr", 0.003)
        result = build_market_input(features=features)
        assert result.price == pytest.approx(0.62)
        assert result.atr == pytest.approx(0.003)
        assert result.spread_bps == pytest.approx(2.5)
        assert result.liquidity_state == pytest.approx(1.2)
        assert result.volatility_state == pytest.approx(0.45)


class TestToFloatEdgeCases:
    """Targeted coverage for _to_float guard in adapters.py."""

    def test_none_raises(self) -> None:
        with pytest.raises(ValueError, match="test_field"):
            _to_float(None, field_name="test_field")

    def test_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="test_field"):
            _to_float(float("nan"), field_name="test_field")

    def test_inf_raises(self) -> None:
        with pytest.raises(ValueError, match="test_field"):
            _to_float(float("inf"), field_name="test_field")

    def test_valid_string(self) -> None:
        assert _to_float("3.14", field_name="x") == pytest.approx(3.14)
