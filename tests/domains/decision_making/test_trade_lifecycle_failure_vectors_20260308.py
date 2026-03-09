from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import AuroraConfig
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.decision_making.md_amr_handler import MDAMRHandler
from apps.reference.domains.feature_engineering.md_amr_strategy import MDAMRSignal


@pytest.fixture
def production_config() -> AuroraConfig:
    config_dir = Path(__file__).parents[3] / "config" / "aurora"
    return ConfigLoader(config_dir=config_dir).load_config()


def _md_amr_handler(symbol: str = "XRPUSDT") -> MDAMRHandler:
    handler = object.__new__(MDAMRHandler)
    handler.logger = MagicMock()
    handler.mlog = MagicMock()
    handler.fsm = MagicMock()
    handler.config = MagicMock()
    handler._enabled = True
    handler._enabled_symbols = {symbol}
    handler._cfg = SimpleNamespace(
        timeframe_sec=900,
        llm_gate=SimpleNamespace(enabled=False),
        concentration_guard=SimpleNamespace(enabled=False),
        assets={symbol: _md_amr_asset_cfg()},
        defer_ttl_sec=60,
    )
    handler._strategies = {}
    handler._last_features = {}
    handler._position_qty = {symbol: Decimal("1")}
    handler._bars_held = {symbol: 4}
    handler._deferred = {}
    handler._macro_block_until_ms = {}
    handler._regime = {symbol: "MEAN_REVERSION"}
    handler._rest_hydrated = False
    handler._rest_last_bar_ts_ms = {}
    handler._last_ingested_bar_ts_ms = {symbol: 0}
    handler._pending_close = {}
    handler._last_close_ts = {}
    handler._gtx_retries = {}
    handler._entries_at_ts = {}
    handler.mandatory_warmup_until = 0
    return handler


def _md_amr_asset_cfg() -> SimpleNamespace:
    tpsl_cfg = SimpleNamespace(
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
    exit_cfg = SimpleNamespace(sl_pct=0.013, tp_rr=0.60, regime_tpsl=tpsl_cfg)
    return SimpleNamespace(
        enabled=True,
        cooldown_sec=60,
        allowed_regimes=["MEAN_REVERSION"],
        exit=exit_cfg,
    )


def _md_amr_full_close_signal() -> MDAMRSignal:
    return MDAMRSignal(
        intent_kind="FULL_CLOSE",
        side="SELL",
        reason_code="VECTOR3_HOT_RELOAD_CLOSE",
        signal_score=-0.9,
        conf_ratio=0.95,
        scaleout_fraction=None,
        price_ref=Decimal("1.25"),
        channel_state={"upper": 1.30, "lower": 1.20, "mid": 1.25},
        atr=0.02,
        dir_score=-0.5,
        trace={"vector": 3},
    )


def _md_amr_event(symbol: str = "XRPUSDT") -> MagicMock:
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


def _emitted_event_names(mock_emit: MagicMock) -> list[str]:
    return [call.args[0] for call in mock_emit.call_args_list if call.args]


@pytest.mark.xfail(
    reason="Known vulnerability: strict regime allowlist blocks Aurora exit/flip after entry regime drift.",
    strict=False,
)
def test_vector1_regime_drift_must_not_block_exit_for_open_aurora_position(
    production_config: AuroraConfig,
) -> None:
    symbol = "SOLUSDT"
    emit_mock = MagicMock()

    asset_cfg = production_config.strategies.aurora.assets[symbol]
    asset_cfg.allowed_regimes = ["HIGH_VOLATILITY"]

    handler = AuroraHandler(config=production_config, emit_fn=emit_mock)
    state = handler._symbol_states[symbol]
    state.regime = "MEAN_REVERSION"
    state.regime_effective = "MEAN_REVERSION"
    state.warmup_full_ready = True
    state.position_side = "buy"
    state.last_regime_heartbeat_ms = int(time.time() * 1000)

    handler.scoring_kernel_cls = MagicMock()
    handler.scoring_kernel_cls.compute.return_value = SimpleNamespace(
        side="sell",
        score=Decimal("-0.9"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=["vector1", "regime_drift"],
        psi_vector={},
        regime="MEAN_REVERSION",
        deferred=False,
        defer_reason=None,
    )

    handler.on_process_strategy(
        {
            "symbol": symbol,
            "tf_sec": 300,
            "bar_close_ts": int(time.time()),
            "bar": {
                "open": 79.7,
                "high": 79.9,
                "low": 79.3,
                "close": 79.64,
                "volume": 100,
            },
            "features": {
                "price": "79.64017857142857",
                "atr": "0.55",
                "volatility": 0.2,
                "liquidity_kappa": "0.5",
                "liquidity": {"depth_usd": 150000},
            },
            "warmup": {"full_ready": True, "ready": {"liquidity_kappa": True}},
        }
    )

    emitted = _emitted_event_names(emit_mock)
    blocked_payloads = [
        call.args[1]
        for call in emit_mock.call_args_list
        if len(call.args) > 1 and call.args[0] == "EVT:STRATEGY_DECISION_BLOCKED"
    ]

    assert "EVT:STRATEGY_SIGNAL_PRODUCED" in emitted
    assert not any(
        isinstance(payload, dict) and payload.get(
            "reason_code") == "REGIME_NOT_ALLOWLISTED"
        for payload in blocked_payloads
    )


@pytest.mark.xfail(
    reason="Known vulnerability: stale pending_flip keeps symbol busy even after flat ACCOUNT_UPDATE state.",
    strict=False,
)
def test_vector2_flat_portfolio_must_self_heal_stale_pending_flip_lock() -> None:
    dm = object.__new__(DecisionMaking)
    dm.latest_portfolio = {
        "positions": [
            {"symbol": "BTCUSDT", "positionAmt": "0", "avg_entry_price": "0"},
        ]
    }
    dm._pending_flips = {
        "BTCUSDT": {
            "state": "closing",
            "rid": "vector2-stale-close",
            "started_ts_ms": 1_700_000_000_000,
        }
    }

    result = dm._get_symbol_entry_block_reason("BTCUSDT", reduce_only=False)

    assert result is None


@pytest.mark.xfail(
    reason="Known vulnerability: hot-reload disabling a symbol silences MD-AMR management for an already open lifecycle.",
    strict=False,
)
def test_vector3_hot_reload_disable_must_not_orphan_open_md_amr_position() -> None:
    symbol = "XRPUSDT"
    handler = _md_amr_handler(symbol)
    strategy = MagicMock()
    strategy.on_bar.return_value = {
        "status": "SIGNAL",
        "signal": _md_amr_full_close_signal(),
    }
    handler._strategies[symbol] = strategy

    # Simulate hot-reload: new config disables the asset for new entries, but the
    # already-open lifecycle should still be allowed to emit the close signal.
    handler._enabled_symbols.clear()

    handler._on_process_strategy(_md_amr_event(symbol))

    emitted = _emitted_event_names(handler.fsm.emit)
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" in emitted
