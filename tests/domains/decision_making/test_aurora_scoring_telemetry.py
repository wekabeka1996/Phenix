from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.domains.decision_making.aurora_handler import AuroraHandler


def _make_config() -> SimpleNamespace:
    return SimpleNamespace(
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                timeframe_sec=300,
                decision=SimpleNamespace(
                    signal_threshold=0.1,
                    side_bias_window_sec=420,
                    regime_threshold_multipliers={"DEFAULT": 1.0},
                    direction_strength_scoring=None,
                    signals=None,
                ),
                assets={},
            )
        )
    )


def test_scoring_telemetry_export_counts_selected_observed_and_fallbacks():
    handler = AuroraHandler(config=_make_config(), emit_fn=MagicMock())

    handler._record_scoring_selection("ETHUSDT", "quadratic_v1")
    handler._record_quadratic_fallback("ETHUSDT")
    handler._record_scoring_observed("ETHUSDT", "aurora_v1")
    handler._record_fallback_also_failed("ETHUSDT")

    telemetry = handler.get_scoring_telemetry()

    assert telemetry["quadratic_engine_selected_count"] == 1
    assert telemetry["quadratic_fallback_count"] == 1
    assert telemetry["fallback_also_failed_count"] == 1
    assert telemetry["engine_names_observed"] == ["aurora_v1"]
    assert telemetry["selected_engine_counts"]["quadratic_v1"] == 1
    assert telemetry["observed_engine_counts"]["aurora_v1"] == 1
    assert telemetry["per_symbol"]["ETHUSDT"]["quadratic_fallback_count"] == 1
