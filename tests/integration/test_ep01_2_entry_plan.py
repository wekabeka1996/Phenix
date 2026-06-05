"""
EP-01.2-INT Test Suite: EntryPlan + AuroraHandler propagation + DecisionMaking integration.

Tests:
A) EntryPlan unit tests (formulas, OBI modulation, clamp)
B) AuroraHandler volatility/liquidity propagation
C) DecisionMaking integration (fail-closed, trade_intent with SL/TP)
D) Schema validation
"""

import pytest
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch
import jsonschema

# EP-01.2-INT imports
from apps.reference.shared.decision_primitives.entry_plan import (
    EntryPlan,
    EntryPlanParams,
    EntryPlanResult,
    ObiMissingPolicy,
    resolve_strategy_entry_prices,
)


# =============================================================================
# A) EntryPlan Unit Tests
# =============================================================================

class TestEntryPlanFormulas:
    """Test EntryPlan SL/TP formulas for correctness."""

    @pytest.fixture
    def default_params(self) -> EntryPlanParams:
        return EntryPlanParams(
            atr_period=14,
            entry_k_atr=0.3,
            sl_k_atr=1.5,
            tp_k_atr=2.0,
            obi_weight=0.0,  # No OBI modulation for pure formula tests
            obi_mod_clamp_min=0.8,
            obi_mod_clamp_max=1.2,
            require_atr=True,
            obi_missing_policy=ObiMissingPolicy.NEUTRAL,
        )

    def test_long_stop_loss_below_ref(self, default_params):
        """LONG SL should be below ref_price."""
        ep = EntryPlan(default_params)
        result = ep.compute(side="BUY", ref_price="100.0", atr="2.0")

        sl = Decimal(result.stop_loss_price)
        ref = Decimal("100.0")
        expected_sl = ref - Decimal("1.5") * Decimal("2.0")  # 100 - 3 = 97

        assert sl == expected_sl, f"Expected SL={expected_sl}, got {sl}"
        assert sl < ref

    def test_long_take_profit_above_ref(self, default_params):
        """LONG TP should be above ref_price."""
        ep = EntryPlan(default_params)
        result = ep.compute(side="BUY", ref_price="100.0", atr="2.0")

        tp = Decimal(result.take_profit_price)
        ref = Decimal("100.0")
        expected_tp = ref + Decimal("2.0") * Decimal("2.0")  # 100 + 4 = 104

        assert tp == expected_tp, f"Expected TP={expected_tp}, got {tp}"
        assert tp > ref

    def test_short_stop_loss_above_ref(self, default_params):
        """SHORT SL should be above ref_price."""
        ep = EntryPlan(default_params)
        result = ep.compute(side="SELL", ref_price="100.0", atr="2.0")

        sl = Decimal(result.stop_loss_price)
        ref = Decimal("100.0")
        expected_sl = ref + Decimal("1.5") * Decimal("2.0")  # 100 + 3 = 103

        assert sl == expected_sl, f"Expected SL={expected_sl}, got {sl}"
        assert sl > ref

    def test_short_take_profit_below_ref(self, default_params):
        """SHORT TP should be below ref_price."""
        ep = EntryPlan(default_params)
        result = ep.compute(side="SELL", ref_price="100.0", atr="2.0")

        tp = Decimal(result.take_profit_price)
        ref = Decimal("100.0")
        expected_tp = ref - Decimal("2.0") * Decimal("2.0")  # 100 - 4 = 96

        assert tp == expected_tp, f"Expected TP={expected_tp}, got {tp}"
        assert tp < ref


class TestEntryPlanObiModulation:
    """Test OBI modulation logic."""

    @pytest.fixture
    def obi_params(self) -> EntryPlanParams:
        return EntryPlanParams(
            atr_period=14,
            entry_k_atr=0.5,
            sl_k_atr=1.5,
            tp_k_atr=2.0,
            obi_weight=1.0,  # Full OBI modulation
            obi_mod_clamp_min=0.5,  # Wide clamp for testing
            obi_mod_clamp_max=1.5,
            require_atr=True,
            obi_missing_policy=ObiMissingPolicy.NEUTRAL,
        )

    def test_long_bullish_obi_reduces_offset(self, obi_params):
        """LONG with bullish OBI (positive) should reduce entry_offset."""
        ep = EntryPlan(obi_params)

        # Bullish OBI = 0.5 → for LONG, multiplier < 1.0
        result_bull = ep.compute(
            side="BUY", ref_price="100.0", atr="2.0", obi="0.5")
        result_neutral = ep.compute(
            side="BUY", ref_price="100.0", atr="2.0", obi="0.0")

        # raw_mult = 1 + 1.0 * (-0.5) = 0.5 → clamped to 0.5
        assert result_bull.obi_multiplier < 1.0

        # Entry should be closer to ref for bullish OBI
        entry_bull = Decimal(result_bull.entry_price)
        entry_neutral = Decimal(result_neutral.entry_price)
        ref = Decimal("100.0")

        # LONG entry is below ref; smaller offset means closer to ref
        assert abs(ref - entry_bull) < abs(ref - entry_neutral)

    def test_short_bullish_obi_increases_offset(self, obi_params):
        """SHORT with bullish OBI should increase entry_offset (more cautious)."""
        ep = EntryPlan(obi_params)

        # Bullish OBI = 0.5 → for SHORT, multiplier > 1.0
        result_bull = ep.compute(
            side="SELL", ref_price="100.0", atr="2.0", obi="0.5")
        result_neutral = ep.compute(
            side="SELL", ref_price="100.0", atr="2.0", obi="0.0")

        # raw_mult = 1 + 1.0 * 0.5 = 1.5
        assert result_bull.obi_multiplier > 1.0

        # Entry should be further from ref for SHORT with bullish OBI
        entry_bull = Decimal(result_bull.entry_price)
        entry_neutral = Decimal(result_neutral.entry_price)
        ref = Decimal("100.0")

        # SHORT entry is above ref; larger offset means further from ref
        assert abs(ref - entry_bull) > abs(ref - entry_neutral)

    def test_obi_none_applies_neutral_policy(self, obi_params):
        """When OBI is None, neutral policy applies multiplier=1.0."""
        ep = EntryPlan(obi_params)
        result = ep.compute(side="BUY", ref_price="100.0", atr="2.0", obi=None)

        assert result.obi_multiplier == 1.0
        assert result.obi_policy_applied is True
        assert result.obi is None


class TestEntryPlanClamp:
    """Test OBI modulation clamp safety."""

    @pytest.fixture
    def clamp_params(self) -> EntryPlanParams:
        return EntryPlanParams(
            atr_period=14,
            entry_k_atr=0.3,
            sl_k_atr=1.5,
            tp_k_atr=2.0,
            obi_weight=5.0,  # Extreme weight to test clamp
            obi_mod_clamp_min=0.8,
            obi_mod_clamp_max=1.2,
            require_atr=True,
            obi_missing_policy=ObiMissingPolicy.NEUTRAL,
        )

    def test_extreme_obi_clamped_to_min(self, clamp_params):
        """Extreme negative raw_mult should clamp to min."""
        ep = EntryPlan(clamp_params)

        # For LONG with extreme positive OBI:
        # raw_mult = 1 + 5.0 * (-1.0) = -4.0 → clamp to 0.8
        result = ep.compute(side="BUY", ref_price="100.0",
                            atr="2.0", obi="1.0")

        assert result.obi_multiplier == 0.8

    def test_extreme_obi_clamped_to_max(self, clamp_params):
        """Extreme positive raw_mult should clamp to max."""
        ep = EntryPlan(clamp_params)

        # For SHORT with extreme positive OBI:
        # raw_mult = 1 + 5.0 * 1.0 = 6.0 → clamp to 1.2
        result = ep.compute(side="SELL", ref_price="100.0",
                            atr="2.0", obi="1.0")

        assert result.obi_multiplier == 1.2

    def test_moderate_obi_not_clamped(self, clamp_params):
        """Moderate OBI should not trigger clamp."""
        # Create params with moderate weight
        params = EntryPlanParams(
            atr_period=14,
            entry_k_atr=0.3,
            sl_k_atr=1.5,
            tp_k_atr=2.0,
            obi_weight=0.1,  # Moderate weight
            obi_mod_clamp_min=0.8,
            obi_mod_clamp_max=1.2,
            require_atr=True,
            obi_missing_policy=ObiMissingPolicy.NEUTRAL,
        )
        ep = EntryPlan(params)

        # raw_mult = 1 + 0.1 * 0.3 = 1.03 → no clamp
        result = ep.compute(side="SELL", ref_price="100.0",
                            atr="2.0", obi="0.3")

        assert 0.8 < result.obi_multiplier < 1.2
        assert result.obi_multiplier != 0.8 and result.obi_multiplier != 1.2


class TestEntryPlanValidation:
    """Test input validation and fail-closed behavior."""

    @pytest.fixture
    def require_atr_params(self) -> EntryPlanParams:
        return EntryPlanParams(
            atr_period=14,
            entry_k_atr=0.3,
            sl_k_atr=1.5,
            tp_k_atr=2.0,
            obi_weight=0.0,
            obi_mod_clamp_min=0.8,
            obi_mod_clamp_max=1.2,
            require_atr=True,  # Strict mode
            obi_missing_policy=ObiMissingPolicy.NEUTRAL,
        )

    def test_atr_not_ready_rejects_when_required(self, require_atr_params):
        """If require_atr=True and atr_ready=False, validation fails."""
        is_valid, reason = EntryPlan.validate_inputs(
            side="BUY",
            ref_price="100.0",
            atr="2.0",  # ATR value present
            atr_ready=False,  # But not ready
            params=require_atr_params,
        )

        assert is_valid is False
        assert "ATR_NOT_READY" in reason

    def test_atr_none_rejects_when_required(self, require_atr_params):
        """If require_atr=True and atr=None, validation fails."""
        is_valid, reason = EntryPlan.validate_inputs(
            side="BUY",
            ref_price="100.0",
            atr=None,
            atr_ready=True,
            params=require_atr_params,
        )

        assert is_valid is False
        assert "ATR" in reason

    def test_invalid_side_rejects(self, require_atr_params):
        """Invalid side should be rejected."""
        is_valid, reason = EntryPlan.validate_inputs(
            side="INVALID",
            ref_price="100.0",
            atr="2.0",
            atr_ready=True,
            params=require_atr_params,
        )

        assert is_valid is False
        assert "SIDE" in reason

    def test_valid_inputs_pass(self, require_atr_params):
        """Valid inputs should pass validation."""
        is_valid, reason = EntryPlan.validate_inputs(
            side="BUY",
            ref_price="100.0",
            atr="2.0",
            atr_ready=True,
            params=require_atr_params,
        )

        assert is_valid is True
        assert reason is None

    def test_soft_start_accepts_zero_atr_when_not_required(self):
        """Soft-start mode should allow zero ATR to reach compute-time floors."""
        params = EntryPlanParams(
            atr_period=14,
            entry_k_atr=0.3,
            sl_k_atr=1.5,
            tp_k_atr=2.0,
            obi_weight=0.0,
            obi_mod_clamp_min=0.8,
            obi_mod_clamp_max=1.2,
            require_atr=False,
            obi_missing_policy=ObiMissingPolicy.NEUTRAL,
        )

        is_valid, reason = EntryPlan.validate_inputs(
            side="BUY",
            ref_price="100.0",
            atr="0",
            atr_ready=False,
            params=params,
        )

        assert is_valid is True
        assert reason is None

    def test_soft_start_rejects_malformed_atr_when_present(self):
        """Soft-start mode still rejects explicit malformed ATR values."""
        params = EntryPlanParams(
            atr_period=14,
            entry_k_atr=0.3,
            sl_k_atr=1.5,
            tp_k_atr=2.0,
            obi_weight=0.0,
            obi_mod_clamp_min=0.8,
            obi_mod_clamp_max=1.2,
            require_atr=False,
            obi_missing_policy=ObiMissingPolicy.NEUTRAL,
        )

        is_valid, reason = EntryPlan.validate_inputs(
            side="BUY",
            ref_price="100.0",
            atr="abc",
            atr_ready=False,
            params=params,
        )

        assert is_valid is False
        assert reason == "ENTRY_PLAN_INVALID_ATR:abc"


# =============================================================================
# B) AuroraHandler Propagation Test
# =============================================================================

class TestAuroraHandlerPropagation:
    """Test that volatility/liquidity are passed in EVT:STRATEGY_SIGNAL_PRODUCED."""

    def test_emit_signal_includes_volatility_liquidity(self):
        """_emit_signal should include volatility and liquidity in payload."""
        import inspect
        from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler

        # Check _emit_signal source code for volatility/liquidity
        source = inspect.getsource(AuroraHandler._emit_signal)

        assert '"volatility"' in source or "'volatility'" in source, \
            "AuroraHandler._emit_signal should include 'volatility' in payload"
        assert '"liquidity"' in source or "'liquidity'" in source, \
            "AuroraHandler._emit_signal should include 'liquidity' in payload"
        assert "features.get" in source, \
            "Should extract from features dict"


# =============================================================================
# C) Schema Validation
# =============================================================================

class TestTradeIntentSchema:
    """Test trade_intent_v1.json schema accepts EP-01.2 fields."""

    @pytest.fixture
    def schema(self):
        schema_path = Path(__file__).parent.parent.parent / \
            "apps/reference/domains/decision_making/intent/schemas/trade_intent_v1.json"
        if not schema_path.exists():
            # Try relative path from workspace root
            schema_path = Path(
                "/home/wekabeka/Музыка/Phenix/apps/reference/domains/decision_making/intent/schemas/trade_intent_v1.json")

        with open(schema_path) as f:
            return json.load(f)

    @pytest.fixture
    def valid_base_payload(self):
        return {
            "instrument": "BTCUSDT",
            "side": "buy",
            "p": "0.55",
            "payoff_ratio_r": "2.0",
            "tca_budget": {
                "max_slippage_bps": "10",
                "max_latency_ms": 100,
                "maker_preference": "allow"
            },
            "risk_budget": {
                "trade_cvar95_max_bps": "200",
                "session_cvar95_max_bps": "500"
            },
            "size": {
                "kelly_fraction": "0.1",
                "notional_cap_usd": "1000.00"
            },
            "order": {
                "price_ref": "50000.00",
                "qty": "0.001",
                "price": "50000.00",
                "reduce_only": False,
                "order_type": "LIMIT",  # ORDER-POLICY-01: required
                "tif": "GTX",
            },
            "valid_for_ms": 5000,
            "why": ["test"],
            "dto_version": "1.0.0",
            "schema_ref": "..."
        }

    def test_schema_accepts_stop_target_price(self, schema, valid_base_payload):
        """Schema should accept stop_price and target_price fields."""
        payload = {
            **valid_base_payload,
            "stop_price": "49000.00",
            "target_price": "52000.00",
        }

        # Should not raise
        jsonschema.validate(payload, schema)

    def test_schema_accepts_null_stop_target(self, schema, valid_base_payload):
        """Schema should accept null stop_price and target_price."""
        payload = {
            **valid_base_payload,
            "stop_price": None,
            "target_price": None,
        }

        # Should not raise
        jsonschema.validate(payload, schema)

    def test_schema_accepts_entry_plan_trace(self, schema, valid_base_payload):
        """Schema should accept entry_plan trace object."""
        payload = {
            **valid_base_payload,
            "entry_plan": {
                "ref_price": "50000.00",
                "atr": "500.0",
                "obi": "0.15",
                "obi_multiplier": 0.95,
                "obi_policy_applied": False
            }
        }

        # Should not raise
        jsonschema.validate(payload, schema)

    def test_schema_accepts_null_entry_plan(self, schema, valid_base_payload):
        """Schema should accept null entry_plan."""
        payload = {
            **valid_base_payload,
            "entry_plan": None
        }

        # Should not raise
        jsonschema.validate(payload, schema)

    def test_resolved_entry_plan_trace_matches_schema_contract(self, schema, valid_base_payload):
        """Gateway helper should emit an entry_plan trace accepted by trade_intent schema."""
        ep_cfg = SimpleNamespace(
            enabled=True,
            atr_period=14,
            entry_k_atr=0.3,
            sl_k_atr=1.5,
            tp_k_atr=2.0,
            obi_weight=0.18,
            obi_mod_clamp_min=0.8,
            obi_mod_clamp_max=1.2,
            require_atr=True,
            obi_missing_policy="neutral",
        )
        config = SimpleNamespace(
            domains=SimpleNamespace(
                decision_making=SimpleNamespace(entry_plan=ep_cfg)
            )
        )
        rejects = []

        stop_price, target_price, entry_plan_trace = resolve_strategy_entry_prices(
            symbol="BTCUSDT",
            strategy_id="mean_reversion",
            side="BUY",
            rid="ep-schema-1",
            price_ctx={"entry_price": "50000.00"},
            pld={
                "volatility": {"atr_14": "500.0", "atr_ready": True},
                "liquidity": {"obi_close": "0.15"},
            },
            entry_price_dec=Decimal("50000.00"),
            why_chain=[],
            config=config,
            logger=MagicMock(),
            reject_fn=lambda **kwargs: rejects.append(kwargs),
        )

        assert rejects == []
        payload = {
            **valid_base_payload,
            "stop_price": stop_price,
            "target_price": target_price,
            "entry_plan": entry_plan_trace,
        }

        jsonschema.validate(payload, schema)


# =============================================================================
# D) Config Validation
# =============================================================================

class TestEntryPlanConfig:
    """Test EntryPlanConfig Pydantic model."""

    def test_valid_config_loads(self):
        """Valid config should load without errors."""
        from apps.reference.config_models import EntryPlanConfig

        cfg = EntryPlanConfig(
            enabled=True,
            atr_period=14,
            entry_k_atr=0.3,
            sl_k_atr=1.5,
            tp_k_atr=2.0,
            obi_weight=0.3,
            obi_mod_clamp_min=0.8,
            obi_mod_clamp_max=1.2,
            require_atr=True,
            obi_missing_policy="neutral",
        )

        assert cfg.enabled is True
        assert cfg.atr_period == 14

    def test_invalid_clamp_order_rejected(self):
        """obi_mod_clamp_min > obi_mod_clamp_max should be rejected."""
        from apps.reference.config_models import EntryPlanConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            EntryPlanConfig(
                enabled=True,
                atr_period=14,
                entry_k_atr=0.3,
                sl_k_atr=1.5,
                tp_k_atr=2.0,
                obi_weight=0.3,
                obi_mod_clamp_min=1.5,  # > max (invalid)
                obi_mod_clamp_max=1.2,
                require_atr=True,
                obi_missing_policy="neutral",
            )

    def test_extra_fields_forbidden(self):
        """Extra fields should be rejected (extra='forbid')."""
        from apps.reference.config_models import EntryPlanConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            EntryPlanConfig(
                enabled=True,
                atr_period=14,
                entry_k_atr=0.3,
                sl_k_atr=1.5,
                tp_k_atr=2.0,
                obi_weight=0.3,
                obi_mod_clamp_min=0.8,
                obi_mod_clamp_max=1.2,
                require_atr=True,
                obi_missing_policy="neutral",
                unknown_field="should_fail",  # Extra field
            )
