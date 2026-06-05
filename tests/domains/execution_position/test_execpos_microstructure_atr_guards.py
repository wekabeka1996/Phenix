from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.domains.execution_position.fsm import ExecPosFSM, PendingEntryMeta


def _snapshot_payload(*, price: float, atr_14: float) -> dict:
    return {
        "symbol": "BTCUSDT",
        "microstructure_snapshot_v1": {
            "contract": "microstructure_snapshot_v1",
            "symbol": "BTCUSDT",
            "ts_ms": 100,
            "tf_sec": 300,
            "price": price,
            "atr_14": atr_14,
            "atr_pct": None,
            "atr_ready": True,
            "orderbook_imbalance": 0.1,
            "obi": 0.1,
            "obi_close": 0.1,
            "spread_bps": 4.0,
            "liquidity_kappa": 0.7,
            "pm_norm_10s": None,
            "pm_norm_60s": None,
            "pm_norm_300s": None,
            "warmup_full_ready": True,
            "source_paths": {"atr_14": "features.volatility.atr_14"},
            "legacy_fallback_fields": [],
            "missing_fields": [],
            "retained_fields": [],
        },
    }


def test_supersede_reprice_guard_uses_canonical_snapshot_atr() -> None:
    fsm = ExecPosFSM.__new__(ExecPosFSM)
    fsm.config = SimpleNamespace(
        domains=SimpleNamespace(
            execution_position=SimpleNamespace(
                pending_entry_ttl=SimpleNamespace(
                    supersede_reprice_guard=SimpleNamespace(
                        enabled=True,
                        enforce=True,
                        min_price_improvement_bps=5.0,
                        min_price_improvement_atr_mult=0.2,
                    )
                )
            )
        )
    )
    fsm._last_features_cache = {"BTCUSDT": _snapshot_payload(price=100.0, atr_14=10.0)}
    fsm._pending_entry_meta = {
        "oid-1": PendingEntryMeta(
            symbol="BTCUSDT",
            side="BUY",
            limit_price="100.0",
            placed_at_ms=0,
            tf_sec=300,
        )
    }

    decision = SimpleNamespace(pld={"order_type": "LIMIT", "side": "BUY", "price": "101.0"})

    result = ExecPosFSM._evaluate_supersede_reprice_guard(
        fsm,
        "BTCUSDT",
        decision,
        ["oid-1"],
    )

    assert result is not None
    assert result["allow_cancel"] is False
    assert result["analyses"][0]["threshold_px"] == 2.0
    assert result["analyses"][0]["improvement_px"] == 1.0


def test_advanced_stale_cancel_uses_canonical_snapshot_price_and_atr() -> None:
    fsm = ExecPosFSM.__new__(ExecPosFSM)
    cancel_pending_entries_for_symbol = MagicMock()
    fsm.config = SimpleNamespace(
        domains=SimpleNamespace(
            execution_position=SimpleNamespace(
                pending_entry_ttl=SimpleNamespace(
                    advanced_stale_cancel=SimpleNamespace(
                        enabled=True,
                        min_age_before_cancel_sec=0,
                        drift_away=SimpleNamespace(atr_mult=0.5),
                        may_cancel_regimes={"BUY": ["TREND_DOWN"], "SELL": ["TREND_UP"]},
                        never_cancel_regimes=["UNCERTAIN"],
                    )
                )
            )
        )
    )
    fsm.watchdog = SimpleNamespace(
        pending_orders={"oid-1": SimpleNamespace(symbol="BTCUSDT")},
        acked_orders={},
    )
    fsm._last_features_cache = {"BTCUSDT": _snapshot_payload(price=101.0, atr_14=1.5)}
    fsm._pending_entry_meta = {
        "oid-1": PendingEntryMeta(
            symbol="BTCUSDT",
            side="BUY",
            limit_price="100.0",
            placed_at_ms=0,
            tf_sec=300,
        )
    }
    fsm._entry_mgr = SimpleNamespace(cancel_pending_entries_for_symbol=cancel_pending_entries_for_symbol)

    ExecPosFSM._evaluate_advanced_stale_cancel(fsm, "BTCUSDT", "TREND_DOWN")

    cancel_pending_entries_for_symbol.assert_called_once()
    kwargs = cancel_pending_entries_for_symbol.call_args.kwargs
    assert kwargs["symbol"] == "BTCUSDT"
    assert kwargs["reason"] == "CANCEL_STALE_REGIME_ADVANCED"
    assert kwargs["filter_order_ids"] == {"oid-1"}