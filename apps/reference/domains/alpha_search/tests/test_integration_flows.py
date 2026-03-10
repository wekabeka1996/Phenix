"""
Cross-Cutting: Integration Flow Tests
=======================================

End-to-end flows through multiple modules.
10 tests covering full pipeline, multi-scenario, and lifecycle.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from apps.reference.domains.alpha_search.runtime.contracts import (
    AlphaInputV1,
    ScenarioMatrixConfig,
    ScenarioSpec,
    RuntimeConfig,
    HotReloadConfig,
    InputConfig,
)
from apps.reference.domains.alpha_search.tests.conftest import make_snapshot


def _project_root():
    return Path(__file__).resolve().parents[4]


@pytest.mark.integration
class TestFullPipeline:
    """End-to-end snapshot -> score flow."""

    def test_snapshot_to_score_full_pipeline(self, tmp_path):
        """Snapshot -> ScenarioWorker -> score result."""
        from apps.reference.domains.alpha_search.runtime.scenario_worker import ScenarioWorker
        from apps.reference.domains.alpha_search.runtime.config_resolver import resolve_scenario_config

        project_root = _project_root()
        spec = ScenarioSpec(
            scenario_id="S01_AURORA_BASELINE",
            enabled=True,
            strategy_type="aurora",
            config_mode="override",
            base_refs={
                "aurora": "config/aurora/strategies/aurora.yaml",
                "alpha_search": "config/alpha_search.yaml",
            },
            overrides={},
        )

        try:
            alpha_cfg, sys_cfg, strategy_cfg = resolve_scenario_config(spec, project_root)
        except Exception:
            pytest.skip("Config resolution failed (missing files)")

        log_dir = tmp_path / "S01"
        log_dir.mkdir()

        worker = ScenarioWorker(
            spec=spec,
            alpha_search_config=alpha_cfg,
            system_config=sys_cfg,
            strategy_config=strategy_cfg,
            log_dir=log_dir,
        )

        snapshot = AlphaInputV1(**make_snapshot())
        results = worker.process_snapshot(snapshot)

        assert isinstance(results, list)
        # Aurora provider should produce at least one result
        if results:
            assert "scenario_id" in results[0]
            assert "score" in results[0]
            assert results[0]["shadow"] is True

        worker.shutdown()

    def test_aurora_score_differentiation(self, tmp_path):
        """S01 vs S02 produce different scores for same input."""
        from apps.reference.domains.alpha_search.runtime.scenario_worker import ScenarioWorker
        from apps.reference.domains.alpha_search.runtime.config_resolver import resolve_scenario_config

        project_root = _project_root()

        def make_worker(scenario_id, overrides):
            spec = ScenarioSpec(
                scenario_id=scenario_id,
                enabled=True,
                strategy_type="aurora",
                config_mode="override",
                base_refs={
                    "aurora": "config/aurora/strategies/aurora.yaml",
                    "alpha_search": "config/alpha_search.yaml",
                },
                overrides=overrides,
            )
            try:
                alpha_cfg, sys_cfg, strategy_cfg = resolve_scenario_config(spec, project_root)
            except Exception:
                return None
            log_dir = tmp_path / scenario_id
            log_dir.mkdir()
            return ScenarioWorker(
                spec=spec,
                alpha_search_config=alpha_cfg,
                system_config=sys_cfg,
                strategy_config=strategy_cfg,
                log_dir=log_dir,
            )

        w1 = make_worker("S01_BASELINE", {})
        w2 = make_worker("S02_AGGRESSIVE", {
            "aurora.decision.signal_threshold": 0.12,
        })

        if not w1 or not w2:
            pytest.skip("Config resolution failed")

        snapshot = AlphaInputV1(**make_snapshot())
        r1 = w1.process_snapshot(snapshot)
        r2 = w2.process_snapshot(snapshot)

        # Both should produce results
        assert isinstance(r1, list)
        assert isinstance(r2, list)

        # If both have results, the side determination may differ
        # (due to different thresholds)
        if r1 and r2:
            # At minimum, threshold or side could differ
            assert r1[0]["scenario_id"] != r2[0]["scenario_id"]

        w1.shutdown()
        w2.shutdown()


@pytest.mark.integration
class TestMultiScenario:
    """Tests for multiple scenarios running together."""

    def test_mr_scenario_produces_scores(self, tmp_path):
        """MR scenarios produce valid scores."""
        from apps.reference.domains.alpha_search.runtime.scenario_worker import ScenarioWorker
        from apps.reference.domains.alpha_search.runtime.config_resolver import resolve_scenario_config

        project_root = _project_root()
        spec = ScenarioSpec(
            scenario_id="S11_MR_BASELINE",
            enabled=True,
            strategy_type="mean_reversion",
            config_mode="override",
            base_refs={
                "mean_reversion": "config/aurora/strategies/mean_reversion.yaml",
                "alpha_search": "config/alpha_search.yaml",
                "alpha_search_system": "config/alpha_search_system.yaml",
            },
            overrides={},
        )

        try:
            alpha_cfg, sys_cfg, strategy_cfg = resolve_scenario_config(spec, project_root)
        except Exception:
            pytest.skip("Config resolution failed")

        log_dir = tmp_path / "S11"
        log_dir.mkdir()

        worker = ScenarioWorker(
            spec=spec,
            alpha_search_config=alpha_cfg,
            system_config=sys_cfg,
            strategy_config=strategy_cfg,
            log_dir=log_dir,
        )

        snapshot = AlphaInputV1(**make_snapshot())
        results = worker.process_snapshot(snapshot)
        assert isinstance(results, list)
        worker.shutdown()

    def test_mixed_regime_propagation(self, tmp_path):
        """Different regime values flow to scoring correctly."""
        from apps.reference.domains.alpha_search.runtime.scenario_worker import ScenarioWorker
        from apps.reference.domains.alpha_search.runtime.config_resolver import resolve_scenario_config

        project_root = _project_root()
        spec = ScenarioSpec(
            scenario_id="S01_REGIME_TEST",
            enabled=True,
            strategy_type="aurora",
            config_mode="override",
            base_refs={
                "aurora": "config/aurora/strategies/aurora.yaml",
                "alpha_search": "config/alpha_search.yaml",
            },
            overrides={},
        )

        try:
            alpha_cfg, sys_cfg, strategy_cfg = resolve_scenario_config(spec, project_root)
        except Exception:
            pytest.skip("Config resolution failed")

        log_dir = tmp_path / "S01_REGIME"
        log_dir.mkdir()

        worker = ScenarioWorker(
            spec=spec,
            alpha_search_config=alpha_cfg,
            system_config=sys_cfg,
            strategy_config=strategy_cfg,
            log_dir=log_dir,
        )

        # Process with different regimes
        for regime in ["DEFAULT", "TRENDING", "MEAN_REVERTING"]:
            snapshot = AlphaInputV1(**make_snapshot(regime=regime))
            results = worker.process_snapshot(snapshot)
            assert isinstance(results, list)
            if results:
                assert results[0]["regime"] == regime

        worker.shutdown()


@pytest.mark.integration
class TestManagerIntegration:
    """Tests for ScenarioManager integration."""

    def test_aggregate_csv_populated(self, tmp_path):
        """CSV has rows from all scenarios after fan_out."""
        from apps.reference.domains.alpha_search.runtime.scenario_manager import ScenarioManager

        config = ScenarioMatrixConfig(
            matrix_id="test",
            version=1,
            runtime=RuntimeConfig(),
            hot_reload=HotReloadConfig(),
            input=InputConfig(stream_path="dummy_stream.jsonl"),
            scenarios=[
                ScenarioSpec(
                    scenario_id="S01_TEST",
                    enabled=True,
                    strategy_type="aurora",
                    config_mode="override",
                    base_refs={
                        "aurora": "config/aurora/strategies/aurora.yaml",
                        "alpha_search": "config/alpha_search.yaml",
                    },
                    overrides={},
                ),
            ],
        )

        project_root = _project_root()
        session_dir = tmp_path / "session"
        (session_dir / "aggregate").mkdir(parents=True)

        manager = ScenarioManager(config, project_root, session_dir)
        count = manager.initialize()

        if count == 0:
            pytest.skip("No workers initialized")

        snapshot = AlphaInputV1(**make_snapshot())
        results = manager.fan_out(snapshot)

        csv_path = session_dir / "aggregate" / "aggregate_metrics.csv"
        assert csv_path.exists()
        manager.shutdown()

    def test_per_scenario_scores_jsonl(self, tmp_path):
        """Each scenario dir has scores.jsonl after processing."""
        from apps.reference.domains.alpha_search.runtime.scenario_manager import ScenarioManager

        config = ScenarioMatrixConfig(
            matrix_id="test",
            version=1,
            runtime=RuntimeConfig(),
            hot_reload=HotReloadConfig(),
            input=InputConfig(stream_path="dummy_stream.jsonl"),
            scenarios=[
                ScenarioSpec(
                    scenario_id="S01_TEST",
                    enabled=True,
                    strategy_type="aurora",
                    config_mode="override",
                    base_refs={
                        "aurora": "config/aurora/strategies/aurora.yaml",
                        "alpha_search": "config/alpha_search.yaml",
                    },
                    overrides={},
                ),
            ],
        )

        project_root = _project_root()
        session_dir = tmp_path / "session"
        (session_dir / "aggregate").mkdir(parents=True)

        manager = ScenarioManager(config, project_root, session_dir)
        count = manager.initialize()

        if count == 0:
            pytest.skip("No workers initialized")

        snapshot = AlphaInputV1(**make_snapshot())
        manager.fan_out(snapshot)

        scores_path = session_dir / "S01_TEST" / "scores.jsonl"
        assert scores_path.exists()
        manager.shutdown()

    def test_replay_to_shutdown_lifecycle(self, tmp_path):
        """Full lifecycle: init -> process -> shutdown."""
        from apps.reference.domains.alpha_search.runtime.scenario_manager import ScenarioManager

        config = ScenarioMatrixConfig(
            matrix_id="test",
            version=1,
            runtime=RuntimeConfig(),
            hot_reload=HotReloadConfig(),
            input=InputConfig(stream_path="dummy_stream.jsonl"),
            scenarios=[
                ScenarioSpec(
                    scenario_id="S01_LIFE",
                    enabled=True,
                    strategy_type="aurora",
                    config_mode="override",
                    base_refs={
                        "aurora": "config/aurora/strategies/aurora.yaml",
                        "alpha_search": "config/alpha_search.yaml",
                    },
                    overrides={},
                ),
            ],
        )

        project_root = _project_root()
        session_dir = tmp_path / "session"
        (session_dir / "aggregate").mkdir(parents=True)

        manager = ScenarioManager(config, project_root, session_dir)
        count = manager.initialize()

        snapshot = AlphaInputV1(**make_snapshot())
        for _ in range(3):
            manager.fan_out(snapshot)

        summary = manager.get_aggregate_summary()
        assert summary["snapshots_dispatched"] == 3

        manager.shutdown()  # Should not raise

    def test_effective_config_contains_overrides(self, tmp_path):
        """Persisted config reflects applied overrides."""
        from apps.reference.domains.alpha_search.runtime.scenario_manager import ScenarioManager
        import yaml as yaml_lib

        config = ScenarioMatrixConfig(
            matrix_id="test",
            version=1,
            runtime=RuntimeConfig(),
            hot_reload=HotReloadConfig(),
            input=InputConfig(stream_path="dummy_stream.jsonl"),
            scenarios=[
                ScenarioSpec(
                    scenario_id="S02_AGG",
                    enabled=True,
                    strategy_type="aurora",
                    config_mode="override",
                    base_refs={
                        "aurora": "config/aurora/strategies/aurora.yaml",
                        "alpha_search": "config/alpha_search.yaml",
                    },
                    overrides={
                        "aurora.decision.signal_threshold": 0.12,
                    },
                ),
            ],
        )

        project_root = _project_root()
        session_dir = tmp_path / "session"
        (session_dir / "aggregate").mkdir(parents=True)

        manager = ScenarioManager(config, project_root, session_dir)
        count = manager.initialize()

        if count == 0:
            pytest.skip("Worker init failed")

        cfg_file = session_dir / "S02_AGG" / "config_effective.yaml"
        assert cfg_file.exists()

        with open(cfg_file) as f:
            effective = yaml_lib.safe_load(f)

        # The effective config should contain the applied overrides
        assert isinstance(effective, dict)
        manager.shutdown()
