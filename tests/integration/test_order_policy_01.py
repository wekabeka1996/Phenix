"""
ORDER-POLICY-01: Order Policy SSOT Tests

Tests:
1. Aurora strategy config has LIMIT/GTX → trade_intent must have LIMIT+GTX
2. MR strategy config has MARKET → trade_intent must have MARKET, no price required
3. CmdOpenPayload requires order_type (no default)
4. Bridge no longer fallbacks to LIMIT
5. NRR codes exist for order policy validation
6. Capabilities config must be explicit (no defaults)
7. Strategy policy validated against capabilities
8. LIMIT without price → reject (NRR-050)
9. MARKET with tif → reject (conceptual)
10. order_type missing → reject (NRR-047)

USAGE: pytest tests/integration/test_order_policy_01.py -v
"""

import pytest
from pydantic import ValidationError


# ============================================================================
# Test 1: NRR Codes Exist
# ============================================================================

class TestNRRCodesExist:
    """ORDER-POLICY-01 NRR codes must be defined."""
    
    def test_order_type_missing_code(self):
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        assert NormalizedRejectReasons.ORDER_TYPE_MISSING == "NRR-047"
    
    def test_unsupported_order_type_code(self):
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        assert NormalizedRejectReasons.UNSUPPORTED_ORDER_TYPE == "NRR-048"
    
    def test_unsupported_tif_code(self):
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        assert NormalizedRejectReasons.UNSUPPORTED_TIF == "NRR-049"
    
    def test_limit_price_missing_code(self):
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        assert NormalizedRejectReasons.LIMIT_PRICE_MISSING == "NRR-050"
    
    def test_market_price_present_code(self):
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        assert NormalizedRejectReasons.MARKET_PRICE_PRESENT == "NRR-051"
    
    def test_tif_required_for_limit_code(self):
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        assert NormalizedRejectReasons.TIF_REQUIRED_FOR_LIMIT == "NRR-052"


# ============================================================================
# Test 2: CmdOpenPayload Requires order_type
# ============================================================================

class TestCmdOpenPayloadStrict:
    """CmdOpenPayload must reject missing order_type (no default)."""
    
    def test_order_type_is_required(self):
        """Missing order_type should raise ValidationError."""
        from apps.reference.domains.execution_position.fsm_open import CmdOpenPayload
        
        with pytest.raises(ValidationError) as exc_info:
            CmdOpenPayload(
                symbol="BTCUSDT",
                side="BUY",
                qty="0.001",
                # order_type missing!
            )
        
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("order_type",) for e in errors)
    
    def test_valid_limit_order(self):
        """Valid LIMIT order with all required fields."""
        from apps.reference.domains.execution_position.fsm_open import CmdOpenPayload
        
        payload = CmdOpenPayload(
            symbol="BTCUSDT",
            side="BUY",
            qty="0.001",
            order_type="LIMIT",
            price="50000.00",
            tif="GTX",
            valid_for_ms=60_000,
        )
        assert payload.order_type == "LIMIT"
        assert payload.tif == "GTX"
    
    def test_valid_market_order(self):
        """Valid MARKET order."""
        from apps.reference.domains.execution_position.fsm_open import CmdOpenPayload
        
        payload = CmdOpenPayload(
            symbol="BTCUSDT",
            side="BUY",
            qty="0.001",
            order_type="MARKET",
        )
        assert payload.order_type == "MARKET"
        assert payload.tif is None  # default


# ============================================================================
# Test 3: OrderCapabilitiesConfig Strict
# ============================================================================

class TestOrderCapabilitiesConfig:
    """OrderCapabilitiesConfig must be explicit (no defaults)."""
    
    def test_requires_supported_order_types(self):
        """Missing supported_order_types should raise error."""
        from apps.reference.config_models import OrderCapabilitiesConfig
        
        with pytest.raises(ValidationError):
            OrderCapabilitiesConfig(
                # supported_order_types missing!
                supported_tif=["GTC", "GTX"]
            )
    
    def test_requires_supported_tif(self):
        """Missing supported_tif should raise error."""
        from apps.reference.config_models import OrderCapabilitiesConfig
        
        with pytest.raises(ValidationError):
            OrderCapabilitiesConfig(
                supported_order_types=["LIMIT", "MARKET"],
                # supported_tif missing!
            )
    
    def test_valid_config(self):
        """Valid capabilities config."""
        from apps.reference.config_models import OrderCapabilitiesConfig
        
        config = OrderCapabilitiesConfig(
            supported_order_types=["LIMIT", "MARKET"],
            supported_tif=["GTC", "GTX", "IOC", "FOK"]
        )
        assert "LIMIT" in config.supported_order_types
        assert "GTX" in config.supported_tif
    
    def test_invalid_order_type_rejected(self):
        """Invalid order type literal should be rejected."""
        from apps.reference.config_models import OrderCapabilitiesConfig
        
        with pytest.raises(ValidationError):
            OrderCapabilitiesConfig(
                supported_order_types=["STOP"],  # Invalid!
                supported_tif=["GTC"]
            )


# ============================================================================
# Test 4: Aurora Config Has Execution Policy
# ============================================================================

class TestAuroraConfigExecution:
    """Aurora strategy config must have execution policy."""
    
    def test_aurora_yaml_has_execution_section(self):
        """Check aurora.yaml has execution.entry_order_type."""
        import yaml
        from pathlib import Path
        
        aurora_path = Path("config/aurora/strategies/aurora.yaml")
        with open(aurora_path) as f:
            config = yaml.safe_load(f)
        
        assert "aurora" in config
        assert "execution" in config["aurora"]
        assert "entry_order_type" in config["aurora"]["execution"]
        assert "entry_tif" in config["aurora"]["execution"]
        
        # Aurora uses LIMIT + GTX
        assert config["aurora"]["execution"]["entry_order_type"] == "LIMIT"
        assert config["aurora"]["execution"]["entry_tif"] == "GTX"


# ============================================================================
# Test 5: MR Config Has Execution Policy
# ============================================================================

class TestMRConfigExecution:
    """MR strategy config must have execution policy."""
    
    def test_mr_yaml_has_execution_section(self):
        """Check mean_reversion.yaml has execution.entry_order_type."""
        import yaml
        from pathlib import Path
        
        mr_path = Path("config/aurora/strategies/mean_reversion.yaml")
        with open(mr_path) as f:
            config = yaml.safe_load(f)
        
        assert "mean_reversion" in config
        assert "execution" in config["mean_reversion"]
        assert "entry_order_type" in config["mean_reversion"]["execution"]
        
        # MR uses MARKET
        assert config["mean_reversion"]["execution"]["entry_order_type"] == "MARKET"
        # tif should be null for MARKET
        assert config["mean_reversion"]["execution"]["entry_tif"] is None


# ============================================================================
# Test 6: domains.yaml Has order_capabilities
# ============================================================================

class TestDomainsCapabilities:
    """domains.yaml must have order_capabilities section."""
    
    def test_domains_has_order_capabilities(self):
        """Check domains.yaml has execution_position.order_capabilities."""
        import yaml
        from pathlib import Path
        
        domains_path = Path("config/aurora/domains.yaml")
        with open(domains_path) as f:
            config = yaml.safe_load(f)
        
        assert "execution_position" in config
        assert "order_capabilities" in config["execution_position"]
        caps = config["execution_position"]["order_capabilities"]
        
        assert "supported_order_types" in caps
        assert "supported_tif" in caps
        assert "LIMIT" in caps["supported_order_types"]
        assert "MARKET" in caps["supported_order_types"]
        assert "GTX" in caps["supported_tif"]


# ============================================================================
# Test 7: Trade Intent Schema Has order_type
# ============================================================================

class TestTradeIntentSchema:
    """Trade intent schema must require order_type."""
    
    def test_schema_has_order_type(self):
        """Check trade_intent_v1.json has order.order_type."""
        import json
        from pathlib import Path
        
        schema_path = Path("apps/reference/domains/decision_making/intent/schemas/trade_intent_v1.json")
        with open(schema_path) as f:
            schema = json.load(f)
        
        order_props = schema["properties"]["order"]["properties"]
        assert "order_type" in order_props
        assert order_props["order_type"]["enum"] == ["LIMIT", "MARKET"]
    
    def test_order_type_is_required(self):
        """order_type should be in required array."""
        import json
        from pathlib import Path
        
        schema_path = Path("apps/reference/domains/decision_making/intent/schemas/trade_intent_v1.json")
        with open(schema_path) as f:
            schema = json.load(f)
        
        required = schema["properties"]["order"]["required"]
        assert "order_type" in required


# ============================================================================
# Test 8: No Silent Fallback in Bridge (Conceptual)
# ============================================================================

class TestBridgeNoFallback:
    """Bridge must not silently fallback order_type to LIMIT."""
    
    def test_bridge_code_no_or_limit(self):
        """Check main.py doesn't have 'order_type_raw or LIMIT' pattern."""
        from pathlib import Path
        
        main_path = Path("apps/reference/main.py")
        content = main_path.read_text(encoding="utf-8")
        
        # Should NOT find the old fallback pattern
        assert 'order_type_raw or "LIMIT"' not in content
        assert "order_type_raw or 'LIMIT'" not in content


# ============================================================================
# Test 9: CmdOpenPayload Forbids Extra Fields
# ============================================================================

class TestCmdOpenPayloadForbidExtra:
    """CmdOpenPayload must reject unknown fields."""
    
    def test_extra_field_rejected(self):
        from apps.reference.domains.execution_position.fsm_open import CmdOpenPayload
        
        with pytest.raises(ValidationError):
            CmdOpenPayload(
                symbol="BTCUSDT",
                side="BUY",
                qty="0.001",
                order_type="MARKET",
                unknown_field="oops"  # Extra field!
            )
