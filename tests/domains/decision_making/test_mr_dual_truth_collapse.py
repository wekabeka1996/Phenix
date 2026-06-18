from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MRSignal,
    MRSignalType,
)
import apps.reference.domains.strategies.runtimes.mean_reversion.handler as mr_handler_module
from apps.reference.domains.strategies.runtimes.mean_reversion.handler import (
    MeanReversionHandler,
)


class _FSMStub:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict, str | None]] = []

    def emit(self, event_name: str, payload=None, *_args, **kwargs) -> None:
        self.emitted.append((event_name, payload or {}, kwargs.get("why")))


def _signal() -> MRSignal:
    return MRSignal(
        signal_type=MRSignalType.LONG,
        symbol="BTCUSDT",
        price=Decimal("100"),
        atr=Decimal("1"),
        flat_regime=SimpleNamespace(name="FLAT_LOW"),
        entry_price=Decimal("100"),
        stop_price=Decimal("99"),
        target_price=Decimal("101"),
        confidence=Decimal("0.8"),
        timestamp_ms=1_700_000_000_000,
        why="enter:buy",
        bar=SimpleNamespace(end_ts_ms=1_700_000_000_000),
    )


def _strategy(signal: MRSignal) -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            allowed_regimes=["FLAT_LOW"],
            entry_threshold_long=None,
            entry_threshold_short=None,
        ),
        on_bar=lambda *_args, **_kwargs: signal,
        set_regime=lambda *_args, **_kwargs: None,
        get_regime=lambda *_args, **_kwargs: "FLAT_LOW",
    )


def _handler() -> tuple[MeanReversionHandler, _FSMStub, list[tuple[tuple, dict]]]:
    handler = object.__new__(MeanReversionHandler)
    fsm = _FSMStub()
    emitted_signals: list[tuple[tuple, dict]] = []

    handler.fsm = fsm
    handler.logger = logging.getLogger("tests.mean_reversion.dual_truth")
    handler.mlog = logging.getLogger("tests.mean_reversion.dual_truth")
    handler._enabled = True
    handler.timeframe_sec = 300
    handler._enabled_symbols = {"BTCUSDT"}
    handler._strategies = {"BTCUSDT": _strategy(_signal())}
    handler._stats = {
        "bars_received": 0,
        "bars_rejected_missing_tf": 0,
        "bars_rejected_wrong_tf": 0,
        "bars_rejected_missing_bar": 0,
        "bars_completed": 0,
        "neutral_bars": 0,
    }
    handler._last_cmd_features = {}
    handler._last_cmd_price_motion = {}
    handler._liquidity_kappa_map = {"BTCUSDT": Decimal("0.12")}
    handler._tfi_ema = {"BTCUSDT": -0.41}
    handler._per_symbol_regime = {}
    handler._regime_confidence = {}
    handler._regime_event_ts_ms = {}
    handler._regime_ts_ms = {}
    handler._last_block_reason = {}
    handler._last_block_ts_ms = {}
    handler._apply_directional_bias = lambda *_args, **_kwargs: None
    handler._log_bar = lambda *_args, **_kwargs: None
    handler._emit_signal = lambda *args, **kwargs: emitted_signals.append(
        (args, kwargs)
    )

    return handler, fsm, emitted_signals


def _cmd_payload() -> dict:
    return {
        "rid": "rid-mr-dual-truth",
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "bar_close_ts": 1_700_000_000_000,
        "structural_regime": "LOW_VOLATILITY",
        "regime": {
            "regime": "TREND_DOWN",
            "confidence": 0.81,
            "ts_ms": 1_700_000_000_000,
        },
        "bar": {
            "open": "100.0",
            "high": "101.0",
            "low": "99.0",
            "close": "100.5",
            "volume": "10.0",
            "start_ts_ms": 1_699_999_700_000,
            "trade_count": 1,
        },
    }


def test_mr_process_strategy_uses_only_canonical_structural_regime() -> None:
    handler, _, _ = _handler()
    observed: list[str] = []
    handler._strategies["BTCUSDT"].set_regime = (
        lambda _symbol, regime: observed.append(regime)
    )
    handler._strategies["BTCUSDT"].on_bar = lambda *_args, **_kwargs: None

    with patch.object(
        mr_handler_module,
        "extract_canonical_bar_identity",
        return_value=None,
    ), patch.object(
        mr_handler_module,
        "extract_canonical_replay_identity",
        return_value=None,
    ), patch.object(
        mr_handler_module,
        "extract_gap_status",
        return_value=None,
    ):
        handler._on_process_strategy(SimpleNamespace(pld=_cmd_payload()))

    assert observed == ["LOW_VOLATILITY"]


def _assert_single_blocked_truth(
    fsm: _FSMStub,
    blocked_writer,
    *,
    reason_code: str,
) -> None:
    blocked_writer.assert_called_once()
    assert blocked_writer.call_args.kwargs["reason_code"] == reason_code
    assert fsm.emitted == [
        (
            "EVT:STRATEGY_DECISION_BLOCKED",
            {"reason_code": reason_code},
            f"mr_blocked:{reason_code}",
        )
    ]


def test_mr_microstructure_block_keeps_only_blocked_truth() -> None:
    handler, fsm, emitted_signals = _handler()
    handler._check_microstructure_veto = lambda *_args, **_kwargs: (
        False,
        "MICROSTRUCTURE_VETO",
    )
    handler._check_liquidity_gate = lambda *_args, **_kwargs: True

    with patch.object(
        mr_handler_module,
        "extract_canonical_bar_identity",
        return_value=None,
    ), patch.object(
        mr_handler_module,
        "extract_canonical_replay_identity",
        return_value=None,
    ), patch.object(
        mr_handler_module,
        "extract_gap_status",
        return_value=None,
    ), patch.object(
        mr_handler_module,
        "get_clock",
        return_value=SimpleNamespace(now_ms=lambda: 1_700_000_000_000),
    ), patch.object(
        mr_handler_module,
        "write_strategy_decision_blocked",
        return_value={"reason_code": "MICROSTRUCTURE_VETO"},
    ) as blocked_writer, patch.object(
        mr_handler_module,
        "write_trade_intent_rejected",
    ) as reject_writer:
        handler._on_process_strategy(_cmd_payload())

    reject_writer.assert_not_called()
    _assert_single_blocked_truth(
        fsm,
        blocked_writer,
        reason_code="MICROSTRUCTURE_VETO",
    )
    assert emitted_signals == []


def test_mr_liquidity_block_keeps_only_blocked_truth() -> None:
    handler, fsm, emitted_signals = _handler()
    handler._check_microstructure_veto = lambda *_args, **_kwargs: (
        True,
        "",
    )
    handler._check_liquidity_gate = lambda *_args, **_kwargs: False

    with patch.object(
        mr_handler_module,
        "extract_canonical_bar_identity",
        return_value=None,
    ), patch.object(
        mr_handler_module,
        "extract_canonical_replay_identity",
        return_value=None,
    ), patch.object(
        mr_handler_module,
        "extract_gap_status",
        return_value=None,
    ), patch.object(
        mr_handler_module,
        "get_clock",
        return_value=SimpleNamespace(now_ms=lambda: 1_700_000_000_000),
    ), patch.object(
        mr_handler_module,
        "write_strategy_decision_blocked",
        return_value={"reason_code": "LIQUIDITY_GATE"},
    ) as blocked_writer, patch.object(
        mr_handler_module,
        "write_trade_intent_rejected",
    ) as reject_writer:
        handler._on_process_strategy(_cmd_payload())

    reject_writer.assert_not_called()
    _assert_single_blocked_truth(
        fsm,
        blocked_writer,
        reason_code="LIQUIDITY_GATE",
    )
    assert emitted_signals == []
