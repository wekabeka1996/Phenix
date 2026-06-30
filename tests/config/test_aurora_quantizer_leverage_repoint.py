"""Focused regression tests for LEV-REPOINT-QUANTIZER-2026-05-09.

Proves:
1. Aurora quantizer reads leverage from instruments.execution.target_leverage (SSOT)
2. BTCUSDT margin_required uses instruments leverage (25), not aurora leverage (35)
3. DOGEUSDT margin_required uses instruments leverage (10), not aurora leverage (20)
4. ETHUSDT is consistent (both surfaces agree at 20)
5. qty and notional are leverage-independent (unchanged by this repoint)
6. Missing instruments.execution.target_leverage is fail-closed (raises, caught as QUANTIZER_ERROR)
"""
from __future__ import annotations
from pathlib import Path
from apps.reference.shared.decision_primitives.instrument_quantizer import (
    InstrumentSpec,
    QuantizedPosition,
    quantize_exposure,
)

import decimal
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STEP = Decimal("0.001")
_MIN_QTY = Decimal("0.001")
_MIN_NOTIONAL = Decimal("5.0")
_TICK = Decimal("0.01")

_SPEC = InstrumentSpec(
    step_size=_STEP,
    min_qty=_MIN_QTY,
    min_notional=_MIN_NOTIONAL,
    tick_size=_TICK,
)

_PRICE = Decimal("50000.0")
_EXPOSURE = 0.8
_MAX_NOTIONAL = Decimal("1000000")

# fee_buffer default = 0.001
# notional = 0.8 * 1_000_000 * (1 - 0.001) = 799_200
# qty = floor_to_step(799_200 / 50_000, 0.001) = 15.984
# actual_notional = 15.984 * 50_000 = 799_200
_EXPECTED_QTY = Decimal("15.984")
_EXPECTED_NOTIONAL = Decimal("799200")


def _quantize(leverage: int) -> QuantizedPosition:
    return quantize_exposure(
        exposure=_EXPOSURE,
        price=_PRICE,
        max_notional=_MAX_NOTIONAL,
        leverage=leverage,
        spec=_SPEC,
        min_notional_policy="floor",
    )


def _make_instrument_mock(target_leverage: int) -> MagicMock:
    """Create an instruments precision mock with explicit execution.target_leverage."""
    m = MagicMock(
        step_size="0.001",
        min_qty="0.001",
        min_notional="5.0",
        tick_size="0.01",
    )
    m.execution.target_leverage = target_leverage
    return m


def _emit_signal_and_capture(handler, symbol: str, result: "ScoringResult") -> dict:
    """Call _emit_signal and return the emitted payload."""
    captured: list[dict] = []

    def _capture(evt, payload):
        if evt == "EVT:STRATEGY_SIGNAL_PRODUCED":
            captured.append(payload)

    handler.emit_fn = _capture
    features = {"price": str(_PRICE)}
    handler._emit_signal(symbol=symbol, result=result,
                         features=features, source_event={})
    return captured[0] if captured else {}


# ---------------------------------------------------------------------------
# Section 1: Quantizer unit tests (prove leverage drives margin_required only)
# ---------------------------------------------------------------------------

class TestQuantizerLeverageSemantic:
    """Direct quantizer tests proving leverage affects only margin_required, not qty/notional."""

    def test_btcusdt_instruments_leverage_25_margin(self):
        """Instruments BTCUSDT leverage=25 → margin_required = notional / 25."""
        pos = _quantize(25)
        assert pos.qty == _EXPECTED_QTY
        assert pos.notional == _EXPECTED_NOTIONAL
        assert pos.margin_required == _EXPECTED_NOTIONAL / Decimal("25")
        assert pos.margin_required == Decimal("31968")

    def test_btcusdt_aurora_leverage_35_would_give_different_margin(self):
        """Aurora BTCUSDT leverage=35 would give a different (lower) margin_required."""
        pos_35 = _quantize(35)
        pos_25 = _quantize(25)
        # qty and notional are identical — leverage-independent
        assert pos_35.qty == pos_25.qty
        assert pos_35.notional == pos_25.notional
        # margin_required diverges: 35 gives underestimate vs 25
        assert pos_35.margin_required < pos_25.margin_required
        assert pos_35.margin_required == _EXPECTED_NOTIONAL / Decimal("35")

    def test_dogeusdt_instruments_leverage_10_margin(self):
        """Instruments DOGEUSDT leverage=10 → margin_required = notional / 10."""
        pos = _quantize(10)
        assert pos.qty == _EXPECTED_QTY
        assert pos.notional == _EXPECTED_NOTIONAL
        assert pos.margin_required == _EXPECTED_NOTIONAL / Decimal("10")
        assert pos.margin_required == Decimal("79920")

    def test_dogeusdt_aurora_leverage_20_would_give_different_margin(self):
        """Aurora DOGEUSDT leverage=20 would give a different (lower) margin_required."""
        pos_20 = _quantize(20)
        pos_10 = _quantize(10)
        assert pos_20.qty == pos_10.qty
        assert pos_20.notional == pos_10.notional
        assert pos_20.margin_required < pos_10.margin_required

    def test_ethusdt_leverage_20_same_on_both_surfaces(self):
        """ETHUSDT leverage=20 is consistent on both aurora and instruments surfaces."""
        pos = _quantize(20)
        assert pos.margin_required == _EXPECTED_NOTIONAL / Decimal("20")
        assert pos.margin_required == Decimal("39960")

    def test_qty_leverage_independent(self):
        """qty is identical across leverage values — proving leverage isolation."""
        for lev in (10, 20, 25, 35):
            assert _quantize(
                lev).qty == _EXPECTED_QTY, f"qty changed at leverage={lev}"

    def test_notional_leverage_independent(self):
        """notional is identical across leverage values."""
        for lev in (10, 20, 25, 35):
            assert _quantize(lev).notional == _EXPECTED_NOTIONAL, (
                f"notional changed at leverage={lev}"
            )


# ---------------------------------------------------------------------------
# Section 2: Handler wiring tests (prove decision.py reads instruments SSOT)
# ---------------------------------------------------------------------------


_CONFIG_DIR = Path("config/aurora")


def _load_handler():
    """Create an AuroraHandler from the real Aurora config."""
    from apps.reference.config_loader import ConfigLoader
    from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler

    cfg = ConfigLoader(_CONFIG_DIR).load_config()
    return AuroraHandler(
        config=cfg,
        emit_fn=MagicMock(),
        wall_time_fn=lambda: 1700000000.0,
    )


def _make_scoring_result() -> "ScoringResult":
    from apps.reference.domains.strategies.runtimes.aurora.handler import ScoringResult
    return ScoringResult(
        score=Decimal(str(_EXPOSURE)),
        thr_buy=Decimal("0.5"),
        thr_sell=Decimal("-0.5"),
        sizing_score=Decimal(str(_EXPOSURE)),
        regime="TREND_UP",
        psi_vector={"trend": _EXPOSURE},
        side="BUY",
        why_chain=["test"],
        shield_multiplier=Decimal("1.0"),
    )


class _InstrumentsProxy:
    """Proxy that forwards all config attribute access except instruments."""

    def __init__(self, real_cfg, instruments_override: dict):
        self._real = real_cfg
        self.instruments = instruments_override

    def __getattr__(self, name: str):
        return getattr(self._real, name)


class TestDecisionPyLeverageRepoint:
    """Prove decision.py quantizer reads instruments.execution.target_leverage (not aurora)."""

    def test_btcusdt_uses_instruments_leverage_25_not_aurora_35(self):
        """BTCUSDT: instruments=25, aurora=35. margin_required must reflect 25."""
        handler = _load_handler()
        result = _make_scoring_result()

        # Real config: instruments BTCUSDT target_leverage=25, aurora.leverage.target=35
        assert handler.config.instruments["BTCUSDT"].execution.target_leverage == 25

        emitted: list[tuple] = []
        handler.emit_fn = lambda evt, p: emitted.append((evt, p))

        with patch.object(handler, "_get_instrument_config") as mock_get:
            instr_cfg = MagicMock()
            instr_cfg.leverage.target = 35  # aurora stale copy — must NOT be used
            instr_cfg.leverage.max_notional_value = _MAX_NOTIONAL
            instr_cfg.volatility_entry_logic = None
            mock_get.return_value = instr_cfg

            handler._emit_signal(
                symbol="BTCUSDT",
                result=result,
                features={"price": str(_PRICE)},
                source_event={},
            )

        signal_payloads = [p for evt, p in emitted if evt ==
                           "EVT:STRATEGY_SIGNAL_PRODUCED"]
        assert signal_payloads, "EVT:STRATEGY_SIGNAL_PRODUCED was not emitted"

        q = signal_payloads[0]["quantization"]
        margin = Decimal(q["margin_required"])
        expected_at_25 = _EXPECTED_NOTIONAL / Decimal("25")
        wrong_at_35 = _EXPECTED_NOTIONAL / Decimal("35")

        assert margin == expected_at_25, (
            f"margin_required={margin} — expected {expected_at_25} (instruments=25), "
            f"got wrong value suggesting aurora leverage=35 ({wrong_at_35:.4f})"
        )

    def test_dogeusdt_uses_instruments_leverage_10_not_aurora_20(self):
        """DOGEUSDT: instruments=10, aurora=20. margin_required must reflect 10."""
        handler = _load_handler()
        result = _make_scoring_result()

        assert handler.config.instruments["DOGEUSDT"].execution.target_leverage == 10

        emitted: list[tuple] = []
        handler.emit_fn = lambda evt, p: emitted.append((evt, p))

        with patch.object(handler, "_get_instrument_config") as mock_get:
            instr_cfg = MagicMock()
            instr_cfg.leverage.target = 20  # aurora stale copy — must NOT be used
            instr_cfg.leverage.max_notional_value = _MAX_NOTIONAL
            instr_cfg.volatility_entry_logic = None
            mock_get.return_value = instr_cfg

            handler._emit_signal(
                symbol="DOGEUSDT",
                result=result,
                features={"price": str(_PRICE)},
                source_event={},
            )

        signal_payloads = [p for evt, p in emitted if evt ==
                           "EVT:STRATEGY_SIGNAL_PRODUCED"]
        assert signal_payloads, "EVT:STRATEGY_SIGNAL_PRODUCED was not emitted"

        q = signal_payloads[0]["quantization"]
        margin = Decimal(q["margin_required"])
        # DOGEUSDT step_size=1: qty floored to 15, actual_notional = 15 * 50000 = 750000
        # At instruments leverage=10: margin_required = 750000 / 10 = 75000
        # At aurora leverage=20 (stale): would give 750000 / 20 = 37500
        expected_at_10 = Decimal("750000") / Decimal("10")
        wrong_at_20 = Decimal("750000") / Decimal("20")

        assert margin == expected_at_10, (
            f"margin_required={margin} — expected {expected_at_10} (instruments=10), "
            f"got wrong value suggesting aurora leverage=20 ({wrong_at_20})"
        )

    def test_ethusdt_consistent_leverage_20_both_surfaces(self):
        """ETHUSDT: both surfaces agree at 20. margin_required is the same regardless of source."""
        handler = _load_handler()
        result = _make_scoring_result()

        assert handler.config.instruments["ETHUSDT"].execution.target_leverage == 20

        emitted: list[tuple] = []
        handler.emit_fn = lambda evt, p: emitted.append((evt, p))

        with patch.object(handler, "_get_instrument_config") as mock_get:
            instr_cfg = MagicMock()
            instr_cfg.leverage.target = 20
            instr_cfg.leverage.max_notional_value = _MAX_NOTIONAL
            instr_cfg.volatility_entry_logic = None
            mock_get.return_value = instr_cfg

            handler._emit_signal(
                symbol="ETHUSDT",
                result=result,
                features={"price": str(_PRICE)},
                source_event={},
            )

        signal_payloads = [p for evt, p in emitted if evt ==
                           "EVT:STRATEGY_SIGNAL_PRODUCED"]
        assert signal_payloads, "EVT:STRATEGY_SIGNAL_PRODUCED was not emitted"

        q = signal_payloads[0]["quantization"]
        margin = Decimal(q["margin_required"])
        assert margin == _EXPECTED_NOTIONAL / Decimal("20")

    def test_qty_notional_unchanged_after_leverage_repoint(self):
        """qty and notional are leverage-independent — repoint does not affect sizing."""
        handler = _load_handler()
        result = _make_scoring_result()

        emitted: list[tuple] = []
        handler.emit_fn = lambda evt, p: emitted.append((evt, p))

        with patch.object(handler, "_get_instrument_config") as mock_get:
            instr_cfg = MagicMock()
            instr_cfg.leverage.max_notional_value = _MAX_NOTIONAL
            instr_cfg.volatility_entry_logic = None
            mock_get.return_value = instr_cfg

            handler._emit_signal(
                symbol="BTCUSDT",
                result=result,
                features={"price": str(_PRICE)},
                source_event={},
            )

        signal_payloads = [p for evt, p in emitted if evt ==
                           "EVT:STRATEGY_SIGNAL_PRODUCED"]
        assert signal_payloads, "EVT:STRATEGY_SIGNAL_PRODUCED was not emitted"

        q = signal_payloads[0]["quantization"]
        assert q["qty"] == str(_EXPECTED_QTY), (
            f"qty={q['qty']} — expected {_EXPECTED_QTY}; leverage repoint must not affect qty"
        )

    def test_missing_execution_target_leverage_is_fail_closed(self):
        """instruments.execution absent → fail-closed: QUANTIZER_ERROR emitted, signal blocked."""
        handler = _load_handler()
        result = _make_scoring_result()

        # Inject a bad instruments precision object (execution=None)
        bad_mock = MagicMock(step_size="0.001", min_qty="0.001",
                             min_notional="5.0", tick_size="0.01")
        bad_mock.execution = None
        proxy_cfg = _InstrumentsProxy(handler.config, {"BTCUSDT": bad_mock})
        handler.config = proxy_cfg

        emitted: list[tuple] = []
        handler.emit_fn = lambda evt, p: emitted.append((evt, p))

        with patch.object(handler, "_get_instrument_config") as mock_get:
            instr_cfg = MagicMock()
            instr_cfg.leverage.max_notional_value = _MAX_NOTIONAL
            instr_cfg.volatility_entry_logic = None
            mock_get.return_value = instr_cfg

            handler._emit_signal(
                symbol="BTCUSDT",
                result=result,
                features={"price": str(_PRICE)},
                source_event={},
            )

        evts = {evt for evt, _ in emitted}
        assert "EVT:STRATEGY_SIGNAL_PRODUCED" not in evts, (
            "Signal emitted despite missing instruments.execution — fail-closed gate broken"
        )
        blocked = [p for evt, p in emitted if evt ==
                   "EVT:STRATEGY_DECISION_BLOCKED"]
        assert blocked, "QUANTIZER_ERROR block event not emitted"
        assert blocked[0]["reason_code"] == "QUANTIZER_ERROR"
