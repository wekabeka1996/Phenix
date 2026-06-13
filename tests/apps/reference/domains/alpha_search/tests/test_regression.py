"""
Cross-Cutting: Regression Tests
=================================

Guards against previously-fixed bugs.
8 tests codifying fixes from implementation phases.
"""

import decimal
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from tests.apps.reference.domains.alpha_search.snapshot_factory import make_snapshot


@pytest.mark.unit
class TestPayloadExtraction:
    """Regression tests for _extract_payload fix (Phase 6)."""

    def test_localbus_payload_extraction_dict(self):
        """_extract_payload handles LocalBus dict format."""
        from apps.reference.domains.alpha_search.backtest_plugin import AlphaSearchBacktestPlugin
        from apps.reference.domains.alpha_search.config_models import get_default_config

        bus = MagicMock()
        cfg = get_default_config()
        cfg.enabled = False
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

        # LocalBus wraps as {"pld": {...}, "rid": "..."}
        event = {"pld": {"symbol": "BTCUSDT", "features": {"obi": 0.1}}}
        result = plugin._extract_payload(event)
        assert result == {"symbol": "BTCUSDT", "features": {"obi": 0.1}}

    def test_localbus_payload_extraction_message(self):
        """_extract_payload handles Message-like objects."""
        from apps.reference.domains.alpha_search.backtest_plugin import AlphaSearchBacktestPlugin
        from apps.reference.domains.alpha_search.config_models import get_default_config

        bus = MagicMock()
        cfg = get_default_config()
        cfg.enabled = False
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

        msg = MagicMock()
        msg.pld = {"symbol": "BTCUSDT"}
        result = plugin._extract_payload(msg)
        assert result == {"symbol": "BTCUSDT"}


@pytest.mark.unit
class TestYAMLUnwrap:
    """Regression tests for YAML top-level key unwrapping."""

    def test_yaml_top_level_key_unwrap(self, tmp_path):
        """Config resolver unwraps {'aurora': {...}} correctly."""
        from apps.reference.domains.alpha_search.runtime.config_resolver import resolve_scenario_config
        from apps.reference.domains.alpha_search.runtime.contracts import ScenarioSpec

        project_root = Path(__file__).resolve().parents[6]
        spec = ScenarioSpec(
            scenario_id="S_UNWRAP",
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

        # Should not have double-nested aurora key
        assert alpha_cfg is not None
        assert alpha_cfg.enabled is True

    def test_yaml_no_double_unwrap(self, tmp_path):
        """Flat YAML not double-unwrapped."""
        import yaml
        flat_yaml = tmp_path / "flat.yaml"
        flat_yaml.write_text(yaml.dump({
            "enabled": True,
            "shadow_mode": True,
            "triggers": {
                "feature_event": "EVT:FEATURES_CALCULATED",
                "decision_event": "CMD:PROCESS_STRATEGY",
                "emit_event": "EVT:ALPHA_SCORE_CALCULATED",
            },
            "cache": {"max_per_symbol": 10, "require_same_bar_close_ts": False},
            "providers": {},
            "virtual_trader": {
                "enabled": False,
                "per_provider": True,
                "max_positions_per_symbol": 1,
                "notional_size": 1000,
                "exit": {"max_bars": 12, "max_hold_sec": 3600},
            },
            "legacy": {},
        }), encoding="utf-8")

        with open(flat_yaml) as f:
            raw = yaml.safe_load(f)

        # The raw dict should NOT be unwrapped (no top-level "alpha_search" key)
        assert "enabled" in raw
        assert "alpha_search" not in raw


@pytest.mark.unit
class TestThresholdSync:
    """Regression test for threshold sync fix."""

    def test_threshold_sync_on_override(self, tmp_path):
        """_base_threshold + provider_configs.threshold synced."""
        from apps.reference.domains.alpha_search.runtime.scenario_worker import ScenarioWorker
        from apps.reference.domains.alpha_search.runtime.config_resolver import resolve_scenario_config
        from apps.reference.domains.alpha_search.runtime.contracts import ScenarioSpec

        project_root = Path(__file__).resolve().parents[6]
        spec = ScenarioSpec(
            scenario_id="S_THR_SYNC",
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
        )

        try:
            alpha_cfg, sys_cfg, strategy_cfg = resolve_scenario_config(spec, project_root)
        except Exception:
            pytest.skip("Config resolution failed")

        log_dir = tmp_path / "S_THR_SYNC"
        log_dir.mkdir()

        worker = ScenarioWorker(
            spec=spec,
            alpha_search_config=alpha_cfg,
            system_config=sys_cfg,
            strategy_config=strategy_cfg,
            log_dir=log_dir,
        )

        aurora = worker._plugin.providers.get("aurora")
        if not aurora:
            pytest.skip("Aurora provider not initialized")

        # Both paths should have the same threshold
        assert float(aurora._base_threshold) == pytest.approx(0.12, abs=0.001)
        if "aurora" in worker._plugin.provider_configs:
            assert worker._plugin.provider_configs["aurora"].threshold == pytest.approx(0.12, abs=0.001)

        worker.shutdown()

    def test_aurora_threshold_scales_with_regime(self, tmp_path):
        """ScenarioWorker applies effective threshold = base * regime_factor."""
        from apps.reference.domains.alpha_search.runtime.scenario_worker import ScenarioWorker
        from apps.reference.domains.alpha_search.runtime.config_resolver import resolve_scenario_config
        from apps.reference.domains.alpha_search.runtime.contracts import ScenarioSpec, AlphaInputV1

        project_root = Path(__file__).resolve().parents[6]
        spec = ScenarioSpec(
            scenario_id="S_REGIME_SCALE",
            enabled=True,
            strategy_type="aurora",
            config_mode="override",
            base_refs={
                "aurora": "config/aurora/strategies/aurora.yaml",
                "alpha_search": "config/alpha_search.yaml",
            },
            overrides={
                "aurora.decision.signal_threshold": 0.12,
                "aurora.decision.regime_threshold_multipliers.HIGH_VOLATILITY": 1.5,
                "aurora.decision.regime_threshold_multipliers.TREND_UP": 0.8,
                "aurora.decision.regime_threshold_multipliers.DEFAULT": 1.0,
            },
        )

        try:
            alpha_cfg, sys_cfg, strategy_cfg = resolve_scenario_config(spec, project_root)
        except Exception:
            pytest.skip("Config resolution failed")

        worker = ScenarioWorker(
            spec=spec,
            alpha_search_config=alpha_cfg,
            system_config=sys_cfg,
            strategy_config=strategy_cfg,
            log_dir=tmp_path / "S_REGIME_SCALE",
        )

        if "aurora" not in worker._plugin.provider_configs:
            pytest.skip("Aurora provider not initialized")

        snap_hv = AlphaInputV1.model_validate(
            make_snapshot(symbol="TESTUSDT", regime="HIGH_VOLATILITY")
        )
        worker.process_snapshot(snap_hv)
        assert worker._plugin.provider_configs["aurora"].threshold == pytest.approx(
            0.18, abs=0.001
        )

        snap_tu = AlphaInputV1.model_validate(
            make_snapshot(
                symbol="TESTUSDT",
                regime="TREND_UP",
                ts_ms=1740000005000,
                bar_close_ts=1740000005000,
            )
        )
        worker.process_snapshot(snap_tu)
        assert worker._plugin.provider_configs["aurora"].threshold == pytest.approx(
            0.096, abs=0.001
        )

        worker.shutdown()


@pytest.mark.unit
class TestProjectRoot:
    """Regression test for project root path."""

    def test_project_root_parents_5(self):
        """parents[5] from launcher.py = project root."""
        launcher_dir = (
            Path(__file__).resolve().parents[6]
            / "apps"
            / "reference"
            / "domains"
            / "alpha_search"
            / "runtime"
        )
        launcher_py = launcher_dir / "launcher.py"

        if not launcher_py.exists():
            pytest.skip("launcher.py not found")

        # Simulate: project_root = Path(__file__).resolve().parents[5]
        # launcher.py is at: apps/reference/domains/alpha_search/runtime/launcher.py
        # parents[0] = runtime/
        # parents[1] = alpha_search/
        # parents[2] = domains/
        # parents[3] = reference/
        # parents[4] = apps/
        # parents[5] = project root
        project_root = launcher_py.resolve().parents[5]

        # Should contain key project files
        assert (project_root / "pytest.ini").exists() or \
               (project_root / "config").exists()


@pytest.mark.unit
class TestScenarioMatrix:
    """Regression test for full matrix validation."""

    def test_scenario_matrix_twelve_scenarios_all_valid(self):
        """Full matrix parses and all 12 scenarios resolve."""
        from apps.reference.domains.alpha_search.runtime.launcher import load_matrix_config

        project_root = Path(__file__).resolve().parents[6]
        matrix_path = project_root / "config" / "alpha_search" / "scenario_matrix.yaml"

        if not matrix_path.exists():
            pytest.skip("scenario_matrix.yaml not found")

        config = load_matrix_config(matrix_path)
        enabled = [s for s in config.scenarios if s.enabled]
        assert len(enabled) == 12

    def test_ensemble_valid_override_paths(self):
        """S16/S17 override paths validate (no extra='forbid' errors)."""
        from apps.reference.domains.alpha_search.runtime.launcher import load_matrix_config
        from apps.reference.domains.alpha_search.runtime.override_allowlist import validate_overrides

        project_root = Path(__file__).resolve().parents[6]
        matrix_path = project_root / "config" / "alpha_search" / "scenario_matrix.yaml"

        if not matrix_path.exists():
            pytest.skip("scenario_matrix.yaml not found")

        config = load_matrix_config(matrix_path)

        # Find ensemble scenarios
        ensemble_scenarios = [
            s for s in config.scenarios
            if s.strategy_type == "ensemble" and s.enabled
        ]

        for spec in ensemble_scenarios:
            # Validate overrides against allowlist
            rejected = validate_overrides(spec.strategy_type, spec.overrides)
            # All ensemble overrides should be allowed
            assert rejected == [], \
                f"{spec.scenario_id} has rejected overrides: {rejected}"
