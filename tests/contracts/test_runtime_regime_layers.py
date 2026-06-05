from apps.reference.contracts.runtime_regime_layers import (
    RuntimeRegimeClock,
    RuntimeRegimeLayer,
    RuntimeRegimeScope,
    is_structural_regime_payload,
    normalize_structural_regime_label,
    should_apply_global_execution_regime,
    structural_regime_ref,
)


def test_structural_payload_defaults_are_backward_compatible() -> None:
    payload = {"symbol": "BTCUSDT", "regime": "TREND_UP"}

    assert is_structural_regime_payload(payload) is True
    assert should_apply_global_execution_regime(payload) is False


def test_execution_micro_global_payload_is_explicitly_distinct() -> None:
    payload = {
        "symbol": "BTCUSDT",
        "regime": "HIGH_VOLATILITY",
        "regime_layer": RuntimeRegimeLayer.EXECUTION_MICRO.value,
        "regime_scope": RuntimeRegimeScope.GLOBAL.value,
        "regime_clock": RuntimeRegimeClock.EVENT_DRIVEN.value,
    }

    assert is_structural_regime_payload(payload) is False
    assert should_apply_global_execution_regime(payload) is True


def test_structural_regime_ref_is_symbol_scoped() -> None:
    assert structural_regime_ref("btcusdt", 1234) == "structural:BTCUSDT:1234"


def test_normalize_structural_regime_label_bridges_legacy_vocabulary() -> None:
    assert normalize_structural_regime_label("BULL_TREND") == "TREND_UP"
    assert normalize_structural_regime_label("BEAR_TREND") == "TREND_DOWN"
    assert normalize_structural_regime_label("mean_reversion") == "MEAN_REVERSION"
