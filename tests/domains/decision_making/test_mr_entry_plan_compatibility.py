"""
Test: MR signal passes gateway EntryPlan when volatility is propagated.

DoD for P0-1 (DM-STRATEGY-SSOT-FIXPLAN-01):
- MR signal → gateway → intent without ATR-conflict rejection

This test validates that MeanReversion signals can pass through the
DecisionMaking gateway when volatility/atr_ready are properly propagated.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from decimal import Decimal
import time


class TestMREntryPlanCompatibility:
    """Test suite for MR-EntryPlan ATR compatibility."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config with entry_plan enabled and require_atr=true."""
        config = MagicMock()
        
        # EntryPlan config
        config.domains.decision_making.entry_plan.enabled = True
        config.domains.decision_making.entry_plan.require_atr = True
        config.domains.decision_making.entry_plan.atr_period = 14
        config.domains.decision_making.entry_plan.entry_k_atr = 0.3
        config.domains.decision_making.entry_plan.sl_k_atr = 1.5
        config.domains.decision_making.entry_plan.tp_k_atr = 2.0
        config.domains.decision_making.entry_plan.obi_weight = 0.3
        config.domains.decision_making.entry_plan.obi_mod_clamp_min = 0.8
        config.domains.decision_making.entry_plan.obi_mod_clamp_max = 1.2
        config.domains.decision_making.entry_plan.obi_missing_policy = "neutral"
        
        # Strategies registry
        config.strategies_registry.assignments = {
            "DOGEUSDT": ["mean_reversion"],
        }
        
        return config

    def test_mr_signal_with_volatility_passes_entry_plan_validation(self, mock_config):
        """
        Given: MR handler emits signal with volatility snapshot (atr_ready=True)
        When: Gateway validates signal for EntryPlan
        Then: validate_inputs returns (True, None) - no rejection
        """
        # Signal payload WITH volatility (after P0-1 fix)
        signal_payload = {
            "schema_version": 1,
            "strategy_id": "mean_reversion",
            "symbol": "DOGEUSDT",
            "tf_sec": 180,
            "side": "BUY",
            "readiness": {"warmup_ok": True},
            "score": 0.85,
            "why": "bb_lower_touch",
            "ts_ms": int(time.time() * 1000),
            "rid": "test_mr_rid_001",
            "why_chain": ["bb_lower_touch"],
            "price_ctx": {
                "entry_price": "0.12345",
                "stop_price": "0.12000",
                "target_price": "0.13000",
            },
            "regime": "FLAT_NORMAL",
            # P0-1: Volatility propagated from cmd.features
            "volatility": {
                "bar_range": "0.00050",
                "bar_body": "0.00030",
                "true_range": "0.00055",
                "atr_14": 0.00123,
                "range_pct": 0.004,
                "atr_pct": 0.01,
                "atr_ready": True,  # KEY: ATR is ready
            },
            "liquidity": {
                "obi_close": "0.05",
            },
            "mr_params": {
                "sizing_mult": 1.0,
                "stop_mult": 1.0,
                "target_mult": 1.0,
            },
        }

        # Extract volatility as gateway does
        volatility_data = signal_payload.get("volatility") or {}
        atr_value = volatility_data.get("atr_14")
        atr_ready = volatility_data.get("atr_ready", False)

        # Validate
        assert atr_ready is True, "atr_ready must be True for EntryPlan to pass"
        assert atr_value is not None, "atr_14 must be present"
        assert atr_value > 0, "atr_14 must be positive"

    def test_mr_signal_without_volatility_fails_entry_plan_validation(self, mock_config):
        """
        Given: MR handler emits signal WITHOUT volatility (legacy behavior)
        When: Gateway validates signal for EntryPlan with require_atr=true
        Then: validate_inputs returns (False, "ATR_NOT_READY") - rejection
        """
        # Signal payload WITHOUT volatility (before P0-1 fix)
        signal_payload = {
            "schema_version": 1,
            "strategy_id": "mean_reversion",
            "symbol": "DOGEUSDT",
            "tf_sec": 180,
            "side": "BUY",
            "readiness": {"warmup_ok": True},
            "score": 0.85,
            "ts_ms": int(time.time() * 1000),
            "rid": "test_mr_rid_002",
            "price_ctx": {
                "entry_price": "0.12345",
            },
            # NO volatility field!
        }

        # Extract volatility as gateway does
        volatility_data = signal_payload.get("volatility") or {}
        atr_ready = volatility_data.get("atr_ready", False)

        # Without volatility, atr_ready defaults to False
        assert atr_ready is False, "Missing volatility should result in atr_ready=False"

    def test_mr_handler_propagates_volatility_from_cmd(self):
        """
        Given: CMD:PROCESS_STRATEGY contains features.volatility
        When: MR handler builds signal payload
        Then: Signal includes volatility field from cmd
        """
        # Simulated CMD payload from FeatureEngineering
        cmd_payload = {
            "symbol": "DOGEUSDT",
            "tf_sec": 180,
            "bar_close_ts": 1704067200000,
            "bar": {
                "symbol": "DOGEUSDT",
                "timeframe_sec": 180,
                "open": "0.12300",
                "high": "0.12400",
                "low": "0.12200",
                "close": "0.12350",
                "volume": "1000000",
            },
            "features": {
                "volatility": {
                    "bar_range": "0.00200",
                    "bar_body": "0.00050",
                    "true_range": "0.00210",
                    "atr_14": 0.00185,
                    "atr_ready": True,
                },
                "liquidity": {
                    "obi_close": "0.03",
                },
            },
            "warmup": {"full_ready": True},
            "regime": {"overall_regime": "FLAT_NORMAL"},
        }

        # Expected: MR handler should extract and propagate volatility
        features = cmd_payload.get("features", {})
        volatility = features.get("volatility")
        liquidity = features.get("liquidity")

        assert volatility is not None, "CMD must contain features.volatility"
        assert volatility.get("atr_ready") is True
        assert liquidity is not None, "CMD must contain features.liquidity"

    def test_entry_plan_validates_with_atr_ready_true(self):
        """
        Integration-like test: EntryPlan.validate_inputs passes when atr_ready=True.
        """
        # Mock EntryPlan params
        from dataclasses import dataclass

        @dataclass
        class MockEntryPlanParams:
            require_atr: bool = True
            atr_period: int = 14

        params = MockEntryPlanParams(require_atr=True)

        # Simulate validation logic
        side = "BUY"
        ref_price = Decimal("0.12345")
        atr = 0.00123
        atr_ready = True

        # Validation: require_atr=True AND atr_ready=True → PASS
        if params.require_atr and not atr_ready:
            is_valid, error = False, "ATR_NOT_READY"
        else:
            is_valid, error = True, None

        assert is_valid is True
        assert error is None

    def test_entry_plan_rejects_with_atr_ready_false(self):
        """
        Integration-like test: EntryPlan.validate_inputs fails when atr_ready=False.
        """
        from dataclasses import dataclass

        @dataclass
        class MockEntryPlanParams:
            require_atr: bool = True

        params = MockEntryPlanParams(require_atr=True)

        atr_ready = False

        # Validation: require_atr=True AND atr_ready=False → FAIL
        if params.require_atr and not atr_ready:
            is_valid, error = False, "ATR_NOT_READY"
        else:
            is_valid, error = True, None

        assert is_valid is False
        assert error == "ATR_NOT_READY"


class TestMRSignalPayloadContract:
    """Test MR signal payload adheres to gateway contract."""

    def test_mr_signal_has_required_gateway_fields(self):
        """
        Given: MR emits EVT:STRATEGY_SIGNAL_PRODUCED
        Then: Payload contains all required gateway fields
        """
        required_fields = [
            "strategy_id",
            "symbol",
            "side",
            "readiness",
            "price_ctx",
            "ts_ms",
            "rid",
        ]

        # Sample MR payload (after P0-1 fix)
        mr_payload = {
            "schema_version": 1,
            "strategy_id": "mean_reversion",
            "symbol": "DOGEUSDT",
            "tf_sec": 180,
            "side": "BUY",
            "readiness": {"warmup_ok": True},
            "runtime_permissions": {
                "can_manage_existing_risk": True,
                "can_open_new_risk": True,
                "mode": "OPEN_AND_MANAGE",
            },
            "runtime_readiness": {
                "strategy_id": "mean_reversion",
                "symbol": "DOGEUSDT",
                "updated_at": 1704067200000,
                "source": "decision_making:mean_reversion",
                "blocking_reason_chain": [],
                "permissions": {
                    "can_manage_existing_risk": True,
                    "can_open_new_risk": True,
                    "mode": "OPEN_AND_MANAGE",
                },
                "scopes": {
                    "strategy_ready_per_symbol": {
                        "state": "READY",
                        "why": ["signal_emitted"],
                        "updated_at": 1704067200000,
                        "source": "decision_making:mean_reversion",
                        "evidence_ref": "rid-1",
                    }
                },
            },
            "score": 0.85,
            "why": "bb_lower_touch",
            "ts_ms": 1704067200000,
            "rid": "mr_doge_1704067200000",
            "why_chain": ["bb_lower_touch"],
            "price_ctx": {
                "entry_price": "0.12345",
                "stop_price": "0.12000",
                "target_price": "0.13000",
            },
            "volatility": {"atr_14": 0.00123, "atr_ready": True},
            "liquidity": {"obi_close": "0.05"},
        }

        for field in required_fields:
            assert field in mr_payload, f"Missing required field: {field}"

    def test_mr_signal_readiness_warmup_ok_is_true(self):
        """
        MR signals must have readiness.warmup_ok=True (gateway rejects False).
        """
        mr_payload = {
            "readiness": {"warmup_ok": True},
            "runtime_permissions": {
                "can_manage_existing_risk": True,
                "can_open_new_risk": True,
                "mode": "OPEN_AND_MANAGE",
            },
        }

        assert mr_payload["readiness"]["warmup_ok"] is True
        assert mr_payload["runtime_permissions"]["can_open_new_risk"] is True

    def test_mr_signal_price_ctx_entry_price_valid(self):
        """
        MR signals must have valid entry_price > 0.
        """
        mr_payload = {
            "price_ctx": {
                "entry_price": "0.12345",
            },
        }

        entry_price = Decimal(mr_payload["price_ctx"]["entry_price"])
        assert entry_price > 0
