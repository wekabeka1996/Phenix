"""Regression tests for partial-close gaps in legacy ManageFlowFSM."""

from __future__ import annotations

import pytest

from tests.domains.execution_position.test_aggregated_oco_scale_in_legacy import (
    assert_position_fully_protected,
    open_position_with_brackets,
    partial_close_position,
    setup_execution_env_for_symbol,
)


@pytest.mark.integration
@pytest.mark.legacy
@pytest.mark.xfail(reason="Legacy ManageFlowFSM never reinstalls SL after partial close", strict=False)
def test_partial_close_legacy_leaves_position_unprotected():
    symbol = "SOLUSDT"
    side = "LONG"
    env = setup_execution_env_for_symbol(symbol)

    # Install the first bracket set for the entry position.
    open_position_with_brackets(env, symbol, side, qty=1.0)
    assert_position_fully_protected(
        env,
        symbol,
        side,
        why="first_entry_should_install_initial_sl",
    )

    # Simulate manual partial close that cancels SL before executing the exit.
    partial_close_position(env, symbol, side, qty=0.4)

    # Legacy ManageFlowFSM never reinstalls SL after partial close, leaving the remainder naked.
    assert_position_fully_protected(
        env,
        symbol,
        side,
        why="partial_close_should_keep_sl_protection",
    )


@pytest.mark.integration
def test_partial_close_with_aggregated_oco_keeps_full_sl_coverage():
    symbol = "SOLUSDT"
    side = "LONG"
    env = setup_execution_env_for_symbol(
        symbol,
        aggregated_oco_enabled=True,
        recalc_on_scale_in=True,
        recalc_on_partial_close=False,
        allow_unprotected_position=False,
    )

    first_qty = 2.0
    open_position_with_brackets(env, symbol, side, qty=first_qty)
    assert_position_fully_protected(
        env,
        symbol,
        side,
        why="agg_first_entry_partial_should_be_fully_protected",
    )

    partial_qty = 0.5
    partial_close_position(env, symbol, side, qty=partial_qty)

    position = env.get_position_state(symbol, side)
    expected_qty = first_qty - partial_qty
    assert float(position.qty) == pytest.approx(expected_qty, rel=1e-4)

    assert_position_fully_protected(
        env,
        symbol,
        side,
        why="agg_partial_close_should_keep_full_sl_protection",
    )
