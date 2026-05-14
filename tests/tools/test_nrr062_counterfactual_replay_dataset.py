from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    file_path = repo_root / "artifacts" / "_tmp" / \
        "phenix_nrr062_counterfactual_replay_dataset.py"
    spec = importlib.util.spec_from_file_location(
        "nrr062_counterfactual_replay_dataset", file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load replay helper module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


replay = _load_module()


def _input_row(**overrides):
    payload = {
        "rid": "r1",
        "decision_id": "d1",
        "symbol": "ETHUSDT",
        "side": "BUY",
        "reject_ts_ms": 1000,
        "entry_price_reference": 100.0,
        "tp_price": 102.0,
        "sl_price": 99.0,
        "horizon_end_ts_ms": 10_000,
        "fee_bps": 8.0,
        "slippage_bps": 2.0,
        "quantity": 1.0,
        "replay_status": replay.REPLAY_STATUS_READY,
        "replay_status_reason": "all_required_inputs_present",
    }
    payload.update(overrides)
    return payload


def _bar(*, open_time_ms: int, close_time_ms: int, open_price: float, high_price: float, low_price: float, close_price: float):
    return {
        "open_time_ms": open_time_ms,
        "close_time_ms": close_time_ms,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "source_path": "data/recorder/2026-05-11/ETHUSDT_180.csv",
    }


def test_tp_before_sl_gives_counterfactual_tp() -> None:
    row = _input_row()
    bars = [
        _bar(open_time_ms=2000, close_time_ms=4000, open_price=100.1,
             high_price=102.2, low_price=99.5, close_price=101.8),
    ]

    result = replay.run_counterfactual_replay(input_row=row, bars=bars)

    assert result["outcome_class"] == replay.OUTCOME_TP
    assert result["estimated_net_bps"] == 190.0


def test_sl_before_tp_gives_counterfactual_sl() -> None:
    row = _input_row()
    bars = [
        _bar(open_time_ms=2000, close_time_ms=4000, open_price=100.1,
             high_price=100.5, low_price=98.8, close_price=99.0),
    ]

    result = replay.run_counterfactual_replay(input_row=row, bars=bars)

    assert result["outcome_class"] == replay.OUTCOME_SL
    assert result["estimated_net_bps"] == -110.0


def test_same_bar_tp_sl_gives_ambiguous_result() -> None:
    row = _input_row()
    bars = [
        _bar(open_time_ms=2000, close_time_ms=4000, open_price=100.0,
             high_price=102.5, low_price=98.5, close_price=100.5),
    ]

    result = replay.run_counterfactual_replay(input_row=row, bars=bars)

    assert result["outcome_class"] == replay.OUTCOME_AMBIGUOUS
    assert result["estimated_net_pnl_quote"] is None


def test_missing_bars_gives_no_market_path() -> None:
    row = _input_row(replay_status=replay.REPLAY_STATUS_NO_MARKET_PATH,
                     replay_status_reason="no_full_post_reject_bars")

    result = replay.run_counterfactual_replay(input_row=row, bars=[])

    assert result["outcome_class"] == replay.OUTCOME_NO_MARKET_PATH
    assert result["estimated_net_pnl_quote"] is None


def test_fee_and_slippage_net_calculation_is_deterministic() -> None:
    row = _input_row(side="SELL", entry_price_reference=100.0,
                     tp_price=98.0, sl_price=101.0, quantity=2.0)
    bars = [
        _bar(open_time_ms=2000, close_time_ms=4000, open_price=99.9,
             high_price=100.1, low_price=97.9, close_price=98.3),
    ]

    result = replay.run_counterfactual_replay(input_row=row, bars=bars)

    assert result["outcome_class"] == replay.OUTCOME_TP
    assert result["estimated_gross_bps"] == 200.0
    assert result["estimated_net_bps"] == 190.0
    assert result["estimated_gross_pnl_quote"] == 4.0
    assert result["estimated_fee_quote"] == 0.16
    assert result["estimated_slippage_quote"] == 0.04
    assert result["estimated_net_pnl_quote"] == 3.8


def test_infer_bar_open_ms_is_deterministic() -> None:
    assert replay.infer_bar_open_ms(1778520959999, 180) == 1778520780000
