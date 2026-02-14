"""
optimization/optimizer.py — AuroraOptimizer: hierarchical 3-stage orchestrator.

Coordinates the full optimization pipeline:
    Stage 0: Regime Calibration (outer grid × Optuna study)
    Stage 1: Alpha Search (Optuna TPE with penalties)
    Stage 2: Robustness Validation (per-fold WF × N_stress × Bootstrap)
    Holdout: Cold holdout go/no-go gate (date-isolated)
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

try:
    import optuna
except ImportError:
    optuna = None  # type: ignore

from optimization.objectives import (
    PenaltyConfig,
    RegimeStabilityMetrics,
    AlphaMetrics,
    compute_stability_score,
    compute_alpha_score,
)
from optimization.backtest_interface import BacktestAdapter, StageResult
from optimization.robustness import (
    WalkForwardValidator,
    WalkForwardFold,
    BlockBootstrap,
    ExecutionStress,
    ColdHoldoutGate,
    HoldoutResult,
)

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config loader helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load a YAML config file."""
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def _flatten_search_space(node: Dict[str, Any], path: list = None) -> Dict[str, Dict]:
    """
    Recursively flatten nested search space into {dotted_name: param_spec}.
    A leaf is identified by having a "type" key.
    """
    if path is None:
        path = []
    result = {}
    for key, value in node.items():
        current_path = path + [key]
        if isinstance(value, dict) and "type" in value:
            result[".".join(current_path)] = value
        elif isinstance(value, dict):
            result.update(_flatten_search_space(value, current_path))
    return result


def _sample_param(trial: "optuna.Trial", name: str, spec: Dict) -> Any:
    """Sample a single parameter from Optuna trial based on spec."""
    ptype = spec["type"]
    if ptype == "float":
        kwargs = {"name": name, "low": spec["low"], "high": spec["high"]}
        if "step" in spec:
            kwargs["step"] = spec["step"]
        return trial.suggest_float(**kwargs)
    elif ptype == "int":
        kwargs = {"name": name, "low": spec["low"], "high": spec["high"]}
        if "step" in spec:
            kwargs["step"] = spec["step"]
        return trial.suggest_int(**kwargs)
    elif ptype == "categorical":
        return trial.suggest_categorical(name, spec["choices"])
    else:
        raise ValueError(f"Unknown param type: {ptype}")


def _build_overlay(flat_params: Dict[str, Any]) -> Dict[str, Any]:
    """Convert flat dotted params back to nested dict for config overlay."""
    overlay: Dict[str, Any] = {}
    for dotted_key, value in flat_params.items():
        parts = dotted_key.split(".")
        d = overlay
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        d[parts[-1]] = value
    return overlay


def _merge_config(target: Dict, source: Dict) -> Dict:
    """Deep-merge source into target (source wins on conflict)."""
    for key, val in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(val, dict):
            _merge_config(target[key], val)
        else:
            target[key] = val
    return target


def _date_add_months(dt: datetime, months: int) -> datetime:
    """Add (or subtract) months to a datetime."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, 28)  # Safe clamp
    return dt.replace(year=year, month=month, day=day)


# ---------------------------------------------------------------------------
# Data range management
# ---------------------------------------------------------------------------

@dataclass
class DateRange:
    """Start/end date pair for backtesting (inclusive date semantics)."""
    start: str   # "YYYY-MM-DD"
    end: str     # "YYYY-MM-DD"

    @property
    def start_dt(self) -> datetime:
        return datetime.strptime(self.start, "%Y-%m-%d")

    @property
    def end_dt(self) -> datetime:
        return datetime.strptime(self.end, "%Y-%m-%d")

    @property
    def total_days(self) -> int:
        return (self.end_dt - self.start_dt).days

    def sub_range(self, start_pct: float, end_pct: float) -> "DateRange":
        """Get a sub-range by percentage of total duration."""
        total = self.total_days
        new_start = self.start_dt + timedelta(days=int(total * start_pct))
        new_end = self.start_dt + timedelta(days=int(total * end_pct))
        return DateRange(
            start=new_start.strftime("%Y-%m-%d"),
            end=new_end.strftime("%Y-%m-%d"),
        )


def compute_train_holdout_split(
    full_start: str,
    full_end: str,
    holdout_months: int = 3,
) -> tuple:
    """
    Split full date range into train and holdout.
    Holdout = last N months. Train = everything before.

    IMPORTANT: BacktestEngine treats end_date as INCLUSIVE.
    To prevent data leakage, train.end is set 1 day BEFORE holdout.start.
    This guarantees zero overlap even with inclusive boundaries.

    Returns:
        (DateRange(train), DateRange(holdout))
    """
    from datetime import timedelta
    full_end_dt = datetime.strptime(full_end, "%Y-%m-%d")
    holdout_start_dt = _date_add_months(full_end_dt, -holdout_months)
    # Gap: train ends 1 day before holdout starts (inclusive boundary safety)
    train_end_dt = holdout_start_dt - timedelta(days=1)
    return (
        DateRange(start=full_start, end=train_end_dt.strftime("%Y-%m-%d")),
        DateRange(start=holdout_start_dt.strftime("%Y-%m-%d"), end=full_end),
    )


# ---------------------------------------------------------------------------
# Stage Results
# ---------------------------------------------------------------------------

@dataclass
class Stage0Result:
    """Results from Stage 0: Regime Calibration."""
    best_stability_score: float = 0.0
    best_params: Dict[str, Any] = field(default_factory=dict)
    best_basis_tf_sec: int = 300
    all_grid_scores: Dict[int, float] = field(default_factory=dict)


@dataclass
class Stage1Result:
    """Results from Stage 1: Alpha Search."""
    best_alpha_score: float = 0.0
    best_sharpe: float = 0.0
    best_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FoldResult:
    """Result of a single Walk-Forward fold in Stage 2."""
    fold_id: int = 0
    test_sharpe: float = 0.0
    test_mdd_pct: float = 0.0
    test_trades: int = 0
    test_reject_rate: float = 0.0
    hard_violation: bool = False     # MDD > hard or starvation
    bootstrap_pnl_positive_pct: float = 0.0
    bootstrap_sharpe_p5: float = 0.0
    stress_sharpe_median: float = 0.0
    stress_runs: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Stage2Result:
    """Results from Stage 2: Robustness Validation."""
    passed: bool = False
    fold_results: List[FoldResult] = field(default_factory=list)
    median_sharpe: float = 0.0
    sharpe_degradation: float = 0.0
    bootstrap_pnl_positive_pct: float = 0.0
    failed_folds: int = 0
    reasons: List[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Full pipeline result: S0 → S1 → S2 → Holdout."""
    stage0: Optional[Stage0Result] = None
    stage1: Optional[Stage1Result] = None
    stage2: Optional[Stage2Result] = None
    holdout: Optional[HoldoutResult] = None
    final_config: Dict[str, Any] = field(default_factory=dict)
    production_ready: bool = False


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class AuroraOptimizer:
    """
    Hierarchical 3-stage optimizer for Aurora trading system.

    Usage:
        optimizer = AuroraOptimizer(
            config_dir=Path("config"),
            train_range=DateRange("2024-01-01", "2025-10-01"),
            holdout_range=DateRange("2025-10-01", "2025-12-31"),
        )
        result = optimizer.run_full_pipeline()
        if result.production_ready:
            deploy(result.final_config)
    """

    def __init__(
        self,
        config_dir: Path = Path("config"),
        data_dir: Optional[Path] = None,
        train_range: Optional[DateRange] = None,
        holdout_range: Optional[DateRange] = None,
    ):
        self.config_dir = config_dir
        self.opt_config_dir = config_dir / "optimization"

        # Load configs
        self.optimizer_cfg = _load_yaml(self.opt_config_dir / "optimizer_config.yaml")
        self.s0_search_space = _load_yaml(self.opt_config_dir / "stage0_search_space.yaml")
        self.s1_search_space = _load_yaml(self.opt_config_dir / "stage1_search_space.yaml")
        self._locked_symbols, self._locked_strategy_id = self._validate_universe_lock_cfg(self.optimizer_cfg)

        # Date ranges
        self.train_range = train_range
        self.holdout_range = holdout_range

        # Backtest adapter
        self.adapter = BacktestAdapter(
            config_dir=config_dir / "aurora",
            data_dir=data_dir,
            locked_symbols=self._locked_symbols,
            locked_strategy_id=self._locked_strategy_id,
        )

        if optuna is None:
            raise ImportError("optuna is required for optimization. Install: pip install optuna")

    @staticmethod
    def _validate_universe_lock_cfg(cfg: Dict[str, Any]) -> tuple[list[str], str]:
        """
        Enforce optimization universe lock (v1):
          symbols=["BTCUSDT"], strategy_id="aurora".
        """
        data_cfg = cfg.get("data", {}) if isinstance(cfg, dict) else {}
        symbols = data_cfg.get("symbols")
        strategy_id = data_cfg.get("strategy_id")
        if symbols != ["BTCUSDT"] or strategy_id != "aurora":
            raise ValueError(
                "Optimization universe lock violation: expected "
                "data.symbols=['BTCUSDT'] and data.strategy_id='aurora'."
            )
        return ["BTCUSDT"], "aurora"

    # ----- Stage 0: Regime Calibration -----

    def run_stage0(self) -> Stage0Result:
        """
        Stage 0: Optimize regime detector for stability.

        Outer grid: iterate over basis_tf_sec values.
        Inner: Optuna study per tf value, maximizing stability_score.
        Backtests run on self.train_range only.
        """
        s0_cfg = self.optimizer_cfg.get("stage0", {})
        optuna_cfg = self.optimizer_cfg.get("optuna", {})
        n_trials = s0_cfg.get("n_trials", 50)
        n_jobs = int(optuna_cfg.get("n_jobs", 1))
        prefix = s0_cfg.get("study_name_prefix", "aurora_regime")
        outer_grid = s0_cfg.get("outer_grid", {}).get("basis_tf_sec", [300])
        storage = optuna_cfg.get("storage", None)

        weights = self.s0_search_space.get("weights", {})
        w_flicker = weights.get("w_flicker", 2.0)
        w_uncertain = weights.get("w_uncertain", 1.0)

        raw_space = self.s0_search_space.get("search_space", {})
        flat_space = _flatten_search_space(raw_space)

        best_overall = Stage0Result()

        for tf_sec in outer_grid:
            study_name = f"{prefix}_tf{tf_sec}"
            LOG.info(f"=== Stage 0: basis_tf_sec={tf_sec}, study={study_name} ===")

            study = optuna.create_study(
                study_name=study_name,
                direction="maximize",
                storage=storage,
                load_if_exists=True,
            )

            def objective(trial: optuna.Trial) -> float:
                sampled = {}
                for param_name, spec in flat_space.items():
                    sampled[param_name] = _sample_param(trial, param_name, spec)

                overlay = _build_overlay(sampled)
                overlay["basis_tf_sec"] = tf_sec

                metrics, stage_result = self.adapter.run_stage0(
                    overlay,
                    start_date=self.train_range.start if self.train_range else None,
                    end_date=self.train_range.end if self.train_range else None,
                )

                if not stage_result.success:
                    return -1e9

                score = compute_stability_score(
                    metrics, w_flicker=w_flicker, w_uncertain=w_uncertain,
                )

                trial.set_user_attr("definite_ratio", metrics.definite_ratio)
                trial.set_user_attr("flicker_per_h", metrics.flicker_per_h)
                trial.set_user_attr("uncertain_share", metrics.uncertain_share)
                trial.set_user_attr("basis_tf_sec", tf_sec)

                return score

            study.optimize(objective, n_trials=n_trials, n_jobs=n_jobs)

            best_score = study.best_value
            best_overall.all_grid_scores[tf_sec] = best_score

            if best_score > best_overall.best_stability_score:
                best_overall.best_stability_score = best_score
                best_overall.best_params = study.best_params
                best_overall.best_basis_tf_sec = tf_sec

        LOG.info(f"Stage 0 complete: best_tf={best_overall.best_basis_tf_sec}, "
                 f"score={best_overall.best_stability_score:.4f}")
        LOG.info(f"Grid scores: {best_overall.all_grid_scores}")

        return best_overall

    # ----- Stage 1: Alpha Search -----

    def run_stage1(self, regime_config: Dict[str, Any]) -> Stage1Result:
        """
        Stage 1: Optimize strategy parameters for risk-adjusted return.

        Regime config FROZEN from Stage 0 best. Backtests run on train_range.

        NOTE (v1): This is a SINGLE-RUN alpha search — each trial executes
        one backtest on the full train_range. Walk-Forward fold validation
        only happens in Stage 2 (robustness gate). This is a deliberate
        design choice for v1: Stage 1 generates candidates, Stage 2 kills
        the weak ones.
        """
        s1_cfg = self.optimizer_cfg.get("stage1", {})
        optuna_cfg = self.optimizer_cfg.get("optuna", {})
        n_trials = s1_cfg.get("n_trials", 100)
        n_jobs = int(optuna_cfg.get("n_jobs", 1))
        prefix = s1_cfg.get("study_name_prefix", "aurora_alpha")
        storage = optuna_cfg.get("storage", None)

        penalty_raw = self.s1_search_space.get("penalties", {})
        penalty_config = PenaltyConfig(**penalty_raw)

        raw_space = self.s1_search_space.get("search_space", {})
        flat_space = _flatten_search_space(raw_space)

        study = optuna.create_study(
            study_name=prefix,
            direction="maximize",
            storage=storage,
            load_if_exists=True,
        )

        def objective(trial: optuna.Trial) -> float:
            sampled = {}
            for param_name, spec in flat_space.items():
                sampled[param_name] = _sample_param(trial, param_name, spec)

            overlay = _build_overlay(sampled)
            _merge_config(overlay, regime_config)

            metrics, stage_result = self.adapter.run_stage1(
                overlay,
                start_date=self.train_range.start if self.train_range else None,
                end_date=self.train_range.end if self.train_range else None,
            )

            if not stage_result.success:
                return -1e9

            score = compute_alpha_score(metrics, penalty_config)

            trial.set_user_attr("sharpe", metrics.sharpe_ratio)
            trial.set_user_attr("calmar", metrics.calmar_ratio)
            trial.set_user_attr("mdd_pct", metrics.max_drawdown_pct)
            trial.set_user_attr("total_trades", metrics.total_trades)
            trial.set_user_attr("roi_pct", metrics.roi_pct)

            return score

        study.optimize(objective, n_trials=n_trials, n_jobs=n_jobs)

        return Stage1Result(
            best_alpha_score=study.best_value,
            best_sharpe=study.best_trial.user_attrs.get("sharpe", 0.0),
            best_params=study.best_params,
        )

    # ----- Stage 2: Robustness (per-fold Walk-Forward + Stress + Bootstrap) -----

    def run_stage2(
        self,
        candidate_overlay: Dict[str, Any],
        *,
        stage1_sharpe: float = 0.0,
    ) -> Stage2Result:
        """
        Stage 2: Validate candidate via real per-fold Walk-Forward execution.

        For each fold:
          1. Run backtest ONLY on test window (train is implicit via optimization)
          2. Run N_stress variants with execution distortions
          3. Block Bootstrap on test returns
          4. Check hard violations (MDD, starvation)

        Final verdict: median test Sharpe across folds + acceptance criteria.

        Args:
            candidate_overlay: Merged regime + strategy config
            stage1_sharpe: Best Sharpe from Stage 1 (for degradation check)
        """
        s2_cfg = self.optimizer_cfg.get("stage2", {})
        acceptance = s2_cfg.get("acceptance", {})

        # Determine Walk-Forward date ranges over the train period
        if not self.train_range:
            LOG.error("Stage 2 requires train_range for Walk-Forward splits")
            return Stage2Result(passed=False, reasons=["No train_range provided"])

        wf_cfg = s2_cfg.get("walk_forward", {})
        train_pct = wf_cfg.get("train_pct", 0.60)
        gap_pct = wf_cfg.get("gap_pct", 0.10)
        test_pct = wf_cfg.get("test_pct", 0.30)
        n_folds = wf_cfg.get("n_folds", 3)

        total_days = self.train_range.total_days
        if total_days < 14:
            return Stage2Result(passed=False, reasons=[f"Train range too short ({total_days}d)"])

        # Generate fold date ranges using percentage-based splitting
        fold_results: List[FoldResult] = []
        step_pct = test_pct  # Each fold rolls forward by test_pct

        for fold_id in range(n_folds):
            offset_pct = fold_id * step_pct
            fold_test_start_pct = offset_pct + train_pct + gap_pct
            fold_test_end_pct = fold_test_start_pct + test_pct

            if fold_test_end_pct > 1.0:
                LOG.info(f"Fold {fold_id}: test range exceeds data, stopping (used {fold_id} folds)")
                break

            test_range = self.train_range.sub_range(fold_test_start_pct, fold_test_end_pct)
            LOG.info(f"Fold {fold_id}: test={test_range.start}..{test_range.end}")

            fold_result = self._run_single_fold(
                fold_id=fold_id,
                candidate_overlay=candidate_overlay,
                test_range=test_range,
                s2_cfg=s2_cfg,
            )
            fold_results.append(fold_result)

        if not fold_results:
            return Stage2Result(passed=False, reasons=["No folds generated"])

        # Aggregate across folds
        failed_folds = sum(1 for f in fold_results if f.hard_violation)
        test_sharpes = [f.test_sharpe for f in fold_results if not f.hard_violation]
        median_sharpe = statistics.median(test_sharpes) if test_sharpes else 0.0
        sharpe_degradation = stage1_sharpe - median_sharpe if stage1_sharpe > 0 else 0.0

        bs_positive_pcts = [f.bootstrap_pnl_positive_pct for f in fold_results if not f.hard_violation]
        avg_bs_positive = statistics.mean(bs_positive_pcts) if bs_positive_pcts else 0.0

        # Acceptance checks
        reasons = []
        passed = True

        # Any fold completely dead → candidate fails
        if failed_folds > 0:
            reasons.append(f"{failed_folds}/{len(fold_results)} folds had hard violations")
            passed = False

        min_median_sharpe = acceptance.get("min_median_sharpe", 0.3)
        if median_sharpe < min_median_sharpe:
            reasons.append(f"median_sharpe={median_sharpe:.3f} < {min_median_sharpe}")
            passed = False

        max_degradation = acceptance.get("max_sharpe_degradation", 0.5)
        if sharpe_degradation > max_degradation:
            reasons.append(f"sharpe_degradation={sharpe_degradation:.3f} > {max_degradation}")
            passed = False

        min_bs_positive = acceptance.get("bootstrap_pnl_positive_pct", 0.80)
        if avg_bs_positive < min_bs_positive:
            reasons.append(f"bootstrap_pnl_positive={avg_bs_positive:.1%} < {min_bs_positive:.1%}")
            passed = False

        if passed:
            LOG.info(f"✅ Stage 2 PASSED: median_sharpe={median_sharpe:.3f}, "
                     f"degradation={sharpe_degradation:.3f}, bootstrap_positive={avg_bs_positive:.1%}")
        else:
            LOG.warning(f"❌ Stage 2 FAILED: {' | '.join(reasons)}")

        return Stage2Result(
            passed=passed,
            fold_results=fold_results,
            median_sharpe=median_sharpe,
            sharpe_degradation=sharpe_degradation,
            bootstrap_pnl_positive_pct=avg_bs_positive,
            failed_folds=failed_folds,
            reasons=reasons,
        )

    def _run_single_fold(
        self,
        fold_id: int,
        candidate_overlay: Dict[str, Any],
        test_range: DateRange,
        s2_cfg: Dict[str, Any],
    ) -> FoldResult:
        """
        Execute a single Walk-Forward fold:
          1. Run baseline backtest on test_range
          2. Run N stress variants on test_range
          3. Block Bootstrap on baseline returns
          4. Check hard violations
        """
        # --- 1. Baseline run on test window ---
        metrics, stage_result = self.adapter.run_stage1(
            candidate_overlay,
            start_date=test_range.start,
            end_date=test_range.end,
        )

        if not stage_result.success:
            LOG.warning(f"Fold {fold_id}: backtest failed — {stage_result.error}")
            return FoldResult(fold_id=fold_id, hard_violation=True)

        # Hard violations: MDD > hard threshold or starvation
        hard_mdd = self.optimizer_cfg.get("stage1", {}).get("acceptance", {}).get("max_dd_pct", 35.0)
        starvation_min = 3  # Minimum trades per fold test window

        hard_violation = False
        if metrics.max_drawdown_pct > hard_mdd:
            LOG.warning(f"Fold {fold_id}: HARD MDD violation {metrics.max_drawdown_pct:.1f}%")
            hard_violation = True
        if metrics.total_trades < starvation_min:
            LOG.warning(f"Fold {fold_id}: STARVATION — only {metrics.total_trades} trades")
            hard_violation = True

        # --- 2. Stress variants ---
        stress_cfg = s2_cfg.get("execution_stress", {})
        stress_sharpes = [metrics.sharpe_ratio]  # Include baseline
        stress_runs: List[Dict[str, Any]] = []

        # Stress must rerun full backtests with execution overrides.
        stress_engine = ExecutionStress(
            latency_ms_range=tuple(stress_cfg.get("latency_ms_range", [50, 500])),
            slippage_bps_range=tuple(stress_cfg.get("slippage_bps_range", [1, 10])),
            fee_multiplier_range=tuple(stress_cfg.get("fee_multiplier_range", [1.0, 1.5])),
            funding_bps_per_day_range=tuple(stress_cfg.get("funding_bps_per_day_range", [0.0, 0.0])),
        )
        n_stress = int(stress_cfg.get("n_seeds", 3))

        for seed in range(n_stress):
            seed_id = int(seed + fold_id * 1000)
            overrides = stress_engine.sample_overrides(seed=seed_id)
            stress_overlay: Dict[str, Any] = {}
            _merge_config(stress_overlay, candidate_overlay)
            bt = stress_overlay.setdefault("trading", {}).setdefault("backtest", {})
            bt["stress_overrides"] = overrides
            bt.setdefault("backtest_mode", "strict")

            stress_metrics, stress_stage_result = self.adapter.run_stage1(
                stress_overlay,
                start_date=test_range.start,
                end_date=test_range.end,
            )
            if not stress_stage_result.success:
                continue
            stress_sharpes.append(stress_metrics.sharpe_ratio)
            stress_runs.append(
                {
                    "seed": seed_id,
                    "overrides": overrides,
                    "sharpe": stress_metrics.sharpe_ratio,
                    "roi_pct": stress_metrics.roi_pct,
                    "mdd_pct": stress_metrics.max_drawdown_pct,
                    "trades": stress_metrics.total_trades,
                }
            )

        # Use baseline equity snapshots for bootstrap
        equity = stage_result.equity_snapshots
        if len(equity) >= 2:
            returns = [(equity[i] - equity[i - 1]) / max(equity[i - 1], 1e-9) for i in range(1, len(equity))]
        else:
            # Fallback: no equity data - single synthetic return
            returns = [metrics.roi_pct / 100.0] if metrics.roi_pct != 0 else []

        stress_median = statistics.median(stress_sharpes)

        # --- 3. Block Bootstrap ---
        bs_cfg = s2_cfg.get("block_bootstrap", {})
        bootstrap = BlockBootstrap(
            n_resamples=bs_cfg.get("n_resamples", 100),
            block_size=min(bs_cfg.get("block_size_bars", 30), max(len(returns), 1)),
            seed=42 + fold_id,
        )
        bs_result = bootstrap.resample(returns) if len(returns) >= 2 else None

        return FoldResult(
            fold_id=fold_id,
            test_sharpe=metrics.sharpe_ratio,
            test_mdd_pct=metrics.max_drawdown_pct,
            test_trades=metrics.total_trades,
            test_reject_rate=metrics.reject_rate,
            hard_violation=hard_violation,
            bootstrap_pnl_positive_pct=bs_result.pnl_positive_pct if bs_result else 0.0,
            bootstrap_sharpe_p5=bs_result.sharpe_p5 if bs_result else 0.0,
            stress_sharpe_median=stress_median,
            stress_runs=stress_runs,
        )

    # ----- Holdout Gate (date-isolated) -----

    def run_holdout(
        self,
        candidate_overlay: Dict[str, Any],
    ) -> HoldoutResult:
        """
        Run cold holdout evaluation — final go/no-go gate.
        Uses self.holdout_range which is NEVER seen during S0/S1/S2.
        """
        if not self.holdout_range:
            return HoldoutResult(passed=False, reason="No holdout_range configured")

        holdout_cfg = self.optimizer_cfg.get("holdout", {})
        acceptance = holdout_cfg.get("acceptance", {})

        gate = ColdHoldoutGate(
            min_sharpe=acceptance.get("min_sharpe", 1.0),
            max_mdd_p90_pct=acceptance.get("max_mdd_p90_pct", 25.0),
        )

        LOG.info(f"Holdout range: {self.holdout_range.start} → {self.holdout_range.end}")

        # Single run on holdout period
        metrics, stage_result = self.adapter.run_stage1(
            candidate_overlay,
            start_date=self.holdout_range.start,
            end_date=self.holdout_range.end,
        )

        if not stage_result.success:
            return HoldoutResult(passed=False, reason=f"Holdout backtest failed: {stage_result.error}")

        # Optional: run bootstrap on holdout to get MDD p90
        mdd_p90 = metrics.max_drawdown_pct  # Default: actual MDD
        equity = stage_result.equity_snapshots
        if len(equity) >= 2:
            returns = [(equity[i] - equity[i-1]) / max(equity[i-1], 1e-9) for i in range(1, len(equity))]
            bs = BlockBootstrap(n_resamples=50, block_size=min(20, len(returns)), seed=99)
            bs_result = bs.resample(returns)
            # Approximate MDD p90 from bootstrap Sharpe distribution
            # (conservative: use actual MDD as p90 if bootstrap unavailable)
            if bs_result and bs_result.sharpe_samples:
                # Use bootstrap PnL to estimate MDD distribution
                sorted_pnls = sorted(bs_result.pnl_samples)
                p10_idx = int(len(sorted_pnls) * 0.10)
                worst_pnl = sorted_pnls[p10_idx] if sorted_pnls else 0
                # Simple conversion: worst PnL → approximate MDD
                if worst_pnl < 0:
                    mdd_p90 = abs(worst_pnl / max(equity[0], 1)) * 100

        return gate.evaluate(
            sharpe=metrics.sharpe_ratio,
            mdd_pct=metrics.max_drawdown_pct,
            mdd_p90_pct=mdd_p90,
            roi_pct=metrics.roi_pct,
        )

    # ----- Full Pipeline -----

    def run_full_pipeline(
        self,
        full_start: Optional[str] = None,
        full_end: Optional[str] = None,
    ) -> PipelineResult:
        """
        Execute the full hierarchical optimization pipeline:
            Stage 0 → Stage 1 → Stage 2 → Holdout

        If train_range/holdout_range were not set in __init__, they are
        computed from full_start/full_end using holdout.reserve_months.

        Args:
            full_start: Overall start date "YYYY-MM-DD" (optional if set in __init__)
            full_end: Overall end date "YYYY-MM-DD" (optional if set in __init__)
        """
        # Auto-split train/holdout if not explicitly set
        if self.train_range is None and full_start and full_end:
            holdout_months = self.optimizer_cfg.get("holdout", {}).get("reserve_months", 3)
            self.train_range, self.holdout_range = compute_train_holdout_split(
                full_start, full_end, holdout_months,
            )
            LOG.info(f"Auto-split: train={self.train_range.start}..{self.train_range.end}, "
                     f"holdout={self.holdout_range.start}..{self.holdout_range.end}")

        result = PipelineResult()

        # Stage 0: Regime Calibration
        LOG.info("=" * 60)
        LOG.info("🔬 STAGE 0: REGIME CALIBRATION")
        LOG.info("=" * 60)
        s0 = self.run_stage0()
        result.stage0 = s0

        s0_acceptance = self.optimizer_cfg.get("stage0", {}).get("acceptance", {})
        if s0.best_stability_score < s0_acceptance.get("min_stability_score", 0.3):
            LOG.error(f"Stage 0 FAILED: stability_score={s0.best_stability_score:.4f} below threshold")
            return result

        # Build frozen regime config
        regime_config = _build_overlay(s0.best_params)
        regime_config["basis_tf_sec"] = s0.best_basis_tf_sec

        # Stage 1: Alpha Search
        LOG.info("=" * 60)
        LOG.info("📈 STAGE 1: ALPHA SEARCH")
        LOG.info("=" * 60)
        s1 = self.run_stage1(regime_config)
        result.stage1 = s1

        s1_acceptance = self.optimizer_cfg.get("stage1", {}).get("acceptance", {})
        if s1.best_sharpe < s1_acceptance.get("min_sharpe", 0.5):
            LOG.error(f"Stage 1 FAILED: best_sharpe={s1.best_sharpe:.4f} below threshold")
            return result

        strategy_config = _build_overlay(s1.best_params)

        # Build merged candidate overlay
        candidate_overlay: Dict[str, Any] = {}
        _merge_config(candidate_overlay, regime_config)
        _merge_config(candidate_overlay, strategy_config)

        # Stage 2: Robustness
        LOG.info("=" * 60)
        LOG.info("🛡️ STAGE 2: ROBUSTNESS VALIDATION")
        LOG.info("=" * 60)
        s2 = self.run_stage2(candidate_overlay, stage1_sharpe=s1.best_sharpe)
        result.stage2 = s2

        if not s2.passed:
            LOG.error(f"Stage 2 FAILED: {' | '.join(s2.reasons)}")
            return result

        # Cold Holdout
        LOG.info("=" * 60)
        LOG.info("🧊 COLD HOLDOUT GATE")
        LOG.info("=" * 60)
        holdout = self.run_holdout(candidate_overlay)
        result.holdout = holdout

        # Final config
        result.final_config = candidate_overlay
        result.production_ready = holdout.passed

        if holdout.passed:
            LOG.info("✅ PIPELINE COMPLETE: Production ready!")
        else:
            LOG.warning(f"❌ PIPELINE FAILED at holdout: {holdout.reason}")

        return result
