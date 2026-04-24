from decimal import Decimal


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
