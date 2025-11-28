"""
Tests for BracketService tick_size propagation.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
    BracketService,
    PositionView,
    BracketRulesConfig,
    BracketState
)

@pytest.fixture
def bracket_service():
    # Mock aggregator to verify it receives correct constraints
    aggregator = MagicMock()
    # Setup aggregator to return dummy levels
    aggregator.compute_aggregated_brackets.return_value = MagicMock(
        sl_price=Decimal("100"),
        tp_price=Decimal("200")
    )
    return BracketService(aggregator=aggregator, guardian=MagicMock())

def test_build_state_propagates_tick_size(bracket_service):
    """Verify that tick_size passed to build_state ends up in BracketState."""
    pos = PositionView(
        symbol="SHIBUSDT",
        side="LONG",
        qty=Decimal("1000000"),
        avg_entry_price=Decimal("0.00002"),
    )

    # Case 1: Default tick size
    states_default = bracket_service.build_state(
        positions=[pos],
        orders=[],
        symbol="SHIBUSDT",
        side="LONG"
    )
    state_default = states_default[("SHIBUSDT", "LONG")]
    assert state_default.tick_size == Decimal("0.01")

    # Case 2: Custom tick size
    custom_tick = Decimal("0.000001")
    states_custom = bracket_service.build_state(
        positions=[pos],
        orders=[],
        symbol="SHIBUSDT",
        side="LONG",
        tick_size=custom_tick
    )
    state_custom = states_custom[("SHIBUSDT", "LONG")]
    assert state_custom.tick_size == custom_tick

def test_evaluate_uses_tick_size_in_aggregator(bracket_service):
    """Verify that evaluate() passes the correct tick_size to aggregator."""
    custom_tick = Decimal("0.5")

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=PositionView(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("1.0"),
            avg_entry_price=Decimal("50000")
        ),
        bracket_set=None,
        tick_size=custom_tick
    )

    cfg = BracketRulesConfig(
        enabled=True,
        recreate_missing_brackets=True,
        sl_pct=0.01,
        tp_rr=2.0
    )

    # Run evaluate
    bracket_service.evaluate(state, cfg)

    # Check aggregator call
    assert bracket_service._aggregator.compute_aggregated_brackets.called

    # Verify all calls used the correct tick size
    for call in bracket_service._aggregator.compute_aggregated_brackets.call_args_list:
        constraints = call.kwargs["constraints"]
        assert constraints.tick_size == custom_tick
        assert constraints.min_price == custom_tick

def test_evaluate_uses_default_tick_size_if_not_provided(bracket_service):
    """Verify fallback to 0.01 if tick_size not provided in state."""
    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=PositionView(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("1.0"),
            avg_entry_price=Decimal("50000")
        ),
        bracket_set=None
        # tick_size defaults to 0.01
    )

    cfg = BracketRulesConfig(
        enabled=True,
        recreate_missing_brackets=True
    )

    bracket_service.evaluate(state, cfg)

    call_kwargs = bracket_service._aggregator.compute_aggregated_brackets.call_args[1]
    constraints = call_kwargs["constraints"]
    assert constraints.tick_size == Decimal("0.01")
