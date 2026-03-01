from decimal import Decimal

from apps.reference.domains.alpha_search.ensemble import EnsembleConfig, EnsembleModel
from apps.reference.domains.alpha_search.models.mean_reversion import MeanReversionAlphaModel
from apps.reference.domains.alpha_search.models.momentum import MomentumAlphaModel
from apps.reference.domains.alpha_search.models.volatility import VolatilityAlphaModel


def _make_ensemble() -> EnsembleModel:
    return EnsembleModel(
        config=EnsembleConfig(),
        models={
            "momentum_v1": MomentumAlphaModel(),
            "mean_reversion_v1": MeanReversionAlphaModel(),
            "volatility_v1": VolatilityAlphaModel(),
        },
    )


def test_ta_ensemble_requires_manifest_not_empty():
    ensemble = _make_ensemble()
    required = ensemble.get_required_features()
    assert required, "ta_ensemble required features manifest must not be empty"
    assert "rsi_14" in required
    assert "atr_14" in required
    assert "bb_position" in required


def test_ta_ensemble_missing_features_yields_zero_confidence():
    ensemble = _make_ensemble()
    score = ensemble.calculate_alpha(
        symbol="BTCUSDT",
        market_data={"close": 50000.0},
        features={},
        context={},
    )
    assert score.score == Decimal("0.0")
    assert score.confidence == Decimal("0.0")
    assert any("missing_features" in reason for reason in score.why)
