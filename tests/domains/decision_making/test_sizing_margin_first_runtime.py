import decimal
import logging
from types import SimpleNamespace


def _mk_instr(*, step_size, min_qty, min_notional, margin_pct, leverage):
    return SimpleNamespace(
        step_size=str(step_size),
        min_qty=str(min_qty),
        min_notional=str(min_notional),
        sizing=SimpleNamespace(margin_pct=float(margin_pct)),
        execution=SimpleNamespace(target_leverage=int(leverage)),
    )


def _mk_dm(*, instruments, min_pos_usd="10", liq_cap_usd="10000"):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    dm = DecisionMaking.__new__(DecisionMaking)
    dm.logger = logging.getLogger("tests.sizing.margin_first")
    dm.min_pos_size_usd = decimal.Decimal(str(min_pos_usd))
    dm.liq_cap_usd = decimal.Decimal(str(liq_cap_usd))
    dm.config = SimpleNamespace(instruments=instruments)
    from apps.reference.domains.decision_making.position_queries import PositionQueries
    dm._pos = PositionQueries(dm.config, lambda: None, dm.min_pos_size_usd, dm.liq_cap_usd, dm.logger)
    return dm


def test_btc_margin_first_passes_min_notional_and_step():
    dm = _mk_dm(
        instruments={
            "BTCUSDT": _mk_instr(
                step_size="0.001",
                min_qty="0.001",
                min_notional="100",
                margin_pct=0.15,
                leverage=20,
            )
        }
    )

    qty, why, reject, dbg = dm._calculate_position_size(
        "BTCUSDT",
        decimal.Decimal("88000"),
        "BUY",
        {"portfolio": {"equity": "677"}, "features": {}},
    )
    assert reject is None
    assert qty is not None and qty > 0
    assert decimal.Decimal(dbg["order_notional"]) >= decimal.Decimal("100")
    assert why == "margin_first_ok"


def test_sol_coarse_step_passes_when_notional_is_large_enough():
    dm = _mk_dm(
        instruments={
            "SOLUSDT": _mk_instr(
                step_size="1",
                min_qty="1",
                min_notional="5",
                margin_pct=0.02,
                leverage=10,
            )
        }
    )

    qty, _why, reject, dbg = dm._calculate_position_size(
        "SOLUSDT",
        decimal.Decimal("124"),
        "BUY",
        {"portfolio": {"equity": "677"}, "features": {}},
    )
    assert reject is None
    assert qty == decimal.Decimal("1")
    assert decimal.Decimal(dbg["order_notional"]) >= decimal.Decimal("5")


def test_btc_rejects_min_notional_after_rounding():
    dm = _mk_dm(
        instruments={
            "BTCUSDT": _mk_instr(
                step_size="0.001",
                min_qty="0.001",
                min_notional="100",
                margin_pct=0.01,
                leverage=10,
            )
        }
    )

    qty, _why, reject, dbg = dm._calculate_position_size(
        "BTCUSDT",
        decimal.Decimal("88000"),
        "BUY",
        {"portfolio": {"equity": "677"}, "features": {}},
    )
    assert qty is None
    assert reject in ("MIN_NOTIONAL", "ZERO_QUANTITY", "MIN_POSITION_USD")
    # At least ensure it is not silently treated as OK.
    assert decimal.Decimal(dbg["order_notional"]) < decimal.Decimal("100")
