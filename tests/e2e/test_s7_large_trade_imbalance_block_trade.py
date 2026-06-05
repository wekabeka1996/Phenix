"""
S7: Large Trade Imbalance regression (TASK31).

Proves: 1 block trade dominates 100 dust trades (volume-weighted, not count-weighted).
"""

from __future__ import annotations

import decimal


class TestS7LargeTradeImbalanceBlockTrade:
    def test_block_trade_not_lost_to_dust(self, scenario_runner):
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from apps.reference.domains.feature_engineering.types import HotState

        class _Cfg:
            neutral_value = decimal.Decimal("0.5")
            ms_per_sec = 1000
            large_trade_imbalance_window_ms = 60_000
            large_trade_imbalance_min_trades = 1
            large_trade_imbalance_eps = decimal.Decimal("1e-12")
            large_trade_imbalance_use_notional = False

        cfg = _Cfg()
        engine = FeatureCalculationEngine(cfg)
        state = HotState()

        tick = {
            # Volume-dominant buy, count-dominant sell
            "buy_volume": "5.0",
            "sell_volume": "1.0",
            "buy_count": 1,
            "sell_count": 100,
            "trades_dropped_out_of_order": 0,
        }

        phi = engine.compute_large_trade_imbalance(tick, state=state)
        scenario_runner.record_event(
            "LTI_RESULT",
            {
                "phi": str(phi),
                "ready": state.large_trade_imbalance_ready,
                "reason": state.large_trade_imbalance_not_ready_reason,
                "trades_used": state.large_trade_imbalance_trades_used,
            },
            source="feature_engineering",
        )

        assert state.large_trade_imbalance_ready is True
        assert phi > decimal.Decimal("0.5")

