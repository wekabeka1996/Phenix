from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.execution_position.bracket_math import compute_bracket_targets
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
from apps.reference.domains.execution_position.open_executor import OpenExecutor


def _build_open_executor(
    *,
    symbol: str = "BTCUSDT",
    sl_pct: float = 0.01,
    tp_low_ratio: float = 0.35,
) -> OpenExecutor:
    instrument_cfg = SimpleNamespace(
        exit=SimpleNamespace(sl_pct=sl_pct),
        take_profit=SimpleNamespace(tp_low_ratio=tp_low_ratio),
    )
    fsm = MagicMock()
    fsm.config = SimpleNamespace(
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(assets={symbol: instrument_cfg})
        )
    )
    return OpenExecutor(fsm)


def _build_manage_config(
    *,
    symbol: str = "BTCUSDT",
    sl_pct: float = 0.01,
    tp_low_ratio: float = 0.35,
    tp_high_ratio: float = 1.2,
    tick_size: str = "0.1",
):
    instrument_cfg = SimpleNamespace(
        exit=SimpleNamespace(sl_pct=sl_pct),
        take_profit=SimpleNamespace(
            tp_low_ratio=tp_low_ratio,
            tp_high_ratio=tp_high_ratio,
            partial_exit_pct=0.5,
        ),
        trailing_stop=SimpleNamespace(
            enabled=False,
            activation_pct=None,
            trail_pct=None,
            min_update_interval_sec=5,
        ),
    )
    return SimpleNamespace(
        trading=SimpleNamespace(
            execution=SimpleNamespace(
                manage=SimpleNamespace(auto=False, emergency=None),
                anti_race_close_ms=250,
            )
        ),
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                decision=SimpleNamespace(
                    bar_gating=SimpleNamespace(bar_ms=900_000)
                ),
                assets={symbol: instrument_cfg},
            )
        ),
        instruments={symbol: SimpleNamespace(tick_size=Decimal(tick_size))},
    )


@pytest.mark.parametrize(
    ("position_side", "expected_sl", "expected_tp1", "expected_tp2"),
    [
        ("BUY", Decimal("99.0"), Decimal("100.35"), Decimal("101.2")),
        ("SELL", Decimal("101.0"), Decimal("99.65"), Decimal("98.8")),
    ],
)
def test_compute_bracket_targets_is_canonical_raw_kernel(
    position_side: str,
    expected_sl: Decimal,
    expected_tp1: Decimal,
    expected_tp2: Decimal,
) -> None:
    targets = compute_bracket_targets(
        reference_price=Decimal("100"),
        position_side=position_side,
        sl_pct=Decimal("0.01"),
        tp_low_ratio=Decimal("0.35"),
        tp_high_ratio=Decimal("1.2"),
    )

    assert targets.sl_price == expected_sl
    assert targets.tp1_price == expected_tp1
    assert targets.tp2_price == expected_tp2


def test_open_executor_config_fallback_uses_mark_reference_price() -> None:
    executor = _build_open_executor()

    sl_price, tp_price, sl_source, tp_source = executor._resolve_sl_tp(
        SimpleNamespace(pld={}),
        "BTCUSDT",
        "BUY",
        Decimal("105"),
    )

    expected = compute_bracket_targets(
        reference_price=Decimal("105"),
        position_side="BUY",
        sl_pct=Decimal("0.01"),
        tp_low_ratio=Decimal("0.35"),
    )

    assert sl_source == "CONFIG_FALLBACK"
    assert tp_source == "CONFIG_FALLBACK"
    assert sl_price == expected.sl_price
    assert tp_price == expected.tp1_price


def test_manage_wrapper_quantizes_after_entry_based_raw_kernel() -> None:
    manage = ManageFlowFSM(config=_build_manage_config())
    manage.symbol = "BTCUSDT"
    manage.position_side = "BUY"
    manage.position_entry_price = Decimal("100")
    manage.position_qty = Decimal("1")

    raw_targets = compute_bracket_targets(
        reference_price=manage.position_entry_price,
        position_side=manage.position_side,
        sl_pct=Decimal("0.01"),
        tp_low_ratio=Decimal("0.35"),
        tp_high_ratio=Decimal("1.2"),
    )
    sl_price, tp1_price, tp2_price = manage._calculate_bracket_prices()

    assert raw_targets.sl_price == Decimal("99")
    assert raw_targets.tp1_price == Decimal("100.35")
    assert sl_price == Decimal("99.0")
    assert tp1_price == Decimal("100.3")
    assert tp2_price == Decimal("101.2")
