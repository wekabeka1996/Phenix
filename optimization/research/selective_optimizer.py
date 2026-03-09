"""
optimization/research/selective_optimizer.py — Selective weight tuning optimizer.

Lightweight Optuna-based optimizer for targeted weight tuning in the Aurora system.
Complements (does NOT replace) the production AuroraOptimizer 3-stage pipeline.

Key design decisions:
    - No universe lock: BacktestAdapter is created without locked_symbols.
      The adapter already handles this case gracefully (backtest_interface.py:58).
    - symbols_to_track is injected into the overlay so the backtest covers
      all requested symbols in a single run.
    - search_space_names select which weight groups to tune; the rest of the
      config stays unchanged (taken from config_dir YAML files).
    - Objective modes: calmar, sharpe, roi, alpha (sharpe - penalties).

Usage:
    optimizer = SelectiveOptimizer(
        config_dir=Path("config/aurora"),
        symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "1000PEPEUSDT"],
        search_space_names=["btc_weights"],
        date_range=("2024-01-01", "2025-10-01"),
        study_config=ResearchStudyConfig(name="btc_weights_v1", n_trials=100),
        gates=ResearchGates(),
        objective=ResearchObjectiveMode.CALMAR,
    )
    study = optimizer.run()
    print(optimizer.best_overlay(study))
"""

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
except ImportError:
    optuna = None  # type: ignore

from optimization.objectives import AlphaMetrics, PenaltyConfig, compute_alpha_score
from optimization.backtest_interface import BacktestAdapter
from optimization.research.weight_registry import resolve_paths
from concurrent.futures import ProcessPoolExecutor
from optimization._worker import _run_trial_in_process
from apps.reference.config_loader import ConfigLoader

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Re-export helpers from optimizer.py to avoid circular imports
# ---------------------------------------------------------------------------

def _flatten_search_space(node: Dict[str, Any], path: list = None) -> Dict[str, Dict]:
    """Flatten nested search_space dict into {dotted_key: param_spec}."""
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


def _build_overlay(flat_params: Dict[str, Any]) -> Dict[str, Any]:
    """Convert flat dotted params to nested dict for config overlay."""
    overlay: Dict[str, Any] = {}
    for dotted_key, value in flat_params.items():
        parts = dotted_key.split(".")
        d = overlay
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        d[parts[-1]] = value
    return overlay


def _sample_param(trial: "optuna.Trial", name: str, spec: Dict) -> Any:
    """Sample single parameter from Optuna trial based on spec."""
    ptype = spec["type"]
    if ptype == "float":
        kwargs: Dict[str, Any] = {"name": name, "low": spec["low"], "high": spec["high"]}
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
        raise ValueError(f"Unknown param type: '{ptype}' for param '{name}'")


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

class ResearchObjectiveMode(str, Enum):
    """Objective metric for Optuna to maximize."""
    CALMAR = "calmar"   # ROI% / MaxDD%  — default, good for trend strategies
    SHARPE = "sharpe"   # Risk-adjusted return (annualized Sharpe)
    ROI    = "roi"      # Raw ROI% — useful for short backtests
    ALPHA  = "alpha"    # Sharpe - soft penalties (churn, reject_rate, starvation)


@dataclass
class ResearchStudyConfig:
    """Optuna study configuration."""
    name: str = "research_study"
    n_trials: int = 100
    n_jobs: int = 1
    storage: str = "sqlite:///runs/optuna/research.db"
    seed: int = 42


@dataclass
class ResearchGates:
    """Anti-degenerate gates — if violated, trial returns -1e9."""
    min_trades: int = 5           # minimum filled trades
    max_dd_pct: float = 40.0     # maximum allowed drawdown %
    min_filled_orders: int = 3   # minimum filled orders (from report)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class SelectiveOptimizer:
    """
    Selective weight tuner — Optuna wrapper for targeted Aurora weight optimization.

    Does NOT use universe lock. Use search_space_names to select which weight
    groups to tune; everything else remains fixed from config_dir YAML files.
    """

    def __init__(
        self,
        *,
        config_dir: Path,
        symbols: List[str],
        search_space_names: List[str],
        date_range: Tuple[str, str],
        study_config: Optional[ResearchStudyConfig] = None,
        gates: Optional[ResearchGates] = None,
        objective: ResearchObjectiveMode = ResearchObjectiveMode.CALMAR,
        penalty_config: Optional[PenaltyConfig] = None,
    ):
        if optuna is None:
            raise ImportError(
                "optuna is required. Install: pip install optuna"
            )
        if not symbols:
            raise ValueError("symbols must not be empty")
        if not search_space_names:
            raise ValueError("search_space_names must not be empty")

        self.config_dir = Path(config_dir)
        self.symbols = list(symbols)
        self.search_space_names = list(search_space_names)
        self.start_date, self.end_date = date_range
        self.study_config = study_config or ResearchStudyConfig()
        self.gates = gates or ResearchGates()
        self.objective_mode = objective
        self.penalty_config = penalty_config or PenaltyConfig()

        # Flat search space loaded from YAML(s)
        self._flat_space: Dict[str, Dict] = {}

        # BacktestAdapter WITHOUT locked_symbols — bypasses universe lock
        self.adapter = BacktestAdapter(
            config_dir=self.config_dir,
            data_dir=None,
            locked_symbols=None,      # no lock = full universe
            locked_strategy_id=None,
        )

        LOG.info(
            f"SelectiveOptimizer init: symbols={self.symbols}, "
            f"spaces={self.search_space_names}, "
            f"date={self.start_date}..{self.end_date}, "
            f"objective={self.objective_mode.value}, "
            f"trials={self.study_config.n_trials}"
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def run(self) -> "optuna.Study":
        """Run the Optuna study and return the resulting Study object."""
        self._flat_space = self._load_search_spaces()
        LOG.info(f"Search space has {len(self._flat_space)} parameters: {list(self._flat_space.keys())}")

        loader = ConfigLoader(config_dir=self.config_dir)
        trading_cfg = loader.load_trading_config()
        turbo_mode = getattr(trading_cfg.backtest.engine, 'turbo_mode', 'off')
        
        n_workers = getattr(trading_cfg.backtest.parallelism, 'n_workers', self.study_config.n_jobs)
        worker_seed_base = getattr(trading_cfg.backtest.parallelism, 'worker_seed_base', 42)
        
        self._worker_seed_base = worker_seed_base
        
        if turbo_mode != "off" and n_workers > 1:
            self._executor = ProcessPoolExecutor(max_workers=n_workers)
            LOG.info(f"SelectiveOptimizer using ProcessPoolExecutor with {n_workers} workers (turbo_mode={turbo_mode})")
        else:
            self._executor = None

        # Ensure storage directory exists for SQLite
        storage = self.study_config.storage
        if storage.startswith("sqlite:///"):
            db_path = Path(storage.replace("sqlite:///", ""))
            db_path.parent.mkdir(parents=True, exist_ok=True)

        sampler = optuna.samplers.TPESampler(seed=self.study_config.seed)
        study = optuna.create_study(
            study_name=self.study_config.name,
            storage=self.study_config.storage,
            sampler=sampler,
            direction="maximize",
            load_if_exists=True,
        )

        study.optimize(
            self.objective_fn,
            n_trials=self.study_config.n_trials,
            n_jobs=self.study_config.n_jobs,
            show_progress_bar=True,
        )

        LOG.info(
            f"Study '{self.study_config.name}' complete. "
            f"Best value: {study.best_value:.4f} | "
            f"Best params: {study.best_params}"
        )
        return study

    def objective_fn(self, trial: "optuna.Trial") -> float:
        """Optuna objective function for a single trial."""
        # 1. Sample params → build overlay
        sampled: Dict[str, Any] = {}
        for param_name, spec in self._flat_space.items():
            sampled[param_name] = _sample_param(trial, param_name, spec)

        overlay = _build_overlay(sampled)

        # 2. Inject symbols_to_track so backtest covers the requested universe.
        # SSOT path: trading.symbols_to_track is read by apply_backtest_symbols_filter
        # (apps.reference.backtest.symbol_filter) which filters strategies_registry.assignments.
        # Do NOT use aurora.decision.symbols_to_track — that key doesn't exist in the schema.
        overlay.setdefault("trading", {})["symbols_to_track"] = self.symbols

        # 3. WARM-UP SAFETY: BacktestEngine already handles QuadBrain pillar warm-up automatically:
        #    - engine.load_data() (engine.py:214) extends start_date by 210 days back in parquet
        #    - engine._warmup_pillars() emits those H4/D1 bars as EVT:BAR_CLOSED before simulation
        #    - engine._warmup_htf_api() fetches from Binance API as backup (with local cache)
        # No extra code needed here — BacktestAdapter → run_backtest_simulation() activates all of it.
        #
        # Set backtest_mode=relaxed so warmup enforcement_mode becomes warn_only.
        # This prevents trial crashes when parquet data doesn't cover the full 210-day lookback
        # (e.g., if start_date is very early and parquet history is limited).
        # Without this, domains.yaml enforcement_mode=fail_fast would raise ValueError.
        overlay.setdefault("trading", {}).setdefault("backtest", {})["backtest_mode"] = "relaxed"

        LOG.debug(f"Trial {trial.number}: {trial.params}")

        # 4. Run backtest
        if getattr(self, "_executor", None) is not None:
            worker_seed = self._worker_seed_base ^ trial.number
            future = self._executor.submit(
                _run_trial_in_process,
                config_dir=str(self.config_dir),
                data_dir=None,
                locked_symbols=None,
                locked_strategy_id=None,
                overlay=overlay,
                start_date=self.start_date,
                end_date=self.end_date,
                stage=1,
                worker_seed=worker_seed
            )
            res = future.result()
            
            if not res.get("success"):
                LOG.warning(f"Trial {trial.number}: backtest failed — {res.get('error')}")
                return -1e9
                
            metrics = res.get("metrics")
            
            class DummyStageResult:
                def __init__(self, raw_report):
                    self.raw_report = raw_report
                    self.success = True
                    self.error = None
            stage_result = DummyStageResult(res.get("report_subset", {}))
            
        else:
            metrics, stage_result = self.adapter.run_stage1(
                overlay,
                start_date=self.start_date,
                end_date=self.end_date,
            )

            if not stage_result.success:
                LOG.warning(f"Trial {trial.number}: backtest failed — {stage_result.error}")
                return -1e9  # hard reject: failed trial

        # 4. Apply hard gates
        gate_result = self._check_gates(trial.number, metrics, stage_result)
        if gate_result is not None:
            return gate_result

        # 5. Compute and return score
        score = self._compute_score(metrics)

        trial.set_user_attr("sharpe", metrics.sharpe_ratio)
        trial.set_user_attr("calmar", metrics.calmar_ratio)
        trial.set_user_attr("mdd_pct", metrics.max_drawdown_pct)
        trial.set_user_attr("total_trades", metrics.total_trades)
        trial.set_user_attr("roi_pct", metrics.roi_pct)
        trial.set_user_attr("reject_rate", metrics.reject_rate)

        LOG.info(
            f"Trial {trial.number}: score={score:.4f} | "
            f"sharpe={metrics.sharpe_ratio:.3f}, calmar={metrics.calmar_ratio:.3f}, "
            f"mdd={metrics.max_drawdown_pct:.1f}%, trades={metrics.total_trades}"
        )
        return score

    def best_overlay(self, study: "optuna.Study") -> Dict[str, Any]:
        """Return the config overlay dict for the best trial."""
        if not study.best_params:
            return {}
        return _build_overlay(study.best_params)

    def export_best_config(
        self,
        study: "optuna.Study",
        output_path: Path,
    ) -> None:
        """
        Export the best trial parameters as a YAML overlay file.

        The output can be used as an optuna_overlay in ConfigLoader or
        applied manually to aurora.yaml.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        overlay = self.best_overlay(study)
        meta = {
            "study_name": self.study_config.name,
            "best_value": float(study.best_value),
            "best_trial": study.best_trial.number,
            "objective": self.objective_mode.value,
            "symbols": self.symbols,
            "search_spaces": self.search_space_names,
            "date_range": [self.start_date, self.end_date],
            "n_trials_completed": len(study.trials),
        }

        output = {"meta": meta, "overlay": overlay}
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(output, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        LOG.info(f"Best config exported: {output_path}")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _load_search_spaces(self) -> Dict[str, Dict]:
        """Load and merge all requested search space YAML files."""
        yaml_paths = resolve_paths(self.search_space_names)
        merged_flat: Dict[str, Dict] = {}

        for path in yaml_paths:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            space_node = raw.get("search_space", raw)
            # Remove top-level 'meta' key if accidentally included
            space_node.pop("meta", None)
            flat = _flatten_search_space(space_node)
            conflicts = set(merged_flat.keys()) & set(flat.keys())
            if conflicts:
                LOG.warning(
                    f"Search space key conflict from '{path.name}': "
                    f"{conflicts} — later file wins"
                )
            merged_flat.update(flat)

        if not merged_flat:
            raise ValueError(
                f"No parameters found in search spaces: {self.search_space_names}. "
                f"Check YAML files have proper 'type'/'low'/'high' leaf nodes."
            )
        return merged_flat

    def _check_gates(
        self,
        trial_number: int,
        metrics: AlphaMetrics,
        stage_result: Any,
    ) -> Optional[float]:
        """Return -1e9 if any gate is violated, else None."""
        if metrics.total_trades < self.gates.min_trades:
            LOG.warning(
                f"Trial {trial_number}: GATE FAIL — trades={metrics.total_trades} < {self.gates.min_trades}"
            )
            return -1e9

        if metrics.max_drawdown_pct > self.gates.max_dd_pct:
            LOG.warning(
                f"Trial {trial_number}: GATE FAIL — dd={metrics.max_drawdown_pct:.1f}% "
                f"> {self.gates.max_dd_pct}%"
            )
            return -1e9

        # Filled orders check from raw report
        if stage_result.raw_report and isinstance(stage_result.raw_report, dict):
            orders_summary = stage_result.raw_report.get("orders_summary", {})
            filled = orders_summary.get("filled_orders", metrics.total_trades)
            if filled < self.gates.min_filled_orders:
                LOG.warning(
                    f"Trial {trial_number}: GATE FAIL — filled_orders={filled} "
                    f"< {self.gates.min_filled_orders}"
                )
                return -1e9

        return None

    def _compute_score(self, metrics: AlphaMetrics) -> float:
        """Compute objective score from metrics based on objective_mode."""
        mode = self.objective_mode

        if mode == ResearchObjectiveMode.CALMAR:
            dd = metrics.max_drawdown_pct
            if dd < 1e-9:
                return metrics.roi_pct if metrics.roi_pct > 0 else -1e9
            return metrics.roi_pct / dd

        elif mode == ResearchObjectiveMode.SHARPE:
            return metrics.sharpe_ratio

        elif mode == ResearchObjectiveMode.ROI:
            return metrics.roi_pct

        elif mode == ResearchObjectiveMode.ALPHA:
            score = compute_alpha_score(metrics, self.penalty_config)
            if math.isinf(score) or math.isnan(score):
                return -1e9
            return score

        else:
            raise ValueError(f"Unknown objective mode: {mode}")
