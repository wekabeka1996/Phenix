import json
import logging
import time
from collections import deque
from decimal import Decimal
from typing import Any, Dict, Optional, TYPE_CHECKING

"""Orchestrate Mean Reversion decisions from CMD:PROCESS_STRATEGY payloads.

This handler wires MeanReversion1mStrategy instances into the DecisionMaking
domain, maintains the per-symbol runtime caches they depend on, and emits the
decision artifacts that downstream execution consumes. Upstream components are
responsible for producing bars, features, warmup status, and regime payloads.

Activation SSOT is strategies_registry.assignments on a per-symbol basis.
mean_reversion.enabled acts only as a global kill-switch and does not activate
the handler by itself.
"""

# DET-BT-09: runtime timestamps come from the shared clock abstraction.
# Stdlib time remains only for human-readable formatting in get_stats().
from apps.reference.core.time import get_clock

from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    StrategyAnalyticsRestoreSnapshot,
    upgrade_cold_execution_restore_if_clean_start,
)
from apps.reference.contracts.runtime_bar_identity import (
    CanonicalBarIdentity,
    CanonicalReplayIdentity,
    RuntimeBarSourceMode,
    extract_canonical_bar_identity,
    extract_canonical_replay_identity,
)
from apps.reference.contracts.runtime_gap_policy import (
    RuntimeGapStatus,
    attach_gap_status_payload,
    extract_gap_status,
)
from apps.reference.contracts.runtime_regime_layers import (
    build_regime_provenance_fields,
    is_structural_regime_payload,
    normalize_structural_regime_label,
)
from apps.reference.contracts.runtime_readiness import (
    RuntimeReadinessScope,
)
from vfoundation.core.protocol import Message
from apps.reference.utils.accessors import aget
from apps.reference.domains.decision_making.intent.truth_artifacts import (
    write_strategy_decision_blocked,
)
from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
from apps.reference.domains.decision_making.intent.reject_wal import write_trade_intent_rejected

# Import MR strategy components (via DM strategy bridge — FE-DM-BOUNDARY-STABILIZATION)
from apps.reference.domains.strategies.runtimes.bridge import (
    MeanReversion1mStrategy,
    MRStrategyConfig,
    MRSignal,
    MRSignalType,
    FlatRegimeThresholds,
    SqueezeExpansionVetoConfig,
    MomentumSeparationVetoConfig,
)
from apps.reference.config_models import (
    AuroraConfig,
    MeanReversion1mStrategyConfig,
    MRAssetConfig,
)
from apps.reference.domains.strategies.runtimes.mean_reversion.logger import MeanReversionBarLogger
from apps.reference.domains.decision_making.primitives.position_queries import PositionQueries
from apps.reference.domains.decision_making.core.runtime_readiness import (
    RestoreScopeSpec,
    RuntimeReadinessBuildRequest,
    build_runtime_readiness,
)

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


LOG = logging.getLogger(__name__)


def normalize_ts_ms(raw: Any) -> int:
    """Best-effort normalize timestamp to milliseconds.

    Accepts seconds or milliseconds (int/str). Returns 0 if missing/invalid.
    """
    if raw is None:
        return 0
    if isinstance(raw, str):
        raw = raw.strip()
        if raw in ("", "0"):
            return 0
    try:
        ts = int(raw)
    except Exception:
        return 0
    if ts <= 0:
        return 0
    if 0 < ts < 1_000_000_000_000:
        ts *= 1000
    return ts


def _decimal_attr(obj: Any, name: str, default: str) -> Decimal:
    """Read a numeric attribute with a deterministic Decimal fallback.

    Runtime uses typed config, but several integration tests pass MagicMock-based
    config objects that may not define newer Tier-D fields.
    """
    value = getattr(obj, name, default)
    if value is None:
        value = default
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _runtime_squeeze_expansion_veto(obj: Any) -> SqueezeExpansionVetoConfig:
    """Normalize typed squeeze-expansion veto config into runtime-friendly typed config."""
    return SqueezeExpansionVetoConfig(
        enabled=bool(getattr(obj, "enabled")),
        squeeze_width_max=Decimal(str(getattr(obj, "squeeze_width_max"))),
        post_squeeze_width_max=Decimal(
            str(getattr(obj, "post_squeeze_width_max"))),
        expansion_ratio_min=Decimal(str(getattr(obj, "expansion_ratio_min"))),
        regimes=[str(regime) for regime in getattr(obj, "regimes", [])],
        sides=[str(side).upper() for side in getattr(obj, "sides", [])],
    )


def _runtime_momentum_separation_veto(obj: Any) -> MomentumSeparationVetoConfig:
    """Normalize typed momentum-separation veto config into runtime-friendly typed config."""
    return MomentumSeparationVetoConfig(
        enabled=bool(getattr(obj, "enabled")),
        lookback_bars=int(getattr(obj, "lookback_bars")),
        min_drift_pct=Decimal(str(getattr(obj, "min_drift_pct"))),
        min_current_bb_width=Decimal(
            str(getattr(obj, "min_current_bb_width"))),
        regimes=[str(regime) for regime in getattr(obj, "regimes", [])],
        sides=[str(side).upper() for side in getattr(obj, "sides", [])],
    )


def _maybe_build_position_queries(
    *,
    config: AuroraConfig,
    portfolio_getter,
    logger: logging.Logger,
) -> PositionQueries | None:
    try:
        dm_sizing_cfg = config.domains.decision_making.position_sizing
        min_position_size_usd = Decimal(
            str(dm_sizing_cfg.min_position_size_usd))
        liquidity_cap_usd = Decimal(str(dm_sizing_cfg.liquidity_based_cap_usd))
    except Exception as exc:
        logger.debug(
            "PositionQueries unavailable during mean_reversion init: %s", exc)
        return None
    return PositionQueries(
        config,
        portfolio_getter,
        min_position_size_usd,
        liquidity_cap_usd,
        logger,
    )


class MeanReversionHandler:
    """Coordinate Mean Reversion decision flow for assigned symbols.

    The handler owns config hydration, per-symbol strategy instances, local
    execution/readiness caches, and the emission of blocked/signal artifacts.
    The primary decision trigger is CMD:PROCESS_STRATEGY; other listeners only
    maintain local state used by later signal evaluation.
    """

    def __init__(self, fsm: "FSMCore", config: AuroraConfig) -> None:
        """
        Initialize Mean Reversion handler.

        Args:
            fsm: FSMCore instance for event emission
            config: Full application config (typed AuroraConfig)
        """
        self.fsm = fsm
        self.config = config
        self.logger = LOG.getChild("MRHandler")
        self.mlog = logging.getLogger("domain_mean_reversion")

        # Parse MR config
        self._mr_config: Optional[MeanReversion1mStrategyConfig] = None
        self._enabled: bool = False
        self._enabled_symbols: set[str] = set()
        self._per_symbol_regime: Dict[str, str] = {}
        self._regime_ts_ms: Dict[str, int] = {}
        self._regime_event_ts_ms: Dict[str, int] = {}
        self._regime_confidence: Dict[str, float] = {}
        self._regime_source: Dict[str, str] = {}
        self._regime_same_bar: Dict[str, bool | None] = {}
        self._regime_provenance_reason: Dict[str, str] = {}
        self._last_tick_ts_ms: Dict[str, int] = {}
        self._last_counted_bar_end_ts_ms: Dict[str, int] = {}
        self._latest_portfolio: Dict[str, Any] | None = None
        self._latest_exposure_summary: Dict[str, Any] | None = None
        self._objective_blocked_ts_ms: Dict[str, deque[int]] = {}
        self._objective_cancel_replace_ts_ms: Dict[str, deque[int]] = {}
        self._objective_reentry_ts_ms: Dict[str, deque[int]] = {}
        self._position_qty: Dict[str, Decimal] = {}
        self._last_close_ts: Dict[str, int] = {}
        self._stats: Dict[str, int] = {
            "ticks_seen": 0,
            "ticks_dropped_missing_ts": 0,
            "ticks_dropped_out_of_order": 0,
            "ticks_dropped_invalid_price": 0,
            "bars_completed": 0,
            "signals_emitted": 0,
            "neutral_bars": 0,
            "bar_logging_errors": 0,
            "tick_processing_errors": 0,
            "regime_processing_errors": 0,
            # T2B-02: Bar gating stats
            "bars_received": 0,
            "bars_rejected_wrong_tf": 0,
            "bars_rejected_missing_tf": 0,
            # T2B-05: Bar OHLCV gating
            "bars_rejected_missing_bar": 0,
        }
        self._position_queries = _maybe_build_position_queries(
            config=self.config,
            portfolio_getter=lambda: self._latest_portfolio,
            logger=self.logger,
        )

        self._parse_config()

        # Initialize strategy per symbol if enabled
        self._strategies: Dict[str, MeanReversion1mStrategy] = {}
        if self._enabled:
            self._init_strategies()

        # Signal tracking for logging
        self._signal_counts: Dict[str, int] = {}
        self._last_signal_time: Dict[str, float] = {}
        self._analytics_restore_snapshots: Dict[str,
                                                StrategyAnalyticsRestoreSnapshot] = {}

        # Cache for liquidity kappa (from FeatureEngineering)
        self._liquidity_kappa_map: Dict[str, Decimal] = {}

        # P0-1: Per-symbol features cache (keyed by symbol) for volatility/liquidity propagation
        # Stores cmd.features from last CMD:PROCESS_STRATEGY per symbol
        self._last_cmd_features: Dict[str, Dict[str, Any]] = {}

        # MR-V1-WIRING: Per-symbol price_motion cache from CMD:PROCESS_STRATEGY
        # Top-level field in CMD payload, NOT nested inside features dict.
        self._last_cmd_price_motion: Dict[str, Dict[str, Any]] = {}

        # Block reason throttling (avoid per-tick spam)
        self._last_block_reason: Dict[str, str] = {}
        self._last_block_ts_ms: Dict[str, int] = {}

        # Vector 1: Microstructure Veto state
        # Per-symbol TFI EMA buffer (smoothed trade flow imbalance)
        self._tfi_ema: Dict[str, float] = {}
        self._tfi_bar_count: Dict[str, int] = {}
        # Resolve per-symbol microstructure veto config (global -> per-asset override)
        self._microstructure_veto_configs: Dict[str, Any] = {}
        if self._mr_config:
            global_veto = self._mr_config.microstructure_veto
            for sym in self._enabled_symbols:
                asset_cfg = self._mr_config.assets.get(sym)
                per_asset_veto = None
                if asset_cfg and asset_cfg.strategy:
                    per_asset_veto = getattr(
                        asset_cfg.strategy, "microstructure_veto", None)
                veto_cfg = per_asset_veto if per_asset_veto is not None else global_veto
                if veto_cfg is not None and veto_cfg.enabled:
                    self._microstructure_veto_configs[sym] = veto_cfg

        # Vector 2: Directional Bias config resolution (global -> per-asset override)
        self._directional_bias_configs: Dict[str, Any] = {}
        # Per-symbol funding rate cache (updated from features / market data)
        self._funding_rate: Dict[str, float] = {}
        if self._mr_config:
            global_bias = self._mr_config.directional_bias
            for sym in self._enabled_symbols:
                asset_cfg = self._mr_config.assets.get(sym)
                per_asset_bias = None
                if asset_cfg and asset_cfg.strategy:
                    per_asset_bias = getattr(
                        asset_cfg.strategy, "directional_bias", None)
                bias_cfg = per_asset_bias if per_asset_bias is not None else global_bias
                if bias_cfg is not None and bias_cfg.enabled:
                    self._directional_bias_configs[sym] = bias_cfg

        self.logger.info(
            f"MeanReversionHandler initialized: enabled={self._enabled}, "
            f"symbols={list(self._enabled_symbols)}, "
            f"strategies={list(self._strategies.keys())}"
        )
        self.mlog.info(
            "MR_INIT %s",
            json.dumps(
                {
                    "strategy_id": "mean_reversion",
                    "enabled": self._enabled,
                    "enabled_symbols": sorted(self._enabled_symbols),
                },
                ensure_ascii=False,
            ),
        )

        # Initialize Bar Logger (Lazy init in _init_strategies might be safer if config not yet parsed,
        # but _parse_config is called in __init__ before this)
        self.bar_logger: Optional[MeanReversionBarLogger] = None
        if self._mr_config and self._mr_config.timeframe_sec > 0:
            self.bar_logger = MeanReversionBarLogger(
                self._mr_config.timeframe_sec)

    def apply_runtime_analytics_restore_snapshot(
        self,
        snapshot: StrategyAnalyticsRestoreSnapshot,
    ) -> None:
        if str(snapshot.strategy_id) != "mean_reversion":
            return
        self._analytics_restore_snapshots[str(snapshot.symbol)] = snapshot

    def get_runtime_analytics_restore_snapshot(
        self,
        symbol: str,
    ) -> StrategyAnalyticsRestoreSnapshot | None:
        return self._analytics_restore_snapshots.get(str(symbol))

    def register(self) -> None:
        """Attach the listeners required by the current MR orchestration path.

        CMD:PROCESS_STRATEGY is the only decision trigger. The remaining wired
        listeners update local state used by later signal evaluation or runtime
        restore handling; they do not independently emit MR signals.
        """
        if not self._enabled:
            return
        # T2B-03: Primary trigger - CMD:PROCESS_STRATEGY (Orchestrated Cycle)
        self.fsm.listen("CMD:PROCESS_STRATEGY", self._on_process_strategy)
        # T2B-03: Data-only listeners (no decision trigger)
        self.fsm.listen("EVT:BAR_CLOSED", self._on_bar_closed_data_only)
        self.fsm.listen("EVT:REGIME_DETECTED", self._on_regime_detected)
        self.fsm.listen("EVT:TRADE_EXECUTED", self._on_trade_executed)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED",
                        self._on_portfolio_state_updated)
        self.fsm.listen("EVT:EXPOSURE_SUMMARY_UPDATED",
                        self._on_exposure_summary_updated)
        self.fsm.listen("EVT:ORDER_STATE_CHANGED",
                        self._on_order_state_changed)
        self.fsm.listen("EVT:TRADE_INTENT_REJECTED",
                        self._on_trade_intent_rejected)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED",
                        self._on_portfolio_clean_start_check)
        self.mlog.info(
            "MR_REGISTER %s",
            json.dumps(
                {
                    "events": [
                        "CMD:PROCESS_STRATEGY",
                        "EVT:BAR_CLOSED",
                        "EVT:REGIME_DETECTED",
                        "EVT:TRADE_EXECUTED",
                        "EVT:PORTFOLIO_STATE_UPDATED",
                        "EVT:EXPOSURE_SUMMARY_UPDATED",
                        "EVT:ORDER_STATE_CHANGED",
                        "EVT:TRADE_INTENT_REJECTED",
                    ],
                    "enabled_symbols": sorted(self._enabled_symbols),
                    "timeframe_sec": self.timeframe_sec,
                },
                ensure_ascii=False,
            ),
        )

    def _get_mr_assigned_symbols(self) -> set[str]:
        """
        Get symbols that have mean_reversion assigned in strategies_registry.

        CFG-STRATEGIES-SSOT-02-MR-HANDLER-STRICT-CONTRACT:
        SSOT for activation is strategies_registry.assignments.
        mean_reversion.enabled is a global kill-switch (can disable but does not activate by itself).
        """
        mr_symbols = set()

        if hasattr(self.config, 'strategies_registry') and self.config.strategies_registry:
            assignments = self.config.strategies_registry.assignments
            for symbol, strategies in assignments.items():
                if "mean_reversion" in strategies:
                    mr_symbols.add(symbol)

        return mr_symbols

    def _parse_config(self) -> None:
        """
        Parse Mean Reversion config from application config.

        CFG-STRATEGIES-SSOT-02-MR-HANDLER-STRICT-CONTRACT:
        - Only typed Pydantic config (no dict-fallback)
        - Fail-closed: missing config when MR assigned → ValueError
        """
        # Check if MR is assigned in strategies_registry
        mr_assigned_symbols = self._get_mr_assigned_symbols()

        # Try Pydantic config (ONLY typed access)
        mr_cfg = getattr(self.config.strategies, "mean_reversion", None)
        if mr_cfg is not None:
            self._mr_config = mr_cfg
        else:
            # MR config missing
            if mr_assigned_symbols:
                # FAIL-CLOSED: MR assigned but config missing
                raise ValueError(
                    f"❌ CRITICAL: mean_reversion assigned to symbols {mr_assigned_symbols} "
                    f"but config.strategies.mean_reversion is missing or invalid. "
                    f"Required: config.strategies.mean_reversion (typed Pydantic) must be present."
                )
            else:
                # MR not assigned and config missing → disabled (fail-closed, no noise)
                self.logger.info(
                    "Mean Reversion 1m: config missing, handler disabled (no assignment)")
                self._enabled = False
                return

        # TASK32: Strategy activation is SSOT-driven via strategies_registry.assignments.
        # Keep config.enabled as a safety flag but fail-closed on conflicts.
        if mr_assigned_symbols and not bool(self._mr_config.enabled):
            raise ValueError(
                f"❌ CRITICAL: mean_reversion is assigned to symbols {mr_assigned_symbols} "
                f"but mean_reversion.enabled=false. Resolve SSOT conflict."
            )

        # Collect enabled symbols
        if self._mr_config and self._mr_config.assets:
            for symbol, asset_cfg in self._mr_config.assets.items():
                if isinstance(asset_cfg, MRAssetConfig):
                    if asset_cfg.enabled:
                        self._enabled_symbols.add(symbol)
                elif isinstance(asset_cfg, dict):
                    raise TypeError(
                        "mean_reversion.assets must contain typed MRAssetConfig values, got dict")

        missing_assets = sorted(
            [s for s in mr_assigned_symbols if not self._mr_config or s not in self._mr_config.assets])
        disabled_assets = sorted(
            [
                s
                for s in mr_assigned_symbols
                if self._mr_config
                and s in self._mr_config.assets
                and isinstance(self._mr_config.assets[s], MRAssetConfig)
                and not bool(self._mr_config.assets[s].enabled)
            ]
        )
        if missing_assets or disabled_assets:
            raise ValueError(
                f"❌ CRITICAL: mean_reversion assigned symbols must exist and be enabled in mean_reversion.assets. "
                f"missing={missing_assets} disabled={disabled_assets}"
            )

        # Final activation is assignment ∩ enabled assets.
        self._enabled_symbols = set(
            mr_assigned_symbols) & set(self._enabled_symbols)
        self._enabled = bool(self._enabled_symbols)

        # TF-SSOT-PACK-001: SSOT timeframe from config (removes hardcode)
        self.timeframe_sec = self._mr_config.timeframe_sec

        if not self._enabled_symbols:
            self.logger.info(
                "Mean Reversion 1m: no assigned+enabled symbols; handler disabled")
            self._enabled = False

    def _init_strategies(self) -> None:
        """Initialize separate strategy instance per symbol with overrides."""
        if not self._mr_config:
            return

        timeframe_sec = self._mr_config.timeframe_sec
        if timeframe_sec <= 0:
            raise ValueError(
                f"mean_reversion.timeframe_sec must be positive, got {timeframe_sec}")

        # Global base config
        base_strat_cfg = self._mr_config.strategy

        # Shared regime sizing
        regime_sizing = None
        if self._mr_config.regime_sizing:
            regime_sizing = {}
            for regime_name, sizing_cfg in self._mr_config.regime_sizing.items():
                if hasattr(sizing_cfg, 'model_dump'):
                    regime_sizing[regime_name] = sizing_cfg.model_dump(
                        exclude_none=True)
                elif isinstance(sizing_cfg, dict):
                    regime_sizing[regime_name] = sizing_cfg

        flat_regime_thresholds = FlatRegimeThresholds(
            high_vol_pct=Decimal(
                str(self._mr_config.regime_thresholds.high_vol_pct)),
            low_vol_pct=Decimal(
                str(self._mr_config.regime_thresholds.low_vol_pct)),
        )

        for symbol in self._enabled_symbols:
            self._objective_blocked_ts_ms[symbol] = deque()
            self._objective_cancel_replace_ts_ms[symbol] = deque()
            self._objective_reentry_ts_ms[symbol] = deque()
            self._position_qty[symbol] = Decimal("0")
            self._last_close_ts[symbol] = 0
            asset_cfg = self._mr_config.assets.get(symbol)
            if isinstance(asset_cfg, dict):
                raise TypeError(
                    "mean_reversion.assets must contain typed MRAssetConfig values, got dict")

            # Start with base config
            config = MRStrategyConfig()
            config.bb_window = base_strat_cfg.bb_window
            config.bb_num_std = base_strat_cfg.bb_num_std
            config.atr_window = base_strat_cfg.atr_window
            config.rsi_window = base_strat_cfg.rsi_window
            config.min_bars = base_strat_cfg.min_bars
            config.min_bb_width = Decimal(str(base_strat_cfg.min_bb_width))
            config.max_bb_width = Decimal(str(base_strat_cfg.max_bb_width))
            config.entry_threshold = Decimal(
                str(base_strat_cfg.entry_threshold))
            config.rsi_oversold = Decimal(str(base_strat_cfg.rsi_oversold))
            config.rsi_overbought = Decimal(str(base_strat_cfg.rsi_overbought))
            config.sl_atr_mult = Decimal(str(base_strat_cfg.sl_atr_mult))
            config.tp_to_mid = base_strat_cfg.tp_to_mid
            config.cooldown_sec = base_strat_cfg.cooldown_sec
            # Tier D: confidence scalars from Pydantic SSOT
            config.confidence_base = _decimal_attr(
                base_strat_cfg, "confidence_base", "0.5")
            config.confidence_bb_slope = _decimal_attr(
                base_strat_cfg, "confidence_bb_slope", "2.0")
            config.confidence_rsi_bonus = _decimal_attr(
                base_strat_cfg, "confidence_rsi_bonus", "0.2")

            # Allowed regimes precedence:
            # global default -> per-asset -> per-asset strategy override (if present)
            config.allowed_regimes = list(self._mr_config.allowed_regimes)
            if asset_cfg is not None:
                config.allowed_regimes = list(asset_cfg.allowed_regimes)

            # Apply asset-specific overrides
            if asset_cfg is not None and hasattr(asset_cfg, "strategy") and asset_cfg.strategy is not None:
                strat_override = asset_cfg.strategy
                # Check for overrides
                if strat_override.bb_window is not None:
                    config.bb_window = strat_override.bb_window
                if strat_override.bb_num_std is not None:
                    config.bb_num_std = strat_override.bb_num_std
                if strat_override.min_bb_width is not None:
                    config.min_bb_width = Decimal(
                        str(strat_override.min_bb_width))
                if strat_override.flat_low_short_min_bb_width is not None:
                    config.flat_low_short_min_bb_width = Decimal(
                        str(strat_override.flat_low_short_min_bb_width))
                if strat_override.squeeze_expansion_veto is not None:
                    config.squeeze_expansion_veto = _runtime_squeeze_expansion_veto(
                        strat_override.squeeze_expansion_veto
                    )
                if strat_override.momentum_separation_veto is not None:
                    config.momentum_separation_veto = _runtime_momentum_separation_veto(
                        strat_override.momentum_separation_veto
                    )
                if strat_override.entry_threshold is not None:
                    config.entry_threshold = Decimal(
                        str(strat_override.entry_threshold))
                if strat_override.tp_to_mid is not None:
                    config.tp_to_mid = bool(strat_override.tp_to_mid)
                if strat_override.cooldown_sec is not None:
                    config.cooldown_sec = strat_override.cooldown_sec
                if strat_override.sl_atr_mult is not None:
                    config.sl_atr_mult = Decimal(
                        str(strat_override.sl_atr_mult))
                if strat_override.allowed_regimes is not None:
                    config.allowed_regimes = list(
                        strat_override.allowed_regimes)
                # Wire sl_buffer_pct and tp_buffer_pct from YAML
                if strat_override.sl_buffer_pct is not None:
                    config.sl_buffer_pct = Decimal(
                        str(strat_override.sl_buffer_pct))
                if strat_override.tp_buffer_pct is not None:
                    config.tp_buffer_pct = Decimal(
                        str(strat_override.tp_buffer_pct))
                # Tier D: per-asset confidence overrides
                if strat_override.confidence_base is not None:
                    config.confidence_base = _decimal_attr(
                        strat_override, "confidence_base", "0.5")
                if strat_override.confidence_bb_slope is not None:
                    config.confidence_bb_slope = _decimal_attr(
                        strat_override, "confidence_bb_slope", "2.0")
                if strat_override.confidence_rsi_bonus is not None:
                    config.confidence_rsi_bonus = _decimal_attr(
                        strat_override, "confidence_rsi_bonus", "0.2")

            self._strategies[symbol] = MeanReversion1mStrategy(
                config=config,
                timeframe_sec=timeframe_sec,
                regime_sizing=regime_sizing,
                regime_thresholds=flat_regime_thresholds,
            )
            self.logger.info(
                f"[{symbol}] Initialized MR Strategy (BB={config.bb_window}, W={config.min_bb_width})")

    @property
    def enabled(self) -> bool:
        """Check if MR handler is enabled."""
        return self._enabled

    def is_symbol_enabled(self, symbol: str) -> bool:
        """Check if MR is enabled for specific symbol."""
        return self._enabled and symbol in self._enabled_symbols

    # ── Vector 1: Microstructure Veto ────────────────────────────────────────

    def _check_microstructure_veto(
        self,
        symbol: str,
        signal_side: str,
        bar: Any,
    ) -> tuple[bool, str]:
        """Evaluate microstructure veto overlay for an actionable MR signal.

        Returns:
            (allowed, reason):
                allowed=True  → signal may proceed
                allowed=False → signal is vetoed (reason explains why)

        Logic (bivariate):
            1. If veto not configured/enabled for this symbol → ALLOW
            2. Extract TFI from cached features → missing → fail-closed (block)
            3. Update TFI EMA → not enough bars → BLOCK with NOT_READY
            4. If smoothed TFI is NOT adverse → ALLOW (no flow problem)
            5. If OBI confirm enabled, check OBI → missing → fail-closed
            6. Measure price reaction (continuation vs absorption):
               - Toxic continuation (adverse price move) → BLOCK
               - Absorption (wick/rebound evidence) → ALLOW
               - Neutral → BLOCK (conservative)
        """
        veto_cfg = self._microstructure_veto_configs.get(symbol)
        if veto_cfg is None:
            return True, ""

        # --- Extract TFI from cached features ---
        features = self._last_cmd_features.get(symbol, {})
        tfi_raw = features.get("tfi")
        if tfi_raw is None:
            return False, "MICROSTRUCTURE_VETO:TFI_MISSING"

        try:
            tfi_val = float(tfi_raw)
        except (ValueError, TypeError):
            return False, "MICROSTRUCTURE_VETO:TFI_INVALID"

        # --- Update TFI EMA ---
        prev_ema = self._tfi_ema.get(symbol)
        alpha = 2.0 / (veto_cfg.tfi_ema_span + 1)
        if prev_ema is None:
            smoothed_tfi = tfi_val
        else:
            smoothed_tfi = alpha * tfi_val + (1.0 - alpha) * prev_ema
        self._tfi_ema[symbol] = smoothed_tfi
        self._tfi_bar_count[symbol] = self._tfi_bar_count.get(symbol, 0) + 1

        # --- Readiness check (warmup) ---
        if self._tfi_bar_count[symbol] < veto_cfg.readiness_min_bars:
            return False, "MICROSTRUCTURE_VETO:NOT_READY"

        # --- Determine adverse direction ---
        # LONG signal: adverse flow = strongly negative TFI (selling pressure)
        # SHORT signal: adverse flow = strongly positive TFI (buying pressure)
        if signal_side == "LONG":
            is_adverse_tfi = smoothed_tfi < -veto_cfg.tfi_adverse_threshold
        else:
            is_adverse_tfi = smoothed_tfi > veto_cfg.tfi_adverse_threshold

        if not is_adverse_tfi:
            return True, ""

        # --- OBI confirmation (optional, never sole driver) ---
        if veto_cfg.obi_confirm_enabled:
            obi_raw = features.get("obi")
            if obi_raw is None:
                return False, "MICROSTRUCTURE_VETO:OBI_MISSING"
            try:
                obi_val = float(obi_raw)
            except (ValueError, TypeError):
                return False, "MICROSTRUCTURE_VETO:OBI_INVALID"

            if signal_side == "LONG":
                is_adverse_obi = obi_val < -veto_cfg.obi_adverse_threshold
            else:
                is_adverse_obi = obi_val > veto_cfg.obi_adverse_threshold

            if not is_adverse_obi:
                # Flow is adverse but book does NOT confirm → not toxic
                return True, ""

        # --- Price reaction: continuation vs absorption ---
        # Use bar geometry (wick ratio) and recent return from features
        try:
            bar_high = float(getattr(bar, "high", 0))
            bar_low = float(getattr(bar, "low", 0))
            bar_open = float(getattr(bar, "open", 0))
            bar_close = float(getattr(bar, "close", 0))
        except (ValueError, TypeError):
            return False, "MICROSTRUCTURE_VETO:BAR_INVALID"

        bar_range = bar_high - bar_low
        if bar_range <= 0:
            # Zero-range bar: no price information → conservative block
            return False, "MICROSTRUCTURE_VETO:TOXIC_FLOW_ZERO_RANGE"

        # Wick ratio: how much of the bar is wick (rejection) vs body
        if signal_side == "LONG":
            # For LONG: lower wick = absorption of selling pressure
            lower_wick = min(bar_open, bar_close) - bar_low
            wick_ratio = lower_wick / bar_range
        else:
            # For SHORT: upper wick = absorption of buying pressure
            upper_wick = bar_high - max(bar_open, bar_close)
            wick_ratio = upper_wick / bar_range

        # Price rebound (favorable move):
        # MR-V1-WIRING: Read price_motion from dedicated cache (top-level CMD field)
        price_motion = self._last_cmd_price_motion.get(symbol, {})
        lookback = veto_cfg.price_reaction_lookback_sec
        # Select the closest matching return horizon
        ret_key = "ret_60s"
        if lookback <= 15:
            ret_key = "ret_10s"
        elif lookback >= 250:
            ret_key = "ret_300s"
        recent_ret = None
        if isinstance(price_motion, dict):
            recent_ret = price_motion.get(ret_key)

        # Determine absorption vs continuation
        has_absorption_wick = wick_ratio >= veto_cfg.absorption_wick_ratio_min

        has_favorable_rebound = False
        has_adverse_continuation = False
        if recent_ret is not None:
            try:
                ret_val = float(recent_ret)
                if signal_side == "LONG":
                    # For LONG: positive return = favorable rebound
                    has_favorable_rebound = ret_val >= veto_cfg.absorption_rebound_threshold
                    has_adverse_continuation = ret_val <= -veto_cfg.price_continuation_threshold
                else:
                    # For SHORT: negative return = favorable rebound
                    has_favorable_rebound = ret_val <= -veto_cfg.absorption_rebound_threshold
                    has_adverse_continuation = ret_val >= veto_cfg.price_continuation_threshold
            except (ValueError, TypeError):
                pass

        # Absorption override: adverse flow absorbed by market
        if has_absorption_wick or has_favorable_rebound:
            return True, ""

        # Toxic continuation: adverse flow + adverse price direction
        if has_adverse_continuation:
            return False, "MICROSTRUCTURE_VETO:TOXIC_FLOW_CONTINUATION"

        # Ambiguous: flow is adverse, no absorption evidence, no clear continuation
        # Conservative: block (fail-closed for unclear situations)
        return False, "MICROSTRUCTURE_VETO:TOXIC_FLOW_AMBIGUOUS"

    # ── Vector 2: Directional Bias Threshold Modulation ──────────────────────

    def _apply_directional_bias(
        self,
        symbol: str,
        strategy: "MeanReversion1mStrategy",
    ) -> None:
        """Compute and set effective long/short thresholds from funding rate.

        Sets transient overrides on strategy.config.entry_threshold_long/short.
        If directional_bias is not configured or funding is missing, clears
        the overrides (strategy falls back to legacy symmetric entry_threshold).

        No fail-closed on missing funding — graceful degradation to static split.
        """
        bias_cfg = self._directional_bias_configs.get(symbol)
        if bias_cfg is None:
            # Not configured → clear any previous overrides
            strategy.config.entry_threshold_long = None
            strategy.config.entry_threshold_short = None
            return

        # Extract funding rate from cached features
        features = self._last_cmd_features.get(symbol, {})
        funding_raw = features.get("funding_rate")

        if funding_raw is None:
            # Missing funding → static split thresholds (graceful degradation)
            strategy.config.entry_threshold_long = Decimal(
                str(bias_cfg.base_long_threshold))
            strategy.config.entry_threshold_short = Decimal(
                str(bias_cfg.base_short_threshold))
            return

        try:
            funding_rate = float(funding_raw)
        except (ValueError, TypeError):
            # Invalid funding → degrade to static
            strategy.config.entry_threshold_long = Decimal(
                str(bias_cfg.base_long_threshold))
            strategy.config.entry_threshold_short = Decimal(
                str(bias_cfg.base_short_threshold))
            return

        # Normalize funding: clamp to [-1, 1]
        norm_funding = funding_rate / bias_cfg.funding_normalization_scale
        norm_funding = max(-1.0, min(1.0, norm_funding))

        # Deadband: suppress noise
        if abs(norm_funding) < bias_cfg.funding_deadband:
            norm_funding = 0.0

        # Compute effective thresholds:
        # positive funding → longs pay → fade the crowd →
        #   LONG harder (lower threshold = needs more extreme pct_b < threshold),
        #   SHORT easier (higher threshold = trigger boundary 1-threshold drops)
        eff_long = bias_cfg.base_long_threshold - \
            norm_funding * bias_cfg.funding_shift_magnitude
        eff_short = bias_cfg.base_short_threshold + \
            norm_funding * bias_cfg.funding_shift_magnitude

        # Clamp to legal range
        eff_long = max(bias_cfg.threshold_clamp_min, min(
            bias_cfg.threshold_clamp_max, eff_long))
        eff_short = max(bias_cfg.threshold_clamp_min, min(
            bias_cfg.threshold_clamp_max, eff_short))

        strategy.config.entry_threshold_long = Decimal(str(round(eff_long, 6)))
        strategy.config.entry_threshold_short = Decimal(
            str(round(eff_short, 6)))

    def _emit_strategy_blocked(
        self,
        *,
        symbol: str,
        reason_code: str,
        reason: str,
        context: str,
        details: dict | None = None,
        why_chain: list[str] | None = None,
        throttle_ms: int = 10_000,
    ) -> None:
        """Emit a throttled EVT:STRATEGY_DECISION_BLOCKED artifact for ``symbol``.

        Throttling is keyed by ``symbol`` and ``reason_code`` so noisy repeated
        guards do not spam identical blocked events on every decision pass.
        """
        # DET-BT-09: Use get_clock() for deterministic backtest
        now_ms = get_clock().now_ms()
        last_reason = self._last_block_reason.get(symbol)
        last_ts = self._last_block_ts_ms.get(symbol, 0)
        if last_reason == reason_code and (now_ms - last_ts) < int(throttle_ms):
            return
        self._last_block_reason[symbol] = reason_code
        self._last_block_ts_ms[symbol] = now_ms

        payload = write_strategy_decision_blocked(
            strategy_id="mean_reversion",
            symbol=symbol,
            reason_code=str(reason_code),
            reason=str(reason),
            context=str(context),
            src="mean_reversion_handler:_emit_strategy_blocked",
            ts_ms=now_ms,
            why=context,
            why_chain=why_chain,
            details=details,
        )
        self.fsm.emit("EVT:STRATEGY_DECISION_BLOCKED",
                      payload, why=f"mr_blocked:{reason_code}")

    def on_regime(self, symbol: str, regime: str) -> None:
        """
        Update regime for symbol.
        """
        if not self._enabled:
            return

        strategy = self._strategies.get(symbol)
        if strategy:
            strategy.set_regime(symbol, regime)
            self.logger.debug(f"[{symbol}] MR regime updated: {regime}")

    def _log_bar(self, signal: MRSignal) -> None:
        """Log completed bar to dedicated TSV/JSONL logger."""
        if not self.bar_logger or not signal.bar:
            return

        try:
            # Extract reason from 'why'
            why = str(getattr(signal, "why", "") or "")
            why_norm = why[len("neutral:"):] if why.startswith(
                "neutral:") else why

            # Build context
            context = {
                # DET-BT-09: Use get_clock() for deterministic backtest
                "generated_ts_ms": get_clock().now_ms(),
                "signal_type": signal.signal_type.name,
                "reason": why_norm,
                "regime": signal.flat_regime.name if signal.flat_regime else (self._per_symbol_regime.get(signal.symbol) or "UNKNOWN"),
                "bb": {
                    "upper": str(signal.bb.upper) if signal.bb else None,
                    "mid": str(signal.bb.mid) if signal.bb else None,
                    "lower": str(signal.bb.lower) if signal.bb else None,
                    "width": str(signal.bb.width) if signal.bb else None,
                    "pct_b": str(signal.bb.pct_b) if signal.bb else None,
                },
                "rsi": float(signal.rsi) if signal.rsi is not None else None,
                "atr": float(signal.atr) if signal.atr is not None else None,
                "mr_params": {
                    "sizing_mult": float(signal.mr_params.sizing_mult) if signal.mr_params else 1.0,
                    "stop_mult": float(signal.mr_params.stop_mult) if signal.mr_params else 1.0,
                    "target_mult": float(signal.mr_params.target_mult) if signal.mr_params else 1.0,
                } if signal.mr_params else None,
                "config": signal.config_params
            }

            self.bar_logger.log_bar(signal.symbol, signal.bar, context)

        except Exception as e:
            self._stats["bar_logging_errors"] += 1
            if self._stats["bar_logging_errors"] <= 5:
                self.logger.warning(
                    f"Failed to log bar for {signal.symbol}: {e}")

    def _emit_signal(
        self,
        signal: MRSignal,
        *,
        bar_identity: CanonicalBarIdentity | None = None,
        replay_identity: CanonicalReplayIdentity | None = None,
        gap_status: RuntimeGapStatus | None = None,
        warmup_readiness: Dict[str, Any] | None = None,
        regime_ctx: Dict[str, Any] | None = None,
    ) -> None:
        """Emit EVT:STRATEGY_SIGNAL_PRODUCED after runtime overlays are applied.

        This method enriches the raw strategy signal with runtime readiness,
        restore state, gap status, and optional objective-engine scoring. When
        objective evaluation blocks or fails closed, it emits a blocked artifact
        and returns without emitting a strategy signal.
        """
        symbol = signal.symbol

        # Track signal
        self._signal_counts[symbol] = (
            self._signal_counts[symbol] if symbol in self._signal_counts else 0) + 1
        # DET-BT-09: Use get_clock() for deterministic backtest
        self._last_signal_time[symbol] = get_clock().now_sec()

        self.logger.info(
            f"[{symbol}] MR Signal: {signal.signal_type.name} "
            f"confidence={signal.confidence:.2f} "
            f"entry={signal.entry_price} stop={signal.stop_price} target={signal.target_price} "
            f"why={signal.why}"
        )

        # DET-BT-13: Use deterministic rid from bar timestamp + symbol + signal type (not random uuid)
        import hashlib
        ts_ms = get_clock().now_ms()
        rid_raw = f"{symbol}:{signal.signal_type.name}:{ts_ms}"
        rid = f"rid-{hashlib.md5(rid_raw.encode()).hexdigest()[:16]}"
        side = signal.side  # "BUY" or "SELL"
        # NOTE (SIZING-MARGIN-FIRST-SSOT-02):
        # Mean Reversion does NOT own sizing. DecisionMaking computes qty from:
        # instruments.<SYM>.sizing.margin_pct + instruments.<SYM>.execution.target_leverage.

        # P0-1: Get cached features for this symbol (from last CMD:PROCESS_STRATEGY)
        cached_features = self._last_cmd_features.get(symbol, {})
        restore_snapshot = self.get_runtime_analytics_restore_snapshot(symbol)
        ts_int = int(signal.timestamp_ms)

        # ── Restore specs ────────────────────────────────────────────
        restore_specs: tuple[RestoreScopeSpec, ...] = ()
        if restore_snapshot is not None:
            restore_specs = (
                RestoreScopeSpec(
                    restore_scope=RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
                    target_scope=RuntimeReadinessScope.EXECUTION_CONTEXT_READY.value,
                    mode="restore_only",
                    source="execution_position:startup_restore",
                    evidence_ref=rid,
                ),
                RestoreScopeSpec(
                    restore_scope=RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_CACHE,
                    target_scope=RuntimeReadinessScope.MICROSTRUCTURE_READY.value,
                    mode="merge_live_first",
                    source="feature_engineering:startup_restore",
                    evidence_ref=rid,
                    live_evidence_present=True,
                ),
                RestoreScopeSpec(
                    restore_scope=RuntimeAnalyticsRestoreScope.REGIME_DETECTOR_STATE,
                    target_scope=RuntimeReadinessScope.REGIME_READY.value,
                    mode="merge_live_first",
                    source="regime_detector:startup_restore",
                    evidence_ref=rid,
                    live_evidence_present=True,
                ),
                RestoreScopeSpec(
                    restore_scope=RuntimeAnalyticsRestoreScope.STRATEGY_LOCAL_STATE,
                    target_scope=RuntimeReadinessScope.STRATEGY_READY_PER_SYMBOL.value,
                    mode="merge_live_first",
                    source="decision_making:mean_reversion",
                    evidence_ref=rid,
                    restored_why=("signal_emitted",),
                    live_evidence_present=True,
                ),
            )

        builder_result = build_runtime_readiness(
            RuntimeReadinessBuildRequest(
                strategy_id="mean_reversion",
                symbol=symbol,
                updated_at=ts_int,
                source_prefix="decision_making:mean_reversion",
                gap_status=gap_status,
                restore_snapshot=restore_snapshot,
                bar_identity=bar_identity,
                base_can_open_new_risk=True,
                warmup_ready=isinstance(warmup_readiness, dict) and bool(
                    warmup_readiness.get("full_ready")),
                regime_present=signal.flat_regime is not None,
                regime_ts_ms=ts_int,
                regime_ready_why="flat_regime_present",
                regime_missing_why="flat_regime_missing",
                regime_live_source="regime_detector:payload_bridge",
                regime_ready_evidence_ref=f"flat_regime:{symbol}:{ts_int}",
                regime_missing_evidence_ref=f"flat_regime:{symbol}:{ts_int}",
                signal_evidence_ref=rid,
                strategy_ready_why=("signal_emitted",),
                restore_specs=restore_specs,
            ),
        )
        runtime_permissions = builder_result.permissions
        runtime_snapshot = builder_result.snapshot
        blocking_reason_chain = list(builder_result.blocking_reason_chain)
        objective_trace = None
        emitted_score = float(signal.confidence)
        resolved_regime_name = ""
        resolved_regime_ts_ms = 0
        resolved_regime_confidence = None
        if isinstance(regime_ctx, dict):
            resolved_regime_name = str(regime_ctx.get("regime") or "")
            try:
                resolved_regime_ts_ms = int(
                    regime_ctx.get("regime_event_ts_ms")
                    or regime_ctx.get("regime_ts_ms")
                    or 0
                )
            except (TypeError, ValueError):
                resolved_regime_ts_ms = 0
            resolved_regime_confidence = regime_ctx.get("confidence")
        domain_cfg = getattr(
            getattr(self.config, "domains", None), "objective_engine", None)
        mr_cfg = getattr(getattr(self.config, "strategies",
                         None), "mean_reversion", None)
        objective_cfg = getattr(mr_cfg, "objective",
                                None) if mr_cfg is not None else None

        # ── Objective Engine Integration (shared evaluator) ──
        _obj_enabled = (
            domain_cfg is not None
            and objective_cfg is not None
            and bool(getattr(domain_cfg, "enabled", False))
            and bool(getattr(objective_cfg, "enabled", False))
        )
        if _obj_enabled:
            from apps.reference.domains.decision_making.gates.objective_gate_evaluator import (
                ObjectiveBehaviorAdapter,
                ObjectiveGateRequest,
                ObjectiveGateStatus,
                ObjectiveSignalAdapter,
                ObjectiveSizingAdapter,
                ObjectiveStructureAdapter,
                evaluate_objective_gate,
            )

            features_for_objective = dict(cached_features or {})
            features_for_objective.setdefault("price", float(signal.price))
            features_for_objective.setdefault("atr", float(signal.atr))

            readiness_source = (
                warmup_readiness.get("ready")
                if isinstance(warmup_readiness, dict) and isinstance(warmup_readiness.get("ready"), dict)
                else warmup_readiness
            )
            regime_name = resolved_regime_name or str(
                signal.flat_regime.name if signal.flat_regime else "")
            regime_ts_ms = int(
                resolved_regime_ts_ms or self._regime_event_ts_ms.get(
                    symbol, 0) or self._regime_ts_ms.get(symbol, 0) or 0
            )
            regime_confidence = (
                resolved_regime_confidence
                if resolved_regime_confidence is not None
                else self._regime_confidence.get(symbol)
            )

            if regime_confidence is None:
                if getattr(domain_cfg.data_requirements, "strict_fail_closed", True):
                    self._objective_blocked_ts_ms.setdefault(
                        symbol, deque()).append(int(signal.timestamp_ms))
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="OBJECTIVE_ENGINE_FAIL_CLOSED",
                        reason="DECISION",
                        context="mean_reversion_handler:objective_engine",
                        details={
                            "error": "OBJECTIVE_REGIME_CONFIDENCE_MISSING"},
                        why_chain=["OBJECTIVE_ENGINE",
                                   "FAIL_CLOSED",
                                   "OBJECTIVE_REGIME_CONFIDENCE_MISSING"],
                    )
                    return
            else:
                obj_gate_result = evaluate_objective_gate(ObjectiveGateRequest(
                    strategy_id="mean_reversion",
                    symbol=symbol,
                    config=self.config,
                    domain_cfg=domain_cfg,
                    strategy_cfg=objective_cfg,
                    market_features=features_for_objective,
                    signal=ObjectiveSignalAdapter(
                        signal_score=float(signal.confidence),
                        signal_direction=1 if str(
                            side).upper() == "BUY" else -1,
                        regime_name=regime_name,
                        regime_ts_ms=regime_ts_ms,
                        regime_confidence=float(regime_confidence),
                        readiness_source=readiness_source if isinstance(
                            readiness_source, dict) else {},
                        active_threshold=float(
                            self._strategies[symbol].config.entry_threshold),
                    ),
                    structure=ObjectiveStructureAdapter(
                        mode="price_ctx",
                        entry_price=Decimal(
                            str(signal.entry_price)) if signal.entry_price is not None else None,
                        stop_price=Decimal(
                            str(signal.stop_price)) if signal.stop_price is not None else None,
                        target_price=Decimal(
                            str(signal.target_price)) if signal.target_price is not None else None,
                        atr=Decimal(str(signal.atr)
                                    ) if signal.atr is not None else None,
                    ),
                    sizing=ObjectiveSizingAdapter(
                        side=str(side).upper(),
                        entry_price=Decimal(
                            str(signal.entry_price)) if signal.entry_price is not None else Decimal("0"),
                        features_payload=features_for_objective,
                    ),
                    behavior=ObjectiveBehaviorAdapter(
                        now_ms=int(signal.timestamp_ms),
                        cancel_replace_ts_ms=self._objective_cancel_replace_ts_ms.setdefault(
                            symbol, deque()),
                        blocked_intent_ts_ms=self._objective_blocked_ts_ms.setdefault(
                            symbol, deque()),
                        reentry_ts_ms=self._objective_reentry_ts_ms.setdefault(
                            symbol, deque()),
                    ),
                    portfolio=self._latest_portfolio,
                    exposure_summary=self._latest_exposure_summary,
                    position_queries=self._position_queries,
                ))

                if obj_gate_result.status == ObjectiveGateStatus.PASSED:
                    objective_trace = obj_gate_result.trace_payload
                    emitted_score = float(
                        obj_gate_result.objective_score.objective_score)
                elif obj_gate_result.status == ObjectiveGateStatus.GATE_BLOCKED:
                    obj_score = obj_gate_result.objective_score
                    self._objective_blocked_ts_ms.setdefault(
                        symbol, deque()).append(int(signal.timestamp_ms))
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="OBJECTIVE_GATE_BLOCKED",
                        reason="DECISION",
                        context="mean_reversion_handler:objective_engine",
                        details={
                            "objective_score": obj_score.objective_score,
                            "objective_multiplier": obj_score.multiplier,
                            "objective_components": obj_score.components,
                            "objective_raw_metrics": obj_score.raw_metrics,
                            "block_reason": obj_score.block_reason,
                        },
                        why_chain=["OBJECTIVE_ENGINE", str(
                            obj_score.block_reason or "GATE_BLOCKED")],
                    )
                    return
                elif obj_gate_result.status == ObjectiveGateStatus.PRECONDITION_FAILED:
                    if getattr(domain_cfg.data_requirements, "strict_fail_closed", True):
                        self._objective_blocked_ts_ms.setdefault(
                            symbol, deque()).append(int(signal.timestamp_ms))
                        self._emit_strategy_blocked(
                            symbol=symbol,
                            reason_code="OBJECTIVE_ENGINE_FAIL_CLOSED",
                            reason="DECISION",
                            context="mean_reversion_handler:objective_engine",
                            details={
                                "error": obj_gate_result.precondition_code},
                            why_chain=["OBJECTIVE_ENGINE",
                                       "FAIL_CLOSED", str(obj_gate_result.precondition_code)],
                        )
                        return
                elif obj_gate_result.status == ObjectiveGateStatus.EVALUATION_ERROR:
                    if getattr(domain_cfg.data_requirements, "strict_fail_closed", True):
                        self._objective_blocked_ts_ms.setdefault(
                            symbol, deque()).append(int(signal.timestamp_ms))
                        self._emit_strategy_blocked(
                            symbol=symbol,
                            reason_code="OBJECTIVE_ENGINE_FAIL_CLOSED",
                            reason="DECISION",
                            context="mean_reversion_handler:objective_engine",
                            details={"error": obj_gate_result.error},
                            why_chain=["OBJECTIVE_ENGINE",
                                       "FAIL_CLOSED", str(obj_gate_result.error)],
                        )
                        return
                # DISABLED status from evaluator: no-op (shouldn't happen since we checked enabled above)

        pld = {
            "schema_version": 1,
            "strategy_id": "mean_reversion",
            "symbol": symbol,
            "tf_sec": self.timeframe_sec,
            "side": side,
            "bar_close_ts": (
                int(bar_identity.bar_end_ts_ms)
                if bar_identity is not None
                else int(signal.bar.end_ts_ms if signal.bar else 0)
            ),
            "readiness": {"warmup_ok": True},
            "runtime_permissions": runtime_permissions.to_payload(),
            "runtime_readiness": runtime_snapshot.to_payload(),
            "score": emitted_score,
            "why": signal.why,
            "ts_ms": int(signal.timestamp_ms),
            "rid": rid,
            "why_chain": [signal.why],
            "source_mode": (
                bar_identity.source_mode.value
                if bar_identity is not None
                else RuntimeBarSourceMode.LIVE.value
            ),
            "price_ctx": {
                "entry_price": str(signal.entry_price),
                "stop_price": str(signal.stop_price) if signal.stop_price else None,
                "target_price": str(signal.target_price) if signal.target_price else None,
            },
            "regime": signal.flat_regime.name if signal.flat_regime else "UNKNOWN",
            # P0-1: Propagate volatility/liquidity from cmd.features for EntryPlan compatibility
            "volatility": cached_features.get("volatility"),
            "liquidity": cached_features.get("liquidity"),
            "mr_params": {
                "sizing_mult": float(signal.mr_params.sizing_mult) if signal.mr_params else 1.0,
                "stop_mult": float(signal.mr_params.stop_mult) if signal.mr_params else 1.0,
                "target_mult": float(signal.mr_params.target_mult) if signal.mr_params else 1.0,
            },
            "scoring": {
                "score": emitted_score,
                "objective": objective_trace,
                "regime": signal.flat_regime.name if signal.flat_regime else "UNKNOWN",
            },
        }
        if isinstance(regime_ctx, dict) and regime_ctx:
            pld["regime_ctx"] = dict(regime_ctx)
        if bar_identity is not None:
            pld["bar_identity"] = bar_identity.to_payload()
            pld["close_boundary_ts_ms"] = int(
                bar_identity.close_boundary_ts_ms)
        if replay_identity is not None:
            pld["replay_identity"] = replay_identity.to_payload()
            pld["replay_generation"] = int(replay_identity.replay_generation)
        if gap_status is not None:
            attach_gap_status_payload(
                pld, gap=gap_status, attach_nested_bar=False)
        if restore_snapshot is not None:
            pld["analytics_restore"] = restore_snapshot.to_payload()

        self.fsm.emit(
            "EVT:STRATEGY_SIGNAL_PRODUCED",
            payload=pld,
            why=f"strategy_signal:mean_reversion:{signal.signal_type.name}",
            data_ref=[f"mr_signal_{rid}"],
        )
        self._stats["signals_emitted"] += 1

        bb = signal.bb
        self.mlog.info(
            "MR_SIGNAL %s",
            json.dumps(
                {
                    "symbol": symbol,
                    "side": side,
                    "confidence": float(signal.confidence),
                    "ts_ms": int(signal.timestamp_ms),
                    "entry_price": str(signal.entry_price) if signal.entry_price is not None else None,
                    "stop_price": str(signal.stop_price) if signal.stop_price is not None else None,
                    "target_price": str(signal.target_price) if signal.target_price is not None else None,
                    "flat_regime": signal.flat_regime.name if signal.flat_regime else None,
                    "why": signal.why,
                    "bb_upper": str(bb.upper) if bb else None,
                    "bb_mid": str(bb.mid) if bb else None,
                    "bb_lower": str(bb.lower) if bb else None,
                    "bb_width": float(bb.width) if bb else None,
                    "pct_b": float(bb.pct_b) if bb else None,
                    "atr": str(signal.atr) if signal.atr is not None else None,
                    "mr_params": pld.get("mr_params"),
                    "counters": dict(self._stats),
                },
                ensure_ascii=False,
            ),
        )

        self.logger.info(
            f"[{symbol}] EVT:STRATEGY_SIGNAL_PRODUCED emitted: {side} @ {signal.entry_price}"
        )

        # TAP LOG: MR signal emitted
        log_entry = {
            "symbol": symbol,
            "tf_sec": self.timeframe_sec,
            "bar_end_ts_ms": signal.bar.end_ts_ms if signal.bar else 0,
            "bar_id": 0,
            "seq": getattr(self, 'seq_counter', 0),
            "source": "mr_signal_emitted",
            "why": signal.why
        }
        print(json.dumps(log_entry), flush=True)
        self.seq_counter = getattr(self, 'seq_counter', 0) + 1

    def _on_regime_detected(self, event: Message) -> None:
        try:
            pld = event.pld or {}
            if not is_structural_regime_payload(pld):
                return
            if isinstance(pld, dict):
                symbol = str(pld.get("symbol") or "")
                regime = normalize_structural_regime_label(
                    pld.get("regime") or pld.get("overall_regime") or "")
            else:
                symbol = str(getattr(pld, "symbol", "") or "")
                regime = normalize_structural_regime_label(
                    aget(pld, "regime", "") or aget(pld, "overall_regime", "") or "")

            if not symbol or symbol not in self._enabled_symbols:
                return
            if not regime:
                return
            self._per_symbol_regime[symbol] = regime
            confidence_raw = pld.get("confidence") if isinstance(
                pld, dict) else getattr(pld, "confidence", None)
            if confidence_raw is not None:
                self._regime_confidence[symbol] = float(confidence_raw)
            ts_ms = normalize_ts_ms(pld.get("ts_ms") if isinstance(
                pld, dict) else getattr(pld, "ts_ms", None))
            if ts_ms <= 0:
                ts_ms = normalize_ts_ms(pld.get("ts") if isinstance(
                    pld, dict) else getattr(pld, "ts", None))
            if ts_ms > 0:
                self._regime_ts_ms[symbol] = int(ts_ms)
            provenance_payload = pld if isinstance(pld, dict) else {
                "regime": regime,
                "ts_ms": ts_ms,
                "bar_close_ts_ms": getattr(pld, "bar_close_ts_ms", None),
            }
            provenance = build_regime_provenance_fields(
                provenance_payload,
                bar_close_ts_ms=(
                    pld.get("bar_close_ts_ms")
                    if isinstance(pld, dict)
                    else getattr(pld, "bar_close_ts_ms", None)
                ),
            )
            if provenance.get("regime_event_ts_ms") is not None:
                self._regime_event_ts_ms[symbol] = int(
                    provenance.get("regime_event_ts_ms")
                )
            self._regime_source[symbol] = str(
                provenance.get("regime_source") or ""
            )
            self._regime_same_bar[symbol] = provenance.get("regime_same_bar")
            self._regime_provenance_reason[symbol] = str(
                provenance.get("regime_provenance_reason") or ""
            )
            self.on_regime(symbol, regime)
        except Exception as e:
            self._stats["regime_processing_errors"] += 1
            self.logger.warning(
                f"MRHandler: failed to process EVT:REGIME_DETECTED: {e}",
                exc_info=True,
            )

    def _on_trade_executed(self, event: Message) -> None:
        """Update local signed position state from execution fills.

        The handler uses this lightweight position view only for objective and
        re-entry bookkeeping; canonical portfolio truth still comes from the
        portfolio/exposure events handled elsewhere.
        """
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return
        symbol = str(pld.get("symbol") or "")
        if symbol not in self._enabled_symbols:
            return
        try:
            qty = Decimal(str(pld.get("quantity") or "0"))
        except Exception:
            return
        if qty == 0:
            return
        side = str(pld.get("side") or "").lower()
        if qty > 0 and side == "sell":
            qty = -qty
        if qty < 0 and side == "buy":
            qty = -qty
        prev = self._position_qty.get(symbol, Decimal("0"))
        now = prev + qty
        if prev == Decimal("0") and now != Decimal("0") and int(self._last_close_ts.get(symbol, 0) or 0) > 0:
            self._objective_reentry_ts_ms.setdefault(
                symbol, deque()).append(get_clock().now_ms())
        if abs(now) < Decimal("1e-9"):
            now = Decimal("0")
            self._last_close_ts[symbol] = get_clock().now_ms()
        self._position_qty[symbol] = now

    def _on_portfolio_state_updated(self, event: Message) -> None:
        pld = event.pld or {}
        if isinstance(pld, dict):
            self._latest_portfolio = pld

    def _on_exposure_summary_updated(self, event: Message) -> None:
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return
        exposure_summary = pld.get("exposure_summary")
        if isinstance(exposure_summary, dict):
            self._latest_exposure_summary = exposure_summary

    def _on_order_state_changed(self, event: Message) -> None:
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return
        symbol = str(pld.get("symbol") or "")
        if symbol not in self._enabled_symbols:
            return
        status = str(pld.get("status") or pld.get("state") or "").upper()
        if status in ("CANCELED", "EXPIRED", "REJECTED"):
            self._objective_cancel_replace_ts_ms.setdefault(symbol, deque()).append(
                int(pld.get("ts_ms") or get_clock().now_ms())
            )

    def _on_trade_intent_rejected(self, event: Message) -> None:
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return
        if str(pld.get("strategy_id") or "") != "mean_reversion":
            return
        symbol = str(pld.get("symbol") or "")
        if symbol not in self._enabled_symbols:
            return
        self._objective_blocked_ts_ms.setdefault(symbol, deque()).append(
            int(pld.get("ts_ms") or get_clock().now_ms())
        )

    # ------------------------------------------------------------------
    # Clean-start execution restore upgrade (PROTECT_ONLY self-heal)
    # ------------------------------------------------------------------

    def _on_portfolio_clean_start_check(self, event: Message) -> None:
        """Upgrade COLD execution restore → RESTORED when *canonical*
        position-tracking state (PORTFOLIO_STATE_UPDATED) confirms zero
        open positions for handler-managed symbols.

        This intentionally listens to EVT:PORTFOLIO_STATE_UPDATED —
        the reconciled output of PositionTracking — instead of the raw
        EVT:ACCOUNT_UPDATE_RECEIVED, because the latter may carry a
        partial WebSocket delta (only *changed* positions) where an
        empty array means "no changes", not "no positions".

        Fail-closed: upgrade only if positions list is present and every
        managed symbol is absent from it (canonical zero position).
        """
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return

        positions_raw = pld.get("positions")
        if not isinstance(positions_raw, list):
            return  # fail-closed: missing positions payload

        ts_ms = int(pld.get("positions_last_ts_ms") or pld.get("ts") or 0)
        if ts_ms <= 0:
            ts_ms = get_clock().now_ms()

        # Build a set of symbols that have non-zero positions
        # PORTFOLIO_STATE_UPDATED uses 'net_position' (string) not 'positionAmt'
        active_symbols: set[str] = set()
        for pos in positions_raw:
            if not isinstance(pos, dict):
                continue
            sym = str(pos.get("symbol") or "").upper()
            try:
                qty = Decimal(str(pos.get("net_position") or "0"))
            except Exception:
                qty = Decimal("0")
            if abs(qty) > Decimal("1e-9"):
                active_symbols.add(sym)

        for symbol in self._enabled_symbols:
            sym_key = str(symbol).upper()
            if sym_key in active_symbols:
                continue  # has open position — no upgrade

            snapshot = self._analytics_restore_snapshots.get(sym_key)
            if snapshot is None:
                continue

            upgraded = upgrade_cold_execution_restore_if_clean_start(
                snapshot,
                updated_at=ts_ms,
                source="position_tracking:canonical_zero_positions",
                evidence_ref=f"portfolio_state:{sym_key}:{ts_ms}:zero_positions",
            )
            if upgraded is not None:
                self._analytics_restore_snapshots[sym_key] = upgraded
                self.logger.info(
                    "[CLEAN_START_UPGRADE] %s execution restore upgraded "
                    "COLD->RESTORED via canonical position-tracking "
                    "zero-positions confirmation (ts_ms=%d)",
                    sym_key,
                    ts_ms,
                )
                self.mlog.info(
                    "MR_CLEAN_START_UPGRADE %s",
                    json.dumps(
                        {
                            "symbol": sym_key,
                            "strategy_id": "mean_reversion",
                            "ts_ms": ts_ms,
                            "source": "canonical_zero_positions",
                            "prev_execution_state": "COLD",
                            "new_execution_state": "RESTORED",
                        },
                        ensure_ascii=False,
                    ),
                )

    def _on_features_calculated(self, event: Message) -> None:
        """Legacy direct-call feature cache hook.

        Current register() wiring does not subscribe EVT:FEATURES_CALCULATED for
        MR decisions; live processing caches features from CMD:PROCESS_STRATEGY.
        If this compatibility hook is called directly, it only updates the local
        feature and liquidity caches after timeframe validation.
        """
        if not self._enabled:
            return
        try:
            pld = event.pld or {}
            if isinstance(pld, dict):
                symbol = str(pld.get("symbol") or "")
                features = pld.get("features", {})
            else:
                symbol = str(getattr(pld, "symbol", "") or "")
                features = getattr(pld, "features", {}) or {}

            if not symbol or symbol not in self._enabled_symbols:
                return

            # TF guard
            tf_sec = pld.get("tf_sec")
            if tf_sec is None:
                self.logger.warning(
                    f"MR rejecting features for {symbol}: missing tf_sec")
                # TAP LOG: MR features rejected
                log_entry = {
                    "symbol": symbol,
                    "tf_sec": None,
                    "bar_end_ts_ms": pld.get("ts", 0),
                    "bar_id": f"{symbol}:None:{pld.get('ts', 0)}",
                    "seq": getattr(self, 'seq_counter', 0),
                    "source": "mr_features_rejected",
                    "why": "missing_tf"
                }
                print(json.dumps(log_entry), flush=True)
                return
            if tf_sec != self.timeframe_sec:
                self.logger.warning(
                    f"MR rejecting features for {symbol}: tf_sec {tf_sec} != {self.timeframe_sec}")
                # TAP LOG: MR features rejected
                log_entry = {
                    "symbol": symbol,
                    "tf_sec": tf_sec,
                    "bar_end_ts_ms": pld.get("ts", 0),
                    "bar_id": f"{symbol}:{tf_sec}:{pld.get('ts', 0)}",
                    "seq": getattr(self, 'seq_counter', 0),
                    "source": "mr_features_rejected",
                    "why": "tf_mismatch"
                }
                print(json.dumps(log_entry), flush=True)
                return

            # Keep the compatibility hook aligned with the CMD-path cache shape.
            self._last_cmd_features[symbol] = features

            # TAP LOG: MR accepted features
            log_entry = {
                "symbol": symbol,
                "tf_sec": self.timeframe_sec,
                "bar_end_ts_ms": pld.get("ts", 0),
                "bar_id": f"{symbol}:{self.timeframe_sec}:{pld.get('ts', 0)}",
                "seq": getattr(self, 'seq_counter', 0),
                "source": "mr_features_accepted",
                "why": "features_stored"
            }
            print(json.dumps(log_entry), flush=True)
            self.seq_counter = getattr(self, 'seq_counter', 0) + 1

            # Update cache
            kappa_raw = features.get("liquidity_kappa")
            if kappa_raw is not None:
                self._liquidity_kappa_map[symbol] = Decimal(str(kappa_raw))

        except Exception as e:
            self.logger.debug(f"MRHandler: failed to process features: {e}")

    def _check_liquidity_gate(self, symbol: str) -> bool:
        """Return whether ``symbol`` passes the configured liquidity gate.

        Configuration resolves from per-asset override to global MR default.
        Missing kappa blocks fail-closed instead of raising.
        """
        # CONFIG HIERARCHY (most specific wins):
        # 1. Per-asset override: mean_reversion.assets.<symbol>.liquidity_gate
        # 2. Global fallback: mean_reversion.liquidity_gate
        gate_cfg = self._mr_config.liquidity_gate  # Global default
        asset_cfg = self._mr_config.assets.get(symbol)
        if asset_cfg and isinstance(asset_cfg, MRAssetConfig) and asset_cfg.liquidity_gate:
            gate_cfg = asset_cfg.liquidity_gate

        if not gate_cfg or not gate_cfg.enabled:
            return True  # Gate disabled / not configured -> Pass

        # FAIL-CLOSED: Block signal when kappa missing (don't crash).
        kappa = self._liquidity_kappa_map.get(symbol)
        if kappa is None:
            self.logger.warning(
                "[%s] LIQUIDITY_GATE_FAIL_CLOSED: kappa not in cache. "
                "FE must emit liquidity_kappa before MR decision. "
                "gate_cfg: enabled=%s, kappa_min=%s",
                symbol, gate_cfg.enabled, gate_cfg.kappa_min,
            )
            return False  # Fail-closed: block signal, don't crash
        if kappa < Decimal(str(gate_cfg.kappa_min)):
            self.logger.info(
                f"[{symbol}] Liquidity Gate Fail: kappa={kappa} < min={gate_cfg.kappa_min}")
            return False

        return True

    # =========================================================================
    # T2B-03: CMD:PROCESS_STRATEGY - Primary Entry Point
    # =========================================================================

    def _on_process_strategy(self, event: Message) -> None:
        """
        T2B-03: Handle CMD:PROCESS_STRATEGY command.

        This is the PRIMARY entry point for MR decision making.
        Strategies are triggered ONLY by this command (orchestrated by FE).

        Payload contract:
        - symbol: str
        - tf_sec: int (required, must match self.timeframe_sec)
        - bar_close_ts: int (required)
        - bar: dict (OHLCV)
        - features: dict
        - warmup: dict
        - regime: dict | None
        """
        if not self._enabled:
            return

        pld = event.pld if hasattr(event, "pld") else event
        self._stats["bars_received"] += 1

        try:
            symbol = pld.get("symbol") if isinstance(
                pld, dict) else getattr(pld, "symbol", None)
            tf_sec = pld.get("tf_sec") if isinstance(
                pld, dict) else getattr(pld, "tf_sec", None)
            bar_identity = extract_canonical_bar_identity(
                pld if isinstance(pld, dict) else None,
                default_symbol=str(symbol or "") or None,
                default_timeframe_sec=int(
                    tf_sec) if tf_sec is not None else None,
                default_source_mode=RuntimeBarSourceMode.LIVE,
            )
            replay_identity = extract_canonical_replay_identity(
                pld if isinstance(pld, dict) else None,
                default_symbol=str(symbol or "") or None,
                default_timeframe_sec=int(
                    tf_sec) if tf_sec is not None else None,
                default_source_mode=RuntimeBarSourceMode.LIVE,
            )
            gap_status = extract_gap_status(
                pld if isinstance(pld, dict) else None,
                default_source="market_data:payload_bridge",
                default_source_mode=RuntimeBarSourceMode.LIVE,
            )

            # T2B-03 GATE 1: Missing tf_sec -> REJECT
            if tf_sec is None:
                self._stats["bars_rejected_missing_tf"] += 1
                self.logger.warning(
                    f"REJECTED: MR CMD missing tf_sec for {symbol}")
                write_trade_intent_rejected(
                    symbol=str(symbol or ""),
                    tf_sec=None,
                    bar_close_ts=(pld.get("bar_close_ts")
                                  if isinstance(pld, dict) else None),
                    reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                    stage="STRATEGY",
                    why="CMD:PROCESS_STRATEGY missing tf_sec for MR (fail-closed)",
                    src="mean_reversion",
                    ts_ms=(pld.get("bar_close_ts")
                           if isinstance(pld, dict) else None),
                    rid=(pld.get("rid") if isinstance(pld, dict) else None),
                )
                return

            # T2B-03 GATE 2: Wrong timeframe -> silently skip (other strategies handle it)
            if tf_sec != self.timeframe_sec:
                self._stats["bars_rejected_wrong_tf"] += 1
                return

            # T2B-03 GATE 3: Missing bar_close_ts -> REJECT
            bar_close_ts = (
                int(bar_identity.bar_end_ts_ms)
                if bar_identity is not None
                else pld.get("bar_close_ts") if isinstance(pld, dict) else getattr(pld, "bar_close_ts", None)
            )
            if not bar_close_ts:
                self._stats["bars_rejected_missing_tf"] += 1
                self.logger.warning(
                    f"REJECTED: MR CMD missing bar_close_ts for {symbol}")
                write_trade_intent_rejected(
                    symbol=str(symbol or ""),
                    tf_sec=int(tf_sec) if tf_sec is not None else None,
                    bar_close_ts=None,
                    reason_code=NormalizedRejectReasons.DATA_NOT_READY,
                    stage="STRATEGY",
                    why="CMD:PROCESS_STRATEGY missing bar_close_ts for MR (fail-closed)",
                    src="mean_reversion",
                    rid=(pld.get("rid") if isinstance(pld, dict) else None),
                )
                return

            # T2B-05 GATE 4: Missing bar data -> REJECT (fail-closed)
            bar_data_raw = pld.get("bar") if isinstance(
                pld, dict) else getattr(pld, "bar", None)
            if not bar_data_raw:
                self._stats["bars_rejected_missing_bar"] += 1
                self.logger.warning(
                    f"REJECTED: MR CMD missing 'bar' field for {symbol}")
                write_trade_intent_rejected(
                    symbol=str(symbol or ""),
                    tf_sec=int(tf_sec) if tf_sec is not None else None,
                    bar_close_ts=int(bar_close_ts) if bar_close_ts else None,
                    reason_code=NormalizedRejectReasons.DATA_NOT_READY,
                    stage="STRATEGY",
                    why="CMD:PROCESS_STRATEGY missing bar for MR (fail-closed)",
                    src="mean_reversion",
                    ts_ms=int(bar_close_ts) if bar_close_ts else None,
                    rid=(pld.get("rid") if isinstance(pld, dict) else None),
                )
                return

            # Skip if symbol not enabled for MR
            if not symbol or symbol not in self._enabled_symbols:
                return

            # Extract bar data from CMD payload
            bar_data = pld.get("bar", {}) if isinstance(
                pld, dict) else getattr(pld, "bar", None) or {}

            # Parse bar into Bar object
            from apps.reference.shared.types import Bar

            bar = Bar(
                symbol=symbol,
                timeframe_sec=tf_sec,
                open=Decimal(str(bar_data.get("open", 0) if isinstance(
                    bar_data, dict) else getattr(bar_data, "open", 0))),
                high=Decimal(str(bar_data.get("high", 0) if isinstance(
                    bar_data, dict) else getattr(bar_data, "high", 0))),
                low=Decimal(str(bar_data.get("low", 0) if isinstance(
                    bar_data, dict) else getattr(bar_data, "low", 0))),
                close=Decimal(str(bar_data.get("close", 0) if isinstance(
                    bar_data, dict) else getattr(bar_data, "close", 0))),
                volume=Decimal(str(bar_data.get("volume", 0) if isinstance(
                    bar_data, dict) else getattr(bar_data, "volume", 0))),
                start_ts_ms=int(bar_data.get("start_ts_ms", 0) if isinstance(
                    bar_data, dict) else getattr(bar_data, "start_ts_ms", 0)),
                end_ts_ms=(
                    int(bar_identity.bar_end_ts_ms)
                    if bar_identity is not None
                    else int(bar_close_ts)
                ),
                trade_count=int(bar_data.get("trade_count", 0) if isinstance(
                    bar_data, dict) else getattr(bar_data, "trade_count", 0)),
            )

            # DET-BT-09: Use get_clock() for deterministic backtest
            ts_ms = bar.end_ts_ms or get_clock().now_ms()

            # OBS-04-INT: Prefer bar-driven features as SSOT for liquidity gate.
            # P0-1: Cache full features for volatility/liquidity propagation to signal
            try:
                features_payload = pld.get("features") if isinstance(
                    pld, dict) else getattr(pld, "features", None)
                if isinstance(features_payload, dict):
                    # P0-1: Store features keyed by symbol for propagation
                    self._last_cmd_features[symbol] = features_payload
                    kappa_raw = features_payload.get("liquidity_kappa")
                    if kappa_raw is not None:
                        self._liquidity_kappa_map[symbol] = Decimal(
                            str(kappa_raw))
            except Exception:
                pass

            # MR-V1-WIRING: Cache price_motion from top-level CMD payload
            try:
                pm_payload = pld.get("price_motion") if isinstance(
                    pld, dict) else getattr(pld, "price_motion", None)
                if isinstance(pm_payload, dict):
                    self._last_cmd_price_motion[symbol] = pm_payload
            except Exception:
                pass

            # Get strategy for symbol
            strategy = self._strategies.get(symbol)
            if not strategy:
                return

            # Set regime from CMD payload or cache
            regime_data = pld.get("regime") if isinstance(
                pld, dict) else getattr(pld, "regime", None)
            resolved_regime_ctx: Dict[str, Any] = {}
            resolved_regime_name = None
            resolved_regime_confidence = None
            resolved_regime_event_ts_ms = 0
            if isinstance(regime_data, dict):
                resolved_regime_name = normalize_structural_regime_label(
                    regime_data.get("regime") or regime_data.get(
                        "overall_regime")
                )
                provenance = build_regime_provenance_fields(
                    regime_data,
                    bar_close_ts_ms=int(
                        bar_close_ts) if bar_close_ts else None,
                )
                confidence_raw = regime_data.get("confidence")
                if confidence_raw not in (None, ""):
                    try:
                        resolved_regime_confidence = float(confidence_raw)
                    except (TypeError, ValueError):
                        resolved_regime_confidence = None
                resolved_regime_event_ts_ms = int(
                    provenance.get("regime_event_ts_ms") or 0
                )
                if resolved_regime_name:
                    resolved_regime_ctx = {
                        "regime": resolved_regime_name,
                        "confidence": resolved_regime_confidence,
                        "regime_ts_ms": resolved_regime_event_ts_ms or None,
                        **provenance,
                    }
            else:
                regime = self._per_symbol_regime.get(symbol)
                if regime:
                    resolved_regime_name = regime
                    resolved_regime_confidence = self._regime_confidence.get(
                        symbol)
                    provenance = build_regime_provenance_fields(
                        {
                            "regime": regime,
                            "regime_event_ts_ms": self._regime_event_ts_ms.get(symbol) or self._regime_ts_ms.get(symbol),
                        },
                        bar_close_ts_ms=int(
                            bar_close_ts) if bar_close_ts else None,
                    )
                    resolved_regime_event_ts_ms = int(
                        provenance.get("regime_event_ts_ms") or 0
                    )
                    resolved_regime_ctx = {
                        "regime": resolved_regime_name,
                        "confidence": resolved_regime_confidence,
                        "regime_ts_ms": resolved_regime_event_ts_ms or None,
                        **provenance,
                    }

            if resolved_regime_name:
                strategy.set_regime(symbol, resolved_regime_name)

            # Vector 2: Directional Bias — compute effective thresholds from funding
            self._apply_directional_bias(symbol, strategy)

            # Process bar through strategy (T2B-03: CMD is the ONLY trigger)
            try:
                signal = strategy.on_bar(symbol, bar, ts_ms)
            finally:
                # R3 hardening: clear transient overrides immediately after on_bar,
                # preventing any stale threshold from persisting beyond the current bar.
                strategy.config.entry_threshold_long = None
                strategy.config.entry_threshold_short = None

            if signal:
                print(
                    f"[DEBUG MR] Signal why: {signal.why} | Type: {signal.signal_type} | Regime: {strategy.get_regime(symbol)} | Allowed: {strategy.config.allowed_regimes}", flush=True)

            self._stats["bars_completed"] += 1

            if signal is None:
                return

            # Log bar
            if signal.bar:
                self._log_bar(signal)

                if signal.is_signal:
                    # Vector 1: Microstructure Veto (handler overlay)
                    # Executes after actionable signal, before liquidity gate
                    signal_side = "LONG" if signal.signal_type == MRSignalType.LONG else "SHORT"
                    veto_allowed, veto_reason = self._check_microstructure_veto(
                        symbol, signal_side, bar)
                    if not veto_allowed:
                        self.logger.info(
                            f"[{symbol}] MR Signal BLOCKED by Microstructure Veto: {veto_reason}")
                        self._emit_strategy_blocked(
                            symbol=symbol,
                            reason_code=veto_reason,
                            reason="MICROSTRUCTURE",
                            context="mean_reversion_handler:_on_process_strategy",
                            details={
                                "tfi_ema": str(round(self._tfi_ema.get(symbol, 0.0), 6)),
                                "signal_side": signal_side,
                            },
                            why_chain=["MICROSTRUCTURE_VETO", veto_reason],
                        )
                    elif self._check_liquidity_gate(symbol):
                        self._emit_signal(
                            signal,
                            bar_identity=bar_identity,
                            replay_identity=replay_identity,
                            gap_status=gap_status,
                            warmup_readiness=(
                                pld.get("warmup") if isinstance(pld, dict) else None),
                            regime_ctx=resolved_regime_ctx if resolved_regime_ctx else None,
                        )
                    else:
                        self.logger.info(
                            f"[{symbol}] MR Signal BLOCKED by Liquidity Gate")
                        self._emit_strategy_blocked(
                            symbol=symbol,
                            reason_code="LIQUIDITY_GATE",
                            reason="LIQUIDITY",
                            context="mean_reversion_handler:_on_process_strategy",
                            details={"kappa": str(
                                self._liquidity_kappa_map.get(symbol, "MISSING"))},
                            why_chain=["LIQUIDITY_GATE"],
                        )
            else:
                self._stats["neutral_bars"] += 1
                why = str(getattr(signal, "why", "") or "")
                why_norm = why[len("neutral:"):] if why.startswith(
                    "neutral:") else why
                reason_code = None
                if why_norm.startswith("regime_not_flat:"):
                    reason_code = "REGIME_MAPPING_NONE"
                elif why_norm.startswith("regime_not_allowed:"):
                    reason_code = "REGIME_NOT_ALLOWED"
                elif why_norm.startswith("flat_low_short_bb_width_too_narrow:"):
                    reason_code = "FLAT_LOW_SHORT_HARDENED"
                elif why_norm.startswith("squeeze_expansion_veto:"):
                    reason_code = "SQUEEZE_EXPANSION_VETO"
                elif why_norm.startswith("momentum_separation_veto:"):
                    reason_code = "MOMENTUM_SEPARATION_VETO"

                if reason_code:
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code=reason_code,
                        reason="REGIME" if reason_code.startswith(
                            "REGIME") else "SIGNAL",
                        context="mean_reversion_handler:_on_process_strategy",
                        details={"why": why_norm},
                        why_chain=[
                            "REGIME" if reason_code.startswith(
                                "REGIME") else "SIGNAL",
                            why_norm,
                        ],
                    )
        except Exception as e:
            self.logger.error(f"Error in _on_process_strategy: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")

    def _on_bar_closed_data_only(self, event: Message) -> None:
        """
        Compatibility hook for EVT:BAR_CLOSED.

        Decision execution is triggered exclusively by CMD:PROCESS_STRATEGY.
        The BAR_CLOSED listener remains registered only to preserve event wiring
        compatibility while this hook stays intentionally inert.
        """
        # No-op for now. Bar data caching can be added if needed.
        # The primary purpose is to maintain backwards compatibility
        # without triggering decision logic.
        pass

    # NOTE (SIZING-MARGIN-FIRST-SSOT-02):
    # Mean Reversion sizing moved to per-symbol instruments SSOT.

    def get_stats(self) -> Dict[str, Any]:
        """Return lightweight handler diagnostics for observability/debugging."""
        return {
            "enabled": self._enabled,
            "enabled_symbols": list(self._enabled_symbols),
            "signal_counts": dict(self._signal_counts),
            "last_signal_times": {
                k: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(v))
                for k, v in self._last_signal_time.items()
            },
        }

    def reset_symbol(self, symbol: str) -> None:
        """Reset state for symbol."""
        strategy = self._strategies.get(symbol)
        if strategy:
            strategy.reset_symbol(symbol)
        self._signal_counts.pop(symbol, None)
        self._last_signal_time.pop(symbol, None)

    def reset_all(self) -> None:
        """Reset all state."""
        for strategy in self._strategies.values():
            strategy.reset_all()
        self._signal_counts.clear()
        self._last_signal_time.clear()
