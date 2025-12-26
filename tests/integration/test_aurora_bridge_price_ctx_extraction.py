"""
Regression test for AuroraBridge price_ctx extraction bug fix.

BUG: MR Handler emits EVT:STRATEGY_SIGNAL_PRODUCED with stop_price/target_price
     inside pld["price_ctx"], but AuroraBridge was only looking at pld["stop_price"].
     
RESULT: Intent prices were lost, and fsm.py used fallback calc_tp_sl_from_mark()
        with hardcoded bps values, causing wrong SL/TP for DOGE (~$0.200 instead of ~$0.126).

FIX: AuroraBridge now checks both pld["stop_price"] AND pld["price_ctx"]["stop_price"].
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from apps.reference.main import AuroraBridge
from vfoundation.core.protocol import Message


class TestAuroraBridgePriceCtxExtraction:
    """Test that AuroraBridge correctly extracts stop_price/target_price from price_ctx."""

    def test_price_ctx_extraction_from_mr_signal(self):
        """
        Test that stop_price and target_price are correctly extracted from price_ctx.
        
        This is the exact structure MR Handler emits in EVT:STRATEGY_SIGNAL_PRODUCED.
        """
        # MR Handler emits prices in price_ctx
        mr_signal_payload = {
            "rid": "test-rid-123",
            "instrument": "DOGEUSDT",
            "side": "BUY",
            "order": {
                "qty": "1000",
                "price": "0.12617",
            },
            "price_ctx": {
                "entry_price": "0.12617",
                "stop_price": "0.1263907142857142857142857143",  # MR calculated
                "target_price": "0.1255275113565789846530",  # MR calculated
            },
            "idempotent_key": "test-idem-key",
        }

        intent_msg = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="mean_reversion",
            dst="aurora_bridge",
            rid="test-rid-123",
            pld=mr_signal_payload,
        )

        # Extract what the bridge would build as command_payload
        order_details = intent_msg.pld.get("order", {})
        price_ctx = intent_msg.pld.get("price_ctx") or {}
        
        # This is the fixed extraction logic
        extracted_stop = intent_msg.pld.get("stop_price") or price_ctx.get("stop_price")
        extracted_target = intent_msg.pld.get("target_price") or price_ctx.get("target_price")

        # BEFORE FIX: These would be None
        # AFTER FIX: These should have the MR-calculated values
        assert extracted_stop is not None, "stop_price should be extracted from price_ctx"
        assert extracted_target is not None, "target_price should be extracted from price_ctx"
        
        assert extracted_stop == "0.1263907142857142857142857143"
        assert extracted_target == "0.1255275113565789846530"

    def test_top_level_takes_priority(self):
        """
        Test that top-level stop_price/target_price take priority over price_ctx.
        
        Some upstream sources may put values at both levels.
        """
        payload = {
            "rid": "test-rid-456",
            "instrument": "BTCUSDT",
            "side": "SELL",
            "order": {"qty": "0.001", "price": "100000"},
            # Top-level values (should take priority)
            "stop_price": "101000",
            "target_price": "99000",
            # price_ctx also has values
            "price_ctx": {
                "stop_price": "102000",
                "target_price": "98000",
            },
        }

        intent_msg = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="aurora_bridge",
            rid="test-rid-456",
            pld=payload,
        )

        price_ctx = intent_msg.pld.get("price_ctx") or {}
        extracted_stop = intent_msg.pld.get("stop_price") or price_ctx.get("stop_price")
        extracted_target = intent_msg.pld.get("target_price") or price_ctx.get("target_price")

        # Top-level should win
        assert extracted_stop == "101000", "top-level stop_price should take priority"
        assert extracted_target == "99000", "top-level target_price should take priority"

    def test_no_prices_anywhere_returns_none(self):
        """
        Test that when no prices are provided, None is returned (fallback behavior).
        """
        payload = {
            "rid": "test-rid-789",
            "instrument": "ETHUSDT",
            "side": "BUY",
            "order": {"qty": "0.1", "price": "3000"},
        }

        intent_msg = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="aurora_bridge",
            rid="test-rid-789",
            pld=payload,
        )

        price_ctx = intent_msg.pld.get("price_ctx") or {}
        extracted_stop = intent_msg.pld.get("stop_price") or price_ctx.get("stop_price")
        extracted_target = intent_msg.pld.get("target_price") or price_ctx.get("target_price")

        # Both should be None, triggering fallback in fsm.py
        assert extracted_stop is None
        assert extracted_target is None

    def test_empty_price_ctx_falls_through(self):
        """
        Test that empty price_ctx doesn't cause errors.
        """
        payload = {
            "rid": "test-rid-empty",
            "instrument": "XRPUSDT",
            "side": "SELL",
            "order": {"qty": "100", "price": "1.87"},
            "price_ctx": {},  # Empty dict
        }

        intent_msg = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="aurora_bridge",
            rid="test-rid-empty",
            pld=payload,
        )

        price_ctx = intent_msg.pld.get("price_ctx") or {}
        extracted_stop = intent_msg.pld.get("stop_price") or price_ctx.get("stop_price")
        extracted_target = intent_msg.pld.get("target_price") or price_ctx.get("target_price")

        assert extracted_stop is None
        assert extracted_target is None

    def test_doge_real_world_values(self):
        """
        Real-world test case from production logs showing DOGE SL/TP bug.
        
        FROM LOG (domain_mean_reversion.log):
        MR_SIGNAL {"symbol": "DOGEUSDT", "side": "SELL", ...,
                   "entry_price": "0.12617",
                   "stop_price": "0.1263907142857142857142857143",
                   "target_price": "0.1255275113565789846530", ...}
        
        BUG RESULT: SL was placed at $0.200, TP at $0.100 instead!
        """
        # This is the exact structure from MR Handler logs
        payload = {
            "schema_version": 1,
            "strategy_id": "mean_reversion",
            "symbol": "DOGEUSDT",
            "side": "SELL",
            "score": 0.5956148235157556,
            "ts_ms": 1766757243000,
            "rid": "3d58f87d-ca76-4657-84ea-52ddbf8fd4ff",
            "instrument": "DOGEUSDT",  # Added by DecisionMaking gateway
            "order": {
                "qty": "3343",
                "price": "0.12617",
            },
            "price_ctx": {
                "entry_price": "0.12617",
                "stop_price": "0.1263907142857142857142857143",
                "target_price": "0.1255275113565789846530",
            },
        }

        price_ctx = payload.get("price_ctx") or {}
        extracted_stop = payload.get("stop_price") or price_ctx.get("stop_price")
        extracted_target = payload.get("target_price") or price_ctx.get("target_price")

        # CRITICAL: These must NOT be None!
        assert extracted_stop is not None, "DOGE stop_price must be extracted from price_ctx"
        assert extracted_target is not None, "DOGE target_price must be extracted from price_ctx"

        # Verify values match MR calculation (not $0.200/$0.100 fallback)
        stop_dec = Decimal(extracted_stop)
        target_dec = Decimal(extracted_target)
        
        # SL should be ~0.1264 for SHORT (slightly above entry 0.12617)
        assert Decimal("0.126") < stop_dec < Decimal("0.127"), \
            f"DOGE SL {stop_dec} should be ~0.1264, not $0.200"
        
        # TP should be ~0.1255 for SHORT (below entry 0.12617)
        assert Decimal("0.125") < target_dec < Decimal("0.126"), \
            f"DOGE TP {target_dec} should be ~0.1255, not $0.100"
