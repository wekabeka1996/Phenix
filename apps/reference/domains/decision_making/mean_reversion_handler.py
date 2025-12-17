"""
Mean Reversion Decision Handler.

Track B: Integrates Mean Reversion 1m Strategy into DecisionMaking workflow.

This handler:
1. Receives tick data via on_tick() from FeatureEngineering
2. Aggregates ticks into 1m bars via BarResampler
3. Computes MR signals via MeanReversion1mStrategy
4. Emits EVT:TRADE_INTENT_PROPOSED when signal is actionable

Feature flag: enabled via config.mean_reversion_1m.enabled (default: false)
"""

import logging
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional, TYPE_CHECKING

from vfoundation.core.protocol import Message

# Import MR strategy components
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MeanReversion1mStrategy,
    MRStrategyConfig,
    MRSignal,
    MRSignalType,
)
from apps.reference.config_models import (
    MeanReversion1mStrategyConfig,
    MRStrategyParamsConfig,
    MRAssetConfig,
)

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


LOG = logging.getLogger(__name__)


class MeanReversionHandler:
    """
    Handler for Mean Reversion 1m strategy integration with DecisionMaking.
    
    Workflow:
    1. on_tick() - receives tick from FeatureEngineering
    2. Strategy processes tick → bar resampling → MR signal
    3. If signal is actionable → emit EVT:TRADE_INTENT_PROPOSED
    
    Feature flag: Controlled by mean_reversion_1m.enabled config.
    """
    
    def __init__(
        self,
        fsm: "FSMCore",
        config: Dict[str, Any],
        decision_making: Any,  # DecisionMaking instance for intent emission
    ) -> None:
        """
        Initialize Mean Reversion handler.
        
        Args:
            fsm: FSMCore instance for event emission
            config: Full application config (dict or Pydantic)
            decision_making: Parent DecisionMaking instance
        """
        self.fsm = fsm
        self.config = config
        self.dm = decision_making
        self.logger = LOG.getChild("MRHandler")
        
        # Parse MR config
        self._mr_config: Optional[MeanReversion1mStrategyConfig] = None
        self._enabled: bool = False
        self._enabled_symbols: set[str] = set()
        
        self._parse_config()
        
        # Initialize strategy per symbol if enabled
        self._strategies: Dict[str, MeanReversion1mStrategy] = {}
        if self._enabled:
            self._init_strategies()
        
        # Signal tracking for logging
        self._signal_counts: Dict[str, int] = {}
        self._last_signal_time: Dict[str, float] = {}
        
        self.logger.info(
            f"MeanReversionHandler initialized: enabled={self._enabled}, "
            f"symbols={list(self._enabled_symbols)}, "
            f"strategies={list(self._strategies.keys())}"
        )
    
    def _get_mr_assigned_symbols(self) -> set[str]:
        """
        Get symbols that have mean_reversion_1m assigned in strategies_registry.
        
        CFG-STRATEGIES-SSOT-02-MR-HANDLER-STRICT-CONTRACT:
        MR is "potentially active" if assigned in registry OR enabled=True in config.
        """
        mr_symbols = set()
        
        if hasattr(self.config, 'strategies_registry') and self.config.strategies_registry:
            assignments = self.config.strategies_registry.assignments
            for symbol, strategies in assignments.items():
                if "mean_reversion_1m" in strategies:
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
        if hasattr(self.config, 'mean_reversion_1m') and self.config.mean_reversion_1m is not None:
            self._mr_config = self.config.mean_reversion_1m
            self._enabled = self._mr_config.enabled
        else:
            # MR config missing
            if mr_assigned_symbols:
                # FAIL-CLOSED: MR assigned but config missing
                raise ValueError(
                    f"❌ CRITICAL: mean_reversion_1m assigned to symbols {mr_assigned_symbols} "
                    f"but config.mean_reversion_1m is missing or invalid. "
                    f"Required: config.mean_reversion_1m (typed Pydantic) must be present."
                )
            else:
                # MR not assigned and config missing → disabled (fail-closed, no noise)
                self.logger.info("Mean Reversion 1m: config missing, handler disabled (no assignment)")
                self._enabled = False
                return
        
        if not self._enabled:
            self.logger.info("Mean Reversion 1m strategy is disabled by config")
            return
        
        # Collect enabled symbols
        if self._mr_config and self._mr_config.assets:
            for symbol, asset_cfg in self._mr_config.assets.items():
                if isinstance(asset_cfg, MRAssetConfig):
                    if asset_cfg.enabled:
                        self._enabled_symbols.add(symbol)
                elif isinstance(asset_cfg, dict):
                    if asset_cfg.get('enabled', False):
                        self._enabled_symbols.add(symbol)
        
        if not self._enabled_symbols:
            self.logger.warning("MR 1m enabled but no symbols are enabled in assets config")
            self._enabled = False
            
    def _init_strategies(self) -> None:
        """Initialize separate strategy instance per symbol with overrides."""
        if not self._mr_config:
            return

        timeframe_sec = self._mr_config.timeframe_sec or 60
        
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

        for symbol in self._enabled_symbols:
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
            config.allowed_regimes = list(self._mr_config.allowed_regimes or [])
            
            # Apply asset-specific overrides
            asset_cfg = self._mr_config.assets.get(symbol)
            if asset_cfg and getattr(asset_cfg, 'strategy', None):
                strat_override = asset_cfg.strategy
                # Check for overrides
                if strat_override.bb_window is not None: config.bb_window = strat_override.bb_window
                if strat_override.bb_num_std is not None: config.bb_num_std = strat_override.bb_num_std
                if strat_override.min_bb_width is not None: config.min_bb_width = Decimal(str(strat_override.min_bb_width))
                if strat_override.cooldown_sec is not None: config.cooldown_sec = strat_override.cooldown_sec
                if strat_override.sl_atr_mult is not None: config.sl_atr_mult = Decimal(str(strat_override.sl_atr_mult))
                if strat_override.allowed_regimes is not None: config.allowed_regimes = list(strat_override.allowed_regimes)
                # Add other overrides as needed...

            self._strategies[symbol] = MeanReversion1mStrategy(
                config=config,
                timeframe_sec=timeframe_sec,
                regime_sizing=regime_sizing
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
        
        # Update regime if provided
        if regime:
            strategy.set_regime(symbol, regime)
        
        # Process tick through strategy
        signal = strategy.on_tick(symbol, price, volume, timestamp_ms)
        
        if signal and signal.is_signal:
            self._handle_signal(signal)
        
        return signal
    
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
    
    def _handle_signal(self, signal: MRSignal) -> None:
        """
        Handle actionable MR signal.
        
        Emits EVT:TRADE_INTENT_PROPOSED via DecisionMaking.
        """
        symbol = signal.symbol
        
        # Track signal
        self._signal_counts[symbol] = self._signal_counts.get(symbol, 0) + 1
        self._last_signal_time[symbol] = time.time()
        
        self.logger.info(
            f"[{symbol}] MR Signal: {signal.signal_type.name} "
            f"confidence={signal.confidence:.2f} "
            f"entry={signal.entry_price} stop={signal.stop_price} target={signal.target_price} "
            f"why={signal.why}"
        )
        
        # Build TradeIntent payload
        rid = str(uuid.uuid4())
        side = signal.side  # "BUY" or "SELL"
        
        # Get per-asset config for this symbol
        sl_pct = self._get_asset_sl_pct(symbol)
        position_size_usd = self._get_position_size_usd(symbol)
        
        # FAIL-CLOSED: missing position_size → block signal
        if position_size_usd is None:
            self.logger.warning(
                f"[{symbol}] MR_SIGNAL_BLOCKED: MR_REJECT:missing_position_size "
                f"(risk.position_size_usd not configured)"
            )
            return
        
        # FIX: Calculate qty = position_size_usd / entry_price
        # This is required for execution_position to know how much to trade
        qty = Decimal("0")
        if signal.entry_price and signal.entry_price > 0:
            qty = position_size_usd / signal.entry_price
            # Apply regime sizing multiplier if available
            if signal.mr_params and signal.mr_params.sizing_mult:
                qty = qty * Decimal(str(signal.mr_params.sizing_mult))
        
        # Calculate SL price from sl_pct if configured
        if sl_pct is not None:
            if side == "BUY":
                stop_price = signal.entry_price * (Decimal("1") - Decimal(str(sl_pct)))
            else:
                stop_price = signal.entry_price * (Decimal("1") + Decimal(str(sl_pct)))
        else:
            stop_price = signal.stop_price
        
        trade_intent = {
            "symbol": symbol,
            "side": side,
            "entry_price": str(signal.entry_price),
            "stop_price": str(stop_price),
            "target_price": str(signal.target_price),
            "position_size_usd": float(position_size_usd),
            "qty": str(qty),  # FIX: Include calculated qty
            "strategy": "mean_reversion_1m",
            "regime": signal.flat_regime.name if signal.flat_regime else "UNKNOWN",
            "confidence": float(signal.confidence),
            "rid": rid,
            "timestamp_ms": signal.timestamp_ms,
            "why": signal.why,
            "mr_params": {
                "sizing_mult": float(signal.mr_params.sizing_mult) if signal.mr_params else 1.0,
                "stop_mult": float(signal.mr_params.stop_mult) if signal.mr_params else 1.0,
                "target_mult": float(signal.mr_params.target_mult) if signal.mr_params else 1.0,
            },
        }
        
        # Emit via FSM
        self.fsm.emit(
            "EVT:TRADE_INTENT_PROPOSED",
            payload=trade_intent,
            why=f"MR_{signal.signal_type.name}",
            data_ref=[f"mr_signal_{rid}"]
        )
        
        self.logger.info(
            f"[{symbol}] EVT:TRADE_INTENT_PROPOSED emitted: {side} @ {signal.entry_price}"
        )
    
    def _get_asset_sl_pct(self, symbol: str) -> Optional[float]:
        """Get SL % for symbol from per-asset config."""
        if not self._mr_config or not self._mr_config.assets:
            return None
        
        asset_cfg = self._mr_config.assets.get(symbol)
        if asset_cfg is None:
            return None
        
        if isinstance(asset_cfg, MRAssetConfig):
            return asset_cfg.sl_pct
        elif isinstance(asset_cfg, dict):
            return asset_cfg.get('sl_pct')
        
        return None
    
    def _get_position_size_usd(self, symbol: str) -> Optional[Decimal]:
        """
        Get position size from risk config.
        
        CFG-STRATEGIES-SSOT-02-MR-HANDLER-STRICT-CONTRACT:
        - NO silent defaults (no fallback to 100)
        - Return None if missing → caller must handle (fail-closed)
        """
        if not self._mr_config or not self._mr_config.risk:
            return None
        
        risk_cfg = self._mr_config.risk
        if hasattr(risk_cfg, 'position_size_usd'):
            return Decimal(str(risk_cfg.position_size_usd))
        
        return None
    
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
