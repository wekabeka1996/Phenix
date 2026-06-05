from collections import deque
from decimal import Decimal
from types import SimpleNamespace

from apps.reference.domains.feature_engineering.calculation_engine import (
    FeatureCalculationEngine,
)
from apps.reference.domains.feature_engineering.feature_engineering import (
    FeatureEngineering,
)
from apps.reference.domains.feature_engineering.types import HotState


def _sanity_cfg() -> SimpleNamespace:
    return SimpleNamespace(
        feature_sanity_enabled=True,
        feature_sanity_nan_inf_behavior="neutral_and_not_ready",
        feature_sanity_bounds={},
        neutral_value=Decimal("0.5"),
    )


def test_macro_resid_none_sentinel_does_not_add_invalid_value_type_reason() -> None:
    engine = FeatureCalculationEngine(_sanity_cfg())

    sanitized, readiness, reasons = engine.sanitize_features_dict({"macro_resid": None})

    assert sanitized["macro_resid"] == "0.5"
    assert readiness["macro_resid"] is False
    assert reasons == []


def test_latest_anchor_price_pair_before_ignores_future_points() -> None:
    handler = FeatureEngineering.__new__(FeatureEngineering)
    handler.anchor_price_points = {
        "BTCUSDT": deque(
            [
                (1_000, Decimal("100")),
                (2_000, Decimal("101")),
                (3_000, Decimal("102")),
            ],
            maxlen=16,
        )
    }

    pair = handler._latest_anchor_price_pair_before("BTCUSDT", current_ts_ms=2_500)

    assert pair == (Decimal("100"), Decimal("101"))


def test_compute_macro_sync_uses_resampler_even_if_latest_anchor_ts_is_newer() -> None:
    hot = HotState()

    class StubEngine:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[str, ...], int]] = []

        def compute_macro_sync_v2(self, state, resampler, *, symbol, anchors, current_ts_ms):
            self.calls.append((symbol, tuple(anchors), int(current_ts_ms)))
            state.macro_sync_ready = True
            state.macro_sync_not_ready_reason = None
            return Decimal("0.91")

    stub_engine = StubEngine()
    handler = FeatureEngineering.__new__(FeatureEngineering)
    handler.cfg = SimpleNamespace(
        macro_sync_enabled=True,
        macro_sync_anchors=["BTCUSDT"],
        neutral_value=Decimal("0.5"),
    )
    handler._macro_sync_anchor_ts_missing = False
    handler._anchor_last_ts_ms = {"BTCUSDT": 10_500}
    handler._macro_sync_resampler = object()
    handler._engine = stub_engine
    handler._get_symbol_state = lambda symbol: SimpleNamespace(hot=hot)

    value = handler._compute_macro_sync("DOGEUSDT", current_ts_ms=10_000)

    assert value == Decimal("0.91")
    assert hot.macro_sync_ready is True
    assert hot.macro_sync_not_ready_reason is None
    assert stub_engine.calls == [("DOGEUSDT", ("BTCUSDT",), 10_000)]
