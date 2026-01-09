"""
Mean Reversion Decision Handler.

Track B: Integrates Mean Reversion 3m Strategy into DecisionMaking workflow.

This handler:
1. Receives tick data via EVT:MARKET_TICK_FORWARDED (forwarded after feature calc)
2. Aggregates ticks into 3m bars via BarResampler
3. Computes MR signals via MeanReversion3mStrategy
4. Emits EVT:STRATEGY_SIGNAL_PRODUCED when signal is actionable

Activation SSOT: strategies_registry.assignments (per symbol).
The config flag mean_reversion.enabled is a global kill-switch (can disable, does not activate without assignment).
"""

import logging
import time
import uuid
import json
from decimal import Decimal
from typing import Any, Dict, Optional, TYPE_CHECKING

from vfoundation.core.protocol import Message
from apps.reference.utils.accessors import aget

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
    
    Workflow:
        1. on_tick() - receives tick from FeatureEngineering via EVT:MARKET_TICK_FORWARDED
        2. Strategy processes tick, bar resampling (3 min), MR signal
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
        """Attach FSM listeners (ticks + regime)."""
        if not self._enabled:
            return
        self.fsm.listen("EVT:MARKET_TICK_FORWARDED", self._on_market_tick)
        self.fsm.listen("EVT:REGIME_DETECTED", self._on_regime_detected)
        self.fsm.listen("EVT:FEATURES_CALCULATED", self._on_features_calculated)
        self.mlog.info(
            "MR_REGISTER %s",
            json.dumps(
                {
                    "events": ["EVT:MARKET_TICK_FORWARDED", "EVT:REGIME_DETECTED", "EVT:FEATURES_CALCULATED"],
                    "enabled_symbols": sorted(self._enabled_symbols),
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

        # Strict Sequential Trading Contract: direct intent mode is only safe when MR is the ONLY
        # strategy assigned for that symbol. Otherwise it bypasses DecisionMaking arbitration/QoS.
        if self._mr_config and bool(self._mr_config.emit_trade_intent_directly) and mr_assigned_symbols:
            hybrid = []
            assignments = {}
            if hasattr(self.config, 'strategies_registry') and self.config.strategies_registry:
                assignments = getattr(self.config.strategies_registry, 'assignments', {}) or {}
            for symbol in sorted(mr_assigned_symbols):
                strategies = assignments.get(symbol) or []
                if any(sid != 'mean_reversion' for sid in strategies):
                    hybrid.append({"symbol": symbol, "assigned": list(strategies)})
            if hybrid:
                raise ValueError(
                    "❌ CRITICAL: mean_reversion.emit_trade_intent_directly=true is forbidden for hybrid symbols "
                    "(it would bypass DecisionMaking arbitration/QoS). Affected: "
                    f"{hybrid}. Set emit_trade_intent_directly=false or remove other strategies from assignments."
                )

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
                # Add other overrides as needed...

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
    
    def on_tick(
        self,
        symbol: str,
        price: Decimal,
        volume: Decimal,
        timestamp_ms: int,
        regime: Optional[str] = None,
    ) -> Optional[MRSignal]:
        """
        Process tick for Mean Reversion signal.
        """
        if not self._enabled:
            return None
        
        # Route to symbol-specific strategy
        strategy = self._strategies.get(symbol)
        if not strategy:
            return None
        
        # Process tick through strategy
        signal = strategy.on_tick(symbol, price, volume, timestamp_ms)
        
        # Log Bar if completed
        if signal and signal.bar:
            self._log_bar(signal)
            # TF-BAR-SSOT-001: Emit bar closed event for FE to use tf_sec
            self.fsm.emit("EVT:BAR_CLOSED", payload={"symbol": symbol, "bar": signal.bar}, why="bar_closed")
        
        if signal and signal.is_signal:
            if self._check_liquidity_gate(symbol):
                self._emit_signal(signal)
            else:
                self.logger.info(f"[{symbol}] MR Signal BLOCKED by Liquidity Gate")
                self._emit_strategy_blocked(
                    symbol=symbol,
                    reason_code="LIQUIDITY_GATE",
                    reason="LIQUIDITY",
                    context="mean_reversion_handler:on_tick",
                    details={"kappa": str(self._liquidity_kappa_map.get(symbol, Decimal('0')))},
                    why_chain=["LIQUIDITY_GATE"],
                )

        # Non-silent blocking for neutral signals with explicit deny reasons.
        if signal and (not signal.is_signal):
            why = str(getattr(signal, "why", "") or "")
            why_norm = why[len("neutral:") :] if why.startswith("neutral:") else why
            reason_code: str | None = None
            reason: str | None = None
            if why_norm.startswith("regime_not_flat:"):
                reason_code = "REGIME_MAPPING_NONE"
                reason = "REGIME_MAPPING_NONE"
            elif why_norm.startswith("regime_not_allowed:"):
                reason_code = "REGIME_NOT_ALLOWED"
                reason = "REGIME"

            if reason_code:
                self._emit_strategy_blocked(
                    symbol=symbol,
                    reason_code=reason_code,
                    reason=reason or reason_code,
                    context="mean_reversion_handler:on_tick",
                    details={"why": why},
                    why_chain=["MR_NEUTRAL", why_norm],
                )
        
        return signal

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
        now_ms = int(time.time() * 1000)
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
                "generated_ts_ms": int(time.time() * 1000),
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
        self._last_signal_time[symbol] = time.time()
        
        self.logger.info(
            f"[{symbol}] MR Signal: {signal.signal_type.name} "
            f"confidence={signal.confidence:.2f} "
            f"entry={signal.entry_price} stop={signal.stop_price} target={signal.target_price} "
            f"why={signal.why}"
        )
        
        rid = str(uuid.uuid4())
        side = signal.side  # "BUY" or "SELL"
        # NOTE (SIZING-MARGIN-FIRST-SSOT-02):
        # Mean Reversion does NOT own sizing. DecisionMaking computes qty from:
        # instruments.<SYM>.sizing.margin_pct + instruments.<SYM>.execution.target_leverage.

        # If configured, MR can emit trade intent directly (legacy mode). This bypasses DecisionMaking.
        if self._mr_config and bool(self._mr_config.emit_trade_intent_directly):
            if side not in ("BUY", "SELL"):
                return

            entry_price = signal.entry_price
            if entry_price is None or entry_price <= 0:
                return

            # Position sizing in direct mode comes from MR risk config.
            # Per-asset override (assets.<SYM>.risk.position_size_usd) wins over global.
            pos_usd = None
            asset_cfg = self._mr_config.assets.get(symbol) if self._mr_config.assets else None
            if isinstance(asset_cfg, MRAssetConfig) and asset_cfg.risk is not None:
                if asset_cfg.risk.position_size_usd is not None:
                    pos_usd = float(asset_cfg.risk.position_size_usd)
            if pos_usd is None:
                pos_usd = float(self._mr_config.risk.position_size_usd)

            qty = Decimal(str(pos_usd)) / Decimal(str(entry_price))
            side_lc = "buy" if side == "BUY" else "sell"
            why_chain = [signal.why] if signal.why else ["mr_signal"]
            trade_intent = {
                "rid": rid,
                "instrument": symbol,
                "side": side_lc,
                "strategy": "mean_reversion",
                "order": {
                    "qty": str(qty),
                    "price": str(entry_price),
                    "price_ref": str(entry_price),
                    "reduce_only": False,
                },
                "p": str(signal.confidence),
                "payoff_ratio_r": "2.0",
                "tca_budget": {
                    "max_slippage_bps": "10",
                    "max_latency_ms": 500,
                    "maker_preference": "neutral",
                },
                "risk_budget": {
                    "trade_cvar95_max_bps": "100",
                    "session_cvar95_max_bps": "200",
                },
                "size": {
                    "kelly_fraction": "0.1",
                    "notional_cap_usd": str(Decimal(str(qty)) * Decimal(str(entry_price))),
                },
                "valid_for_ms": 5000,
                "why": why_chain,
                "dto_version": "1.0.0",
                "schema_ref": "trade_intent_v1.json",
                "idempotent_key": str(uuid.uuid4()),
            }

            self.fsm.emit(
                "EVT:TRADE_INTENT_PROPOSED",
                payload=trade_intent,
                why=f"trade_intent:mean_reversion:{side_lc}",
                data_ref=why_chain,
            )
            self._stats["signals_emitted"] += 1
            return
        
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
            "bar_id": f"{symbol}:{self.timeframe_sec}:{signal.bar.bar_id if signal.bar else 0}",
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
        # Get Config
        gate_cfg = self._mr_config.liquidity_gate # Global default
        asset_cfg = self._mr_config.assets.get(symbol)
        if asset_cfg and isinstance(asset_cfg, MRAssetConfig) and asset_cfg.liquidity_gate:
            gate_cfg = asset_cfg.liquidity_gate
        
        if not gate_cfg or not gate_cfg.enabled:
            return True # Gate disabled / not configured -> Pass
            
        kappa = self._liquidity_kappa_map.get(symbol, Decimal("0"))
        if kappa < Decimal(str(gate_cfg.kappa_min)):
             self.logger.info(f"[{symbol}] Liquidity Gate Fail: kappa={kappa} < min={gate_cfg.kappa_min}")
             return False
        
        return True

    def _on_market_tick(self, event: Message) -> None:
        if not self._enabled:
            return

        pld = event.pld
        
        # === [DEBUG PROBE: Phase 2] ===
        # Verify tick reception for enabled symbols (DOGE/XRP diagnostics)
        sym_debug = pld.get("symbol") if isinstance(pld, dict) else getattr(pld, "symbol", "unknown")
        if sym_debug in self._enabled_symbols:
            self.logger.debug(f"[{sym_debug}] MR Handler received tick payload")
        # === END DEBUG PROBE ===
        
        try:
            if isinstance(pld, dict):
                symbol = str(pld.get("symbol") or "")
                try:
                    raw_price = pld.get("price")
                    price = Decimal(str(raw_price if raw_price is not None else 0))
                except Exception:
                    price = Decimal("0")

                raw_ts = pld.get("timestamp_ms")
                if raw_ts in (None, 0, "0", ""):
                    raw_ts = pld.get("ts")
                timestamp_ms = normalize_ts_ms(raw_ts)

                raw_vol = pld.get("volume")
                if raw_vol is None:
                    bv_raw = pld.get("buy_volume") or "0"
                    sv_raw = pld.get("sell_volume") or "0"
                    raw_vol = Decimal(str(bv_raw)) + Decimal(str(sv_raw))
                volume = Decimal(str(raw_vol or 0))
            else:
                symbol = str(getattr(pld, "symbol", "") or "")
                try:
                    price = Decimal(str(aget(pld, "price", 0)))
                except Exception:
                    price = Decimal("0")

                raw_ts = aget(pld, "timestamp_ms", None)
                if raw_ts in (None, 0, "0", ""):
                    raw_ts = aget(pld, "ts", 0)
                timestamp_ms = normalize_ts_ms(raw_ts)
                raw_vol = aget(pld, "volume", None)
                if raw_vol is None:
                    raw_vol = (aget(pld, "buy_volume", 0) or 0) + (aget(pld, "sell_volume", 0) or 0)
                volume = Decimal(str(raw_vol or 0))

            if not symbol or symbol not in self._enabled_symbols:
                return
            if timestamp_ms <= 0:
                self._stats["ticks_dropped_missing_ts"] += 1
                self.mlog.debug(
                    "MR_TICK_DROP %s",
                    json.dumps(
                        {
                            "symbol": symbol,
                            "reason": "missing_ts",
                            "raw_ts": str(raw_ts) if "raw_ts" in locals() else None,
                            "counters": dict(self._stats),
                        },
                        ensure_ascii=False,
                    ),
                )
                return
            if price <= 0:
                self._stats["ticks_dropped_invalid_price"] += 1
                self.mlog.debug(
                    "MR_TICK_DROP %s",
                    json.dumps(
                        {
                            "symbol": symbol,
                            "reason": "invalid_price",
                            "price": str(price),
                            "ts_ms": timestamp_ms,
                            "counters": dict(self._stats),
                        },
                        ensure_ascii=False,
                    ),
                )
                return

            regime = self._per_symbol_regime.get(symbol)
            last_ts = self._last_tick_ts_ms.get(symbol, 0)
            if last_ts and timestamp_ms < last_ts:
                self._stats["ticks_dropped_out_of_order"] += 1
                self.mlog.debug(
                    "MR_TICK_DROP %s",
                    json.dumps(
                        {
                            "symbol": symbol,
                            "reason": "out_of_order",
                            "ts_ms": timestamp_ms,
                            "last_ts_ms": last_ts,
                            "counters": dict(self._stats),
                        },
                        ensure_ascii=False,
                    ),
                )
                return
            self._last_tick_ts_ms[symbol] = timestamp_ms
            self._stats["ticks_seen"] += 1

            self.mlog.debug(
                "MR_TICK %s",
                json.dumps(
                    {
                        "symbol": symbol,
                        "price": str(price),
                        "volume": str(volume),
                        "ts_ms": timestamp_ms,
                        "regime": regime,
                        "counters": dict(self._stats),
                    },
                    ensure_ascii=False,
                ),
            )

            signal = self.on_tick(symbol, price, volume, timestamp_ms, regime)
            if signal is None:
                return

            try:
                strat = self._strategies.get(symbol)
                if strat is not None:
                    st = strat.get_state(symbol)
                    if st.bars:
                        bar = st.bars[-1]
                        bar_end = int(getattr(bar, "end_ts_ms", 0) or 0)
                        last_counted = self._last_counted_bar_end_ts_ms.get(symbol, 0)

                        # Count bars once per new bar end timestamp.
                        if bar_end and bar_end != last_counted:
                            self._stats["bars_completed"] += 1
                            if not bool(getattr(signal, "is_signal", False)):
                                self._stats["neutral_bars"] += 1
                            self._last_counted_bar_end_ts_ms[symbol] = bar_end

                            # TAP LOG: Bar closed and ready
                            log_entry = {
                                "symbol": symbol,
                                "tf_sec": self.timeframe_sec,
                                "bar_end_ts_ms": bar.end_ts_ms,
                                "bar_id": f"{symbol}:{self.timeframe_sec}:{bar.end_ts_ms}",
                                "seq": getattr(self, 'seq_counter', 0),
                                "source": "bar_closed",
                                "why": "bar_ready"
                            }
                            print(json.dumps(log_entry), flush=True)
                            self.seq_counter = getattr(self, 'seq_counter', 0) + 1

                            self.mlog.info(
                                "MR_BAR %s",
                                json.dumps(
                                    {
                                        "symbol": symbol,
                                        "start_ts_ms": bar.start_ts_ms,
                                        "end_ts_ms": bar.end_ts_ms,
                                        "open": str(bar.open),
                                        "high": str(bar.high),
                                        "low": str(bar.low),
                                        "close": str(bar.close),
                                        "volume": str(bar.volume),
                                        "trade_count": int(bar.trade_count),
                                        "bb": {
                                            "upper": str(st.bb.upper),
                                            "mid": str(st.bb.mid),
                                            "lower": str(st.bb.lower),
                                            "width": float(st.bb.width),
                                            "pct_b": float(st.bb.pct_b),
                                        }
                                        if st.bb is not None
                                        else None,
                                        "atr": str(st.atr) if st.atr is not None else None,
                                        "rsi": float(st.rsi) if st.rsi is not None else None,
                                        "regime": regime,
                                        "kappa": float(self._liquidity_kappa_map.get(symbol, 0)),
                                        "signal_type": signal.signal_type.name,
                                        "signal_why": signal.why,
                                        "counters": dict(self._stats),
                                    },
                                    ensure_ascii=False,
                                ),
                            )
            except Exception as e:
                self._stats["bar_logging_errors"] += 1
                self.logger.warning(
                    f"MRHandler: failed to log bar state: {e}",
                    exc_info=True,
                )
        except Exception as e:
            self._stats["tick_processing_errors"] += 1
            self.logger.warning(
                f"MRHandler: failed to process EVT:MARKET_TICK_FORWARDED: {e}",
                exc_info=True,
            )
    
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
