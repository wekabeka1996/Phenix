"""
Scenario Worker
===============

Core execution unit: wraps AlphaSearchBacktestPlugin via composition.
Each worker owns an isolated LocalBus, plugin instance, and state.

Self-triggering pattern: on each feature snapshot the worker:
1. Emits synthetic EVT:FEATURES_CALCULATED to its local bus -> caches FE features
2. Emits synthetic EVT:TA_FEATURES_CALCULATED when TA features are present
3. Immediately emits synthetic CMD:PROCESS_STRATEGY -> triggers scoring
4. Collects EVT:ALPHA_SCORE_CALCULATED events from local bus
"""

import decimal
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.reference.domains.ta_features.contracts import (
    TA_WARMUP_KEY,
    extract_ta_feature_vector,
)
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
        shadow_book: Optional[Any] = None,
    ):
        self._spec = spec
        self._scenario_id = spec.scenario_id
        self._strategy_type = spec.strategy_type
        self._log_dir = log_dir
        self._strategy_config = strategy_config
        self._aurora_base_threshold: Optional[float] = None
        self._aurora_default_base_threshold: Optional[float] = None

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
            shadow_book=shadow_book,
        )

        # --- Override adapter parameters for aurora strategy ---
        if self._strategy_type == "aurora" and strategy_config:
            self._inject_aurora_params(strategy_config)
        if self._strategy_type == "aurora":
            self._aurora_default_base_threshold = self._capture_aurora_base_threshold()
            self._aurora_base_threshold = self._aurora_default_base_threshold

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
        Phase 1: emit synthetic feature events -> plugin caches features
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
            feature_event_name = self._plugin.config.triggers.feature_event
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
                event_name=feature_event_name,
                payload=feature_payload,
                why=f"alpha_search_standalone:{self._scenario_id}",
            )

            ta_features = extract_ta_feature_vector(snapshot.features)
            ta_feature_event_name = self._plugin.config.triggers.ta_feature_event
            if ta_features and ta_feature_event_name != feature_event_name:
                # alpha_input_v1 currently preserves TA readiness as a bool flag only.
                # Replay-local synthetic TA events therefore carry explicit readiness
                # but not the original warmup bar counters.
                ta_feature_payload = {
                    "ts": snapshot.ts_ms,
                    "symbol": snapshot.symbol,
                    "tf_sec": snapshot.tf_sec,
                    "bar_close_ts": snapshot.bar_close_ts,
                    "close": snapshot.price,
                    **ta_features,
                    "is_warm": bool(
                        snapshot.warmup_status.get(TA_WARMUP_KEY, True)
                    ),
                    "source": "ta_features",
                }
                self._bus.emit(
                    event_name=ta_feature_event_name,
                    payload=ta_feature_payload,
                    why=f"alpha_search_standalone_ta:{self._scenario_id}",
                )

            if self._strategy_type == "aurora":
                self._prepare_aurora_symbol_policy(snapshot.symbol)
                self._apply_regime_adaptive_threshold(
                    snapshot.regime,
                    symbol=snapshot.symbol,
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
                enriched = AlphaShadowResultV1.model_validate({
                    "scenario_id": self._scenario_id,
                    "strategy_type": self._strategy_type,
                    "version": self._spec.version,
                    "family": self._spec.family or self._strategy_type,
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
                    "shadow_only": self._spec.shadow_only,
                    "authority_applied": self._spec.authority_applied,
                    "no_effect": self._spec.no_effect,
                    "regime": snapshot.regime,
                }).model_dump()
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
        - _blocked_regimes
        - _symbol_allowed_regimes
        - _symbol_signal_weights
        - _symbol_feature_neutrals
        - _symbol_regime_thresholds
        - _symbol_signal_thresholds
        - _decision_exit_cfg
        - _symbol_exit_configs
        - _symbol_trailing_stop_configs
        - _symbol_take_profit_configs

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
                self._plugin.provider_configs["aurora"].threshold = float(
                    thr_val)
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

        decision_exit = decision.get("exit") or {}
        aurora_provider._decision_exit_cfg = (
            dict(decision_exit) if isinstance(decision_exit, dict) else {}
        )

        blocked_regimes = decision.get("blocked_regimes") or []
        aurora_provider._blocked_regimes = {
            str(regime) for regime in blocked_regimes if str(regime).strip()
        }

        assets = aurora_root.get("assets", {}) or {}
        symbol_allowed_regimes: Dict[str, set[str]] = {}
        symbol_signal_weights: Dict[str, Dict[str, Any]] = {}
        symbol_feature_neutrals: Dict[str, Dict[str, Any]] = {}
        symbol_regime_thresholds: Dict[str, Dict[str, Any]] = {}
        symbol_signal_thresholds: Dict[str, float] = {}
        symbol_exit_configs: Dict[str, Dict[str, Any]] = {}
        symbol_trailing_stop_configs: Dict[str, Dict[str, Any]] = {}
        symbol_take_profit_configs: Dict[str, Dict[str, Any]] = {}

        for symbol, asset_cfg in assets.items():
            if not isinstance(asset_cfg, dict):
                continue

            allowed_regimes = asset_cfg.get("allowed_regimes") or []
            if allowed_regimes:
                symbol_allowed_regimes[symbol] = {
                    str(regime) for regime in allowed_regimes if str(regime).strip()
                }

            if isinstance(asset_cfg.get("weights"), dict) and asset_cfg["weights"]:
                symbol_signal_weights[symbol] = dict(asset_cfg["weights"])

            if isinstance(asset_cfg.get("feature_neutrals"), dict) and asset_cfg["feature_neutrals"]:
                symbol_feature_neutrals[symbol] = dict(asset_cfg["feature_neutrals"])

            if isinstance(asset_cfg.get("regime_thresholds"), dict) and asset_cfg["regime_thresholds"]:
                symbol_regime_thresholds[symbol] = dict(asset_cfg["regime_thresholds"])

            threshold_cfg = asset_cfg.get("signal_threshold")
            if (
                isinstance(threshold_cfg, dict)
                and threshold_cfg.get("enabled")
                and threshold_cfg.get("value") is not None
            ):
                symbol_signal_thresholds[symbol] = float(threshold_cfg["value"])

            exit_cfg = asset_cfg.get("exit")
            if isinstance(exit_cfg, dict) and exit_cfg:
                symbol_exit_configs[symbol] = dict(exit_cfg)

            trailing_stop_cfg = asset_cfg.get("trailing_stop")
            if isinstance(trailing_stop_cfg, dict) and trailing_stop_cfg:
                symbol_trailing_stop_configs[symbol] = dict(trailing_stop_cfg)

            take_profit_cfg = asset_cfg.get("take_profit")
            if isinstance(take_profit_cfg, dict) and take_profit_cfg:
                symbol_take_profit_configs[symbol] = dict(take_profit_cfg)

        aurora_provider._symbol_allowed_regimes = symbol_allowed_regimes
        aurora_provider._symbol_signal_weights = symbol_signal_weights
        aurora_provider._symbol_feature_neutrals = symbol_feature_neutrals
        aurora_provider._symbol_regime_thresholds = symbol_regime_thresholds
        aurora_provider._symbol_signal_thresholds = symbol_signal_thresholds
        aurora_provider._symbol_exit_configs = symbol_exit_configs
        aurora_provider._symbol_trailing_stop_configs = symbol_trailing_stop_configs
        aurora_provider._symbol_take_profit_configs = symbol_take_profit_configs

        if hasattr(self._plugin, "configure_aurora_virtual_policy"):
            self._plugin.configure_aurora_virtual_policy(
                decision_exit=aurora_provider._decision_exit_cfg,
                symbol_exit_configs=symbol_exit_configs,
                symbol_trailing_stop_configs=symbol_trailing_stop_configs,
                symbol_take_profit_configs=symbol_take_profit_configs,
            )

    def _capture_aurora_base_threshold(self) -> Optional[float]:
        """Capture initial aurora threshold once for regime scaling."""
        provider_cfg = self._plugin.provider_configs.get("aurora")
        if provider_cfg is None:
            return None
        try:
            base_thr = float(provider_cfg.threshold)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, base_thr))

    def _prepare_aurora_symbol_policy(self, symbol: str) -> None:
        """Apply per-symbol Aurora threshold state before scoring the snapshot."""
        provider_cfg = self._plugin.provider_configs.get("aurora")
        aurora_provider = self._plugin.providers.get("aurora")
        if provider_cfg is None or aurora_provider is None:
            return

        base_threshold = self._resolve_aurora_base_threshold(symbol)
        if base_threshold is None:
            return

        self._aurora_base_threshold = base_threshold
        provider_cfg.threshold = base_threshold
        aurora_provider._base_threshold = decimal.Decimal(str(base_threshold))

    def _resolve_aurora_base_threshold(self, symbol: Optional[str]) -> Optional[float]:
        """Resolve per-symbol aurora threshold with global fallback."""
        aurora_provider = self._plugin.providers.get("aurora")
        if aurora_provider is not None and symbol:
            symbol_thresholds = getattr(
                aurora_provider,
                "_symbol_signal_thresholds",
                {},
            ) or {}
            raw_value = symbol_thresholds.get(symbol)
            if raw_value is not None:
                try:
                    return max(0.0, min(1.0, float(raw_value)))
                except (TypeError, ValueError):
                    pass

        if self._aurora_default_base_threshold is not None:
            return self._aurora_default_base_threshold
        return self._capture_aurora_base_threshold()

    def _resolve_aurora_regime_thresholds(self, symbol: Optional[str]) -> Dict[str, Any]:
        """Resolve per-symbol regime threshold map with global fallback."""
        aurora_provider = self._plugin.providers.get("aurora")
        if aurora_provider is None:
            return {}

        if symbol:
            symbol_thresholds = getattr(
                aurora_provider,
                "_symbol_regime_thresholds",
                {},
            ) or {}
            per_symbol = symbol_thresholds.get(symbol)
            if per_symbol:
                return per_symbol

        return getattr(aurora_provider, "_regime_thresholds", {}) or {}

    def _apply_regime_adaptive_threshold(
        self,
        regime: str,
        symbol: Optional[str] = None,
    ) -> None:
        """Apply per-snapshot effective threshold: base * regime_factor."""
        if self._aurora_base_threshold is None:
            return

        provider_cfg = self._plugin.provider_configs.get("aurora")
        aurora_provider = self._plugin.providers.get("aurora")
        if provider_cfg is None or aurora_provider is None:
            return

        regime_thresholds = self._resolve_aurora_regime_thresholds(symbol)
        raw_factor = regime_thresholds.get(
            regime, regime_thresholds.get("DEFAULT", 1.0)
        )

        try:
            factor = float(raw_factor)
        except (TypeError, ValueError):
            factor = 1.0
        if factor <= 0.0:
            factor = 1.0

        effective_thr = self._aurora_base_threshold * factor
        provider_cfg.threshold = max(0.0, min(1.0, effective_thr))

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
