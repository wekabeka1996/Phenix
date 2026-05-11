from datetime import date
from types import SimpleNamespace

from backtest_engine.reporting import build_backtest_report
from tools.backtest.backtest_summarize import summarize


def test_build_backtest_report_exports_scoring_telemetry_and_proxy_universe():
    config = SimpleNamespace(
        system_meta=SimpleNamespace(
            runtime=SimpleNamespace(
                research_proxy=SimpleNamespace(
                    model_dump=lambda: {
                        "label": "eth_btc_proxy",
                        "tracked_symbols": ["ETHUSDT", "BTCUSDT"],
                        "tradable_symbols": ["ETHUSDT"],
                        "context_symbols": ["BTCUSDT"],
                        "strategy_assignments": {"ETHUSDT": ["aurora"]},
                        "fail_closed_on_scoring_fallback": True,
                    }
                ),
                research_trial=SimpleNamespace(
                    model_dump=lambda: {
                        "trial_id": "trial-anchor",
                        "arm_id": "anchor",
                        "trial_params_json": {},
                        "overlay_hash": "overlay-hash",
                        "effective_config_hash": "cfg-hash",
                        "effective_strategy_slice_hash": "slice-hash",
                        "proxy_universe": {"tracked_symbols": ["ETHUSDT", "BTCUSDT"]},
                        "fail_closed_on_scoring_fallback": True,
                        "run_id": None,
                        "parent_anchor": "v1",
                        "timestamp": "2026-03-15T00:00:00+00:00",
                        "expected_changed_paths": [],
                        "effective_changed_values": {},
                        "preflight_passed": True,
                        "rejection_reason": None,
                        "anchor_effective_config_hash": "cfg-hash",
                        "anchor_effective_strategy_slice_hash": "slice-hash",
                        "manifest_path": "artifacts/search_trials/trial-anchor.json",
                        "execution_status": "completed",
                    }
                )
            )
        )
    )
    results = SimpleNamespace(
        total_pnl=1.5,
        roi_pct=0.15,
        max_drawdown=0.02,
        win_rate=0.5,
        total_trades=2,
        end_balance=1001.5,
    )
    engine = SimpleNamespace(broker=None)

    report = build_backtest_report(
        run_id="R1",
        config=config,
        results=results,
        engine=engine,
        start_date=date(2024, 3, 1),
        end_date=date(2024, 3, 31),
        symbols=["ETHUSDT", "BTCUSDT"],
        timeframe="5m",
        initial_balance=1000.0,
        regimes={},
        features={},
        trade_intents=[],
        pipeline={},
        scoring_telemetry={
            "quadratic_engine_selected_count": 12,
            "quadratic_fallback_count": 0,
            "fallback_also_failed_count": 0,
            "engine_names_observed": ["quadratic_v1"],
            "observed_engine_counts": {"quadratic_v1": 12},
        },
    )

    assert report["report_version"] == "2.2.0"
    assert report["scoring_telemetry"]["quadratic_engine_selected_count"] == 12
    assert report["proxy_universe"]["tracked_symbols"] == ["ETHUSDT", "BTCUSDT"]
    assert report["search_provenance"]["trial_id"] == "trial-anchor"
    assert report["search_provenance"]["run_id"] == "R1"

    summary = summarize(report)

    assert summary["scoring_telemetry"]["quadratic_fallback_count"] == 0
    assert summary["proxy_universe"]["tradable_symbols"] == ["ETHUSDT"]
    assert summary["search_provenance"]["effective_config_hash"] == "cfg-hash"
