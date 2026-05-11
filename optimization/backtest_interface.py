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

from apps.reference.config_models import ResearchProxyRuntimeMeta, ResearchTrialRuntimeMeta, SystemRuntimeMeta
from optimization.objectives import (
    RegimeStabilityMetrics,
    AlphaMetrics,
)
from optimization.research.provenance import (
    ResearchTrialRequest,
    build_materialization,
    build_trial_payload,
    update_materialization,
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
    scoring_telemetry: Dict[str, Any] = field(default_factory=dict)
    proxy_universe: Dict[str, Any] = field(default_factory=dict)
    search_provenance: Dict[str, Any] = field(default_factory=dict)
    preflight_manifest_path: Optional[str] = None


@dataclass(frozen=True)
class ResearchProxySpec:
    """Explicit proxy-universe contract for research harness runs."""

    label: str
    tracked_symbols: List[str]
    tradable_symbols: List[str]
    strategy_assignments: Dict[str, List[str]]
    context_symbols: List[str] = field(default_factory=list)


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
        research_proxy: Optional[ResearchProxySpec] = None,
        fail_on_scoring_fallback: bool = False,
        trial_artifacts_dir: Optional[Path] = None,
    ):
        self.config_dir = config_dir or Path("config/aurora")
        self.data_dir = data_dir
        self.locked_symbols = [str(s) for s in (locked_symbols or [])]
        self.locked_strategy_id = str(locked_strategy_id) if locked_strategy_id else None
        self.research_proxy = research_proxy
        self.fail_on_scoring_fallback = bool(fail_on_scoring_fallback)
        self.trial_artifacts_dir = Path(trial_artifacts_dir) if trial_artifacts_dir is not None else Path("artifacts/search_trials")

    def _ensure_runtime_meta(self, config: Any) -> Any:
        system_meta = getattr(config, "system_meta", None)
        if system_meta is None:
            raise ValueError("Research proxy: config.system_meta missing")
        runtime = getattr(system_meta, "runtime", None)
        if runtime is None:
            runtime = SystemRuntimeMeta()
            system_meta.runtime = runtime
        return runtime

    def _apply_research_proxy(self, config: Any) -> Dict[str, Any]:
        if self.research_proxy is None:
            return {}

        tracked_symbols = list(dict.fromkeys(str(s) for s in self.research_proxy.tracked_symbols))
        tradable_symbols = list(dict.fromkeys(str(s) for s in self.research_proxy.tradable_symbols))
        context_symbols = list(dict.fromkeys(str(s) for s in self.research_proxy.context_symbols))
        assignments = {
            str(symbol): [str(strategy_id) for strategy_id in strategy_ids]
            for symbol, strategy_ids in self.research_proxy.strategy_assignments.items()
        }

        instruments = getattr(config, "instruments", None)
        if not isinstance(instruments, dict):
            raise ValueError("Research proxy: config.instruments missing/invalid")
        for symbol in tracked_symbols:
            if symbol not in instruments:
                raise ValueError(f"Research proxy: symbol {symbol} missing in instruments")

        tracked_set = set(tracked_symbols)
        for symbol in tradable_symbols:
            if symbol not in tracked_set:
                raise ValueError(f"Research proxy: tradable symbol {symbol} missing from tracked_symbols")
        for symbol in context_symbols:
            if symbol not in tracked_set:
                raise ValueError(f"Research proxy: context symbol {symbol} missing from tracked_symbols")
        for symbol in assignments.keys():
            if symbol not in tracked_set:
                raise ValueError(f"Research proxy: assignment symbol {symbol} missing from tracked_symbols")

        strategies = getattr(config, "strategies", None)
        for strategy_ids in assignments.values():
            for strategy_id in strategy_ids:
                if not hasattr(strategies, strategy_id):
                    raise ValueError(
                        f"Research proxy: strategy_id={strategy_id} profile is not loaded in config.strategies"
                    )

        trading = getattr(config, "trading", None)
        if trading is None or not hasattr(trading, "symbols_to_track"):
            raise ValueError("Research proxy: config.trading.symbols_to_track missing")
        trading.symbols_to_track = list(tracked_symbols)

        sr = getattr(config, "strategies_registry", None)
        if sr is None or not hasattr(sr, "assignments"):
            raise ValueError("Research proxy: config.strategies_registry.assignments missing")
        sr.assignments = dict(assignments)

        runtime = self._ensure_runtime_meta(config)
        runtime.research_proxy = ResearchProxyRuntimeMeta(
            label=self.research_proxy.label,
            tracked_symbols=list(tracked_symbols),
            tradable_symbols=list(tradable_symbols),
            context_symbols=list(context_symbols),
            strategy_assignments=dict(assignments),
            fail_closed_on_scoring_fallback=bool(self.fail_on_scoring_fallback),
        )

        return runtime.research_proxy.model_dump()

    def _get_proxy_universe(self, config: Any) -> Dict[str, Any]:
        runtime = self._ensure_runtime_meta(config)
        proxy = getattr(runtime, "research_proxy", None)
        if proxy is None:
            return {}
        if hasattr(proxy, "model_dump"):
            return proxy.model_dump()
        return dict(proxy)

    def _set_trial_runtime_meta(self, config: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        runtime = self._ensure_runtime_meta(config)
        runtime.research_trial = ResearchTrialRuntimeMeta(
            trial_id=str(payload.get("trial_id") or ""),
            arm_id=str(payload.get("arm_id") or ""),
            trial_params_json=dict(payload.get("trial_params_json") or {}),
            overlay_hash=str(payload.get("overlay_hash") or ""),
            effective_config_hash=str(payload.get("effective_config_hash") or ""),
            effective_strategy_slice_hash=str(payload.get("effective_strategy_slice_hash") or ""),
            proxy_universe=dict(payload.get("proxy_universe") or {}),
            fail_closed_on_scoring_fallback=bool(payload.get("fail_closed_on_scoring_fallback")),
            run_id=(str(payload.get("run_id")) if payload.get("run_id") else None),
            parent_anchor=(str(payload.get("parent_anchor")) if payload.get("parent_anchor") else None),
            timestamp=str(payload.get("timestamp") or ""),
            expected_changed_paths=list(payload.get("expected_changed_paths") or []),
            effective_changed_values=dict(payload.get("effective_changed_values") or {}),
            preflight_passed=bool(payload.get("preflight_passed")),
            rejection_reason=(str(payload.get("rejection_reason")) if payload.get("rejection_reason") else None),
            anchor_effective_config_hash=(
                str(payload.get("anchor_effective_config_hash")) if payload.get("anchor_effective_config_hash") else None
            ),
            anchor_effective_strategy_slice_hash=(
                str(payload.get("anchor_effective_strategy_slice_hash"))
                if payload.get("anchor_effective_strategy_slice_hash")
                else None
            ),
            manifest_path=(str(payload.get("manifest_path")) if payload.get("manifest_path") else None),
            execution_status=(str(payload.get("execution_status")) if payload.get("execution_status") else None),
        )
        merged_payload = dict(payload)
        merged_payload.update(runtime.research_trial.model_dump())
        return merged_payload

    def _enforce_universe_lock(self, config: Any) -> None:
        """Runtime assert and lock for optimization universe."""
        if self.research_proxy is not None:
            self._apply_research_proxy(config)
            return
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

    def _load_config_with_overlay(
        self,
        overlay: Dict[str, Any],
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Tuple[Any, Dict[str, Any]]:
        from apps.reference.config_loader import ConfigLoader

        overlay_copy = dict(overlay)
        bt_overlay = overlay_copy.setdefault("trading", {}).setdefault("backtest", {})
        bt_overlay.setdefault("backtest_mode", "strict")
        if start_date:
            bt_overlay["start_date"] = start_date
        if end_date:
            bt_overlay["end_date"] = end_date

        loader = ConfigLoader(
            config_dir=self.config_dir,
            optuna_overlay=overlay_copy,
        )
        config = loader.load_config()
        self._enforce_universe_lock(config)
        return config, overlay_copy

    def _prepare_trial_materialization(
        self,
        *,
        config: Any,
        overlay: Dict[str, Any],
        trial_request: ResearchTrialRequest,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        proxy_universe = self._get_proxy_universe(config)
        anchor_effective_config_hash = None
        anchor_effective_strategy_slice_hash = None
        rejection_reason = None

        if trial_request.trial_params_json:
            if not trial_request.parent_anchor:
                rejection_reason = "MISSING_PARENT_ANCHOR"
            else:
                anchor_config, anchor_overlay = self._load_config_with_overlay(
                    trial_request.anchor_overrides or {},
                    start_date=start_date,
                    end_date=end_date,
                )
                anchor_payload = build_trial_payload(
                    config=anchor_config,
                    overlay=anchor_overlay,
                    request=ResearchTrialRequest(
                        trial_id=f"{trial_request.trial_id}__anchor",
                        arm_id=f"{trial_request.arm_id}__anchor",
                        trial_params_json={},
                        expected_changed_paths=list(trial_request.expected_changed_paths),
                        parent_anchor=trial_request.parent_anchor,
                        strategy_id=trial_request.strategy_id,
                        strategy_symbol=trial_request.strategy_symbol,
                    ),
                    proxy_universe=self._get_proxy_universe(anchor_config),
                    fail_closed_on_scoring_fallback=self.fail_on_scoring_fallback,
                )
                anchor_effective_config_hash = anchor_payload.get("effective_config_hash")
                anchor_effective_strategy_slice_hash = anchor_payload.get("effective_strategy_slice_hash")

        materialization = build_materialization(
            manifest_dir=self.trial_artifacts_dir,
            config=config,
            overlay=overlay,
            request=trial_request,
            proxy_universe=proxy_universe,
            fail_closed_on_scoring_fallback=self.fail_on_scoring_fallback,
            anchor_effective_config_hash=anchor_effective_config_hash,
            anchor_effective_strategy_slice_hash=anchor_effective_strategy_slice_hash,
            rejection_reason=rejection_reason,
        )

        if (
            rejection_reason is None
            and trial_request.trial_params_json
            and anchor_effective_config_hash is not None
            and anchor_effective_strategy_slice_hash is not None
            and materialization.payload.get("effective_config_hash") == anchor_effective_config_hash
            and materialization.payload.get("effective_strategy_slice_hash") == anchor_effective_strategy_slice_hash
        ):
            materialization.payload = update_materialization(
                materialization.manifest_path,
                materialization.payload,
                preflight_passed=False,
                rejection_reason="NO_EFFECTIVE_CONFIG_DELTA",
                execution_status="preflight_rejected",
            )

        materialization.payload = self._set_trial_runtime_meta(config, materialization.payload)
        materialization.payload["manifest_path"] = str(materialization.manifest_path)
        return {
            "manifest_path": str(materialization.manifest_path),
            "payload": materialization.payload,
        }

    def _run_loaded_config(self, config: Any) -> StageResult:
        from apps.reference.main import run_backtest_simulation

        result_tuple = run_backtest_simulation(config, return_result=True)

        if result_tuple is None:
            return StageResult(success=False, error="run_backtest_simulation returned None")

        bt_result, report_data = result_tuple

        regime_log = []
        trade_intents_list = []
        intent_log_list = []
        equity_snapshots = []
        if isinstance(report_data, dict):
            regime_log = report_data.get("regime_log", [])
            intent_log_list = report_data.get("intents", [])
            if not intent_log_list:
                intent_log_list = report_data.get("trade_intents", [])
            trade_intents_list = [
                i for i in intent_log_list
                if isinstance(i, dict) and str(i.get("intent_status", "PROPOSED")).upper() == "PROPOSED"
            ]

        engine = report_data.get("_engine") if isinstance(report_data, dict) else None
        if engine and hasattr(engine, "_equity_snapshots"):
            equity_snapshots = list(engine._equity_snapshots)

        scoring_telemetry = report_data.get("scoring_telemetry", {}) if isinstance(report_data, dict) else {}
        proxy_universe = report_data.get("proxy_universe", {}) if isinstance(report_data, dict) else {}
        search_provenance = report_data.get("search_provenance", {}) if isinstance(report_data, dict) else {}

        if self.fail_on_scoring_fallback:
            fallback_count = 0
            if isinstance(scoring_telemetry, dict):
                try:
                    fallback_count = int(scoring_telemetry.get("quadratic_fallback_count") or 0)
                except Exception:
                    fallback_count = 0
            if fallback_count > 0:
                return StageResult(
                    success=False,
                    error=(
                        "Research harness fail-closed: quadratic fallback observed "
                        f"({fallback_count})"
                    ),
                    raw_result=bt_result,
                    raw_report=report_data,
                    regime_log=regime_log,
                    trade_intents=trade_intents_list,
                    intent_log=intent_log_list,
                    equity_snapshots=equity_snapshots,
                    scoring_telemetry=scoring_telemetry,
                    proxy_universe=proxy_universe,
                    search_provenance=search_provenance,
                )

        return StageResult(
            success=True,
            raw_result=bt_result,
            raw_report=report_data,
            regime_log=regime_log,
            trade_intents=trade_intents_list,
            intent_log=intent_log_list,
            equity_snapshots=equity_snapshots,
            scoring_telemetry=scoring_telemetry,
            proxy_universe=proxy_universe,
            search_provenance=search_provenance,
        )

    def _run_backtest_with_overlay(
        self,
        overlay: Dict[str, Any],
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        trial_request: Optional[ResearchTrialRequest] = None,
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
            config, effective_overlay = self._load_config_with_overlay(
                overlay,
                start_date=start_date,
                end_date=end_date,
            )

            manifest_path = None
            preflight_payload = None
            if trial_request is not None:
                preflight = self._prepare_trial_materialization(
                    config=config,
                    overlay=effective_overlay,
                    trial_request=trial_request,
                    start_date=start_date,
                    end_date=end_date,
                )
                manifest_path = preflight["manifest_path"]
                payload = preflight["payload"]
                preflight_payload = dict(payload)
                if not payload.get("preflight_passed"):
                    return StageResult(
                        success=False,
                        error=str(payload.get("rejection_reason") or "PREFLIGHT_REJECTED"),
                        proxy_universe=dict(payload.get("proxy_universe") or {}),
                        search_provenance=dict(payload),
                        preflight_manifest_path=manifest_path,
                    )

            stage_result = self._run_loaded_config(config)
            if manifest_path is not None:
                payload = dict(preflight_payload or {})
                payload.update(dict(stage_result.search_provenance or {}))
                updates = {
                    "execution_status": "completed" if stage_result.success else "runtime_error",
                    "run_id": ((stage_result.raw_report or {}).get("run_id") if isinstance(stage_result.raw_report, dict) else None),
                    "rejection_reason": (stage_result.error if not stage_result.success else payload.get("rejection_reason")),
                }
                payload = update_materialization(Path(manifest_path), payload, **updates)
                stage_result.search_provenance = payload
                stage_result.preflight_manifest_path = manifest_path
            return stage_result
        except Exception as e:
            LOG.exception(f"Backtest failed: {e}")
            return StageResult(success=False, error=str(e))

    def run_stage0(
        self,
        overrides: Dict[str, Any],
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        trial_request: Optional[ResearchTrialRequest] = None,
    ) -> Tuple[RegimeStabilityMetrics, StageResult]:
        """Run backtest and extract regime stability metrics for Stage 0."""
        stage_result = self._run_backtest_with_overlay(
            overrides, start_date=start_date, end_date=end_date, trial_request=trial_request,
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
        trial_request: Optional[ResearchTrialRequest] = None,
    ) -> Tuple[AlphaMetrics, StageResult]:
        """Run full backtest and extract alpha metrics for Stage 1."""
        stage_result = self._run_backtest_with_overlay(
            overrides, start_date=start_date, end_date=end_date, trial_request=trial_request,
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
