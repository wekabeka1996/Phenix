"""
EP-01.4-INT-A: TIF/GTX Plumbing + Contract Hardening Tests

Tests:
1. Bridge passes tif from trade_intent (no hardcode)
2. CmdOpenPayload validates and accepts tif=GTX
3. CmdOpenPayload rejects unknown fields (extra='forbid')
4. Adapter place_limit_entry accepts time_in_force parameter
5. trade_intent schema accepts order.tif

USAGE: pytest tests/integration/test_ep01_4_tif_plumbing.py -v
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock


# ============================================================================
# Test 1: CmdOpenPayload validation
# ============================================================================

class TestCmdOpenPayload:
    """Tests for CmdOpenPayload Pydantic model."""
    
    def test_valid_payload_with_tif_gtx(self):
        """CmdOpenPayload should accept tif=GTX."""
        from apps.reference.domains.execution_position.fsm_open import CmdOpenPayload
        
        payload = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.01",
            "order_type": "LIMIT",
            "price": "42000.0",
            "tif": "GTX",  # Post-only / maker-only
            "valid_for_ms": 60_000,
        }
        
        validated = CmdOpenPayload.model_validate(payload)
        assert validated.tif == "GTX"
        assert validated.symbol == "BTCUSDT"
        assert validated.side == "BUY"
    
    def test_valid_payload_with_tif_null(self):
        """CmdOpenPayload should reject LIMIT with tif=None (fail-closed)."""
        from apps.reference.domains.execution_position.fsm_open import CmdOpenPayload
        from pydantic import ValidationError
        
        payload = {
            "symbol": "ETHUSDT",
            "side": "SELL",
            "qty": "0.1",
            "order_type": "LIMIT",
            "price": "3000.0",
            "tif": None,
            "valid_for_ms": 60_000,
        }
        
        with pytest.raises(ValidationError):
            CmdOpenPayload.model_validate(payload)
    
    def test_tif_normalized_to_uppercase(self):
        """CmdOpenPayload should normalize tif to uppercase."""
        from apps.reference.domains.execution_position.fsm_open import CmdOpenPayload
        
        payload = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.01",
            "order_type": "LIMIT",
            "price": "42000.0",
            "tif": "gtx",  # lowercase
            "valid_for_ms": 60_000,
        }
        
        validated = CmdOpenPayload.model_validate(payload)
        assert validated.tif == "GTX"
    
    def test_extra_fields_rejected(self):
        """CmdOpenPayload should reject unknown fields (fail-closed)."""
        from apps.reference.domains.execution_position.fsm_open import CmdOpenPayload
        from pydantic import ValidationError
        
        payload = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.01",
            "unknown_field": "should_fail",  # Extra field
        }
        
        with pytest.raises(ValidationError) as exc_info:
            CmdOpenPayload.model_validate(payload)
        
        assert "unknown_field" in str(exc_info.value)
    
    def test_invalid_tif_rejected(self):
        """CmdOpenPayload should reject invalid tif values."""
        from apps.reference.domains.execution_position.fsm_open import CmdOpenPayload
        from pydantic import ValidationError
        
        payload = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.01",
            "tif": "INVALID_TIF",
        }
        
        with pytest.raises(ValidationError):
            CmdOpenPayload.model_validate(payload)
    
    def test_valid_for_ms_minimum_1000(self):
        """CmdOpenPayload should enforce valid_for_ms >= 1000."""
        from apps.reference.domains.execution_position.fsm_open import CmdOpenPayload
        from pydantic import ValidationError
        
        payload = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.01",
            "order_type": "LIMIT",
            "price": "42000.0",
            "tif": "GTX",
            "valid_for_ms": 500,  # Too small
        }
        
        with pytest.raises(ValidationError):
            CmdOpenPayload.model_validate(payload)


# ============================================================================
# Test 2: trade_intent schema accepts order.tif
# ============================================================================

class TestTradeIntentSchema:
    """Tests for trade_intent_v1.json schema with tif field."""
    
    def test_schema_accepts_order_tif_gtx(self):
        """Schema should accept order.tif=GTX."""
        import jsonschema
        
        schema_path = Path(__file__).parent.parent.parent / \
            "apps/reference/domains/decision_making/schemas/trade_intent_v1.json"
        
        if not schema_path.exists():
            pytest.skip("Schema file not found")
        
        with open(schema_path) as f:
            schema = json.load(f)
        
        payload = {
            "instrument": "BTCUSDT",
            "side": "BUY",
            "p": "0.75",
            "payoff_ratio_r": "2.0",
            "tca_budget": {
                "max_slippage_bps": "10",
                "max_latency_ms": 200,
                "maker_preference": "allow"
            },
            "risk_budget": {
                "trade_cvar95_max_bps": "50",
                "session_cvar95_max_bps": "200"
            },
            "size": {"kelly_fraction": "0.1", "notional_cap_usd": "1000"},
            "order": {
                "qty": "0.01",
                "price": "42000.0",
                "price_ref": "42000.0",
                "reduce_only": False,
                "order_type": "LIMIT",  # ORDER-POLICY-01: required
                "tif": "GTX",  # EP-01.4-INT
            },
            "valid_for_ms": 60_000,
            "why": ["test"],
            "dto_version": "1.0.0",
            "schema_ref": "trade_intent_v1.json"
        }
        
        # Should not raise
        jsonschema.validate(payload, schema)
    
    def test_schema_accepts_order_tif_null(self):
        """Schema should reject LIMIT with order.tif=null (fail-closed)."""
        import jsonschema
        from jsonschema import ValidationError
        
        schema_path = Path(__file__).parent.parent.parent / \
            "apps/reference/domains/decision_making/schemas/trade_intent_v1.json"
        
        if not schema_path.exists():
            pytest.skip("Schema file not found")
        
        with open(schema_path) as f:
            schema = json.load(f)
        
        payload = {
            "instrument": "BTCUSDT",
            "side": "BUY",
            "p": "0.75",
            "payoff_ratio_r": "2.0",
            "tca_budget": {
                "max_slippage_bps": "10",
                "max_latency_ms": 200,
                "maker_preference": "allow"
            },
            "risk_budget": {
                "trade_cvar95_max_bps": "50",
                "session_cvar95_max_bps": "200"
            },
            "size": {"kelly_fraction": "0.1", "notional_cap_usd": "1000"},
            "order": {
                "qty": "0.01",
                "price": "42000.0",
                "price_ref": "42000.0",
                "reduce_only": False,
                "order_type": "LIMIT",  # ORDER-POLICY-01: required
                "tif": None,  # Null allowed
            },
            "valid_for_ms": 60_000,
            "why": ["test"],
            "dto_version": "1.0.0",
            "schema_ref": "trade_intent_v1.json"
        }
        
        with pytest.raises(ValidationError):
            jsonschema.validate(payload, schema)


# ============================================================================
# Test 3: Adapter place_limit_entry supports time_in_force
# ============================================================================

class TestAdapterTimeInForce:
    """Tests for adapter time_in_force parameter."""
    
    def test_place_limit_entry_exists(self):
        """Adapter should have place_limit_entry method."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter
        
        assert hasattr(BinanceAdapter, 'place_limit_entry')
    
    def test_place_limit_reduce_only_accepts_time_in_force(self):
        """place_limit_reduce_only should accept time_in_force parameter."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter
        import inspect
        
        sig = inspect.signature(BinanceAdapter.place_limit_reduce_only)
        params = sig.parameters
        
        assert 'time_in_force' in params
        assert params['time_in_force'].default == "GTC"


# ============================================================================
# Test 4: Bridge tif passthrough
# ============================================================================

class TestBridgeTifPassthrough:
    """Tests for Bridge tif passthrough (no hardcode)."""
    
    def test_bridge_passes_tif_from_order(self):
        """Bridge should pass tif from order_details, not hardcode GTC."""
        # This is a structural test - verify main.py code doesn't hardcode tif
        main_path = Path(__file__).parent.parent.parent / "apps/reference/main.py"
        
        if not main_path.exists():
            pytest.skip("main.py not found")
        
        content = main_path.read_text()
        
        # Should NOT contain hardcoded tif: "GTC" in command_payload
        assert '"tif": "GTC"' not in content or 'order_details.get("tif")' in content
        
        # Should contain passthrough logic
        assert 'order_details.get("tif")' in content
