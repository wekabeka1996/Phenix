from apps.reference.domains.alpha_search.backtest_plugin import (
    AlphaSearchBacktestPlugin,
    VirtualPosition,
)
from apps.reference.domains.alpha_search.config_models import (
    AlphaSearchConfig,
    ObjectiveFeedbackConfig,
    ProviderConfig,
    TAEnsembleConfig,
    VirtualTraderConfig,
)
from apps.reference.orchestrator.utils_event_bus import LocalBus


def _objective_feedback_cfg() -> ObjectiveFeedbackConfig:
    return ObjectiveFeedbackConfig(
        enabled=True,
        window_trades=20,
        min_trades_before_reweight=5,
        rebalance_every_closed_trades=1,
        quality_metric_weights={
            "realized_quality_score": 0.4,
            "realized_pnl": 0.35,
            "duration_efficiency": 0.25,
        },
        min_provider_weight=0.1,
        max_provider_weight=0.8,
    )


def _plugin_config() -> AlphaSearchConfig:
    return AlphaSearchConfig(
        enabled=True,
        providers={
            "ta_ensemble": ProviderConfig(
                enabled=True,
                threshold=0.15,
                fail_closed=True,
                ensemble=TAEnsembleConfig(),
            )
        },
        virtual_trader=VirtualTraderConfig(
            enabled=True,
            per_provider=True,
            max_positions_per_symbol=1,
            notional_size=1_000.0,
        ),
        objective_feedback=_objective_feedback_cfg(),
    )


def test_virtual_close_emits_and_attaches_objective_feedback() -> None:
    bus = LocalBus()
    plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=_plugin_config())
    ensemble = plugin.providers["ta_ensemble"]

    ensemble._pending_signals["sig_internal_1"] = ("ensemble", 0.5, "BTCUSDT", 1.0)
    plugin._signal_provider["ta_ensemble_sig_1"] = "ta_ensemble"
    position = VirtualPosition(
        provider_id="ta_ensemble",
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100.0,
        entry_ts=1_700_000_000_000,
        signal_id="ta_ensemble_sig_1",
        model_signal_id="sig_internal_1",
        bars_held=3,
    )

    plugin._close_virtual_position(
        provider_id="ta_ensemble",
        pos=position,
        exit_price=103.0,
        exit_ts=1_700_000_300_000,
        exit_reason="time_exit",
    )

    closed = plugin.closed_positions["ta_ensemble"][0]
    assert "objective_realized" in closed
    assert "objective_feedback_score" in closed
    assert closed["objective_realized"]["signal_id"] == "ta_ensemble_sig_1"
    assert plugin.provider_stats["ta_ensemble"].objective_feedback_events == 1
    assert any(history for history in ensemble.model_performance.values())


def test_external_objective_event_attaches_to_closed_trade_and_updates_ensemble() -> None:
    bus = LocalBus()
    plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=_plugin_config())
    ensemble = plugin.providers["ta_ensemble"]

    ensemble._pending_signals["sig_internal_2"] = ("ensemble", 0.4, "ETHUSDT", 1.0)
    plugin._signal_provider["ta_ensemble_sig_2"] = "ta_ensemble"
    plugin.closed_positions["ta_ensemble"].append(
        {
            "provider_id": "ta_ensemble",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "entry_price": 200.0,
            "exit_price": 190.0,
            "entry_ts": 1_700_000_000_000,
            "exit_ts": 1_700_000_120_000,
            "bars_held": 2,
            "pnl": 50.0,
            "signal_id": "ta_ensemble_sig_2",
            "model_signal_id": "sig_internal_2",
            "exit_reason": "time_exit",
        }
    )

    bus.emit(
        "EVT:OBJECTIVE_REALIZED_V1",
        payload={
            "strategy_id": "aurora",
            "symbol": "ETHUSDT",
            "entry_rid": "rid-entry",
            "close_rid": "rid-close",
            "regime_entry": "TREND_UP",
            "regime_exit": "TREND_UP",
            "pretrade_objective_trace": {},
            "realized_components": {
                "duration_efficiency": 0.8,
            },
            "realized_quality_score": 0.6,
            "realized_pnl": 50.0,
            "fees": 0.0,
            "duration_sec": 120.0,
            "mae": 0.0,
            "mfe": 0.01,
            "close_reason": "time_exit",
            "signal_id": "ta_ensemble_sig_2",
        },
        why="test",
    )

    closed = plugin.closed_positions["ta_ensemble"][0]
    assert closed["objective_realized"]["close_rid"] == "rid-close"
    assert closed["objective_feedback_score"] > 0.0
    assert any(history for history in ensemble.model_performance.values())
