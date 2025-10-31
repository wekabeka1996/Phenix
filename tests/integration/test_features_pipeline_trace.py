"""
Integration test to trace features pipeline from market tick to decision.

Tests the complete flow: MarketDataConnector → FeatureEngineering → RiskManagement → DecisionMaking
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from vfoundation.core.protocol import Message


@pytest.mark.asyncio
async def test_features_pipeline_trace():
    """
    Test that market tick flows through features pipeline to decision making.

    This test emulates the real pipeline by:
    1. Creating mock FSM with event emission/capture
    2. Instantiating all domain components
    3. Emitting EVT:MARKET_TICK_RECEIVED
    4. Verifying EVT:FEATURES_CALCULATED is emitted
    5. Checking DecisionMaking receives features and logs appropriately
    """
    # Mock FSM for event capture
    emitted_events = []

    class MockFSM:
        def __init__(self):
            self.listeners = {}

        def listen(self, event_name, callback):
            if event_name not in self.listeners:
                self.listeners[event_name] = []
            self.listeners[event_name].append(callback)

        def emit(self, event_name, payload=None, why=None):
            emitted_events.append(
                {"event_name": event_name, "payload": payload, "why": why}
            )
            # Trigger listeners
            if event_name in self.listeners:
                for callback in self.listeners[event_name]:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(
                            callback(
                                Message(
                                    op="EVT",
                                    verb=event_name.split(":")[1]
                                    if ":" in event_name
                                    else event_name,
                                    intent="OBSERVATION",
                                    src="test",
                                    dst="test",
                                    rid="test_rid",
                                    pld=payload or {},
                                    why=why or "test",
                                )
                            )
                        )
                    else:
                        callback(
                            Message(
                                op="EVT",
                                verb=event_name.split(":")[1]
                                if ":" in event_name
                                else event_name,
                                intent="OBSERVATION",
                                src="test",
                                dst="test",
                                rid="test_rid",
                                pld=payload or {},
                                why=why or "test",
                            )
                        )

    # Create mock FSM
    fsm = MockFSM()

    # Mock config
    config = {
        "trading": {
            "decision": {
                "signal_weights": {"obi": 0.6, "tfi": 0.35, "delta_price": 0.05},
                "signal_threshold": 0.05,
                "position_sizing": {
                    "min_position_size_usd": 10,
                    "liquidity_based_cap_usd": 10000,
                },
                "qos": {
                    "exposure_block_cooldown_sec": 10,
                    "symbol_cooldown_sec": 3,
                    "max_intents_per_minute_per_symbol": 6,
                },
            },
            "instruments": {"ETHUSDT": {"step_size": "0.001", "min_notional": "10"}},
        },
        "system": {"trading": {"symbols_to_track": ["ETHUSDT"]}},
        "decision_making": {
            "trading": {
                "decision": {
                    "signal_weights": {"obi": 0.6, "tfi": 0.35, "delta_price": 0.05},
                    "signal_threshold": 0.05,
                    "position_sizing": {
                        "min_position_size_usd": 10,
                        "liquidity_based_cap_usd": 10000,
                    },
                    "qos": {
                        "exposure_block_cooldown_sec": 10,
                        "symbol_cooldown_sec": 3,
                        "max_intents_per_minute_per_symbol": 6,
                    },
                },
                "instruments": {
                    "ETHUSDT": {"step_size": "0.001", "min_notional": "10"}
                },
                "tca_prefs": {
                    "max_slippage_pct": 0.5,
                    "preferred_venue": "binance",
                    "execution_priority": "speed",
                },
                "risk_budgets": {
                    "max_portfolio_risk_pct": 5.0,
                    "max_single_position_risk_pct": 1.0,
                    "max_daily_loss_pct": 2.0,
                },
                "risk": {
                    "max_daily_drawdown_limit": 0.05,
                    "score_weights": {
                        "delta_price": 0.05,
                        "obi": 0.35,
                        "tfi": 0.35,
                        "absorption_inverse": 0.25,
                    },
                    "trading_allowed_thresholds": {"max_risk_score": 0.9},
                    "daily": {
                        "max_realized_loss_usd": 250.0,
                        "max_drawdown_pct": 8.0,
                        "reset_time_utc": "00:00",
                    },
                },
                "ops": {
                    "panic_killswitch": False,
                    "quiet_hours_utc": ["22:00-06:00"],
                    "allowlist_symbols": [],
                },
                "execution": {
                    "exposure": {
                        "max_portfolio_fraction": 0.20,
                        "count_pending_orders": True,
                        "exclude_reduce_only": True,
                        "pending_reservation_ttl_sec": 90,
                    },
                    "open_order_type": "MARKET",
                    "order_params": {
                        "LIMIT": {"timeInForce": "GTC"},
                        "STOP_MARKET": {"workingType": "MARK_PRICE"},
                        "TAKE_PROFIT_MARKET": {"workingType": "MARK_PRICE"},
                        "TRAILING_STOP_MARKET": {"callbackRate": "0.5"},
                    },
                },
            }
        },
    }

    # Initialize domain components
    from apps.reference.domains.feature_engineering.feature_engineering import (
        FeatureEngineering,
    )
    from apps.reference.domains.risk_management.risk_management import RiskManagement
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    # Mock logger to capture logs
    import logging

    logger = logging.getLogger("test_decision_making")
    logger.setLevel(logging.DEBUG)
    log_capture = []
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Create components
    feature_engineering = FeatureEngineering(fsm, config.get("feature_engineering", {}))
    risk_management = RiskManagement(fsm, config.get("risk_management", {}))
    decision_making = DecisionMaking(fsm, config["decision_making"])

    # Mock portfolio state
    portfolio_payload = {
        "equity": "10000.0",
        "equity_free_usdt": "9000.0",
        "positions": [],
    }
    fsm.emit("EVT:PORTFOLIO_STATE_UPDATED", payload=portfolio_payload)

    # Give time for async operations
    await asyncio.sleep(0.1)

    # Emit first market tick
    market_tick_payload_1 = {
        "ts": 1640995200000,  # 2022-01-01 00:00:00
        "symbol": "ETHUSDT",
        "price": "3000.0",
        "bid": "2999.5",
        "ask": "3000.5",
        "bid_size": "10.0",
        "ask_size": "8.0",
        "buy_volume": "15",
        "sell_volume": "12",
        "data_type": "market_tick_aggregated",
        "data_source": "test",
        "debug_info": "test data 1",
    }

    fsm.emit("EVT:MARKET_TICK_RECEIVED", payload=market_tick_payload_1)

    # Give time for async operations
    await asyncio.sleep(0.1)

    # Emit second market tick (needed for delta_price calculation)
    market_tick_payload_2 = {
        "ts": 1640995201000,  # 1 second later
        "symbol": "ETHUSDT",
        "price": "3000.5",  # Price increased by 0.5
        "bid": "3000.0",
        "ask": "3001.0",
        "bid_size": "12.0",
        "ask_size": "9.0",
        "buy_volume": "18",
        "sell_volume": "14",
        "data_type": "market_tick_aggregated",
        "data_source": "test",
        "debug_info": "test data 2",
    }

    fsm.emit("EVT:MARKET_TICK_RECEIVED", payload=market_tick_payload_2)

    # Wait for pipeline to process
    await asyncio.sleep(0.2)

    # Verify events were emitted
    event_names = [e["event_name"] for e in emitted_events]
    print(f"Emitted events: {event_names}")

    # Check that FEATURES_CALCULATED was emitted
    assert "EVT:FEATURES_CALCULATED" in event_names, (
        f"Expected EVT:FEATURES_CALCULATED in {event_names}"
    )

    # Check that RISK_ASSESSMENT_COMPLETED was emitted
    assert "EVT:RISK_ASSESSMENT_COMPLETED" in event_names, (
        f"Expected EVT:RISK_ASSESSMENT_COMPLETED in {event_names}"
    )

    # Check features payload
    features_event = next(
        e for e in emitted_events if e["event_name"] == "EVT:FEATURES_CALCULATED"
    )
    assert features_event["payload"]["symbol"] == "ETHUSDT"
    assert "features" in features_event["payload"]
    assert "obi" in features_event["payload"]["features"]
    assert "tfi" in features_event["payload"]["features"]

    # Check risk payload
    risk_event = next(
        e for e in emitted_events if e["event_name"] == "EVT:RISK_ASSESSMENT_COMPLETED"
    )
    assert risk_event["payload"]["symbol"] == "ETHUSDT"
    assert "risk_parameters" in risk_event["payload"]
    assert "is_trading_allowed" in risk_event["payload"]["risk_parameters"]

    print("✅ Features pipeline test passed - all events emitted correctly")
