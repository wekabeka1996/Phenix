from __future__ import annotations

import types
from decimal import Decimal
from unittest.mock import MagicMock

from apps.reference.domains.decision_making.md_amr_handler import MDAMRHandler
from apps.reference.domains.feature_engineering.md_amr_strategy import MDAMRSignal


def _make_handler(symbol: str = "XRPUSDT") -> MDAMRHandler:
    h = object.__new__(MDAMRHandler)
    h.logger = MagicMock()
    h.mlog = MagicMock()
    h.fsm = MagicMock()
    h.config = MagicMock()
    h._enabled = True
    h._enabled_symbols = {symbol}
    h._strategies = {}
    h._last_features = {}
    h._position_qty = {symbol: Decimal("0")}
    h._bars_held = {symbol: 0}
    h._deferred = {}
    h._macro_block_until_ms = {}
    h._regime = {}
    h._rest_hydrated = False
    h._rest_last_bar_ts_ms = {}
    h._last_ingested_bar_ts_ms = {symbol: 0}
    h._pending_close = {}
    h._last_close_ts = {}
    h._gtx_retries = {}
    h._entries_at_ts = {}
    h.mandatory_warmup_until = 0
    return h


def _asset_cfg() -> types.SimpleNamespace:
    tpsl_cfg = types.SimpleNamespace(
        enabled=True,
        mode="pct_mult",
        sl_mult={"DEFAULT": 1.0, "MEAN_REVERSION": 0.88},
        tp_mult={"DEFAULT": 1.0, "MEAN_REVERSION": 0.78},
        min_sl_pct=0.0025,
        max_sl_pct=0.030,
        min_tp_rr=0.35,
        max_tp_rr=4.0,
        min_dist_bps=15,
    )
    exit_cfg = types.SimpleNamespace(
        sl_pct=0.013, tp_rr=0.60, regime_tpsl=tpsl_cfg)
    return types.SimpleNamespace(
        cooldown_sec=60,
        allowed_regimes=["MEAN_REVERSION"],
        exit=exit_cfg,
    )


def _entry_signal(side: str = "BUY") -> MDAMRSignal:
    return MDAMRSignal(
        intent_kind="ENTRY",
        side=side,
        reason_code="MD_AMR_ENTRY",
        signal_score=0.8,
        conf_ratio=0.9,
        scaleout_fraction=None,
        price_ref=Decimal("1.25"),
        channel_state={"upper": 1.30, "lower": 1.20, "mid": 1.25},
        atr=0.02,
        dir_score=0.5,
        trace={},
    )


def _event(symbol: str = "XRPUSDT") -> MagicMock:
    event = MagicMock()
    event.pld = {
        "symbol": symbol,
        "tf_sec": 900,
        "bar": {
            "open": "1.24",
            "high": "1.26",
            "low": "1.23",
            "close": "1.25",
            "volume": "1000",
            "start_ts_ms": 1_700_000_000_000 - 900_000,
            "end_ts_ms": 1_700_000_000_000,
        },
        "bar_close_ts": 1_700_000_000_000,
        "features": {},
        "warmup": {"full_ready": True},
    }
    return event


def test_md_amr_entry_allowed_in_mean_reversion() -> None:
    symbol = "XRPUSDT"
    h = _make_handler(symbol)
    mock_strategy = MagicMock()
    mock_strategy.on_bar.return_value = {
        "status": "SIGNAL",
        "signal": _entry_signal(),
    }
    h._strategies[symbol] = mock_strategy
    h._cfg = types.SimpleNamespace(
        timeframe_sec=900,
        llm_gate=types.SimpleNamespace(enabled=False),
        concentration_guard=types.SimpleNamespace(enabled=False),
        assets={symbol: _asset_cfg()},
        defer_ttl_sec=60,
    )
    h._regime[symbol] = "MEAN_REVERSION"

    h._on_process_strategy(_event(symbol))

    event_names = [call.args[0] for call in h.fsm.emit.call_args_list]
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" in event_names
    assert "EVT:TRADE_INTENT_REJECTED" not in event_names


def test_md_amr_entry_blocked_in_uncertain() -> None:
    symbol = "XRPUSDT"
    h = _make_handler(symbol)
    mock_strategy = MagicMock()
    mock_strategy.on_bar.return_value = {
        "status": "SIGNAL",
        "signal": _entry_signal(),
    }
    h._strategies[symbol] = mock_strategy
    h._cfg = types.SimpleNamespace(
        timeframe_sec=900,
        llm_gate=types.SimpleNamespace(enabled=False),
        concentration_guard=types.SimpleNamespace(enabled=False),
        assets={symbol: _asset_cfg()},
        defer_ttl_sec=60,
    )
    h._regime[symbol] = "UNCERTAIN"

    h._on_process_strategy(_event(symbol))

    event_names = [call.args[0] for call in h.fsm.emit.call_args_list]
    assert "EVT:TRADE_INTENT_REJECTED" in event_names
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" not in event_names


def test_md_amr_entry_blocked_when_regime_not_allowlisted() -> None:
    symbol = "BNBUSDT"
    h = _make_handler(symbol)
    mock_strategy = MagicMock()
    mock_strategy.on_bar.return_value = {
        "status": "SIGNAL",
        "signal": _entry_signal(),
    }
    h._strategies[symbol] = mock_strategy
    h._cfg = types.SimpleNamespace(
        timeframe_sec=900,
        llm_gate=types.SimpleNamespace(enabled=False),
        concentration_guard=types.SimpleNamespace(enabled=False),
        assets={symbol: _asset_cfg()},
        defer_ttl_sec=60,
    )
    h._regime[symbol] = "LOW_VOLATILITY"

    h._on_process_strategy(_event(symbol))

    event_names = [call.args[0] for call in h.fsm.emit.call_args_list]
    assert "EVT:TRADE_INTENT_REJECTED" in event_names
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" not in event_names


def test_md_amr_entry_rejected_during_mandatory_live_warmup() -> None:
    symbol = "XRPUSDT"
    h = _make_handler(symbol)
    mock_strategy = MagicMock()
    mock_strategy.on_bar.return_value = {
        "status": "SIGNAL",
        "signal": _entry_signal(),
    }
    h._strategies[symbol] = mock_strategy
    h._cfg = types.SimpleNamespace(
        timeframe_sec=900,
        llm_gate=types.SimpleNamespace(enabled=False),
        concentration_guard=types.SimpleNamespace(enabled=False),
        assets={symbol: _asset_cfg()},
        defer_ttl_sec=60,
    )
    h._regime[symbol] = "MEAN_REVERSION"
    h.mandatory_warmup_until = 9_999_999_999_999_999

    h._on_process_strategy(_event(symbol))

    event_names = [call.args[0] for call in h.fsm.emit.call_args_list]
    assert "EVT:TRADE_INTENT_REJECTED" in event_names
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" not in event_names
