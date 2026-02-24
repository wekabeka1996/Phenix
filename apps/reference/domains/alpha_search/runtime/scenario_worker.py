"""
Scenario Worker
===============

Core execution unit: wraps AlphaSearchBacktestPlugin via composition.
Each worker owns an isolated LocalBus, plugin instance, and state.

Self-triggering pattern: on each feature snapshot the worker:
1. Emits synthetic EVT:FEATURES_CALCULATED to its local bus -> caches features
2. Immediately emits synthetic CMD:PROCESS_STRATEGY -> triggers scoring
3. Collects EVT:ALPHA_SCORE_CALCULATED events from local bus
"""

import decimal
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.reference.orchestrator.utils_event_bus import LocalBus

from ..backtest_plugin import AlphaSearchBacktestPlugin
from ..config_models import AlphaSearchConfig, AlphaSearchSystemConfig
from .contracts import AlphaInputV1, AlphaShadowResultV1, ScenarioSpec

LOG = logging.getLogger(__name__)


class ScenarioWorker:
    """
    Isolated shadow-execution unit for a single scenario.

    Design:
    - Owns a dedicated LocalBus (state isolation)
    - Wraps AlphaSearchBacktestPlugin (reuse, not rewrite)
    - Self-triggers scoring on each feature snapshot
    - Injects regime context into scoring calls
    - Overrides adapter parameters if strategy requires different config

    Thread safety:
    - Each worker is single-threaded from its own perspective.
    - ScenarioExecutor dispatches one snapshot at a time per worker.
    """

    def __init__(
        self,
        spec: ScenarioSpec,
        alpha_search_config: AlphaSearchConfig,
        system_config: AlphaSearchSystemConfig,
        strategy_config: Dict[str, Any],
        log_dir: Path,
    ):
        self._scenario_id = spec.scenario_id
        self._strategy_type = spec.strategy_type
        self._log_dir = log_dir
        self._strategy_config = strategy_config

        # --- Isolated event bus (no cross-scenario contamination) ---
        self._bus = LocalBus()

        # --- Result collection buffer ---
        self._result_buffer: List[Dict[str, Any]] = []
        self._bus.listen("EVT:ALPHA_SCORE_CALCULATED", self._collect_result)

        # --- Plugin instance (owns models, caches, virtual trader) ---
        self._plugin = AlphaSearchBacktestPlugin(
            event_bus=self._bus,
            config=alpha_search_config,
            system_config=system_config,
        )

        # --- Override adapter parameters for aurora strategy ---
        if self._strategy_type == "aurora" and strategy_config:
            self._inject_aurora_params(strategy_config)

        # --- Stats ---
        self._snapshots_processed = 0
        self._snapshots_failed = 0
        self._total_results = 0
        self._start_ts = time.time()

        LOG.info(
            f"[{self._scenario_id}] Worker initialized: "
            f"strategy={self._strategy_type}, providers={list(self._plugin.providers.keys())}"
        )

    @property
    def scenario_id(self) -> str:
        return self._scenario_id

    @property
    def strategy_type(self) -> str:
        return self._strategy_type

    def process_snapshot(self, snapshot: AlphaInputV1) -> List[Dict[str, Any]]:
        """
        Process a single feature snapshot through the self-triggering pipeline.

        SELF-TRIGGERING PATTERN:
        Phase 1: emit EVT:FEATURES_CALCULATED -> plugin caches features
        Phase 2: emit CMD:PROCESS_STRATEGY -> plugin reads cache, runs scoring
        Collect: read results from local bus

        Args:
            snapshot: Validated AlphaInputV1 inbound feature snapshot.

        Returns:
            List of score result dicts (one per provider that produced a score).
        """
        self._result_buffer.clear()

        try:
            # --- Phase 1: cache features ---
            feature_payload = {
                "symbol": snapshot.symbol,
                "features": snapshot.features,
                "tf_sec": snapshot.tf_sec,
                "bar_close_ts": snapshot.bar_close_ts,
                "ts": snapshot.ts_ms,
                "bar": {"close_ts": snapshot.bar_close_ts},
                # Inject regime context for aurora scoring
                "regime": snapshot.regime,
                "warmup_readiness": snapshot.warmup_status,
            }

            self._bus.emit(
                event_name="EVT:FEATURES_CALCULATED",
                payload=feature_payload,
                why=f"alpha_search_standalone:{self._scenario_id}",
            )

            # --- Phase 2: self-trigger scoring ---
            decision_payload = {
                "symbol": snapshot.symbol,
                "tf_sec": snapshot.tf_sec,
                "bar_close_ts": snapshot.bar_close_ts,
                # Pass regime through decision payload too
                "regime": snapshot.regime,
            }

            self._bus.emit(
                event_name="CMD:PROCESS_STRATEGY",
                payload=decision_payload,
                why=f"alpha_search_standalone_self_trigger:{self._scenario_id}",
            )

            # --- Enrich results with scenario metadata ---
            results = []
            for raw_result in self._result_buffer:
                pld = raw_result.get("pld", raw_result)
                enriched = {
                    "scenario_id": self._scenario_id,
                    "strategy_type": self._strategy_type,
                    "ts_ms": snapshot.ts_ms,
                    "symbol": pld.get("symbol", snapshot.symbol),
                    "score": pld.get("score", 0.0),
                    "confidence": pld.get("confidence", 0.0),
                    "threshold": pld.get("threshold", 0.0),
                    "side": self._determine_side(
                        pld.get("score", 0.0), pld.get("threshold", 0.0)
                    ),
                    "provider_id": pld.get("provider_id", ""),
                    "model_name": pld.get("model_name", ""),
                    "why": pld.get("why", []),
                    "features_used": pld.get("features_used", []),
                    "shadow": True,
                    "regime": snapshot.regime,
                }
                results.append(enriched)

            self._snapshots_processed += 1
            self._total_results += len(results)
            return results

        except Exception as e:
            self._snapshots_failed += 1
            LOG.error(
                f"[{self._scenario_id}] Snapshot processing failed: {e}",
                exc_info=True,
            )
            return []

    def _collect_result(self, event: Any) -> None:
        """Callback registered on local bus to collect score events."""
        self._result_buffer.append(event)

    def _inject_aurora_params(self, strategy_config: Dict[str, Any]) -> None:
        """
        Override AuroraAlphaAdapter parameters from scenario strategy config.

        The AuroraAlphaAdapter stores:
        - _signal_weights
        - _feature_neutrals
        - _regime_thresholds
        - _base_threshold
        - _direction_strength_cfg
        - _delta_price_cap_pct

        We override these from the resolved aurora.yaml decision section.
        """
        aurora_provider = self._plugin.providers.get("aurora")
        if not aurora_provider:
            LOG.debug(
                f"[{self._scenario_id}] No aurora provider to inject params into"
            )
            return

        # Navigate to decision config
        # strategy_config shape: {"aurora": {"decision": {...}, "assets": {...}}}
        # or just {"decision": {...}} if already unwrapped
        aurora_root = strategy_config.get("aurora", strategy_config)
        decision = aurora_root.get("decision", {})

        if not decision:
            return

        # Override adapter attributes
        if "signal_weights" in decision:
            aurora_provider._signal_weights = decision["signal_weights"]
            LOG.debug(f"[{self._scenario_id}] Injected signal_weights")

        if "feature_neutrals" in decision:
            aurora_provider._feature_neutrals = decision["feature_neutrals"]
            LOG.debug(f"[{self._scenario_id}] Injected feature_neutrals")

        if "regime_threshold_multipliers" in decision:
            aurora_provider._regime_thresholds = decision["regime_threshold_multipliers"]
            LOG.debug(f"[{self._scenario_id}] Injected regime_thresholds")

        if "signal_threshold" in decision:
            thr_val = decision["signal_threshold"]
            aurora_provider._base_threshold = decimal.Decimal(str(thr_val))
            # Sync plugin provider config threshold so score events
            # and side determination use the same overridden value
            if "aurora" in self._plugin.provider_configs:
                self._plugin.provider_configs["aurora"].threshold = float(thr_val)
            LOG.debug(
                f"[{self._scenario_id}] Injected base_threshold={thr_val}"
            )

        direction_cfg = decision.get("direction_strength_scoring")
        if direction_cfg:
            aurora_provider._direction_strength_cfg = direction_cfg
            LOG.debug(f"[{self._scenario_id}] Injected direction_strength_cfg")

        gates = decision.get("gates", {})
        if gates:
            LOG.debug(
                f"[{self._scenario_id}] Gates config available: {list(gates.keys())}"
            )

    @staticmethod
    def _determine_side(score: float, threshold: float) -> str:
        """Determine trade side from score and threshold."""
        if score > threshold:
            return "BUY"
        elif score < -threshold:
            return "SELL"
        return "NEUTRAL"

    def get_summary(self) -> Dict[str, Any]:
        """Return worker stats merged with plugin summary."""
        plugin_summary = {}
        try:
            plugin_summary = self._plugin.get_summary()
        except Exception:
            pass

        return {
            "scenario_id": self._scenario_id,
            "strategy_type": self._strategy_type,
            "snapshots_processed": self._snapshots_processed,
            "snapshots_failed": self._snapshots_failed,
            "total_results": self._total_results,
            "uptime_sec": round(time.time() - self._start_ts, 1),
            "plugin": plugin_summary,
        }

    def shutdown(self) -> None:
        """Clean shutdown: finalize plugin, flush logs."""
        try:
            self._plugin.shutdown()
        except Exception as e:
            LOG.warning(f"[{self._scenario_id}] Plugin shutdown error: {e}")

        LOG.info(
            f"[{self._scenario_id}] Worker stopped: "
            f"processed={self._snapshots_processed}, "
            f"results={self._total_results}, "
            f"failed={self._snapshots_failed}"
        )
