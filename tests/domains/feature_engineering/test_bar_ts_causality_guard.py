import decimal
import inspect
import re
from types import SimpleNamespace
from unittest.mock import patch


def _make_fe_for_macro_sync_tests(*, anchor_ts_ms: int):
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
    from apps.reference.domains.feature_engineering.types import HotState

    hot = HotState()

    class _Engine:
        def compute_macro_sync_v2(self, state, _resampler, *, symbol, anchors, current_ts_ms):
            state.macro_sync_ready = True
            state.macro_sync_not_ready_reason = None
            return decimal.Decimal("0.7")

    with patch.object(FeatureEngineering, "__init__", lambda self, **kw: None):
        fe = FeatureEngineering()
        fe.cfg = SimpleNamespace(
            neutral_value=decimal.Decimal("0.5"),
            macro_sync_anchors=["BTCUSDT"],
        )
        fe._macro_sync_anchor_ts_missing = False
        fe._anchor_last_ts_ms = {"BTCUSDT": int(anchor_ts_ms)}
        fe._macro_sync_resampler = object()
        fe._engine = _Engine()
        fe._get_symbol_state = lambda _symbol: SimpleNamespace(hot=hot)

    return fe, hot


def test_compute_macro_sync_uses_causality_ts_ms_when_provided():
    """BAR-TS-CAUSALITY-FIX: Bar events should not be blocked by anchor ts > bar_close ts."""
    fe, hot = _make_fe_for_macro_sync_tests(anchor_ts_ms=1_000_000_150)

    _ = fe._compute_macro_sync(
        "DOGEUSDT",
        current_ts_ms=1_000_000_000,
        causality_ts_ms=1_000_001_000,
    )

    assert hot.macro_sync_not_ready_reason != "anchor_from_future:BTCUSDT"


def test_compute_macro_sync_preserves_tick_level_causality_guard():
    """Tick-level causality guard MUST still block future anchors."""
    fe, hot = _make_fe_for_macro_sync_tests(anchor_ts_ms=200)

    _ = fe._compute_macro_sync("DOGEUSDT", current_ts_ms=100)

    assert hot.macro_sync_not_ready_reason == "anchor_from_future:BTCUSDT"


def test_macro_resid_guard_uses_causality_ts_ms_not_current_ts_ms():
    """BAR-TS-CAUSALITY-FIX: macro_resid guard should compare against causality_ts_ms."""
    from apps.reference.domains.feature_engineering import feature_engineering

    source = inspect.getsource(
        feature_engineering.FeatureEngineering._calculate_and_emit_features_for_tf
    )

    assert re.search(
        r"btc_anchor_ts\s*>\s*0\s*and\s*btc_anchor_ts\s*>\s*int\(\s*causality_ts_ms\s*\)",
        source,
    ), "Expected macro_resid causality guard to use causality_ts_ms"

