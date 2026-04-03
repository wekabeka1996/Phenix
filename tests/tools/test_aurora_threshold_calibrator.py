import pytest

from tools.calibration.calibrate_aurora_thresholds import (
    CalibrationError,
    THRESHOLD_SOURCE_MODE_ASSET_OVERRIDE_ONLY,
    THRESHOLD_SOURCE_MODE_LIVE_EFFECTIVE,
    ThresholdSurface,
    _candidate_blockers_for_surface,
    _extract_live_threshold_surface,
)


def _aurora_fixture() -> dict:
    return {
        "decision": {
            "signal_threshold": 0.162,
            "regime_threshold_multipliers": {
                "DEFAULT": 1.0,
                "TREND_UP": 0.1,
            },
        },
        "assets": {
            "BTCUSDT": {
                "signal_threshold": {
                    "enabled": False,
                    "value": None,
                },
                "regime_thresholds": {
                    "DEFAULT": 1.0,
                    "TREND_UP": 0.1,
                },
            }
        },
    }


def test_extract_live_threshold_surface_live_effective_falls_back_to_global_threshold():
    surface = _extract_live_threshold_surface(
        _aurora_fixture(),
        symbol="BTCUSDT",
        threshold_source_mode=THRESHOLD_SOURCE_MODE_LIVE_EFFECTIVE,
    )

    assert surface.signal_threshold_value == pytest.approx(0.162)
    assert surface.signal_threshold_source == "global_decision"
    assert surface.signal_threshold_path == "decision.signal_threshold"
    assert surface.regime_threshold_source == "asset_override"
    assert surface.regime_threshold_path == "assets.BTCUSDT.regime_thresholds"


def test_extract_live_threshold_surface_asset_override_only_rejects_disabled_override():
    with pytest.raises(
        CalibrationError,
        match=r"requires assets\.BTCUSDT\.signal_threshold\.enabled=true",
    ):
        _extract_live_threshold_surface(
            _aurora_fixture(),
            symbol="BTCUSDT",
            threshold_source_mode=THRESHOLD_SOURCE_MODE_ASSET_OVERRIDE_ONLY,
        )


def test_candidate_blockers_for_surface_reject_global_threshold_baseline():
    blockers = _candidate_blockers_for_surface(
        ThresholdSurface(
            symbol="BTCUSDT",
            signal_threshold_value=0.162,
            regime_thresholds={"DEFAULT": 1.0, "TREND_UP": 0.1},
            signal_threshold_source="global_decision",
            signal_threshold_path="decision.signal_threshold",
            regime_threshold_source="asset_override",
            regime_threshold_path="assets.BTCUSDT.regime_thresholds",
        )
    )

    assert blockers
    assert "decision.signal_threshold" in blockers[0]
