"""
optimization/_worker.py — ProcessPool worker for backtest trials.

Provides a top-level picklable function `_run_trial_in_process` that can be dispatched
to a ProcessPoolExecutor to bypass the GIL during CPU-bound backtesting.
"""

import logging
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from optimization.backtest_interface import BacktestAdapter
from vfoundation.logging.wal import set_wal_dir

LOG = logging.getLogger(__name__)

def _run_trial_in_process(
    config_dir: str,
    data_dir: Optional[str],
    locked_symbols: Optional[List[str]],
    locked_strategy_id: Optional[str],
    overlay: Dict[str, Any],
    start_date: Optional[str],
    end_date: Optional[str],
    stage: int,
    worker_seed: int,
) -> Dict[str, Any]:
    """
    Picklable worker function for running a single backtest trial in a separate process.
    
    Args:
        config_dir: Path to config directory (string for pickling)
        data_dir: Path to data directory (string for pickling)
        locked_symbols: List of symbols to lock for the universe
        locked_strategy_id: Strategy ID to lock
        overlay: Config overrides for this trial
        start_date: Optional start date override
        end_date: Optional end date override
        stage: 0 (Regime) or 1 (Alpha)
        worker_seed: Seed for deterministic execution
        
    Returns:
        Dict containing success flag, error message, metrics dict, and raw report subset.
    """
    try:
        # 1. Deterministic execution
        random.seed(worker_seed)
        np.random.seed(worker_seed)
        
        # 2. Isolate WAL per process to avoid file locking collisions
        pid = os.getpid()
        set_wal_dir(f"logs/wal_worker_{pid}")
        
        # 3. Initialize Adapter
        adapter = BacktestAdapter(
            config_dir=Path(config_dir),
            data_dir=Path(data_dir) if data_dir else None,
            locked_symbols=locked_symbols,
            locked_strategy_id=locked_strategy_id
        )
        
        # 4. Execute backtest
        if stage == 0:
            metrics, result = adapter.run_stage0(overlay, start_date=start_date, end_date=end_date)
        elif stage == 1:
            metrics, result = adapter.run_stage1(overlay, start_date=start_date, end_date=end_date)
        else:
            raise ValueError(f"Unknown stage {stage}")
            
        # 5. Extract picklable results
        # We cannot pass raw BacktestEngine objects across process boundaries
        report_subset = {}
        if isinstance(result.raw_report, dict):
            report_subset["orders_summary"] = result.raw_report.get("orders_summary", {})
            
        return {
            "success": result.success,
            "error": result.error,
            "metrics": metrics,
            "trade_intents": result.trade_intents,
            "report_subset": report_subset
        }
        
    except Exception as e:
        LOG.exception(f"Worker process failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "metrics": None,
            "trade_intents": [],
            "report_subset": {}
        }
