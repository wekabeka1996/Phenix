from pathlib import Path

import pytest

from optimization.backtest_interface import BacktestAdapter


def _has_btc_data() -> bool:
    return Path("data/processed/BTCUSDT/5m").exists()


@pytest.mark.integration
@pytest.mark.slow
def test_stage0_real_data_has_non_empty_regime_log_and_flips():
    if not _has_btc_data():
        pytest.skip("BTCUSDT 5m backtest data not found")

    adapter = BacktestAdapter(config_dir=Path("config/aurora"))
    metrics, stage_result = adapter.run_stage0(
        overrides={"trading": {"backtest": {"max_ticks": 600}}},
        start_date="2023-06-14",
        end_date="2023-06-16",
    )
    assert stage_result.success is True
    assert isinstance(stage_result.regime_log, list) and len(stage_result.regime_log) > 0
    assert metrics.regime_flips > 0


@pytest.mark.integration
@pytest.mark.slow
def test_stage1_reject_rate_can_be_non_zero_on_real_data():
    if not _has_btc_data():
        pytest.skip("BTCUSDT 5m backtest data not found")

    adapter = BacktestAdapter(config_dir=Path("config/aurora"))
    metrics, stage_result = adapter.run_stage1(
        overrides={
            "trading": {
                "backtest": {
                    "max_ticks": 600,
                    "backtest_mode": "relaxed",
                }
            }
        },
        start_date="2023-06-14",
        end_date="2023-06-16",
    )
    assert stage_result.success is True
    intent_log = stage_result.intent_log or []
    proposed = sum(
        1 for i in intent_log
        if isinstance(i, dict) and str(i.get("intent_status", "PROPOSED")).upper() == "PROPOSED"
    )
    rejected = sum(
        1 for i in intent_log
        if isinstance(i, dict) and str(i.get("intent_status", "")).upper() == "REJECTED"
    )
    expected = (rejected / proposed) if proposed > 0 else 0.0
    assert metrics.reject_rate == pytest.approx(expected, rel=1e-9)


@pytest.mark.integration
@pytest.mark.slow
def test_stage1_stress_overrides_reach_broker():
    if not _has_btc_data():
        pytest.skip("BTCUSDT 5m backtest data not found")

    adapter = BacktestAdapter(config_dir=Path("config/aurora"))
    _, stage_result = adapter.run_stage1(
        overrides={
            "trading": {
                "backtest": {
                    "max_ticks": 120,
                    "backtest_mode": "strict",
                    "stress_overrides": {
                        "fee_mult": 1.2,
                        "slippage_bps": 7.0,
                        "latency_ms": 150,
                        "funding_bps_per_day": 10.0,
                    },
                }
            }
        },
        start_date="2023-06-14",
        end_date="2023-06-15",
    )
    assert stage_result.success is True
    report = stage_result.raw_report if isinstance(stage_result.raw_report, dict) else {}
    params = ((report.get("execution_stress") or {}).get("applied_params") or {})
    assert float(params.get("fee_mult", 0.0)) == pytest.approx(1.2, rel=1e-6)
    assert int(params.get("latency_ms", 0)) == 150
    assert float(params.get("funding_bps_per_day", 0.0)) == pytest.approx(10.0, rel=1e-6)
