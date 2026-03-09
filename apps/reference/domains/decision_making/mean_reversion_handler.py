"""
Mean Reversion Decision Handler.

Track B: Integrates Mean Reversion 3m Strategy into DecisionMaking workflow.

T2B-03 Architecture (Orchestrated Cycle):
1. FeatureEngineering emits CMD:PROCESS_STRATEGY after bar closes + features ready
2. This handler receives bar data via CMD:PROCESS_STRATEGY (includes full OHLCV bar)
3. Computes MR signals via MeanReversion3mStrategy
4. Emits EVT:STRATEGY_SIGNAL_PRODUCED when signal is actionable

Activation SSOT: strategies_registry.assignments (per symbol).
The config flag mean_reversion.enabled is a global kill-switch (can disable, does not activate without assignment).
"""

import logging
# DET-BT-09: Removed 'import time' - use get_clock() for deterministic backtest
from apps.reference.core.time import get_clock
import uuid
import json
from decimal import Decimal
from typing import Any, Dict, Optional, TYPE_CHECKING

from vfoundation.core.protocol import Message
from apps.reference.utils.accessors import aget
from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
from apps.reference.domains.decision_making.trade_intent_reject_wal import write_trade_intent_rejected

# Import MR strategy components
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MeanReversion1mStrategy,
    MRStrategyConfig,
    MRSignal,
    MRSignalType,
)
from apps.reference.domains.feature_engineering.regime_mapping import FlatRegimeThresholds
from apps.reference.config_models import (
    AuroraConfig,
    MeanReversion1mStrategyConfig,
    MRStrategyParamsConfig,
    MRAssetConfig,
    LiquidityGateConfig,
)
from apps.reference.domains.decision_making.mean_reversion_logger import MeanReversionBarLogger

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


class MeanReversionHandler:
    """Handler for Mean Reversion 3m strategy integration with DecisionMaking.
    
    T2B-03 Workflow (Orchestrated Cycle):
        1. _on_process_strategy() — receives CMD:PROCESS_STRATEGY from FE
        2. Strategy processes bar (OHLCV from CMD payload), MR signal
        3. If signal is actionable, emit EVT:STRATEGY_SIGNAL_PRODUCED
    
    Activation SSOT: strategies_registry.assignments.
    The config flag mean_reversion.enabled is a global kill-switch.
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
        self._last_tick_ts_ms: Dict[str, int] = {}
        self._last_counted_bar_end_ts_ms: Dict[str, int] = {}
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
        
        self._parse_config()
        
        # Initialize strategy per symbol if enabled
        self._strategies: Dict[str, MeanReversion1mStrategy] = {}
        if self._enabled:
            self._init_strategies()
        
        # Signal tracking for logging
        self._signal_counts: Dict[str, int] = {}
        self._last_signal_time: Dict[str, float] = {}
        
        # Cache for liquidity kappa (from FeatureEngineering)
        self._liquidity_kappa_map: Dict[str, Decimal] = {}

        # P0-1: Per-symbol features cache (keyed by symbol) for volatility/liquidity propagation
        # Stores cmd.features from last CMD:PROCESS_STRATEGY per symbol
        self._last_cmd_features: Dict[str, Dict[str, Any]] = {}

        # Block reason throttling (avoid per-tick spam)
        self._last_block_reason: Dict[str, str] = {}
        self._last_block_ts_ms: Dict[str, int] = {}
        
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
            self.bar_logger = MeanReversionBarLogger(self._mr_config.timeframe_sec)

    def register(self) -> None:
        """Attach FSM listeners.
        
        T2B-03: Primary trigger is CMD:PROCESS_STRATEGY (Orchestrated Cycle).
        EVT:BAR_CLOSED and EVT:FEATURES_CALCULATED are kept for data caching only.
        """
        if not self._enabled:
            return
        # T2B-03: Primary trigger - CMD:PROCESS_STRATEGY (Orchestrated Cycle)
        self.fsm.listen("CMD:PROCESS_STRATEGY", self._on_process_strategy)
        # T2B-03: Data-only listeners (no decision trigger)
        self.fsm.listen("EVT:BAR_CLOSED", self._on_bar_closed_data_only)
        self.fsm.listen("EVT:REGIME_DETECTED", self._on_regime_detected)
        self.mlog.info(
            "MR_REGISTER %s",
            json.dumps(
                {
                    "events": ["CMD:PROCESS_STRATEGY", "EVT:BAR_CLOSED", "EVT:REGIME_DETECTED"],
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
                self.logger.info("Mean Reversion 1m: config missing, handler disabled (no assignment)")
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
                    raise TypeError("mean_reversion.assets must contain typed MRAssetConfig values, got dict")

        missing_assets = sorted([s for s in mr_assigned_symbols if not self._mr_config or s not in self._mr_config.assets])
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
        self._enabled_symbols = set(mr_assigned_symbols) & set(self._enabled_symbols)
        self._enabled = bool(self._enabled_symbols)
        
        # TF-SSOT-PACK-001: SSOT timeframe from config (removes hardcode)
        self.timeframe_sec = self._mr_config.timeframe_sec
        
        if not self._enabled_symbols:
            self.logger.info("Mean Reversion 1m: no assigned+enabled symbols; handler disabled")
            self._enabled = False
            
    def _init_strategies(self) -> None:
        """Initialize separate strategy instance per symbol with overrides."""
        if not self._mr_config:
            return

        timeframe_sec = self._mr_config.timeframe_sec
        if timeframe_sec <= 0:
            raise ValueError(f"mean_reversion.timeframe_sec must be positive, got {timeframe_sec}")
        
        # Global base config
        base_strat_cfg = self._mr_config.strategy
        
        # Shared regime sizing
        regime_sizing = None
        if self._mr_config.regime_sizing:
            regime_sizing = {}
            for regime_name, sizing_cfg in self._mr_config.regime_sizing.items():
                if hasattr(sizing_cfg, 'model_dump'):
                    regime_sizing[regime_name] = sizing_cfg.model_dump(exclude_none=True)
                elif isinstance(sizing_cfg, dict):
                    regime_sizing[regime_name] = sizing_cfg

        flat_regime_thresholds = FlatRegimeThresholds(
            high_vol_pct=Decimal(str(self._mr_config.regime_thresholds.high_vol_pct)),
            low_vol_pct=Decimal(str(self._mr_config.regime_thresholds.low_vol_pct)),
        )

        for symbol in self._enabled_symbols:
            asset_cfg = self._mr_config.assets.get(symbol)
            if isinstance(asset_cfg, dict):
                raise TypeError("mean_reversion.assets must contain typed MRAssetConfig values, got dict")

            # Start with base config
            config = MRStrategyConfig()
            config.bb_window = base_strat_cfg.bb_window
            config.bb_num_std = base_strat_cfg.bb_num_std
            config.atr_window = base_strat_cfg.atr_window
            config.rsi_window = base_strat_cfg.rsi_window
            config.min_bars = base_strat_cfg.min_bars
            config.min_bb_width = Decimal(str(base_strat_cfg.min_bb_width))
            config.max_bb_width = Decimal(str(base_strat_cfg.max_bb_width))
            config.entry_threshold = Decimal(str(base_strat_cfg.entry_threshold))
            config.rsi_oversold = Decimal(str(base_strat_cfg.rsi_oversold))
            config.rsi_overbought = Decimal(str(base_strat_cfg.rsi_overbought))
            config.sl_atr_mult = Decimal(str(base_strat_cfg.sl_atr_mult))
            config.tp_to_mid = base_strat_cfg.tp_to_mid
            config.cooldown_sec = base_strat_cfg.cooldown_sec
            # Tier D: confidence scalars from Pydantic SSOT
            config.confidence_base = Decimal(str(base_strat_cfg.confidence_base))
            config.confidence_bb_slope = Decimal(str(base_strat_cfg.confidence_bb_slope))
            config.confidence_rsi_bonus = Decimal(str(base_strat_cfg.confidence_rsi_bonus))

            # Allowed regimes precedence:
            # global default -> per-asset -> per-asset strategy override (if present)
            config.allowed_regimes = list(self._mr_config.allowed_regimes)
            if asset_cfg is not None:
                config.allowed_regimes = list(asset_cfg.allowed_regimes)
            
            # Apply asset-specific overrides
            if asset_cfg is not None and hasattr(asset_cfg, "strategy") and asset_cfg.strategy is not None:
                strat_override = asset_cfg.strategy
                # Check for overrides
                if strat_override.bb_window is not None: config.bb_window = strat_override.bb_window
                if strat_override.bb_num_std is not None: config.bb_num_std = strat_override.bb_num_std
                if strat_override.min_bb_width is not None: config.min_bb_width = Decimal(str(strat_override.min_bb_width))
                if strat_override.entry_threshold is not None: config.entry_threshold = Decimal(str(strat_override.entry_threshold))
                if strat_override.tp_to_mid is not None: config.tp_to_mid = bool(strat_override.tp_to_mid)
                if strat_override.cooldown_sec is not None: config.cooldown_sec = strat_override.cooldown_sec
                if strat_override.sl_atr_mult is not None: config.sl_atr_mult = Decimal(str(strat_override.sl_atr_mult))
                if strat_override.allowed_regimes is not None: config.allowed_regimes = list(strat_override.allowed_regimes)
                # Wire sl_buffer_pct and tp_buffer_pct from YAML
                if strat_override.sl_buffer_pct is not None: config.sl_buffer_pct = Decimal(str(strat_override.sl_buffer_pct))
                if strat_override.tp_buffer_pct is not None: config.tp_buffer_pct = Decimal(str(strat_override.tp_buffer_pct))
                # Tier D: per-asset confidence overrides
                if strat_override.confidence_base is not None: config.confidence_base = Decimal(str(strat_override.confidence_base))
                if strat_override.confidence_bb_slope is not None: config.confidence_bb_slope = Decimal(str(strat_override.confidence_bb_slope))
                if strat_override.confidence_rsi_bonus is not None: config.confidence_rsi_bonus = Decimal(str(strat_override.confidence_rsi_bonus))

            self._strategies[symbol] = MeanReversion1mStrategy(
                config=config,
                timeframe_sec=timeframe_sec,
                regime_sizing=regime_sizing,
                regime_thresholds=flat_regime_thresholds,
            )
            self.logger.info(f"[{symbol}] Initialized MR Strategy (BB={config.bb_window}, W={config.min_bb_width})")

    @property
    def enabled(self) -> bool:
        """Check if MR handler is enabled."""
        return self._enabled
    
    def is_symbol_enabled(self, symbol: str) -> bool:
        """Check if MR is enabled for specific symbol."""
        return self._enabled and symbol in self._enabled_symbols

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
        # DET-BT-09: Use get_clock() for deterministic backtest
        now_ms = get_clock().now_ms()
        last_reason = self._last_block_reason.get(symbol)
        last_ts = self._last_block_ts_ms.get(symbol, 0)
        if last_reason == reason_code and (now_ms - last_ts) < int(throttle_ms):
            return
        self._last_block_reason[symbol] = reason_code
        self._last_block_ts_ms[symbol] = now_ms

        payload: Dict[str, Any] = {
            "schema_version": 1,
            "strategy_id": "mean_reversion",
            "symbol": symbol,
            "reason_code": str(reason_code),
            "reason": str(reason),
            "context": str(context),
            "ts_ms": now_ms,
            "why_chain": list(why_chain or []),
        }
        if details:
            payload["details"] = details
        self.fsm.emit("EVT:STRATEGY_DECISION_BLOCKED", payload, why=f"mr_blocked:{reason_code}")
    
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
            why_norm = why[len("neutral:") :] if why.startswith("neutral:") else why
            
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
                self.logger.warning(f"Failed to log bar for {signal.symbol}: {e}")

    def _emit_signal(self, signal: MRSignal) -> None:
        symbol = signal.symbol
        
        # Track signal
        self._signal_counts[symbol] = (self._signal_counts[symbol] if symbol in self._signal_counts else 0) + 1
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
        
        pld = {
            "schema_version": 1,
            "strategy_id": "mean_reversion",
            "symbol": symbol,
            "tf_sec": self.timeframe_sec,
            "side": side,
            "readiness": {"warmup_ok": True},
            "score": float(signal.confidence),
            "why": signal.why,
            "ts_ms": int(signal.timestamp_ms),
            "rid": rid,
            "why_chain": [signal.why],
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
        }

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
            if isinstance(pld, dict):
                symbol = str(pld.get("symbol") or "")
                regime = str(pld.get("regime") or pld.get("overall_regime") or "")
            else:
                symbol = str(getattr(pld, "symbol", "") or "")
                regime = str(aget(pld, "regime", "") or aget(pld, "overall_regime", "") or "")

            if not symbol or symbol not in self._enabled_symbols:
                return
            if not regime:
                return
            self._per_symbol_regime[symbol] = regime
            self.on_regime(symbol, regime)
        except Exception as e:
            self._stats["regime_processing_errors"] += 1
            self.logger.warning(
                f"MRHandler: failed to process EVT:REGIME_DETECTED: {e}",
                exc_info=True,
            )

    def _on_features_calculated(self, event: Message) -> None:
        """Cache liquidity kappa from FE."""
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
                self.logger.warning(f"MR rejecting features for {symbol}: missing tf_sec")
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
                self.logger.warning(f"MR rejecting features for {symbol}: tf_sec {tf_sec} != {self.timeframe_sec}")
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

            # Update features cache
            self.features[symbol] = features

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
        """Check if symbol passes liquidity gate."""
        # CONFIG HIERARCHY (most specific wins):
        # 1. Per-asset override: mean_reversion.assets.<symbol>.liquidity_gate
        # 2. Global fallback: mean_reversion.liquidity_gate
        gate_cfg = self._mr_config.liquidity_gate  # Global default
        asset_cfg = self._mr_config.assets.get(symbol)
        if asset_cfg and isinstance(asset_cfg, MRAssetConfig) and asset_cfg.liquidity_gate:
            gate_cfg = asset_cfg.liquidity_gate
        
        if not gate_cfg or not gate_cfg.enabled:
            return True  # Gate disabled / not configured -> Pass
        
        # FAIL-CLOSED: Require explicit kappa when gate is enabled.
        # No silent fallback - missing kappa is a contract violation.
        kappa = self._liquidity_kappa_map.get(symbol)
        if kappa is None:
            raise RuntimeError(
                f"[{symbol}] Liquidity gate enabled but liquidity_kappa not found in cache. "
                f"Ensure FeatureEngineering emits liquidity_kappa before MR decision. "
                f"Gate config: enabled={gate_cfg.enabled}, kappa_min={gate_cfg.kappa_min}"
            )
        if kappa < Decimal(str(gate_cfg.kappa_min)):
            self.logger.info(f"[{symbol}] Liquidity Gate Fail: kappa={kappa} < min={gate_cfg.kappa_min}")
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
            symbol = pld.get("symbol") if isinstance(pld, dict) else getattr(pld, "symbol", None)
            tf_sec = pld.get("tf_sec") if isinstance(pld, dict) else getattr(pld, "tf_sec", None)
            
            # T2B-03 GATE 1: Missing tf_sec -> REJECT
            if tf_sec is None:
                self._stats["bars_rejected_missing_tf"] += 1
                self.logger.warning(f"REJECTED: MR CMD missing tf_sec for {symbol}")
                write_trade_intent_rejected(
                    symbol=str(symbol or ""),
                    tf_sec=None,
                    bar_close_ts=(pld.get("bar_close_ts") if isinstance(pld, dict) else None),
                    reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                    stage="STRATEGY",
                    why="CMD:PROCESS_STRATEGY missing tf_sec for MR (fail-closed)",
                    src="mean_reversion",
                    ts_ms=(pld.get("bar_close_ts") if isinstance(pld, dict) else None),
                    rid=(pld.get("rid") if isinstance(pld, dict) else None),
                )
                return
            
            # T2B-03 GATE 2: Wrong timeframe -> silently skip (other strategies handle it)
            if tf_sec != self.timeframe_sec:
                self._stats["bars_rejected_wrong_tf"] += 1
                return
            
            # T2B-03 GATE 3: Missing bar_close_ts -> REJECT
            bar_close_ts = pld.get("bar_close_ts") if isinstance(pld, dict) else getattr(pld, "bar_close_ts", None)
            if not bar_close_ts:
                self._stats["bars_rejected_missing_tf"] += 1
                self.logger.warning(f"REJECTED: MR CMD missing bar_close_ts for {symbol}")
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
            bar_data_raw = pld.get("bar") if isinstance(pld, dict) else getattr(pld, "bar", None)
            if not bar_data_raw:
                self._stats["bars_rejected_missing_bar"] += 1
                self.logger.warning(f"REJECTED: MR CMD missing 'bar' field for {symbol}")
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
            bar_data = pld.get("bar", {}) if isinstance(pld, dict) else getattr(pld, "bar", None) or {}
            
            # Parse bar into Bar object
            from apps.reference.domains.feature_engineering.bar_resampler import Bar
            
            bar = Bar(
                symbol=symbol,
                timeframe_sec=tf_sec,
                open=Decimal(str(bar_data.get("open", 0) if isinstance(bar_data, dict) else getattr(bar_data, "open", 0))),
                high=Decimal(str(bar_data.get("high", 0) if isinstance(bar_data, dict) else getattr(bar_data, "high", 0))),
                low=Decimal(str(bar_data.get("low", 0) if isinstance(bar_data, dict) else getattr(bar_data, "low", 0))),
                close=Decimal(str(bar_data.get("close", 0) if isinstance(bar_data, dict) else getattr(bar_data, "close", 0))),
                volume=Decimal(str(bar_data.get("volume", 0) if isinstance(bar_data, dict) else getattr(bar_data, "volume", 0))),
                start_ts_ms=int(bar_data.get("start_ts_ms", 0) if isinstance(bar_data, dict) else getattr(bar_data, "start_ts_ms", 0)),
                end_ts_ms=int(bar_close_ts),
                trade_count=int(bar_data.get("trade_count", 0) if isinstance(bar_data, dict) else getattr(bar_data, "trade_count", 0)),
            )
            
            # DET-BT-09: Use get_clock() for deterministic backtest
            ts_ms = bar.end_ts_ms or get_clock().now_ms()

            # OBS-04-INT: Prefer bar-driven features as SSOT for liquidity gate.
            # P0-1: Cache full features for volatility/liquidity propagation to signal
            try:
                features_payload = pld.get("features") if isinstance(pld, dict) else getattr(pld, "features", None)
                if isinstance(features_payload, dict):
                    # P0-1: Store features keyed by symbol for propagation
                    self._last_cmd_features[symbol] = features_payload
                    kappa_raw = features_payload.get("liquidity_kappa")
                    if kappa_raw is not None:
                        self._liquidity_kappa_map[symbol] = Decimal(str(kappa_raw))
            except Exception:
                pass
            
            # Get strategy for symbol
            strategy = self._strategies.get(symbol)
            if not strategy:
                return
            
            # Set regime from CMD payload or cache
            regime_data = pld.get("regime") if isinstance(pld, dict) else getattr(pld, "regime", None)
            if regime_data:
                regime_name = regime_data.get("regime") if isinstance(regime_data, dict) else getattr(regime_data, "regime", None)
                if regime_name:
                    strategy.set_regime(symbol, regime_name)
            else:
                regime = self._per_symbol_regime.get(symbol)
                if regime:
                    strategy.set_regime(symbol, regime)
            
            # Process bar through strategy (T2B-03: CMD is the ONLY trigger)
            signal = strategy.on_bar(symbol, bar, ts_ms)
            
            if signal:
                print(f"[DEBUG MR] Signal why: {signal.why} | Type: {signal.signal_type} | Regime: {strategy.get_regime(symbol)} | Allowed: {strategy.config.allowed_regimes}", flush=True)

            self._stats["bars_completed"] += 1
            
            if signal is None:
                return
            
            # Log bar
            if signal.bar:
                self._log_bar(signal)
            
                if signal.is_signal:
                    if self._check_liquidity_gate(symbol):
                        self._emit_signal(signal)
                    else:
                        self.logger.info(f"[{symbol}] MR Signal BLOCKED by Liquidity Gate")
                        write_trade_intent_rejected(
                            symbol=str(symbol),
                            tf_sec=int(tf_sec) if tf_sec is not None else None,
                            bar_close_ts=int(bar_close_ts) if bar_close_ts else None,
                            reason_code=NormalizedRejectReasons.LIQUIDITY_LOW,
                            stage="STRATEGY",
                            why="Liquidity gate blocked MR signal",
                            src="mean_reversion",
                            ts_ms=int(bar_close_ts) if bar_close_ts else None,
                        )
                        self._emit_strategy_blocked(
                            symbol=symbol,
                            reason_code="LIQUIDITY_GATE",
                            reason="LIQUIDITY",
                        context="mean_reversion_handler:_on_process_strategy",
                        details={"kappa": str(self._liquidity_kappa_map.get(symbol, "MISSING"))},
                        why_chain=["LIQUIDITY_GATE"],
                    )
            else:
                self._stats["neutral_bars"] += 1
                why = str(getattr(signal, "why", "") or "")
                why_norm = why[len("neutral:"):] if why.startswith("neutral:") else why
                reason_code = None
                if why_norm.startswith("regime_not_flat:"):
                    reason_code = "REGIME_MAPPING_NONE"
                elif why_norm.startswith("regime_not_allowed:"):
                    reason_code = "REGIME_NOT_ALLOWED"
                
                if reason_code:
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code=reason_code,
                        reason="REGIME",
                        context="mean_reversion_handler:_on_process_strategy",
                        details={"why": why_norm},
                        why_chain=["REGIME", why_norm],
                    )
        except Exception as e:
            self.logger.error(f"Error in _on_process_strategy: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")

    def _on_bar_closed_data_only(self, event: Message) -> None:
        """
        T2B-03: Data-only handler for EVT:BAR_CLOSED.
        
        Caches bar data but does NOT trigger decision.
        Decision is now triggered exclusively by CMD:PROCESS_STRATEGY.
        """
        # No-op for now. Bar data caching can be added if needed.
        # The primary purpose is to maintain backwards compatibility
        # without triggering decision logic.
        pass
    
    # NOTE (SIZING-MARGIN-FIRST-SSOT-02):
    # Mean Reversion sizing moved to per-symbol instruments SSOT.
    
    def get_stats(self) -> Dict[str, Any]:
        """Get handler statistics."""
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
