from types import SimpleNamespace
from pathlib import Path

from optimization.backtest_interface import BacktestAdapter
from optimization.research.provenance import ResearchTrialRequest
from optimization.research.proxy_runner import ResearchHarnessConfig, ResearchHarnessRunner, build_strategy_proxy_spec


def _build_dummy_config(*, macro_resid: float = 0.25):
    return SimpleNamespace(
        instruments={"ETHUSDT": {"symbol": "ETHUSDT"}, "BTCUSDT": {"symbol": "BTCUSDT"}},
        strategies=SimpleNamespace(
            aurora={
                "assets": {
                    "ETHUSDT": {
                        "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "MEAN_REVERSION"],
                        "weights": {"macro_resid": macro_resid},
                    }
                }
            }
        ),
        trading=SimpleNamespace(symbols_to_track=[]),
        strategies_registry=SimpleNamespace(assignments={}),
        system_meta=SimpleNamespace(runtime=None),
    )


class _DummyLoader:
    def __init__(self, config_dir=None, optuna_overlay=None):
        weights = (
            (((optuna_overlay or {}).get("strategies") or {}).get("aurora") or {}).get("assets") or {}
        ).get("ETHUSDT", {}).get("weights", {})
        self.config = _build_dummy_config(macro_resid=float(weights.get("macro_resid", 0.25)))

    def load_config(self):
        return self.config


def test_build_strategy_proxy_spec_keeps_context_symbols_tracked_only():
    spec = build_strategy_proxy_spec(
        label="eth_btc_proxy",
        strategy_id="aurora",
        tradable_symbols=["ETHUSDT"],
        context_symbols=["BTCUSDT"],
    )

    assert spec.tracked_symbols == ["ETHUSDT", "BTCUSDT"]
    assert spec.tradable_symbols == ["ETHUSDT"]
    assert spec.context_symbols == ["BTCUSDT"]
    assert spec.strategy_assignments == {"ETHUSDT": ["aurora"]}


def test_research_proxy_enforcement_tracks_context_and_locks_assignments():
    spec = build_strategy_proxy_spec(
        label="eth_btc_proxy",
        strategy_id="aurora",
        tradable_symbols=["ETHUSDT"],
        context_symbols=["BTCUSDT"],
    )
    adapter = BacktestAdapter(research_proxy=spec, fail_on_scoring_fallback=True)
    config = SimpleNamespace(
        instruments={"ETHUSDT": object(), "BTCUSDT": object()},
        strategies=SimpleNamespace(aurora=object()),
        trading=SimpleNamespace(symbols_to_track=[]),
        strategies_registry=SimpleNamespace(assignments={}),
        system_meta=SimpleNamespace(runtime=None),
    )

    proxy_dump = adapter._apply_research_proxy(config)

    assert config.trading.symbols_to_track == ["ETHUSDT", "BTCUSDT"]
    assert config.strategies_registry.assignments == {"ETHUSDT": ["aurora"]}
    assert proxy_dump["context_symbols"] == ["BTCUSDT"]
    assert proxy_dump["fail_closed_on_scoring_fallback"] is True


def test_research_harness_fail_closed_rejects_quadratic_fallback(monkeypatch):
    spec = build_strategy_proxy_spec(
        label="eth_btc_proxy",
        strategy_id="aurora",
        tradable_symbols=["ETHUSDT"],
        context_symbols=["BTCUSDT"],
    )
    runner = ResearchHarnessRunner(
        config=ResearchHarnessConfig(
            config_dir=Path("config/aurora"),
            proxy=spec,
            fail_on_scoring_fallback=True,
        )
    )

    class _DummyLoader:
        def __init__(self, config_dir=None, optuna_overlay=None):
            self.config = SimpleNamespace(
                instruments={"ETHUSDT": object(), "BTCUSDT": object()},
                strategies=SimpleNamespace(aurora=object()),
                trading=SimpleNamespace(symbols_to_track=[]),
                strategies_registry=SimpleNamespace(assignments={}),
                system_meta=SimpleNamespace(runtime=None),
            )

        def load_config(self):
            return self.config

    def _fake_run_backtest_simulation(config, return_result=False):
        return (
            SimpleNamespace(sharpe_ratio=0.0, calmar_ratio=0.0, max_drawdown=0.0, total_trades=0, roi_pct=0.0),
            {
                "run_id": "R_FAIL",
                "scoring_telemetry": {
                    "quadratic_fallback_count": 1,
                    "quadratic_engine_selected_count": 4,
                },
                "proxy_universe": {
                    "tracked_symbols": ["ETHUSDT", "BTCUSDT"],
                    "tradable_symbols": ["ETHUSDT"],
                },
            },
        )

    monkeypatch.setattr("apps.reference.config_loader.ConfigLoader", _DummyLoader)
    monkeypatch.setattr("apps.reference.main.run_backtest_simulation", _fake_run_backtest_simulation)

    metrics, stage_result = runner.run_stage1({}, start_date="2024-03-01", end_date="2024-03-31")

    assert metrics.total_trades == 0
    assert stage_result.success is False
    assert "quadratic fallback observed" in str(stage_result.error)
    assert stage_result.scoring_telemetry["quadratic_fallback_count"] == 1


def test_distinct_overlay_materializes_distinct_effective_hashes(monkeypatch, tmp_path):
    spec = build_strategy_proxy_spec(
        label="eth_btc_proxy",
        strategy_id="aurora",
        tradable_symbols=["ETHUSDT"],
        context_symbols=["BTCUSDT"],
    )
    runner = ResearchHarnessRunner(
        config=ResearchHarnessConfig(
            config_dir=Path("config/aurora"),
            proxy=spec,
            fail_on_scoring_fallback=True,
            trial_artifacts_dir=tmp_path,
        )
    )

    def _fake_run_backtest_simulation(config, return_result=False):
        trial = config.system_meta.runtime.research_trial.model_dump()
        return (
            SimpleNamespace(
                sharpe_ratio=0.0,
                calmar_ratio=0.0,
                max_drawdown=0.0,
                total_trades=1,
                roi_pct=0.1,
            ),
            {
                "run_id": f"RUN_{trial['trial_id']}",
                "scoring_telemetry": {"quadratic_fallback_count": 0},
                "proxy_universe": trial["proxy_universe"],
                "search_provenance": dict(trial, run_id=f"RUN_{trial['trial_id']}"),
            },
        )

    monkeypatch.setattr("apps.reference.config_loader.ConfigLoader", _DummyLoader)
    monkeypatch.setattr("apps.reference.main.run_backtest_simulation", _fake_run_backtest_simulation)

    anchor_overlay = {
        "strategies": {
            "aurora": {
                "assets": {
                    "ETHUSDT": {
                        "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "MEAN_REVERSION"],
                    }
                }
            }
        }
    }
    distinct_overlay = {
        "strategies": {
            "aurora": {
                "assets": {
                    "ETHUSDT": {
                        "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "MEAN_REVERSION"],
                        "weights": {"macro_resid": 0.31},
                    }
                }
            }
        }
    }

    anchor_request = ResearchTrialRequest(
        trial_id="anchor",
        arm_id="anchor",
        trial_params_json={},
        expected_changed_paths=[],
        parent_anchor="v1",
        anchor_overrides=anchor_overlay,
    )
    distinct_request = ResearchTrialRequest(
        trial_id="distinct",
        arm_id="scoring",
        trial_params_json={"macro_resid": 0.31},
        expected_changed_paths=["strategies.aurora.assets.ETHUSDT.weights.macro_resid"],
        parent_anchor="v1",
        anchor_overrides=anchor_overlay,
    )

    _, anchor_stage = runner.run_stage1(
        anchor_overlay,
        start_date="2024-03-01",
        end_date="2024-03-02",
        trial_request=anchor_request,
    )
    _, distinct_stage = runner.run_stage1(
        distinct_overlay,
        start_date="2024-03-01",
        end_date="2024-03-02",
        trial_request=distinct_request,
    )

    assert anchor_stage.success is True
    assert distinct_stage.success is True
    assert anchor_stage.search_provenance["effective_config_hash"] != distinct_stage.search_provenance["effective_config_hash"]
    assert anchor_stage.search_provenance["effective_strategy_slice_hash"] != distinct_stage.search_provenance["effective_strategy_slice_hash"]


def test_preflight_rejects_no_effective_delta(monkeypatch, tmp_path):
    spec = build_strategy_proxy_spec(
        label="eth_btc_proxy",
        strategy_id="aurora",
        tradable_symbols=["ETHUSDT"],
        context_symbols=["BTCUSDT"],
    )
    runner = ResearchHarnessRunner(
        config=ResearchHarnessConfig(
            config_dir=Path("config/aurora"),
            proxy=spec,
            fail_on_scoring_fallback=True,
            trial_artifacts_dir=tmp_path,
        )
    )

    def _should_not_run(*args, **kwargs):
        raise AssertionError("Backtest must not start when preflight finds no effective delta")

    monkeypatch.setattr("apps.reference.config_loader.ConfigLoader", _DummyLoader)
    monkeypatch.setattr("apps.reference.main.run_backtest_simulation", _should_not_run)

    anchor_overlay = {
        "strategies": {
            "aurora": {
                "assets": {
                    "ETHUSDT": {
                        "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "MEAN_REVERSION"],
                    }
                }
            }
        }
    }
    trial_request = ResearchTrialRequest(
        trial_id="no-effect",
        arm_id="scoring",
        trial_params_json={"macro_resid": 0.25},
        expected_changed_paths=["strategies.aurora.assets.ETHUSDT.weights.macro_resid"],
        parent_anchor="v1",
        anchor_overrides=anchor_overlay,
    )

    metrics, stage_result = runner.run_stage1(
        anchor_overlay,
        start_date="2024-03-01",
        end_date="2024-03-02",
        trial_request=trial_request,
    )

    assert metrics.total_trades == 0
    assert stage_result.success is False
    assert stage_result.error == "NO_EFFECTIVE_CONFIG_DELTA"
    assert stage_result.search_provenance["rejection_reason"] == "NO_EFFECTIVE_CONFIG_DELTA"
    assert Path(stage_result.preflight_manifest_path).exists()


def test_partial_runs_preserve_completed_trial_manifests(monkeypatch, tmp_path):
    spec = build_strategy_proxy_spec(
        label="eth_btc_proxy",
        strategy_id="aurora",
        tradable_symbols=["ETHUSDT"],
        context_symbols=["BTCUSDT"],
    )
    runner = ResearchHarnessRunner(
        config=ResearchHarnessConfig(
            config_dir=Path("config/aurora"),
            proxy=spec,
            fail_on_scoring_fallback=True,
            trial_artifacts_dir=tmp_path,
        )
    )

    monkeypatch.setattr("apps.reference.config_loader.ConfigLoader", _DummyLoader)

    def _fake_run_backtest_simulation(config, return_result=False):
        trial = config.system_meta.runtime.research_trial.model_dump()
        return (
            SimpleNamespace(
                sharpe_ratio=0.0,
                calmar_ratio=0.0,
                max_drawdown=0.0,
                total_trades=1,
                roi_pct=0.1,
                total_pnl=1.0,
                win_rate=1.0,
                end_balance=1001.0,
            ),
            {
                "run_id": f"RUN_{trial['trial_id']}",
                "scoring_telemetry": {"quadratic_fallback_count": 0, "engine_names_observed": ["quadratic_v1"]},
                "proxy_universe": trial["proxy_universe"],
                "search_provenance": dict(trial, run_id=f"RUN_{trial['trial_id']}"),
            },
        )

    monkeypatch.setattr("apps.reference.main.run_backtest_simulation", _fake_run_backtest_simulation)

    anchor_overlay = {
        "strategies": {
            "aurora": {
                "assets": {
                    "ETHUSDT": {
                        "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "MEAN_REVERSION"],
                    }
                }
            }
        }
    }
    scoring_overlay = {
        "strategies": {
            "aurora": {
                "assets": {
                    "ETHUSDT": {
                        "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "MEAN_REVERSION"],
                        "weights": {"macro_resid": 0.31},
                    }
                }
            }
        }
    }

    first_request = ResearchTrialRequest(
        trial_id="trial-one",
        arm_id="anchor",
        trial_params_json={},
        expected_changed_paths=[],
        parent_anchor="v1",
        anchor_overrides=anchor_overlay,
    )
    second_request = ResearchTrialRequest(
        trial_id="trial-two",
        arm_id="scoring",
        trial_params_json={"macro_resid": 0.31},
        expected_changed_paths=["strategies.aurora.assets.ETHUSDT.weights.macro_resid"],
        parent_anchor="v1",
        anchor_overrides=anchor_overlay,
    )

    _, first_stage = runner.run_stage1(
        anchor_overlay,
        start_date="2024-03-01",
        end_date="2024-03-02",
        trial_request=first_request,
    )
    _, second_stage = runner.run_stage1(
        scoring_overlay,
        start_date="2024-03-01",
        end_date="2024-03-02",
        trial_request=second_request,
    )

    first_manifest = Path(first_stage.preflight_manifest_path)
    second_manifest = Path(second_stage.preflight_manifest_path)
    assert first_manifest.exists()
    assert second_manifest.exists()
    assert first_manifest != second_manifest
    assert '"manifest_version": "1.0.0"' in first_manifest.read_text(encoding="utf-8")
    assert '"manifest_version": "1.0.0"' in second_manifest.read_text(encoding="utf-8")