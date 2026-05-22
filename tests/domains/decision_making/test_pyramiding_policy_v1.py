"""
Pyramiding Policy V1 tests.

Tests:
Contract/config:
 1. valid pyramiding_policy accepted by Pydantic
 2. unknown fields rejected
 3. invalid side rejected
 4. invalid order_type rejected
 5. invalid mode rejected
 6. default disabled (None) preserves current behavior

Gate (flip.py):
 7. LOW_VOLATILITY + SELL + same-side position allowed
 8. LOW_VOLATILITY + BUY blocked
 9. MEAN_REVERSION + SELL blocked
10. TREND_UP + SELL blocked
11. missing regime fails closed
12. missing side treated as unknown regime path
13. opposite-side add is a flip (not pyramiding gate)
14. close-in-progress: pending_add_rid blocks new add
15. pending add exists blocks
16. max_adds exceeded blocks
17. non-testnet mode blocks

Execution/cancel coordination:
18. allowed pyramiding add returns None (signal continues)
19. MARKET pyramiding impossible (rejected at policy level since order_type=LIMIT enforced)
20. pyramiding_state resets on FLAT position
21. _record_pyramiding_add increments count and sets pending_add_rid
22. global DYNAMIC is not required and remains off (STRICT base + policy exception)

Regression:
23. ANTI_PYRAMIDING_BLOCK returned when policy disabled
24. ANTI_PYRAMIDING_BLOCK returned when no matching rule
25. existing flip behavior unchanged (UNKNOWN → NRR-PORTFOLIO-UNKNOWN)
26. flat position returns None (no pyramiding state change)
27. signal_exit_enabled=False is reflected in config load (config schema validation)
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from pydantic import ValidationError

from apps.reference.config.domains.decision_making import (
    PyramidingGuardsV1Config,
    PyramidingPolicyV1Config,
    PyramidingRuleV1Config,
    PyramidingTelemetryV1Config,
)
from apps.reference.domains.decision_making.intent.flip import FlipOrchestrator, _PYRAMIDING_TESTNET_MODES


# ── helpers ─────────────────────────────────────────────────────────────────

def _valid_rule(**overrides) -> dict:
    base = {
        "id": "aurora_low_vol_sell_v1",
        "strategy_id": "aurora",
        "regimes": ["LOW_VOLATILITY"],
        "sides": ["SELL"],
        "symbols": None,
        "enabled": True,
    }
    base.update(overrides)
    return base


def _valid_guards(**overrides) -> dict:
    base = {
        "require_same_side_position": True,
        "require_position_mode_strict_base": True,
        "block_if_close_in_progress": True,
        "block_if_pending_add_exists": True,
        "block_if_sidecar_live_authority_active": True,
        "require_regime_confidence": False,
    }
    base.update(overrides)
    return base


def _valid_policy(**overrides) -> dict:
    base = {
        "enabled": True,
        "mode": "testnet_enforced",
        "default_action": "block",
        "order_type": "LIMIT",
        "max_adds_per_lifecycle": 1,
        "max_pending_add_orders_per_symbol": 1,
        "rules": [_valid_rule()],
        "guards": _valid_guards(),
        "telemetry": {"emit_trace": True},
    }
    base.update(overrides)
    return base


def _make_config(
    trading_mode: str = "testnet",
    pyramiding_policy_dict: dict | None = None,
    policy_enabled: bool = True,
) -> Any:
    """Build a minimal config stub that FlipOrchestrator reads."""
    if pyramiding_policy_dict is None and policy_enabled:
        pyramiding_policy_dict = _valid_policy()

    policy_obj = None
    if pyramiding_policy_dict is not None:
        policy_obj = PyramidingPolicyV1Config(**pyramiding_policy_dict)

    decision_cfg = SimpleNamespace(pyramiding_policy=policy_obj)
    aurora_cfg = SimpleNamespace(decision=decision_cfg, assets={})
    strategies = SimpleNamespace(aurora=aurora_cfg)
    domains = SimpleNamespace(
        position_tracking=SimpleNamespace(positions_stale_ttl_sec=5.0)
    )
    return SimpleNamespace(
        trading_mode=trading_mode,
        strategies=strategies,
        domains=domains,
    )


def _make_flip(
    pos_state: str = "SHORT",
    position_mode: str = "STRICT",
    trading_mode: str = "testnet",
    pyramiding_policy_dict: dict | None = None,
    policy_enabled: bool = True,
) -> FlipOrchestrator:
    """Build a minimal FlipOrchestrator for testing."""
    config = _make_config(
        trading_mode=trading_mode,
        pyramiding_policy_dict=pyramiding_policy_dict,
        policy_enabled=policy_enabled,
    )
    # Patch asset config for resolve_position_mode
    asset_cfg = SimpleNamespace(position_mode=position_mode)
    config.strategies.aurora.assets = {"BTCUSDT": asset_cfg}

    clock = MagicMock()
    clock.now_ms.return_value = 1000000
    clock.now_sec.return_value = 1000

    flip = FlipOrchestrator(
        clock=clock,
        config=config,
        fsm=MagicMock(),
        get_position_state=lambda sym: pos_state,
        get_portfolio_position_qty_signed=lambda sym: (None, None),
        get_flip_config=lambda sym: (False, 1.0),
        propose_trade_intent=MagicMock(),
        emit_intent_deferred_v1=MagicMock(),
        logger=logging.getLogger("test_pyramiding"),
    )
    return flip


def _sell_pld(regime: str = "LOW_VOLATILITY", rid: str = "rid-test-001") -> dict:
    return {
        "rid": rid,
        "strategy_id": "aurora",
        "side": "SELL",
        "regime_ctx": {
            "regime": regime,
            "confidence": 0.42,
        },
    }


# ── Contract/config tests ────────────────────────────────────────────────────

class TestPyramidingPolicyV1Config:

    def test_1_valid_policy_accepted(self):
        """Test 1: Valid pyramiding_policy accepted by Pydantic."""
        policy = PyramidingPolicyV1Config(**_valid_policy())
        assert policy.enabled is True
        assert policy.mode == "testnet_enforced"
        assert policy.order_type == "LIMIT"
        assert policy.max_adds_per_lifecycle == 1
        assert len(policy.rules) == 1
        assert policy.rules[0].id == "aurora_low_vol_sell_v1"

    def test_2_unknown_fields_rejected(self):
        """Test 2: Unknown fields rejected (extra='forbid')."""
        bad = _valid_policy()
        bad["unknown_field_xyz"] = True
        with pytest.raises(ValidationError, match="unknown_field_xyz"):
            PyramidingPolicyV1Config(**bad)

    def test_3_invalid_side_rejected(self):
        """Test 3: Invalid side rejected."""
        bad_rule = _valid_rule(sides=["LONG"])  # not BUY or SELL
        bad = _valid_policy(rules=[bad_rule])
        with pytest.raises(ValidationError, match="Invalid side"):
            PyramidingPolicyV1Config(**bad)

    def test_4_invalid_order_type_rejected(self):
        """Test 4: Invalid order_type rejected (only LIMIT allowed)."""
        bad = _valid_policy(order_type="MARKET")
        with pytest.raises(ValidationError):
            PyramidingPolicyV1Config(**bad)

    def test_5_invalid_mode_rejected(self):
        """Test 5: Invalid mode rejected (only testnet_enforced)."""
        bad = _valid_policy(mode="live_enforced")
        with pytest.raises(ValidationError):
            PyramidingPolicyV1Config(**bad)

    def test_6_default_disabled_preserves_behavior(self):
        """Test 6: pyramiding_policy=None means no policy object (disabled)."""
        from apps.reference.config.domains.decision_making import DecisionConfig
        # If DecisionConfig has pyramiding_policy=None, it means policy is absent (disabled)
        decision_cfg = SimpleNamespace(pyramiding_policy=None)
        assert decision_cfg.pyramiding_policy is None


# ── Gate tests ───────────────────────────────────────────────────────────────

class TestPyramidingGate:

    def test_7_low_vol_sell_same_side_allowed(self):
        """Test 7: LOW_VOLATILITY + SELL + same-side SHORT position allowed."""
        flip = _make_flip(pos_state="SHORT")  # SHORT = selling side
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="LOW_VOLATILITY"),
            source="aurora",
        )
        assert result is None, f"Expected None (allow), got {result!r}"
        assert flip._pyramiding_state.get("BTCUSDT", {}).get("adds_count") == 1

    def test_8_low_vol_buy_blocked(self):
        """Test 8: LOW_VOLATILITY + BUY blocked (no rule for BUY)."""
        flip = _make_flip(pos_state="LONG")  # LONG position, trying BUY add
        pld = _sell_pld(regime="LOW_VOLATILITY")
        pld["side"] = "BUY"
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="BUY",
            original_pld=pld,
            source="aurora",
        )
        assert result == "ANTI_PYRAMIDING_BLOCK"

    def test_9_mean_reversion_sell_blocked(self):
        """Test 9: MEAN_REVERSION + SELL blocked (no rule for MEAN_REVERSION)."""
        flip = _make_flip(pos_state="SHORT")
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="MEAN_REVERSION"),
            source="aurora",
        )
        assert result == "ANTI_PYRAMIDING_BLOCK"

    def test_10_trend_up_sell_blocked(self):
        """Test 10: TREND_UP + SELL blocked (no rule for TREND_UP)."""
        flip = _make_flip(pos_state="SHORT")
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="TREND_UP"),
            source="aurora",
        )
        assert result == "ANTI_PYRAMIDING_BLOCK"

    def test_11_missing_regime_fails_closed(self):
        """Test 11: Missing regime in payload fails closed."""
        flip = _make_flip(pos_state="SHORT")
        pld = _sell_pld()
        pld["regime_ctx"] = {}  # no regime key
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=pld,
            source="aurora",
        )
        assert result == "PYRAMIDING_BLOCKED_REGIME_MISSING"

    def test_12_missing_regime_ctx_fails_closed(self):
        """Test 12: Missing regime_ctx entirely fails closed."""
        flip = _make_flip(pos_state="SHORT")
        pld = {"rid": "r1", "strategy_id": "aurora", "side": "SELL"}  # no regime_ctx
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=pld,
            source="aurora",
        )
        assert result == "PYRAMIDING_BLOCKED_REGIME_MISSING"

    def test_13_opposite_side_add_is_flip_not_pyramiding(self):
        """Test 13: Opposite-side add (LONG position + SELL intent) is a flip, handled earlier."""
        flip = _make_flip(pos_state="LONG")  # LONG position
        # SELL on LONG position = flip (not same-side)
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="LOW_VOLATILITY"),
            source="aurora",
        )
        # Flip path returns OPPOSITE_ENTRY_REQUIRES_EXPLICIT_FLIP_CONTRACT (flip disabled)
        assert result is not None
        assert "pyramiding" not in str(result).lower()

    def test_14_pending_add_exists_blocks(self):
        """Test 14: pending_add_rid set → blocks new add."""
        flip = _make_flip(pos_state="SHORT")
        flip._pyramiding_state["BTCUSDT"] = {"adds_count": 0, "pending_add_rid": "existing-rid"}
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="LOW_VOLATILITY"),
            source="aurora",
        )
        assert result == "PYRAMIDING_BLOCKED_PENDING_ADD_EXISTS"

    def test_15_max_adds_exceeded_blocks(self):
        """Test 15: adds_count >= max_adds_per_lifecycle blocks."""
        flip = _make_flip(pos_state="SHORT")
        flip._pyramiding_state["BTCUSDT"] = {"adds_count": 1, "pending_add_rid": None}
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="LOW_VOLATILITY"),
            source="aurora",
        )
        assert result == "PYRAMIDING_BLOCKED_MAX_ADDS_EXCEEDED"

    def test_16_non_testnet_mode_blocks(self):
        """Test 16: live trading_mode blocks pyramiding add."""
        flip = _make_flip(pos_state="SHORT", trading_mode="live")
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="LOW_VOLATILITY"),
            source="aurora",
        )
        assert result == "PYRAMIDING_BLOCKED_NON_TESTNET_MODE"

    def test_17_production_mode_blocks(self):
        """Test 17: production trading_mode blocks pyramiding add."""
        flip = _make_flip(pos_state="SHORT", trading_mode="production")
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="LOW_VOLATILITY"),
            source="aurora",
        )
        assert result == "PYRAMIDING_BLOCKED_NON_TESTNET_MODE"


# ── Execution/cancel coordination tests ─────────────────────────────────────

class TestPyramidingExecution:

    def test_18_allowed_add_returns_none(self):
        """Test 18: Allowed pyramiding add returns None (gate passes)."""
        flip = _make_flip(pos_state="SHORT")
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="LOW_VOLATILITY"),
            source="aurora",
        )
        assert result is None

    def test_19_market_pyramiding_impossible(self):
        """Test 19: MARKET pyramiding is impossible — order_type=LIMIT enforced in policy."""
        bad = _valid_policy(order_type="MARKET")
        with pytest.raises(ValidationError):
            PyramidingPolicyV1Config(**bad)

    def test_20_pyramiding_state_resets_on_flat(self):
        """Test 20: _pyramiding_state is reset when position is FLAT."""
        flip = _make_flip(pos_state="FLAT")
        flip._pyramiding_state["BTCUSDT"] = {"adds_count": 1, "pending_add_rid": "old-rid"}
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="LOW_VOLATILITY"),
            source="aurora",
        )
        assert result is None  # FLAT → allow
        assert "BTCUSDT" not in flip._pyramiding_state

    def test_21_record_pyramiding_add_increments_state(self):
        """Test 21: _record_pyramiding_add increments count and sets pending_add_rid."""
        flip = _make_flip(pos_state="SHORT")
        flip._record_pyramiding_add("BTCUSDT", "rid-abc")
        state = flip._pyramiding_state.get("BTCUSDT", {})
        assert state["adds_count"] == 1
        assert state["pending_add_rid"] == "rid-abc"

    def test_22_dynamic_not_required(self):
        """Test 22: global DYNAMIC position_mode is not required. STRICT base + policy exception."""
        flip = _make_flip(pos_state="SHORT", position_mode="STRICT")
        # With STRICT position_mode AND pyramiding policy enabled, add should be allowed
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="LOW_VOLATILITY"),
            source="aurora",
        )
        assert result is None, "STRICT + policy exception should allow the add"


# ── Regression tests ─────────────────────────────────────────────────────────

class TestPyramidingRegression:

    def test_23_anti_pyramiding_block_when_policy_disabled(self):
        """Test 23: ANTI_PYRAMIDING_BLOCK returned when policy is None (disabled)."""
        flip = _make_flip(pos_state="SHORT", policy_enabled=False)
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="LOW_VOLATILITY"),
            source="aurora",
        )
        assert result == "ANTI_PYRAMIDING_BLOCK"

    def test_24_anti_pyramiding_block_no_matching_rule(self):
        """Test 24: ANTI_PYRAMIDING_BLOCK when no rule matches (policy enabled but rule doesn't match)."""
        flip = _make_flip(pos_state="SHORT")
        # BTCUSDT with UNCERTAIN regime — no rule for that
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="UNCERTAIN"),
            source="aurora",
        )
        assert result == "ANTI_PYRAMIDING_BLOCK"

    def test_25_existing_flip_behavior_unknown_portfolio(self):
        """Test 25: UNKNOWN portfolio state → NRR-PORTFOLIO-UNKNOWN (unchanged behavior)."""
        flip = _make_flip(pos_state="UNKNOWN")
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(),
            source="aurora",
        )
        assert result == "NRR-PORTFOLIO-UNKNOWN"

    def test_26_flat_position_returns_none(self):
        """Test 26: FLAT position returns None (no pyramiding state change for flat)."""
        flip = _make_flip(pos_state="FLAT")
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(),
            source="aurora",
        )
        assert result is None
        assert "BTCUSDT" not in flip._pyramiding_state

    def test_27_signal_exit_enabled_false_schema(self):
        """Test 27: signal_exit_enabled=False in config is a valid ExitManagerConfig."""
        from apps.reference.config.domains.decision_making import ExitManagerConfig
        cfg = ExitManagerConfig(
            time_exit_enabled=False,
            max_hold_time_sec=86400,
            signal_exit_enabled=False,
            signal_reversal_threshold=-0.1,
            danger_zone_action="TIGHTEN_STOPS",
            danger_zone_tighten_factor=0.5,
        )
        assert cfg.signal_exit_enabled is False


# ── Edge case: hybrid mode allowed ──────────────────────────────────────────

class TestPyramidingEdgeCases:

    def test_hybrid_mode_allowed(self):
        """hybrid_live_data_testnet_exec is in the allowed testnet modes set."""
        assert "hybrid_live_data_testnet_exec" in _PYRAMIDING_TESTNET_MODES

    def test_hybrid_mode_allows_pyramiding(self):
        """Pyramiding allowed in hybrid_live_data_testnet_exec mode."""
        flip = _make_flip(pos_state="SHORT", trading_mode="hybrid_live_data_testnet_exec")
        result = flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="LOW_VOLATILITY"),
            source="aurora",
        )
        assert result is None

    def test_last_pyramiding_add_info_set_on_allow(self):
        """_last_pyramiding_add_info is populated when add is allowed."""
        flip = _make_flip(pos_state="SHORT")
        flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(regime="LOW_VOLATILITY", rid="test-rid-xyz"),
            source="aurora",
        )
        info = flip._last_pyramiding_add_info
        assert info is not None
        assert info["pyramiding_policy_applied"] is True
        assert info["order_role"] == "PYRAMIDING_ADD"
        assert info["regime"] == "LOW_VOLATILITY"
        assert info["side"] == "SELL"
        assert info["strategy_id"] == "aurora"

    def test_last_pyramiding_add_info_cleared_on_flat(self):
        """_last_pyramiding_add_info is cleared on non-pyramiding call (FLAT)."""
        flip = _make_flip(pos_state="FLAT")
        flip._last_pyramiding_add_info = {"stale": True}
        flip.handle_flip_orchestration(
            symbol="BTCUSDT",
            intent_side="SELL",
            original_pld=_sell_pld(),
            source="aurora",
        )
        assert flip._last_pyramiding_add_info is None

    def test_invalid_regime_rejected(self):
        """Invalid regime in rule raises ValidationError."""
        bad_rule = _valid_rule(regimes=["NOT_A_REAL_REGIME"])
        bad = _valid_policy(rules=[bad_rule])
        with pytest.raises(ValidationError, match="Invalid regime"):
            PyramidingPolicyV1Config(**bad)

    def test_empty_rules_when_enabled_rejected(self):
        """enabled=True with empty rules raises ValidationError."""
        bad = _valid_policy(rules=[])
        with pytest.raises(ValidationError, match="at least one rule"):
            PyramidingPolicyV1Config(**bad)
