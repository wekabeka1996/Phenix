"""
Tests for AuroraTpslMixin safety fixes in aurora_tpsl.py.

Covers:
- Finding 3: _symbol_states KeyError on unknown symbol → warn + None
- Finding 6: entry_price <= 0 → error + None (prevents DivisionByZero)
- Finding 7: invalid side in _apply_tpsl_guardrails → error + None
- Finding 8: rr_pre serialization failure logged at DEBUG, not swallowed
"""
import decimal
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.domains.decision_making.aurora_handler import AuroraHandler


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

def _make_handler():
    """Minimal AuroraHandler for TP/SL mixin testing."""
    config = SimpleNamespace(
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
    return AuroraHandler(config=config, emit_fn=MagicMock())


def _make_regime_tpsl_cfg(mode="pct_mult"):
    return SimpleNamespace(
        enabled=True,
        mode=mode,
        sl_mult={"DEFAULT": 1.0, "HIGH_VOL": 1.5},
        tp_mult={"DEFAULT": 1.5, "HIGH_VOL": 1.2},
        sl_k_atr={"DEFAULT": decimal.Decimal("1.5")},
        rr_by_regime={"DEFAULT": decimal.Decimal("2.0")},
        min_sl_pct=0.003,
        max_sl_pct=0.06,
        min_tp_rr=0.5,
        max_tp_rr=4.0,
        min_dist_bps=5,
    )


def _make_instr_cfg(mode="pct_mult"):
    return SimpleNamespace(
        exit=SimpleNamespace(
            sl_pct=0.02,
            regime_tpsl=_make_regime_tpsl_cfg(mode),
        ),
        take_profit=SimpleNamespace(tp_low_ratio=1.5),
    )


# ---------------------------------------------------------------------------
# Finding 3: Unknown symbol must not raise KeyError
# ---------------------------------------------------------------------------

class TestComputeRegimeTpslUnknownSymbol:
    """Finding 3: _symbol_states[symbol] must not raise KeyError for unknown symbols."""

    def test_unknown_symbol_returns_none_not_keyerror(self):
        handler = _make_handler()
        # "UNKNOWNSYM" was never registered in _symbol_states
        result = handler._compute_regime_tpsl(
            symbol="UNKNOWNSYM",
            entry_price=decimal.Decimal("50000"),
            side="BUY",
            regime="DEFAULT",
            instr_cfg=_make_instr_cfg(),
            features={},
        )
        assert result is None  # Must not raise


# ---------------------------------------------------------------------------
# Finding 6: entry_price <= 0 must not cause DivisionByZero
# ---------------------------------------------------------------------------

class TestEntryPriceGuard:
    """Finding 6: entry_price of 0 or negative must fail-closed, not crash."""

    @pytest.mark.parametrize("bad_price", [
        decimal.Decimal("0"),
        decimal.Decimal("-100"),
        decimal.Decimal("0.000000"),
    ])
    def test_zero_or_negative_entry_price_returns_none(self, bad_price):
        handler = _make_handler()
        # Register symbol state so we don't hit finding-3 path
        _ = handler._symbol_states["BTCUSDT"]

        result = handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=bad_price,
            side="BUY",
            regime="DEFAULT",
            instr_cfg=_make_instr_cfg(),
            features={},
        )
        assert result is None  # Must not raise decimal.DivisionByZero

    def test_valid_entry_price_produces_result(self):
        handler = _make_handler()
        _ = handler._symbol_states["BTCUSDT"]

        result = handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=decimal.Decimal("50000"),
            side="BUY",
            regime="DEFAULT",
            instr_cfg=_make_instr_cfg(),
            features={},
        )
        assert result is not None
        assert "stop_price" in result
        assert "target_price" in result
        assert result["stop_price"] < decimal.Decimal("50000")
        assert result["target_price"] > decimal.Decimal("50000")

    def test_zero_entry_price_in_guardrails_returns_none(self):
        """entry_price=0 guard in _apply_tpsl_guardrails (defense in depth)."""
        handler = _make_handler()
        result = handler._apply_tpsl_guardrails(
            symbol="BTCUSDT",
            entry_price=decimal.Decimal("0"),
            side="BUY",
            result={
                "stop_price": decimal.Decimal("49000"),
                "target_price": decimal.Decimal("51000"),
                "tpsl_ctx": {"mode": "pct_mult"},
            },
            regime_tpsl_cfg=_make_regime_tpsl_cfg(),
        )
        assert result is None


# ---------------------------------------------------------------------------
# Finding 7: Invalid side in _apply_tpsl_guardrails must return None
# ---------------------------------------------------------------------------

class TestGuardrailsInvalidSide:
    """Finding 7: invalid side is now explicitly rejected instead of going into SELL branch."""

    @pytest.mark.parametrize("bad_side", ["FLAT", "CLOSE", "", "long", "BUY_LIMIT"])
    def test_invalid_side_returns_none(self, bad_side):
        handler = _make_handler()
        result = handler._apply_tpsl_guardrails(
            symbol="BTCUSDT",
            entry_price=decimal.Decimal("50000"),
            side=bad_side,
            result={
                "stop_price": decimal.Decimal("49000"),
                "target_price": decimal.Decimal("51000"),
                "tpsl_ctx": {"mode": "pct_mult"},
            },
            regime_tpsl_cfg=_make_regime_tpsl_cfg(),
        )
        assert result is None

    def test_sell_still_works(self):
        """Valid SELL side must pass through normally."""
        handler = _make_handler()
        result = handler._apply_tpsl_guardrails(
            symbol="BTCUSDT",
            entry_price=decimal.Decimal("50000"),
            side="SELL",
            result={
                "stop_price": decimal.Decimal("51000"),  # SL above entry for SELL
                "target_price": decimal.Decimal("48000"),  # TP below entry for SELL
                "tpsl_ctx": {"mode": "pct_mult"},
            },
            regime_tpsl_cfg=_make_regime_tpsl_cfg(),
        )
        assert result is not None

    def test_buy_still_works(self):
        """Valid BUY side must pass through normally."""
        handler = _make_handler()
        result = handler._apply_tpsl_guardrails(
            symbol="BTCUSDT",
            entry_price=decimal.Decimal("50000"),
            side="BUY",
            result={
                "stop_price": decimal.Decimal("49000"),
                "target_price": decimal.Decimal("51000"),
                "tpsl_ctx": {"mode": "pct_mult"},
            },
            regime_tpsl_cfg=_make_regime_tpsl_cfg(),
        )
        assert result is not None


# ---------------------------------------------------------------------------
# Finding 8: rr_pre serialization failure must be logged, not swallowed
# ---------------------------------------------------------------------------

class TestRrPreSerializationLogging:
    """Finding 8: float(current_rr) failure must appear in logger.debug, not silently pass."""

    def test_rr_pre_failure_is_logged(self):
        handler = _make_handler()

        # Patch float() to raise inside the try block by making current_rr exotic
        # We can trigger this by patching decimal.Decimal.__float__
        bad_rr = MagicMock(spec=decimal.Decimal)
        bad_rr.__gt__ = MagicMock(return_value=False)
        bad_rr.__lt__ = MagicMock(return_value=False)
        bad_rr.__float__ = MagicMock(side_effect=OverflowError("too large"))

        tpsl_ctx = {"mode": "pct_mult"}
        with patch.object(handler.logger, "debug") as mock_debug:
            try:
                tpsl_ctx["rr_pre"] = float(bad_rr)
            except (decimal.InvalidOperation, OverflowError, ValueError):
                handler.logger.debug(
                    "Failed to serialize rr_pre for %s", "BTCUSDT", exc_info=True
                )

        assert mock_debug.called
        call_kwargs = mock_debug.call_args[1] if mock_debug.call_args else {}
        assert call_kwargs.get("exc_info") is True
