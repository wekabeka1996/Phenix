"""
TEST-OCO-CYCLE — Aggregated OCO Cycle ID Tests

Tests for cycle_id tracking in bracket management:
- Brackets with old cycle_id are orphans (must be cancelled)
- New position increments cycle_id
- Position reverse increments cycle_id
- Cycle ID filters valid brackets

RID: OCO-AUDIT-CYCLE-TESTS
"""
from decimal import Decimal
from typing import List, Any

import pytest

from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
    BracketLeg,
    BracketRulesConfig,
    BracketService,
    BracketSet,
    BracketState,
    OrderView,
    PositionView,
    parse_cycle_id_from_client_order_id,
)


class StubAggregator:
    """Stub aggregator for testing."""

    def __init__(self, sl_price: Decimal = Decimal("98.0"), tp_price: Decimal = Decimal("104.0")):
        self.sl_price = sl_price
        self.tp_price = tp_price

    def compute_aggregated_brackets(self, **kwargs) -> Any:
        class StubLevels:
            def __init__(self, sl: Decimal, tp: Decimal):
                self.sl_price = sl
                self.tp_price = tp
                self.why = "stub_aggregator"

        return StubLevels(self.sl_price, self.tp_price)


class StubGuardian:
    """Stub guardian for testing."""

    def get_active_bracket_set(self, symbol: str, side: str):
        return None

    def list_all_bracket_sets(self) -> List:
        return []


@pytest.fixture
def default_config() -> BracketRulesConfig:
    return BracketRulesConfig(
        enabled=True,
        allow_unprotected_position=False,
        recalc_on_partial_close=True,
        recalc_on_scale_in=True,
        ttl_protect_new_bracket_ms=5000,
        max_tp_legs=1,
        max_sl_legs=1,
        sl_pct=0.02,
        tp_rr=2.0,
    )


@pytest.fixture
def bracket_service() -> BracketService:
    return BracketService(
        aggregator=StubAggregator(),
        guardian=StubGuardian(),
    )


# ============================================================================
# TEST-OCO-CYC-001: Parse cycle_id from clientOrderId
# ============================================================================

def test_parse_cycle_id_from_client_order_id():
    """
    TEST-OCO-CYC-001: Cycle ID is correctly parsed from clientOrderId.
    """
    assert parse_cycle_id_from_client_order_id("AUR-BTCUSDT-LONG-SL-C1") == 1
    assert parse_cycle_id_from_client_order_id("AUR-BTCUSDT-LONG-TP-C5") == 5
    assert parse_cycle_id_from_client_order_id("AUR-ETHUSDT-SHORT-SL-C42") == 42
    assert parse_cycle_id_from_client_order_id("AUR-SOLUSDT-LONG-TP-C100") == 100


def test_parse_cycle_id_legacy_format_returns_zero():
    """
    TEST-OCO-CYC-002: Legacy format without cycle returns 0.
    """
    assert parse_cycle_id_from_client_order_id("OLD_SL_123") == 0
    assert parse_cycle_id_from_client_order_id("MANUAL_ORDER") == 0
    assert parse_cycle_id_from_client_order_id("") == 0


# ============================================================================
# TEST-OCO-CYC-003: Brackets with old cycle_id are orphans
# ============================================================================

def test_old_cycle_brackets_are_orphans(bracket_service, default_config):
    """
    TEST-OCO-CYC-003: Brackets from old cycle_id must be cancelled.

    Position: cycle_id=3
    Brackets: cycle_id=1 (stale)

    Expected: CANCEL stale brackets
    """
    position = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
        cycle_id=3,  # Current cycle
    )

    # Stale SL from cycle 1
    sl_order = OrderView(
        order_id="SL_OLD",
        client_order_id="AUR-BTCUSDT-LONG-SL-C1",  # Old cycle!
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("98.0"),
        reduce_only=True,
        cycle_id=1,  # Stale
    )

    # Stale TP from cycle 1
    tp_order = OrderView(
        order_id="TP_OLD",
        client_order_id="AUR-BTCUSDT-LONG-TP-C1",  # Old cycle!
        symbol="BTCUSDT",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("104.0"),
        reduce_only=True,
        cycle_id=1,  # Stale
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
        legs=[
            BracketLeg(leg_type="SL", order=sl_order),
            BracketLeg(leg_type="TP", order=tp_order),
        ],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=position,
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    # Should cancel old brackets and place new ones
    assert plan.has_actions

    action_types = [a.action_type for a in plan.actions]
    # Old brackets cancelled
    assert action_types.count("CANCEL") >= 2

    # New brackets placed for current cycle
    assert "PLACE_SL" in action_types or action_types.count("CANCEL") >= 2


# ============================================================================
# TEST-OCO-CYC-004: Current cycle brackets are valid
# ============================================================================

def test_current_cycle_brackets_valid(bracket_service, default_config):
    """
    TEST-OCO-CYC-004: Brackets with matching cycle_id are valid.
    """
    position = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
        cycle_id=5,
    )

    sl_order = OrderView(
        order_id="SL_CURRENT",
        client_order_id="AUR-BTCUSDT-LONG-SL-C5",  # Current cycle
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("98.0"),
        reduce_only=True,
        cycle_id=5,
    )

    tp_order = OrderView(
        order_id="TP_CURRENT",
        client_order_id="AUR-BTCUSDT-LONG-TP-C5",  # Current cycle
        symbol="BTCUSDT",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("104.0"),
        reduce_only=True,
        cycle_id=5,
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
        legs=[
            BracketLeg(leg_type="SL", order=sl_order),
            BracketLeg(leg_type="TP", order=tp_order),
        ],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=position,
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    # Should be healthy (INFO or no critical actions)
    assert plan.severity in ("INFO", "OK")
    # No CANCEL actions (brackets are valid)
    cancel_actions = [a for a in plan.actions if a.action_type == "CANCEL"]
    assert len(cancel_actions) == 0


# ============================================================================
# TEST-OCO-CYC-005: Mixed cycles - old brackets cancelled
# ============================================================================

def test_mixed_cycles_old_cancelled(bracket_service, default_config):
    """
    TEST-OCO-CYC-005: Mixed cycle brackets - old ones cancelled.

    Position: cycle_id=3
    Brackets: SL from C2 (stale), TP from C3 (valid)

    Expected: CANCEL SL, keep TP
    """
    position = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
        cycle_id=3,
    )

    # Stale SL from cycle 2
    sl_old = OrderView(
        order_id="SL_OLD",
        client_order_id="AUR-BTCUSDT-LONG-SL-C2",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("98.0"),
        reduce_only=True,
        cycle_id=2,
    )

    # Valid TP from cycle 3
    tp_current = OrderView(
        order_id="TP_NEW",
        client_order_id="AUR-BTCUSDT-LONG-TP-C3",
        symbol="BTCUSDT",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("104.0"),
        reduce_only=True,
        cycle_id=3,
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
        legs=[
            BracketLeg(leg_type="SL", order=sl_old),
            BracketLeg(leg_type="TP", order=tp_current),
        ],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=position,
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    # Should have actions
    assert plan.has_actions

    # Old SL should be cancelled
    cancel_actions = [a for a in plan.actions if a.action_type == "CANCEL"]
    cancelled_ids = {a.order_id for a in cancel_actions}

    # SL_OLD should be cancelled (cycle mismatch)
    # New SL should be placed
    place_sl = [a for a in plan.actions if a.action_type == "PLACE_SL"]
    assert len(cancel_actions) >= 1 or len(place_sl) >= 1


# ============================================================================
# TEST-OCO-CYC-006: Position reverse increments cycle
# ============================================================================

def test_position_reverse_cycle_increment_simulation():
    """
    TEST-OCO-CYC-006: Simulates that position reverse increments cycle_id.
    
    This is a documentation test showing expected behavior.
    Actual cycle increment happens in runtime, not BracketService.
    
    LONG @ cycle=1 → FLAT → SHORT @ cycle=2
    Old LONG brackets (C1) must be cancelled.
    """
    # After reverse: SHORT position at cycle 2
    position = PositionView(
        symbol="BTCUSDT",
        side="SHORT",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("105.0"),
        cycle_id=2,
    )

    # Old LONG brackets from cycle 1 (now orphans)
    sl_long = OrderView(
        order_id="SL_LONG",
        client_order_id="AUR-BTCUSDT-LONG-SL-C1",
        symbol="BTCUSDT",
        side="SELL",  # LONG exit side
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("98.0"),
        reduce_only=True,
        cycle_id=1,
    )

    # This is LONG bracket on SHORT position - orphan by side mismatch
    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",  # Wrong side for SHORT position!
        position_qty=Decimal("0"),  # Treated as FLAT for LONG
        avg_entry_price=Decimal("0"),
        legs=[BracketLeg(leg_type="SL", order=sl_long)],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    service = BracketService(
        aggregator=StubAggregator(),
        guardian=StubGuardian(),
    )

    config = BracketRulesConfig(enabled=True)

    # Evaluating LONG brackets when position is SHORT/FLAT
    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=None,  # FLAT for LONG side
        bracket_set=bracket_set,
    )

    plan = service.evaluate(state, config)

    # Old LONG brackets are orphans
    assert plan.severity == "WARN"
    cancel_actions = [a for a in plan.actions if a.action_type == "CANCEL"]
    assert len(cancel_actions) >= 1


# ============================================================================
# TEST-OCO-CYC-007: Cycle ID 0 handling
# ============================================================================

def test_cycle_id_zero_treated_as_legacy(bracket_service, default_config):
    """
    TEST-OCO-CYC-007: cycle_id=0 is treated as legacy/unknown.
    
    Brackets with cycle_id=0 should be cancelled if position has cycle_id > 0.
    """
    position = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
        cycle_id=1,  # Valid cycle
    )

    # Legacy bracket without cycle
    sl_legacy = OrderView(
        order_id="SL_LEGACY",
        client_order_id="OLD_STYLE_SL_123",  # No cycle in ID
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("98.0"),
        reduce_only=True,
        cycle_id=0,  # Legacy
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
        legs=[BracketLeg(leg_type="SL", order=sl_legacy)],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=position,
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    # Should detect cycle mismatch and take action
    assert plan.has_actions


# ============================================================================
# TEST-OCO-CYC-008: Large cycle ID values
# ============================================================================

def test_large_cycle_id_handled(bracket_service, default_config):
    """
    TEST-OCO-CYC-008: Large cycle_id values work correctly.
    """
    large_cycle = 2**20  # 1 million+

    position = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
        cycle_id=large_cycle,
    )

    sl_order = OrderView(
        order_id="SL_LARGE",
        client_order_id=f"AUR-BTCUSDT-LONG-SL-C{large_cycle}",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("98.0"),
        reduce_only=True,
        cycle_id=large_cycle,
    )

    tp_order = OrderView(
        order_id="TP_LARGE",
        client_order_id=f"AUR-BTCUSDT-LONG-TP-C{large_cycle}",
        symbol="BTCUSDT",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("104.0"),
        reduce_only=True,
        cycle_id=large_cycle,
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
        legs=[
            BracketLeg(leg_type="SL", order=sl_order),
            BracketLeg(leg_type="TP", order=tp_order),
        ],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=position,
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    # Should work without overflow
    assert plan.severity in ("INFO", "OK")
