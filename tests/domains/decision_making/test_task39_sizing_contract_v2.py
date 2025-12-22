import decimal
import logging
from types import SimpleNamespace


def _mk_dm(*, pos_sizing, instruments, min_pos_usd="10", liq_cap_usd="10000"):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    dm = DecisionMaking.__new__(DecisionMaking)
    dm.logger = logging.getLogger("tests.task39.sizing")
    dm.min_pos_size_usd = decimal.Decimal(str(min_pos_usd))
    dm.liq_cap_usd = decimal.Decimal(str(liq_cap_usd))

    dm.config = SimpleNamespace(
        domains=SimpleNamespace(decision_making=SimpleNamespace(position_sizing=pos_sizing)),
        instruments=instruments,
        trading=SimpleNamespace(execution=None),
    )

    # These are only used after sizing; keep disabled in these unit tests.
    dm._compute_risk_contract_cap_notional = lambda *_a, **_k: None
    dm._compute_regime_scaled_notional = lambda *_a, **_k: None

    return dm


def test_sizing_fail_closed_when_contract_missing():
    pos_sizing = SimpleNamespace(
        risk_fraction_q=None,
        liquidity_kappa_mode="dynamic",
        liquidity_kappa=1.0,
        sizing=None,
    )
    instruments = {"SOLUSDT": SimpleNamespace(tick_size=0.01, step_size=0.01)}
    dm = _mk_dm(pos_sizing=pos_sizing, instruments=instruments)

    qty, why = dm._calculate_position_size(
        "SOLUSDT",
        decimal.Decimal("20"),
        "BUY",
        {"portfolio": {"equity": "1000"}, "features": {}},
    )
    assert qty is None
    assert why == "NRR-SIZING-CONTRACT-MISSING"


def test_sizing_fixed_qty_exact():
    pos_sizing = SimpleNamespace(
        risk_fraction_q=None,
        liquidity_kappa_mode="dynamic",
        liquidity_kappa=1.0,
        sizing=SimpleNamespace(mode="fixed_qty", fixed_qty={"SOLUSDT": 1.0}),
    )
    instruments = {"SOLUSDT": SimpleNamespace(tick_size=0.01, step_size=0.01)}
    dm = _mk_dm(pos_sizing=pos_sizing, instruments=instruments)

    qty, why = dm._calculate_position_size(
        "SOLUSDT",
        decimal.Decimal("20"),
        "BUY",
        {"portfolio": {"equity": "1000"}, "features": {}},
    )
    assert qty == decimal.Decimal("1.0")
    assert "sizing=v2:fixed_qty" in why


def test_sizing_fixed_notional_converts_to_qty():
    pos_sizing = SimpleNamespace(
        risk_fraction_q=None,
        liquidity_kappa_mode="dynamic",
        liquidity_kappa=1.0,
        sizing=SimpleNamespace(mode="fixed_notional_usd", fixed_notional_usd=30.0),
    )
    instruments = {"SOLUSDT": SimpleNamespace(tick_size=0.01, step_size=0.01)}
    dm = _mk_dm(pos_sizing=pos_sizing, instruments=instruments)

    qty, why = dm._calculate_position_size(
        "SOLUSDT",
        decimal.Decimal("20"),
        "BUY",
        {"portfolio": {"equity": "1000"}, "features": {}},
    )
    assert qty == decimal.Decimal("1.5")
    assert "sizing=v2:fixed_notional_usd" in why


def test_sizing_percent_equity_uses_config_value_not_fallback():
    pos_sizing = SimpleNamespace(
        risk_fraction_q=None,
        liquidity_kappa_mode="dynamic",
        liquidity_kappa=1.0,
        sizing=SimpleNamespace(mode="percent_equity", percent_equity=0.02),
    )
    instruments = {"SOLUSDT": SimpleNamespace(tick_size=0.01, step_size=0.01)}
    dm = _mk_dm(pos_sizing=pos_sizing, instruments=instruments)

    qty, why = dm._calculate_position_size(
        "SOLUSDT",
        decimal.Decimal("20"),
        "BUY",
        {"portfolio": {"equity": "1000"}, "features": {}},
    )
    assert qty == decimal.Decimal("1.0")
    assert "sizing=v2:percent_equity" in why


def test_sizing_respects_caps_and_rounding():
    pos_sizing = SimpleNamespace(
        risk_fraction_q=None,
        liquidity_kappa_mode="dynamic",
        liquidity_kappa=1.0,
        sizing=SimpleNamespace(mode="fixed_notional_usd", fixed_notional_usd=1000.0),
    )
    instruments = {"SOLUSDT": SimpleNamespace(tick_size=0.01, step_size=0.01)}
    dm = _mk_dm(pos_sizing=pos_sizing, instruments=instruments, liq_cap_usd="100")

    qty, why = dm._calculate_position_size(
        "SOLUSDT",
        decimal.Decimal("33"),
        "BUY",
        {"portfolio": {"equity": "1000"}, "features": {}},
    )
    # 100 cap / 33 = 3.0303... → 3.03 after step rounding
    assert qty == decimal.Decimal("3.03")
    assert "sizing=v2:fixed_notional_usd" in why

