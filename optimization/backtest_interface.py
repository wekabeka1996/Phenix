"""
optimization/backtest_interface.py — Adapter between optimizer and backtest pipeline.

Bridges the optimization module with `run_backtest_simulation` in apps/reference/main.py.
Provides stage-specific run modes that return the metrics each stage needs.

Supports date-range slicing for Walk-Forward folds and holdout isolation.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from optimization.objectives import (
    RegimeStabilityMetrics,
    AlphaMetrics,
)

LOG = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Generic container for any stage's backtest output."""
    success: bool = False
    error: Optional[str] = None
    raw_result: Any = None          # BacktestResult from engine
    raw_report: Any = None          # report dict from reporting.py
    regime_log: List[Any] = field(default_factory=list)
    trade_intents: List[Dict] = field(default_factory=list)
    intent_log: List[Dict] = field(default_factory=list)
    equity_snapshots: List[float] = field(default_factory=list)


class BacktestAdapter:
    """
    Adapter that runs Aurora backtests with parameter overrides
    and extracts stage-specific metrics.

    Supports date_range injection for Walk-Forward folds and holdout.
    """

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        data_dir: Optional[Path] = None,
        locked_symbols: Optional[List[str]] = None,
        locked_strategy_id: Optional[str] = None,
    ):
        self.config_dir = config_dir or Path("config/aurora")
        self.data_dir = data_dir
        self.locked_symbols = [str(s) for s in (locked_symbols or [])]
        self.locked_strategy_id = str(locked_strategy_id) if locked_strategy_id else None

    def _enforce_universe_lock(self, config: Any) -> None:
        """Runtime assert and lock for optimization universe."""
        if not self.locked_symbols or not self.locked_strategy_id:
            return
        # Ensure symbols exist in instruments
        instruments = getattr(config, "instruments", None)
        if not isinstance(instruments, dict):
            raise ValueError("Universe lock: config.instruments missing/invalid")
        for symbol in self.locked_symbols:
            if symbol not in instruments:
                raise ValueError(f"Universe lock: symbol {symbol} missing in instruments")

        # Ensure strategy profile exists
        strategies = getattr(config, "strategies", None)
        if not hasattr(strategies, self.locked_strategy_id):
            raise ValueError(
                f"Universe lock: strategy_id={self.locked_strategy_id} profile is not loaded in config.strategies"
            )

        # Force runtime tracked symbols (prevents multi-symbol leakage in backtests)
        trading = getattr(config, "trading", None)
        if trading is not None and hasattr(trading, "symbols_to_track"):
            trading.symbols_to_track = list(self.locked_symbols)

        # Force assignments to the locked strategy (single-symbol, single-strategy universe)
        sr = getattr(config, "strategies_registry", None)
        if sr is not None and hasattr(sr, "assignments"):
            sr.assignments = {s: [self.locked_strategy_id] for s in self.locked_symbols}

    def _run_backtest_with_overlay(
        self,
        overlay: Dict[str, Any],
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> StageResult:
        """
        Run a single backtest with the given config overlay.

        Args:
            overlay: Config parameter overlay
            start_date: Optional date override (format: "YYYY-MM-DD")
            end_date: Optional date override (format: "YYYY-MM-DD")

        Returns StageResult with raw backtest output.
        """
        try:
            from apps.reference.config_loader import ConfigLoader
            from apps.reference.main import run_backtest_simulation

            # Optimization default: strict backtest mode (no implicit relaxations)
            bt_overlay = overlay.setdefault("trading", {}).setdefault("backtest", {})
            bt_overlay.setdefault("backtest_mode", "strict")

            # Inject date range into overlay if provided
            if start_date or end_date:
                if start_date:
                    bt_overlay["start_date"] = start_date
                if end_date:
                    bt_overlay["end_date"] = end_date

            loader = ConfigLoader(
                config_dir=self.config_dir,
                optuna_overlay=overlay,
            )
            config = loader.load_config()
            self._enforce_universe_lock(config)

            result_tuple = run_backtest_simulation(config, return_result=True)

            if result_tuple is None:
                return StageResult(success=False, error="run_backtest_simulation returned None")

            bt_result, report_data = result_tuple

            # Extract regime log and intent log from report
            regime_log = []
            trade_intents_list = []
            intent_log_list = []
            equity_snapshots = []
            if isinstance(report_data, dict):
                # SSOT: report["regime_log"]
                regime_log = report_data.get("regime_log", [])
                intent_log_list = report_data.get("intents", [])
                if not intent_log_list:
                    intent_log_list = report_data.get("trade_intents", [])
                trade_intents_list = [
                    i for i in intent_log_list
                    if isinstance(i, dict) and str(i.get("intent_status", "PROPOSED")).upper() == "PROPOSED"
                ]

            # Extract equity snapshots from engine if available
            engine = report_data.get("_engine") if isinstance(report_data, dict) else None
            if engine and hasattr(engine, "_equity_snapshots"):
                equity_snapshots = list(engine._equity_snapshots)

            return StageResult(
                success=True,
                raw_result=bt_result,
                raw_report=report_data,
                regime_log=regime_log,
                trade_intents=trade_intents_list,
                intent_log=intent_log_list,
                equity_snapshots=equity_snapshots,
            )
        except Exception as e:
            LOG.exception(f"Backtest failed: {e}")
            return StageResult(success=False, error=str(e))

    def run_stage0(
        self,
        overrides: Dict[str, Any],
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Tuple[RegimeStabilityMetrics, StageResult]:
        """Run backtest and extract regime stability metrics for Stage 0."""
        stage_result = self._run_backtest_with_overlay(
            overrides, start_date=start_date, end_date=end_date,
        )

        if not stage_result.success:
            return RegimeStabilityMetrics(), stage_result

        metrics = self._extract_regime_metrics(stage_result)
        return metrics, stage_result

    def run_stage1(
        self,
        overrides: Dict[str, Any],
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Tuple[AlphaMetrics, StageResult]:
        """Run full backtest and extract alpha metrics for Stage 1."""
        stage_result = self._run_backtest_with_overlay(
            overrides, start_date=start_date, end_date=end_date,
        )

        if not stage_result.success:
            return AlphaMetrics(), stage_result

        metrics = self._extract_alpha_metrics(stage_result)
        return metrics, stage_result

    def _extract_regime_metrics(self, stage_result: StageResult) -> RegimeStabilityMetrics:
        """Extract regime stability metrics from backtest regime log."""
        regime_log = stage_result.regime_log
        if not regime_log:
            LOG.warning("No regime events in backtest output — returning empty metrics")
            return RegimeStabilityMetrics()

        def _norm_regime(item: Any) -> str:
            if isinstance(item, str):
                return item.upper().strip()
            if isinstance(item, dict):
                raw = item.get("regime", item.get("type", item.get("value", "UNKNOWN")))
                return str(raw).upper().strip()
            return str(item).upper().strip()

        def _extract_ts_ms(item: Any) -> Optional[int]:
            if not isinstance(item, dict):
                return None
            ts = item.get("ts_ms", item.get("ts", item.get("timestamp_ms")))
            try:
                return int(ts)
            except Exception:
                return None

        uncertain_values = {"UNCERTAIN", "UNKNOWN"}
        total_bars = len(regime_log)
        definite_bars = 0
        uncertain_bars = 0
        regime_flips = 0
        prev_regime = None

        for event in regime_log:
            regime_type = _norm_regime(event)
            if regime_type in uncertain_values:
                uncertain_bars += 1
            else:
                definite_bars += 1

            if prev_regime is not None and regime_type != prev_regime:
                regime_flips += 1
            prev_regime = regime_type

        # Duration from first to last event timestamps
        duration_hours = 0.0
        if len(regime_log) >= 2:
            first_ts = _extract_ts_ms(regime_log[0])
            last_ts = _extract_ts_ms(regime_log[-1])
            if first_ts is not None and last_ts is not None:
                duration_hours = (last_ts - first_ts) / (3600 * 1000)

        return RegimeStabilityMetrics(
            total_bars=total_bars,
            definite_bars=definite_bars,
            uncertain_bars=uncertain_bars,
            regime_flips=regime_flips,
            duration_hours=max(duration_hours, 0.001),
        )

    def _extract_alpha_metrics(self, stage_result: StageResult) -> AlphaMetrics:
        """Extract alpha search metrics from full backtest results."""
        bt = stage_result.raw_result
        if bt is None:
            return AlphaMetrics()

        # --- Churn: position sign changes / total intents ---
        # Guard: <2 intents → churn is undefined, return 0
        churn_ratio = 0.0
        intents = stage_result.trade_intents
        if intents and len(intents) >= 2:
            sign_changes = 0
            prev_side = None
            for intent in intents:
                side = intent.get("side", "").upper()
                if not side:
                    continue
                if prev_side is not None and side != prev_side:
                    sign_changes += 1
                prev_side = side
            # Normalize: sign_changes / (total_intents - 1)
            churn_ratio = sign_changes / max(len(intents) - 1, 1)

        # --- Reject rate: rejected intents / proposed intents ---
        reject_rate = 0.0
        intent_log = stage_result.intent_log or intents
        if intent_log:
            proposed = sum(
                1 for i in intent_log
                if isinstance(i, dict) and str(i.get("intent_status", "PROPOSED")).upper() == "PROPOSED"
            )
            rejected = sum(
                1 for i in intent_log
                if isinstance(i, dict) and (
                    str(i.get("intent_status", "")).upper() == "REJECTED"
                    or str(i.get("outcome", "")).startswith("GUARD_REJECT")
                    or str(i.get("outcome", "")).startswith("NRR")
                )
            )
            if proposed > 0:
                reject_rate = rejected / proposed

        # --- Utilization: None if not available ---
        # We don't fabricate data. Penalty is skipped when None.
        utilization = None

        return AlphaMetrics(
            sharpe_ratio=getattr(bt, "sharpe_ratio", 0.0),
            calmar_ratio=getattr(bt, "calmar_ratio", 0.0),
            max_drawdown_pct=getattr(bt, "max_drawdown", 0.0) * 100,
            total_trades=getattr(bt, "total_trades", 0),
            churn_ratio=churn_ratio,
            reject_rate=reject_rate,
            utilization=utilization,
            roi_pct=getattr(bt, "roi_pct", 0.0),
        )
