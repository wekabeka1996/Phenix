"""
Optuna Runner — Hyperparameter Optimization Wrapper
====================================================

Wraps existing backtest infrastructure to run Optuna optimization trials.
Minimal core changes: just calls run_backtest_simulation with overlay.
"""

import logging
import optuna
import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

LOG = logging.getLogger(__name__)


@dataclass
class OptunaGates:
    """Anti-degenerate strategy gates."""
    min_filled_orders: int = 30
    max_dd_pct: float = 20.0
    min_intents: int = 10


@dataclass
class OptunaStudyConfig:
    """Study configuration."""
    name: str = "aurora_optimization"
    n_trials: int = 50
    n_jobs: int = 1
    storage: str = "sqlite:///runs/optuna/aurora.db"
    seed: int = 42


class OptunaRunner:
    """Optuna wrapper around existing backtest infrastructure."""

    def __init__(
        self,
        optuna_config_path: Path,
        config_dir: Path,
    ):
        self.optuna_config_path = optuna_config_path
        self.config_dir = config_dir
        self.optuna_cfg = self._load_optuna_config()
        
        LOG.info(f"OptunaRunner initialized: config={optuna_config_path}, trials={self.study_cfg.n_trials}")

    def _load_optuna_config(self) -> Dict[str, Any]:
        """Load optuna_config.yaml."""
        if not self.optuna_config_path.exists():
            raise FileNotFoundError(f"Optuna config not found: {self.optuna_config_path}")
        
        with open(self.optuna_config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        
        cfg = raw.get("optuna", raw)
        
        # Parse study config
        study_raw = cfg.get("study", {})
        self.study_cfg = OptunaStudyConfig(
            name=study_raw.get("name", "aurora_optimization"),
            n_trials=study_raw.get("n_trials", 50),
            n_jobs=study_raw.get("n_jobs", 1),
            storage=study_raw.get("storage", "sqlite:///runs/optuna/aurora.db"),
            seed=study_raw.get("seed", 42),
        )
        
        # Parse gates
        obj_raw = cfg.get("objective", {})
        gates_raw = obj_raw.get("gates", {})
        self.gates = OptunaGates(
            min_filled_orders=gates_raw.get("min_filled_orders", 30),
            max_dd_pct=gates_raw.get("max_dd_pct", 20.0),
            min_intents=gates_raw.get("min_intents", 10),
        )
        
        # Search space
        self.search_space = cfg.get("search_space", {})
        
        return cfg

    def run(self) -> optuna.Study:
        """Create and run Optuna study."""
        # Ensure storage directory exists
        storage_path = self.study_cfg.storage
        if storage_path.startswith("sqlite:///"):
            db_path = Path(storage_path.replace("sqlite:///", ""))
            db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create sampler with seed for reproducibility
        sampler = optuna.samplers.TPESampler(seed=self.study_cfg.seed)
        
        study = optuna.create_study(
            study_name=self.study_cfg.name,
            storage=self.study_cfg.storage,
            sampler=sampler,
            direction="maximize",
            load_if_exists=True,
        )
        
        LOG.info(f"Starting Optuna optimization: {self.study_cfg.n_trials} trials")
        study.optimize(
            self.objective,
            n_trials=self.study_cfg.n_trials,
            n_jobs=self.study_cfg.n_jobs,
            show_progress_bar=True,
        )
        
        return study

    def objective(self, trial: optuna.Trial) -> float:
        """Objective function for Optuna trial."""
        # 1. Sample params from search space and build overlay
        overlay = self._sample_params_to_overlay(trial)
        
        LOG.info(f"Trial {trial.number}: params={trial.params}")
        
        # 2. Run backtest with overlay
        result, report = self._run_backtest(overlay)
        
        # 3. Apply gates (return -inf if violated)
        orders_summary = report.get("orders_summary", {})
        strategies = report.get("strategies", {})
        
        filled_orders = orders_summary.get("filled_orders", 0)
        intents_total = strategies.get("intents_total", 0)
        
        if filled_orders < self.gates.min_filled_orders:
            LOG.warning(f"Trial {trial.number}: GATE FAIL - filled_orders={filled_orders} < {self.gates.min_filled_orders}")
            return -1e9
        
        if intents_total < self.gates.min_intents:
            LOG.warning(f"Trial {trial.number}: GATE FAIL - intents={intents_total} < {self.gates.min_intents}")
            return -1e9
        
        if result.max_drawdown * 100 > self.gates.max_dd_pct:
            LOG.warning(f"Trial {trial.number}: GATE FAIL - dd={result.max_drawdown*100:.2f}% > {self.gates.max_dd_pct}%")
            return -1e9
        
        # 4. Compute Calmar ratio (ROI% / MaxDD%)
        roi_pct = result.roi_pct
        dd_pct = result.max_drawdown * 100
        
        if dd_pct < 1e-9:
            calmar = roi_pct if roi_pct > 0 else -1e9
        else:
            calmar = roi_pct / dd_pct
        
        LOG.info(f"Trial {trial.number}: ROI={roi_pct:.2f}%, DD={dd_pct:.2f}%, Calmar={calmar:.4f}")
        
        return calmar

    def _sample_params_to_overlay(self, trial: optuna.Trial) -> Dict[str, Any]:
        """Sample params from search_space and build overlay dict."""
        overlay: Dict[str, Any] = {}
        
        def traverse(node: Dict[str, Any], path: list, target: Dict[str, Any]) -> None:
            for key, value in node.items():
                current_path = path + [key]
                
                if isinstance(value, dict):
                    if "type" in value and "low" in value:
                        # This is a param spec
                        param_name = ".".join(current_path)
                        sampled = self._sample_param(trial, param_name, value)
                        
                        # Build nested dict
                        d = target
                        for p in current_path[:-1]:
                            d = d.setdefault(p, {})
                        d[current_path[-1]] = sampled
                    else:
                        # Recurse into nested dict
                        traverse(value, current_path, target)
        
        traverse(self.search_space, [], overlay)
        return overlay

    def _sample_param(self, trial: optuna.Trial, name: str, spec: Dict[str, Any]) -> Any:
        """Sample a single parameter based on its spec."""
        ptype = spec.get("type", "float")
        low = spec.get("low")
        high = spec.get("high")
        step = spec.get("step")
        choices = spec.get("choices")
        
        if ptype == "int":
            return trial.suggest_int(name, low, high, step=step or 1)
        elif ptype == "float":
            if step:
                return trial.suggest_float(name, low, high, step=step)
            else:
                return trial.suggest_float(name, low, high)
        elif ptype == "categorical":
            return trial.suggest_categorical(name, choices)
        else:
            raise ValueError(f"Unknown param type: {ptype}")

    def _run_backtest(self, overlay: Dict[str, Any]) -> tuple:
        """Run backtest with given overlay."""
        from apps.reference.config_loader import ConfigLoader, AuroraConfig
        from apps.reference.main import run_backtest_simulation
        
        # Load config with overlay
        loader = ConfigLoader(
            config_dir=self.config_dir,
            optuna_overlay=overlay,
        )
        config = loader.load_config()
        
        # Ensure backtest mode
        config.trading_mode = "backtest"
        
        # Run backtest and get result
        result, report = run_backtest_simulation(config, return_result=True)
        
        return result, report
