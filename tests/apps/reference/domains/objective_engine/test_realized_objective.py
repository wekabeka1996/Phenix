from decimal import Decimal

from apps.reference.domains.objective_engine.posttrade_evaluator import evaluate_realized_quality
from apps.reference.domains.objective_engine.snapshot_registry import ObjectiveSnapshotRegistry


def _objective_trace() -> dict:
    return {
        "trace_id": "obj-1",
        "multiplier": 0.9,
        "objective_score": 0.45,
        "components": {"cost": -0.1, "edge": 0.3},
        "raw_metrics": {"spread_bps": 1.2},
    }


def test_snapshot_registry_binds_entry_and_realizes_close() -> None:
    registry = ObjectiveSnapshotRegistry()
    registry.register_trade_intent(
        {
            "strategy": "aurora",
            "instrument": "BTCUSDT",
            "side": "BUY",
            "rid": "entry-rid-1",
            "decision_ts_ms": 1_700_000_000_000,
            "order": {"price_ref": "100.0"},
            "stop_price": "95.0",
            "target_price": "110.0",
            "regime": "TREND_UP",
            "trace": {
                "objective": _objective_trace(),
                "alpha_search": {"signal_id": "alpha-sig-1"},
            },
        }
    )

    registry.note_regime(symbol="BTCUSDT", regime="TREND_UP")
    registry.note_market_tick(symbol="BTCUSDT", price=Decimal("102.0"))
    assert registry.on_trade_executed(
        {
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "1.0",
            "price": "100.0",
            "fees": "0.5",
            "ts_ms": 1_700_000_000_500,
        }
    ) == []

    registry.note_market_tick(symbol="BTCUSDT", price=Decimal("108.0"))
    registry.note_market_tick(symbol="BTCUSDT", price=Decimal("97.5"))
    registry.note_regime(symbol="BTCUSDT", regime="MEAN_REVERSION")
    realized_candidates = registry.on_trade_executed(
        {
            "symbol": "BTCUSDT",
            "side": "sell",
            "quantity": "1.0",
            "price": "107.0",
            "fees": "0.4",
            "ts_ms": 1_700_000_600_000,
            "rid": "close-rid-1",
        }
    )

    assert len(realized_candidates) == 1
    active, close_qty, exit_price, ts_ms, close_reason = realized_candidates[0]
    assert active.snapshot.signal_id == "alpha-sig-1"
    assert close_qty == Decimal("1.0")
    assert exit_price == Decimal("107.0")
    assert close_reason == "POSITION_UPDATE"

    realized = evaluate_realized_quality(
        active=active,
        close_rid="close-rid-1",
        exit_price=exit_price,
        close_ts_ms=ts_ms,
        closed_qty=close_qty,
        close_reason=close_reason,
    )

    assert realized.strategy_id == "aurora"
    assert realized.signal_id == "alpha-sig-1"
    assert realized.realized_quality_score > -1.0
    assert "duration_efficiency" in realized.realized_components
    assert realized.regime_exit == "MEAN_REVERSION"


def test_snapshot_registry_reduce_only_reason_flows_into_realized_event() -> None:
    registry = ObjectiveSnapshotRegistry()
    registry.register_trade_intent(
        {
            "strategy": "md_amr",
            "instrument": "ETHUSDT",
            "side": "BUY",
            "rid": "entry-rid-2",
            "decision_ts_ms": 1_700_000_000_000,
            "order": {"price_ref": "200.0"},
            "stop_price": "190.0",
            "target_price": "220.0",
            "regime": "TREND_UP",
            "trace": {"objective": _objective_trace()},
        }
    )
    assert registry.on_trade_executed(
        {
            "symbol": "ETHUSDT",
            "side": "buy",
            "quantity": "2.0",
            "price": "200.0",
            "fees": "0.2",
            "ts_ms": 1_700_000_000_500,
        }
    ) == []
    registry.register_trade_intent(
        {
            "strategy": "md_amr",
            "instrument": "ETHUSDT",
            "why": ["TP_HIT"],
            "order": {"reduce_only": True},
            "trace": {},
        }
    )

    realized_candidates = registry.on_trade_executed(
        {
            "symbol": "ETHUSDT",
            "side": "sell",
            "quantity": "2.0",
            "price": "218.0",
            "fees": "0.2",
            "ts_ms": 1_700_000_200_000,
        }
    )

    assert realized_candidates[0][-1] == "TP_HIT"
