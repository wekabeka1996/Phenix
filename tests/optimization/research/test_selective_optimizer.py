"""
tests/optimization/research/test_selective_optimizer.py

Unit tests for the Optuna Research Domain.
All tests use mocks — no real backtest is executed.

Coverage:
    - WeightRegistry: list_groups, resolve_paths, unknown name
    - SearchSpaceLoading: single YAML, merge multiple, unknown raises
    - ResearchGates: min_trades fail, max_dd fail, pass
    - ObjectiveScore: calmar, sharpe, roi, alpha modes
    - SelectiveOptimizerMocked: run calls adapter N times, overlay keys,
      best_overlay, export_writes_yaml, symbols injected in overlay
"""

import math
import sys
import yaml
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

# ============================================================================
# TestWeightRegistry
# ============================================================================

class TestWeightRegistry:
    def test_list_groups_returns_8_groups(self):
        from optimization.research.weight_registry import list_groups
        groups = list_groups()
        assert len(groups) == 8
        expected = {
            "btc_weights", "eth_weights", "sol_weights",
            "global_signal_weights", "feature_neutrals",
            "regime_knobs", "risk_weights", "pillar_weights",
        }
        assert set(groups) == expected

    def test_resolve_paths_all_files_exist(self):
        from optimization.research.weight_registry import list_groups, resolve_paths
        paths = resolve_paths(list_groups())
        for p in paths:
            assert p.exists(), f"Search space file missing: {p}"
            assert p.suffix == ".yaml"

    def test_resolve_paths_single_group(self):
        from optimization.research.weight_registry import resolve_paths
        paths = resolve_paths(["btc_weights"])
        assert len(paths) == 1
        assert paths[0].name == "btc_weights.yaml"

    def test_unknown_name_raises_key_error(self):
        from optimization.research.weight_registry import resolve_paths
        with pytest.raises(KeyError, match="phantom_group"):
            resolve_paths(["phantom_group"])

    def test_describe_group_returns_meta(self):
        from optimization.research.weight_registry import describe_group
        meta = describe_group("btc_weights")
        assert "description" in meta
        assert "BTCUSDT" in meta.get("description", "") or meta.get("symbol") == "BTCUSDT"


# ============================================================================
# TestSearchSpaceLoading
# ============================================================================

class TestSearchSpaceLoading:
    def test_single_yaml_flattens_correctly(self):
        from optimization.research.selective_optimizer import (
            SelectiveOptimizer, _flatten_search_space
        )
        from optimization.research.weight_registry import resolve_paths
        [path] = resolve_paths(["btc_weights"])
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        space = raw.get("search_space", raw)
        space.pop("meta", None)
        flat = _flatten_search_space(space)
        # All keys should start with aurora.assets.BTCUSDT.weights.
        for k in flat:
            assert k.startswith("aurora.assets.BTCUSDT.weights."), (
                f"Unexpected key: {k}"
            )
        assert "aurora.assets.BTCUSDT.weights.obi" in flat
        assert "aurora.assets.BTCUSDT.weights.tfi" in flat
        assert "aurora.assets.BTCUSDT.weights.delta_price" in flat

    def test_all_yaml_files_parse_without_error(self):
        from optimization.research.weight_registry import list_groups, resolve_paths
        from optimization.research.selective_optimizer import _flatten_search_space
        for name in list_groups():
            [path] = resolve_paths([name])
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            space = raw.get("search_space", raw)
            space.pop("meta", None)
            flat = _flatten_search_space(space)
            assert len(flat) > 0, f"Empty search space in {name}"

    def test_multiple_yamls_merge_no_conflicts(self):
        from optimization.research.selective_optimizer import (
            SelectiveOptimizer, _flatten_search_space
        )
        from optimization.research.weight_registry import resolve_paths
        paths = resolve_paths(["btc_weights", "global_signal_weights"])
        all_keys = set()
        for path in paths:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            space = raw.get("search_space", raw)
            space.pop("meta", None)
            flat = _flatten_search_space(space)
            all_keys.update(flat.keys())
        # BTC + global should cover at least 15 unique params
        assert len(all_keys) >= 15

    def test_param_specs_have_required_fields(self):
        from optimization.research.weight_registry import list_groups, resolve_paths
        from optimization.research.selective_optimizer import _flatten_search_space
        for name in list_groups():
            [path] = resolve_paths([name])
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            space = raw.get("search_space", raw)
            space.pop("meta", None)
            flat = _flatten_search_space(space)
            for key, spec in flat.items():
                assert "type" in spec, f"Missing 'type' in {name}:{key}"
                if spec["type"] in ("float", "int"):
                    assert "low" in spec, f"Missing 'low' in {name}:{key}"
                    assert "high" in spec, f"Missing 'high' in {name}:{key}"
                    assert spec["low"] < spec["high"], (
                        f"low >= high in {name}:{key}: low={spec['low']} high={spec['high']}"
                    )


# ============================================================================
# TestResearchGates
# ============================================================================

class TestResearchGates:
    def _make_metrics(self, trades, dd, roi=5.0, sharpe=1.0, calmar=1.0):
        from optimization.objectives import AlphaMetrics
        return AlphaMetrics(
            sharpe_ratio=sharpe,
            calmar_ratio=calmar,
            max_drawdown_pct=dd,
            total_trades=trades,
            roi_pct=roi,
        )

    def _make_optimizer(self, min_trades=5, max_dd=40.0):
        from optimization.research.selective_optimizer import (
            SelectiveOptimizer, ResearchGates, ResearchStudyConfig
        )
        opt = SelectiveOptimizer.__new__(SelectiveOptimizer)
        opt.gates = ResearchGates(min_trades=min_trades, max_dd_pct=max_dd)
        opt.objective_mode = None
        opt.penalty_config = None
        opt.study_config = ResearchStudyConfig()
        return opt

    def test_gate_min_trades_fail_returns_hard_reject(self):
        opt = self._make_optimizer(min_trades=5)
        metrics = self._make_metrics(trades=0, dd=10.0)
        stage_result = SimpleNamespace(success=True, raw_report={})
        result = opt._check_gates(0, metrics, stage_result)
        assert result == -1e9

    def test_gate_max_dd_fail_returns_hard_reject(self):
        opt = self._make_optimizer(max_dd=40.0)
        metrics = self._make_metrics(trades=10, dd=99.9)
        stage_result = SimpleNamespace(success=True, raw_report={})
        result = opt._check_gates(0, metrics, stage_result)
        assert result == -1e9

    def test_gate_pass_returns_none(self):
        opt = self._make_optimizer(min_trades=5, max_dd=40.0)
        metrics = self._make_metrics(trades=20, dd=15.0)
        stage_result = SimpleNamespace(success=True, raw_report={})
        result = opt._check_gates(0, metrics, stage_result)
        assert result is None


# ============================================================================
# TestObjectiveScore
# ============================================================================

class TestObjectiveScore:
    def _make_metrics(self, sharpe=1.5, calmar=2.0, roi=10.0, dd=5.0, trades=20):
        from optimization.objectives import AlphaMetrics
        return AlphaMetrics(
            sharpe_ratio=sharpe,
            calmar_ratio=calmar,
            max_drawdown_pct=dd,
            total_trades=trades,
            roi_pct=roi,
        )

    def _make_optimizer(self, mode):
        from optimization.research.selective_optimizer import (
            SelectiveOptimizer, ResearchObjectiveMode, ResearchGates, ResearchStudyConfig
        )
        from optimization.objectives import PenaltyConfig
        opt = SelectiveOptimizer.__new__(SelectiveOptimizer)
        opt.objective_mode = ResearchObjectiveMode(mode)
        opt.penalty_config = PenaltyConfig()
        opt.gates = ResearchGates()
        opt.study_config = ResearchStudyConfig()
        return opt

    def test_calmar_mode(self):
        opt = self._make_optimizer("calmar")
        m = self._make_metrics(roi=10.0, dd=5.0)
        score = opt._compute_score(m)
        assert abs(score - 2.0) < 0.001  # 10.0 / 5.0 = 2.0

    def test_sharpe_mode(self):
        opt = self._make_optimizer("sharpe")
        m = self._make_metrics(sharpe=1.75)
        score = opt._compute_score(m)
        assert abs(score - 1.75) < 0.001

    def test_roi_mode(self):
        opt = self._make_optimizer("roi")
        m = self._make_metrics(roi=13.5)
        score = opt._compute_score(m)
        assert abs(score - 13.5) < 0.001

    def test_alpha_mode_uses_compute_alpha_score(self):
        opt = self._make_optimizer("alpha")
        m = self._make_metrics(sharpe=1.0, dd=5.0, trades=20)
        score = opt._compute_score(m)
        # No penalties (dd=5 < soft=20, trades=20 >= min=10) → score ≈ sharpe = 1.0
        assert math.isfinite(score)
        assert score > 0.0

    def test_calmar_zero_dd_returns_roi(self):
        """Calmar with dd=0 should fall back to roi (not divide-by-zero)."""
        opt = self._make_optimizer("calmar")
        m = self._make_metrics(roi=5.0, dd=0.0)
        score = opt._compute_score(m)
        assert score == 5.0  # fallback to roi_pct

    def test_calmar_negative_roi_zero_dd_returns_hard_reject(self):
        opt = self._make_optimizer("calmar")
        m = self._make_metrics(roi=-3.0, dd=0.0)
        score = opt._compute_score(m)
        assert score == -1e9


# ============================================================================
# TestSelectiveOptimizerMocked
# ============================================================================

class TestSelectiveOptimizerMocked:

    def _build_optimizer(self, n_trials=3, spaces=None):
        """Build SelectiveOptimizer with mocked BacktestAdapter."""
        from optimization.research.selective_optimizer import (
            SelectiveOptimizer, ResearchGates, ResearchStudyConfig, ResearchObjectiveMode
        )
        from optimization.objectives import AlphaMetrics
        from optimization.backtest_interface import StageResult

        # Mock BacktestAdapter
        mock_adapter = MagicMock()
        good_metrics = AlphaMetrics(
            sharpe_ratio=1.5,
            calmar_ratio=2.0,
            max_drawdown_pct=8.0,
            total_trades=20,
            roi_pct=12.0,
        )
        good_stage = StageResult(success=True, raw_report={})
        mock_adapter.run_stage1.return_value = (good_metrics, good_stage)

        opt = SelectiveOptimizer.__new__(SelectiveOptimizer)
        opt.config_dir = Path("config/aurora")
        opt.symbols = ["BTCUSDT", "ETHUSDT"]
        opt.search_space_names = spaces or ["btc_weights"]
        opt.start_date = "2024-01-01"
        opt.end_date = "2024-12-31"
        opt.study_config = ResearchStudyConfig(
            name=f"test_study_{id(opt)}",
            n_trials=n_trials,
            storage=None,   # in-memory
            seed=0,
        )
        opt.gates = ResearchGates(min_trades=5, max_dd_pct=40.0)
        opt.objective_mode = ResearchObjectiveMode.CALMAR
        from optimization.objectives import PenaltyConfig
        opt.penalty_config = PenaltyConfig()
        opt.adapter = mock_adapter
        opt._flat_space = None
        return opt, mock_adapter

    def test_load_search_spaces_returns_nonempty(self):
        opt, _ = self._build_optimizer(spaces=["btc_weights"])
        flat = opt._load_search_spaces()
        assert len(flat) > 0
        assert all(k.startswith("aurora.assets.BTCUSDT.weights.") for k in flat)

    def test_run_calls_adapter_n_trials_times(self):
        import optuna
        opt, mock_adapter = self._build_optimizer(n_trials=3)
        opt._flat_space = opt._load_search_spaces()

        study = optuna.create_study(
            study_name=opt.study_config.name,
            sampler=optuna.samplers.TPESampler(seed=0),
            direction="maximize",
        )
        study.optimize(opt.objective_fn, n_trials=3)

        assert mock_adapter.run_stage1.call_count == 3

    def test_overlay_contains_sampled_param_keys(self):
        import optuna
        from optimization.research.selective_optimizer import _build_overlay

        opt, mock_adapter = self._build_optimizer(n_trials=1)
        opt._flat_space = opt._load_search_spaces()

        captured_overlays = []
        original_run = mock_adapter.run_stage1.side_effect

        def capture_overlay(overlay, **kwargs):
            from optimization.objectives import AlphaMetrics
            from optimization.backtest_interface import StageResult
            captured_overlays.append(dict(overlay))
            return (
                AlphaMetrics(sharpe_ratio=1.0, calmar_ratio=1.5, max_drawdown_pct=5.0,
                             total_trades=10, roi_pct=5.0),
                StageResult(success=True, raw_report={}),
            )

        mock_adapter.run_stage1.side_effect = capture_overlay

        study = optuna.create_study(
            study_name=opt.study_config.name,
            sampler=optuna.samplers.TPESampler(seed=42),
            direction="maximize",
        )
        study.optimize(opt.objective_fn, n_trials=1)

        assert len(captured_overlays) == 1
        overlay = captured_overlays[0]
        # Must have aurora root with BTCUSDT weights
        assert "aurora" in overlay
        assert "assets" in overlay["aurora"]
        assert "BTCUSDT" in overlay["aurora"]["assets"]

    def test_symbols_injected_in_overlay(self):
        import optuna
        opt, mock_adapter = self._build_optimizer(n_trials=1)
        opt._flat_space = opt._load_search_spaces()

        captured_overlays = []

        def capture_overlay(overlay, **kwargs):
            from optimization.objectives import AlphaMetrics
            from optimization.backtest_interface import StageResult
            captured_overlays.append(dict(overlay))
            return (
                AlphaMetrics(sharpe_ratio=1.0, calmar_ratio=1.5, max_drawdown_pct=5.0,
                             total_trades=10, roi_pct=5.0),
                StageResult(success=True, raw_report={}),
            )

        mock_adapter.run_stage1.side_effect = capture_overlay

        study = optuna.create_study(direction="maximize")
        study.optimize(opt.objective_fn, n_trials=1)

        overlay = captured_overlays[0]
        # SSOT path: trading.symbols_to_track (read by apply_backtest_symbols_filter)
        symbols_injected = overlay.get("trading", {}).get("symbols_to_track")
        assert symbols_injected == ["BTCUSDT", "ETHUSDT"]

    def test_best_overlay_returns_nonempty_dict(self):
        import optuna
        opt, mock_adapter = self._build_optimizer(n_trials=2)
        opt._flat_space = opt._load_search_spaces()

        study = optuna.create_study(direction="maximize")
        study.optimize(opt.objective_fn, n_trials=2)

        overlay = opt.best_overlay(study)
        assert isinstance(overlay, dict)
        assert len(overlay) > 0

    def test_export_best_config_writes_valid_yaml(self, tmp_path):
        import optuna
        opt, mock_adapter = self._build_optimizer(n_trials=2)
        opt._flat_space = opt._load_search_spaces()

        study = optuna.create_study(direction="maximize")
        study.optimize(opt.objective_fn, n_trials=2)

        output = tmp_path / "test_export.yaml"
        opt.export_best_config(study, output)

        assert output.exists()
        parsed = yaml.safe_load(output.read_text(encoding="utf-8"))
        assert "meta" in parsed
        assert "overlay" in parsed
        assert parsed["meta"]["study_name"] == opt.study_config.name
        assert isinstance(parsed["overlay"], dict)

    def test_backtest_failure_returns_hard_reject(self):
        import optuna
        from optimization.backtest_interface import StageResult
        opt, mock_adapter = self._build_optimizer(n_trials=1)
        opt._flat_space = opt._load_search_spaces()

        # Make adapter return failure
        from optimization.objectives import AlphaMetrics
        mock_adapter.run_stage1.return_value = (
            AlphaMetrics(),
            StageResult(success=False, error="Simulated backtest failure"),
        )

        study = optuna.create_study(direction="maximize")
        study.optimize(opt.objective_fn, n_trials=1)
        assert study.best_value == -1e9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
