from decimal import Decimal

from apps.reference.domains.decision_making.signal_score_v2 import SignalScoreV2


def test_score_clamp_explosion_containment() -> None:
    features = {"x": 100.0}
    weights = {"x": 1.0}
    neutrals = {"x": 0.0}
    readiness = {"x": True}

    result = SignalScoreV2.calculate_score(
        features=features,
        weights=weights,
        neutrals=neutrals,
        readiness=readiness,
        essential_features=set(),
        symbol="TEST",
    )

    assert result.deferred is False
    assert result.score == Decimal("1")
    assert result.score_raw == Decimal("100")


def test_zero_weights_returns_neutral_no_crash() -> None:
    features = {"x": 5.0}
    weights = {"x": 0.0}
    neutrals = {"x": 0.0}
    readiness = {"x": True}

    result = SignalScoreV2.calculate_score(
        features=features,
        weights=weights,
        neutrals=neutrals,
        readiness=readiness,
        essential_features=set(),
        symbol="TEST",
    )

    assert result.deferred is False
    assert result.score == Decimal("0")
    assert result.wabs == Decimal("0")

