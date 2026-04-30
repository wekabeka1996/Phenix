from decimal import Decimal

import pytest


def test_portfolio_state_payload_accepts_legacy_shape_positions_only():
    from apps.reference.domains.decision_making.contracts.schemas import PortfolioStatePayload

    p = PortfolioStatePayload(positions=[])
    assert p.schema_version == 1
    assert p.ts_ms is None
    assert p.equity_usdt is None
    assert p.available_usdt is None


def test_portfolio_state_payload_parses_optional_decimals():
    from apps.reference.domains.decision_making.contracts.schemas import PortfolioStatePayload

    p = PortfolioStatePayload(
        ts_ms=123,
        equity_usdt="100.5",
        available_usdt=200,
        positions=[],
    )
    assert p.ts_ms == 123
    assert p.equity_usdt == Decimal("100.5")
    assert p.available_usdt == Decimal("200")


def test_position_data_accepts_additive_symbol_economics_fields():
    from apps.reference.domains.decision_making.contracts.schemas import PortfolioStatePayload, PositionData

    position = PositionData(
        symbol="BTCUSDT",
        positionAmt="1.0",
        entryPrice="100.0",
        unRealizedProfit="10.0",
        markPrice="110.0",
        unrealizedPnl="10.0",
        unrealizedPnlPct="10.0",
    )
    payload = PortfolioStatePayload(positions=[position])

    assert payload.positions[0].markPrice == Decimal("110.0")
    assert payload.positions[0].unrealizedPnl == Decimal("10.0")
    assert payload.positions[0].unrealizedPnlPct == Decimal("10.0")


def test_position_data_symbol_economics_are_nullable_and_strictly_decimal():
    from apps.reference.domains.decision_making.contracts.schemas import PositionData

    position = PositionData(
        symbol="ETHUSDT",
        positionAmt="-2.0",
        entryPrice="2000.0",
        unRealizedProfit="0.0",
    )

    assert position.markPrice is None
    assert position.unrealizedPnl is None
    assert position.unrealizedPnlPct is None

    with pytest.raises(ValueError):
        PositionData(
            symbol="ETHUSDT",
            positionAmt="-2.0",
            entryPrice="2000.0",
            unRealizedProfit="0.0",
            markPrice="not-a-number",
        )
