import pytest

from apps.reference.domains.alpha_search.backtest_plugin import (
    AlphaSearchBacktestPlugin,
    VirtualPosition,
)
from apps.reference.domains.alpha_search.config_models import (
    AlphaSearchConfig,
    AuroraAdapterConfig,
    ProviderConfig,
    RuntimeCostConfig,
    VirtualTraderConfig,
)
from apps.reference.domains.alpha_search.runtime.shadow_book import ShadowBook
from tests.domains.alpha_search.test_backtest_plugin import MockEventBus


def _plugin(cost: RuntimeCostConfig) -> AlphaSearchBacktestPlugin:
    config = AlphaSearchConfig(
        enabled=True,
        providers={
            "aurora": ProviderConfig(
                enabled=True,
                adapter=AuroraAdapterConfig(),
            )
        },
        virtual_trader=VirtualTraderConfig(
            enabled=True,
            per_provider=True,
            max_positions_per_symbol=1,
            notional_size=5_000.0,
            runtime_cost=cost,
        ),
    )
    return AlphaSearchBacktestPlugin(event_bus=MockEventBus(), config=config)


def _position(side: str = "BUY") -> VirtualPosition:
    return VirtualPosition(
        provider_id="aurora",
        symbol="BTCUSDT",
        side=side,
        entry_price=100.0,
        entry_ts=1_700_000_000_000,
        signal_id=f"sig-{side}",
        bars_held=1,
    )


def test_zero_cost_config_reproduces_old_raw_pnl_exactly():
    plugin = _plugin(
        RuntimeCostConfig(
            enabled=False,
            cost_model_id="zero_cost_v1",
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
        )
    )

    plugin._close_virtual_position(
        provider_id="aurora",
        pos=_position("BUY"),
        exit_price=101.0,
        exit_ts=1_700_000_060_000,
    )

    trade = plugin.closed_positions["aurora"][0]
    assert trade["pnl"] == pytest.approx(50.0)
    assert trade["raw_pnl"] == pytest.approx(50.0)
    assert trade["total_cost"] == pytest.approx(0.0)
    assert trade["net_pnl_after_cost"] == pytest.approx(50.0)
    assert plugin.provider_stats["aurora"].total_pnl == pytest.approx(50.0)
    assert plugin.provider_stats["aurora"].net_total_pnl_after_cost == pytest.approx(50.0)


def test_nonzero_cost_config_reduces_net_pnl_deterministically():
    plugin = _plugin(
        RuntimeCostConfig(
            enabled=True,
            cost_model_id="test_cost_v1",
            fee_bps_per_side=10.0,
            slippage_bps_per_side=5.0,
        )
    )

    plugin._close_virtual_position(
        provider_id="aurora",
        pos=_position("BUY"),
        exit_price=101.0,
        exit_ts=1_700_000_060_000,
    )

    trade = plugin.closed_positions["aurora"][0]
    assert trade["raw_pnl"] == pytest.approx(50.0)
    assert trade["fee_cost"] == pytest.approx(10.0)
    assert trade["slippage_cost"] == pytest.approx(5.0)
    assert trade["total_cost"] == pytest.approx(15.0)
    assert trade["net_pnl_after_cost"] == pytest.approx(35.0)


def test_fee_slippage_arithmetic_exact_for_simple_long_trade():
    plugin = _plugin(
        RuntimeCostConfig(
            enabled=True,
            cost_model_id="long_cost_v1",
            fee_bps_per_side=12.5,
            slippage_bps_per_side=5.0,
        )
    )

    plugin._close_virtual_position(
        provider_id="aurora",
        pos=_position("BUY"),
        exit_price=101.0,
        exit_ts=1_700_000_060_000,
    )

    trade = plugin.closed_positions["aurora"][0]
    assert trade["raw_pnl"] == pytest.approx(50.0)
    assert trade["fee_cost"] == pytest.approx(12.5)
    assert trade["slippage_cost"] == pytest.approx(5.0)
    assert trade["total_cost"] == pytest.approx(17.5)
    assert trade["net_pnl_after_cost"] == pytest.approx(32.5)


def test_fee_slippage_arithmetic_exact_for_simple_short_trade():
    plugin = _plugin(
        RuntimeCostConfig(
            enabled=True,
            cost_model_id="short_cost_v1",
            fee_bps_per_side=12.5,
            slippage_bps_per_side=5.0,
        )
    )

    plugin._close_virtual_position(
        provider_id="aurora",
        pos=_position("SELL"),
        exit_price=99.0,
        exit_ts=1_700_000_060_000,
    )

    trade = plugin.closed_positions["aurora"][0]
    assert trade["raw_pnl"] == pytest.approx(50.0)
    assert trade["fee_cost"] == pytest.approx(12.5)
    assert trade["slippage_cost"] == pytest.approx(5.0)
    assert trade["total_cost"] == pytest.approx(17.5)
    assert trade["net_pnl_after_cost"] == pytest.approx(32.5)


def test_trade_and_summary_outputs_include_raw_and_net_cost_fields():
    plugin = _plugin(
        RuntimeCostConfig(
            enabled=True,
            cost_model_id="summary_cost_v1",
            fee_bps_per_side=10.0,
            slippage_bps_per_side=5.0,
        )
    )

    plugin._close_virtual_position(
        provider_id="aurora",
        pos=_position("BUY"),
        exit_price=101.0,
        exit_ts=1_700_000_060_000,
    )

    trade = plugin.closed_positions["aurora"][0]
    for field in (
        "raw_pnl",
        "fee_cost",
        "slippage_cost",
        "total_cost",
        "net_pnl_after_cost",
        "cost_model_id",
        "cost_model_source",
        "notional_size",
    ):
        assert field in trade

    vt_summary = plugin.get_summary()["provider_stats"]["aurora"]["virtual_trader"]
    for field in (
        "raw_cumulative_pnl",
        "cumulative_fee_cost",
        "cumulative_slippage_cost",
        "cumulative_total_cost",
        "net_cumulative_pnl_after_cost",
        "raw_profit_factor",
        "net_profit_factor_after_cost",
        "cost_model_id",
        "cost_model_source",
    ):
        assert field in vt_summary
    assert vt_summary["raw_cumulative_pnl"] == pytest.approx(50.0)
    assert vt_summary["net_cumulative_pnl_after_cost"] == pytest.approx(35.0)


def test_shadow_book_trade_receives_raw_and_net_cost_fields():
    shadow_book = ShadowBook("scenario-a", notional_size=5_000.0)
    plugin = _plugin(
        RuntimeCostConfig(
            enabled=True,
            cost_model_id="shadow_cost_v1",
            fee_bps_per_side=12.5,
            slippage_bps_per_side=5.0,
            cost_model_source="unit-test",
        )
    )
    plugin.shadow_book = shadow_book

    plugin._close_virtual_position(
        provider_id="aurora",
        pos=_position("BUY"),
        exit_price=101.0,
        exit_ts=1_700_000_060_000,
    )

    trade = shadow_book.trades[0]
    assert trade.pnl == pytest.approx(50.0)
    assert trade.raw_pnl == pytest.approx(50.0)
    assert trade.fee_cost == pytest.approx(12.5)
    assert trade.slippage_cost == pytest.approx(5.0)
    assert trade.total_cost == pytest.approx(17.5)
    assert trade.net_pnl_after_cost == pytest.approx(32.5)
    assert trade.cost_model_id == "shadow_cost_v1"
    assert trade.cost_model_source == "unit-test"


def test_generated_objective_payload_uses_configured_cost_fields():
    plugin = _plugin(
        RuntimeCostConfig(
            enabled=True,
            cost_model_id="objective_cost_v1",
            fee_bps_per_side=12.5,
            slippage_bps_per_side=5.0,
            cost_model_source="unit-test",
        )
    )
    position = _position("BUY")
    cost_breakdown = plugin._calculate_runtime_trade_costs(5_000.0)

    payload = plugin._build_virtual_objective_payload(
        provider_id="aurora",
        position=position,
        exit_price=101.0,
        exit_ts=1_700_000_060_000,
        exit_reason="time_exit",
        realized_pnl=50.0,
        cost_breakdown=cost_breakdown,
        net_pnl_after_cost=32.5,
        notional_size=5_000.0,
    )

    assert payload["realized_pnl"] == pytest.approx(50.0)
    assert payload["raw_pnl"] == pytest.approx(50.0)
    assert payload["fees"] == pytest.approx(12.5)
    assert payload["slippage"] == pytest.approx(5.0)
    assert payload["total_cost"] == pytest.approx(17.5)
    assert payload["net_pnl_after_cost"] == pytest.approx(32.5)
    assert payload["cost_model_id"] == "objective_cost_v1"


def test_invalid_runtime_cost_config_fails_closed_via_pydantic():
    with pytest.raises(Exception):
        RuntimeCostConfig(
            enabled=True,
            cost_model_id="bad_cost_v1",
            fee_bps_per_side=-1.0,
            slippage_bps_per_side=0.0,
        )
