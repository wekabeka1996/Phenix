import time
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.decision_making.contracts import PortfolioSnapshot
from apps.reference.domains.decision_making.decision_making import DecisionMaking


def make_config_get(decision_maker, mapping):
    def getter(*args, **kwargs):
        if len(args) >= 2 and args[0] == "trading" and args[1] == "instruments":
            instruments = decision_maker.config["trading"]["instruments"]
            if len(args) == 2:
                return instruments
            symbol = args[2]
            inst = instruments.get(symbol, {})
            if len(args) == 3:
                return inst or kwargs.get("default")
            if len(args) == 4:
                return inst.get(args[3], kwargs.get("default"))
        return mapping.get(args, kwargs.get("default"))

    return getter


@pytest.fixture
def dm_base_config():
    return {
        "trading": {
            "decision": {
                "signal_threshold": 0.1,
                "position_sizing": {
                    "min_position_size_usd": 10.0,
                    "liquidity_based_cap_usd": 10000.0,
                    "risk_fraction_q": 0.01,
                },
            },
            "execution": {
                "brackets": {"sl": {"fixed_bps": 50}, "tp": {"fixed_bps": 100}}
            },
            "tca_prefs": {},
            "risk_budgets": {},
            "instruments": {
                "BTCUSDT": {"step_size": "0.001", "quote_precision": 3}
            },
        }
    }


@pytest.fixture
def decision_maker(dm_base_config):
    fsm = MagicMock()
    fsm.listen = MagicMock()
    return DecisionMaking(fsm=fsm, config=dm_base_config)


def test_portfolio_snapshot_contract_accepts_decimal_and_blocks_negative():
    snap = PortfolioSnapshot(
        equity_total="1000.5",
        equity_free="500.25",
        timestamp=datetime.utcnow(),
    )
    assert snap.equity_free_usdt == Decimal("500.25")
    assert snap.equity_total_usdt == Decimal("1000.5")

    with pytest.raises(ValueError):
        PortfolioSnapshot(
            equity_total="-1",
            equity_free="0",
            timestamp=datetime.utcnow(),
        )


def test_calculate_position_size_uses_nonzero_equity_snapshot(decision_maker):
    snap = PortfolioSnapshot(
        equity_total="1000", equity_free="500", timestamp=datetime.utcnow()
    )
    decision_maker.portfolio_provider.ingest_snapshot(snap)

    context = {
        "portfolio_snapshot": snap,
        "portfolio": snap.model_dump(),
        "_sizing_meta": {},
        "features": {"features": {"ts": time.time() * 1000}},
        "risk_params": {"risk_parameters": {"is_trading_allowed": True}},
    }

    mapping = {
        ("trading", "decision", "position_sizing"): decision_maker.config["trading"]["decision"]["position_sizing"],
        ("trading", "decision", "position_sizing", "risk_fraction_q"): 0.01,
        ("trading", "decision", "position_sizing", "liquidity_kappa_mode"): "static",
        ("trading", "decision", "position_sizing", "liquidity_kappa"): 1.0,
        ("trading", "execution", "brackets", "sl", "fixed_bps"): 50,
        ("trading", "execution", "brackets", "tp", "fixed_bps"): 100,
        ("trading",): decision_maker.config["trading"],
        ("trading", "instruments"): decision_maker.config["trading"]["instruments"],
        ("trading", "instruments", "BTCUSDT"): {
            "step_size": "0.001",
            "quote_precision": 3,
            "tick_size": "0.01",
        },
    }

    with patch.object(decision_maker, "_safe_config_get") as mock_cfg:
        mock_cfg.side_effect = make_config_get(decision_maker, mapping)
        qty, why = decision_maker._calculate_position_size(
            symbol="BTCUSDT", price=Decimal("20000"), side="BUY", context=context
        )

    assert qty is not None and qty > 0, f"Expected positive qty from equity snapshot, got {qty}"
    assert "equity" not in why.lower()


def test_calculate_position_size_rejects_when_equity_zero(decision_maker):
    snap = PortfolioSnapshot(
        equity_total="0", equity_free="0", timestamp=datetime.utcnow()
    )
    context = {
        "portfolio_snapshot": snap,
        "portfolio": snap.model_dump(),
        "_sizing_meta": {},
        "features": {"features": {"ts": time.time() * 1000}},
        "risk_params": {"risk_parameters": {"is_trading_allowed": True}},
    }

    mapping = {
        ("trading", "decision", "position_sizing"): decision_maker.config["trading"]["decision"]["position_sizing"],
        ("trading", "decision", "position_sizing", "risk_fraction_q"): 0.01,
        ("trading", "decision", "position_sizing", "liquidity_kappa_mode"): "static",
        ("trading", "decision", "position_sizing", "liquidity_kappa"): 1.0,
        ("trading", "execution", "brackets", "sl", "fixed_bps"): 50,
        ("trading", "execution", "brackets", "tp", "fixed_bps"): 100,
        ("trading",): decision_maker.config["trading"],
        ("trading", "instruments"): decision_maker.config["trading"]["instruments"],
        ("trading", "instruments", "BTCUSDT"): {
            "step_size": "0.001",
            "quote_precision": 3,
            "tick_size": "0.01",
        },
    }

    with patch.object(decision_maker, "_safe_config_get") as mock_cfg:
        mock_cfg.side_effect = make_config_get(decision_maker, mapping)
        qty, why = decision_maker._calculate_position_size(
            symbol="BTCUSDT", price=Decimal("20000"), side="BUY", context=context
        )

    assert qty is None, "Sizing should reject when equity_free_usdt is zero"
    assert "equity" in why


def test_trade_intent_uses_snapshot_equity(decision_maker):
    snap = PortfolioSnapshot(
        equity_total="1000", equity_free="500", timestamp=datetime.utcnow()
    )
    decision_maker.portfolio_provider.ingest_snapshot(snap)

    # Ingest a zero snapshot afterward to ensure prefer_nonzero keeps last good
    zero_snap = PortfolioSnapshot(
        equity_total="0", equity_free="0", timestamp=datetime.utcnow()
    )
    decision_maker.portfolio_provider.ingest_snapshot(zero_snap)

    preferred = decision_maker.portfolio_provider.get_snapshot(prefer_nonzero=True)
    assert preferred.equity_free_usdt == Decimal("500")
