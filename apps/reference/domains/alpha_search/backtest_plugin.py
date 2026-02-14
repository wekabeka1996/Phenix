"""
AlphaSearch Backtest Plugin — Multi-Provider Architecture
==========================================================

Shadow-mode plugin that runs alpha models alongside main strategies during backtest.

ALPHA-A3 Architecture:
- Two-phase bridge: EVT:FEATURES_CALCULATED → cache → CMD:PROCESS_STRATEGY
- Multi-provider: aurora + ta_ensemble can run simultaneously
- Per-provider virtual trader for clean feedback
- Fail-closed: missing features → score=0 + why
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from decimal import Decimal

from .alpha_model import AlphaModel, AlphaScore
from .config_models import (
    AlphaSearchConfig, 
    ProviderConfig,
    load_alpha_search_config,
    get_default_config,
)

LOG = logging.getLogger(__name__)


@dataclass
class FeatureCacheEntry:
    """Cached features for a single bar."""
    symbol: str
    tf_sec: int
    bar_close_ts: int
    features: Dict[str, Any]
    ts: int


@dataclass
class VirtualPosition:
    """Virtual position for PnL tracking."""
    provider_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    entry_price: float
    entry_ts: int
    signal_id: str
    bars_held: int = 0
    
    
@dataclass
class ProviderStats:
    """Stats for a single provider."""
    signals_generated: int = 0
    signals_long: int = 0
    signals_short: int = 0
    total_pnl: float = 0.0
    trades_closed: int = 0
    wins: int = 0


class AlphaSearchBacktestPlugin:
    """
    Multi-provider backtest plugin for alpha search.
    
    Architecture (A3):
    - Listens to EVT:FEATURES_CALCULATED → caches features by (symbol, tf_sec, bar_close_ts)
    - Listens to CMD:PROCESS_STRATEGY → reads cache, runs all enabled providers
    - Emits EVT:ALPHA_SCORE_CALCULATED with provider_id
    - Per-provider virtual trader for clean PnL feedback
    """
    
    def __init__(
        self,
        event_bus: Any,
        config: Optional[AlphaSearchConfig] = None,
        config_path: Optional[str] = None,
    ):
        """
        Initialize multi-provider plugin.
        
        Args:
            event_bus: LocalBus or compatible for event subscription
            config: Pre-loaded AlphaSearchConfig (or loads from config_path)
            config_path: Path to alpha_search.yaml (if config not provided)
        """
        self.event_bus = event_bus
        
        # Load config
        if config:
            if isinstance(config, dict):
                try:
                    self.config = AlphaSearchConfig(**config)
                except Exception as e:
                    LOG.warning(f"Failed to parse dict config for AlphaSearch: {e}. Using defaults.")
                    self.config = get_default_config()
            else:
                self.config = config
        elif config_path:
            try:
                self.config = load_alpha_search_config(config_path)
            except Exception as e:
                LOG.warning(f"Failed to load alpha_search config: {e}. Using defaults.")
                self.config = get_default_config()
        else:
            self.config = get_default_config()
        
        self.enabled = self.config.enabled
        self.shadow_mode = self.config.shadow_mode
        
        # Initialize providers
        self.providers: Dict[str, AlphaModel] = {}
        self.provider_configs: Dict[str, ProviderConfig] = {}
        self._init_providers()
        
        # Feature cache: key = (symbol, tf_sec, bar_close_ts) → FeatureCacheEntry
        self._feature_cache: Dict[Tuple[str, int, int], FeatureCacheEntry] = {}
        self._cache_max = self.config.cache.max_per_symbol
        
        # Per-provider stats
        self.provider_stats: Dict[str, ProviderStats] = {
            name: ProviderStats() for name in self.providers
        }
        
        # Virtual positions per provider
        self.open_positions: Dict[str, List[VirtualPosition]] = {
            name: [] for name in self.providers
        }
        self.closed_positions: Dict[str, List[Dict[str, Any]]] = {
            name: [] for name in self.providers
        }
        
        # Signal counter for IDs
        self._signal_counter = 0
        
        # Cache hit/miss tracking (for validation)
        self._cache_hits = 0
        self._cache_misses = 0
        
        if self.enabled:
            self._register_listeners()
            LOG.info(
                f"AlphaSearchBacktestPlugin initialized: "
                f"providers={list(self.providers.keys())}, shadow_mode={self.shadow_mode}"
            )
    
    def _init_providers(self) -> None:
        """Initialize alpha model providers from config."""
        for name, cfg in self.config.providers.items():
            if not cfg.enabled:
                LOG.debug(f"Provider '{name}' is disabled, skipping")
                continue
            
            try:
                model = self._create_provider_model(name, cfg)
                if model:
                    self.providers[name] = model
                    self.provider_configs[name] = cfg
                    LOG.info(f"Initialized provider: {name}")
            except Exception as e:
                LOG.warning(f"Failed to init provider '{name}': {e}")
    
    def _create_provider_model(self, name: str, cfg: ProviderConfig) -> Optional[AlphaModel]:
        """Create alpha model for a provider."""
        if cfg.adapter:
            # Aurora adapter
            from .models.aurora_adapter import AuroraAlphaAdapter
            return AuroraAlphaAdapter(
                essential_features=cfg.adapter.essential_features,
                scoring_version=cfg.adapter.scoring_version,
            )
        elif cfg.ensemble:
            # TA ensemble
            from .ensemble import EnsembleModel, EnsembleConfig
            from .models.momentum import MomentumAlphaModel
            from .models.mean_reversion import MeanReversionAlphaModel
            from .models.volatility import VolatilityAlphaModel
            
            models = {}
            model_map = {
                "mean_reversion_v1": MeanReversionAlphaModel,
                "momentum_v1": MomentumAlphaModel,
                "volatility_v1": VolatilityAlphaModel,
            }
            
            for model_name, model_cfg in cfg.ensemble.models.items():
                if model_cfg.enabled and model_name in model_map:
                    models[model_name] = model_map[model_name]()
            
            if not models:
                LOG.warning(f"No enabled models for ensemble '{name}'")
                return None
            
            ensemble_cfg = EnsembleConfig(
                rebalance_frequency_days=cfg.ensemble.rebalance_frequency_days,
                performance_window_days=cfg.ensemble.performance_window_days,
                risk_adjustment=cfg.ensemble.risk_adjustment,
            )
            return EnsembleModel(config=ensemble_cfg, models=models)
        else:
            LOG.warning(f"Provider '{name}' has no adapter or ensemble config")
            return None
    
    def _register_listeners(self) -> None:
        """Register event listeners for two-phase bridge."""
        if hasattr(self.event_bus, "listen"):
            # Phase 1: Cache features
            self.event_bus.listen(
                self.config.triggers.feature_event, 
                self._on_features_cache
            )
            # Phase 2: Score on decision event
            self.event_bus.listen(
                self.config.triggers.decision_event, 
                self._on_decision_score
            )
            # Trade tracking for virtual PnL
            self.event_bus.listen("EVT:TRADE_EXECUTED", self._on_trade)
            
            LOG.debug(
                f"AlphaSearch listeners: {self.config.triggers.feature_event} → cache, "
                f"{self.config.triggers.decision_event} → score"
            )
    
    # =========================================================================
    # Phase 1: Cache features on EVT:FEATURES_CALCULATED
    # =========================================================================
    
    def _on_features_cache(self, event: Any, **kwargs) -> None:
        """
        Cache features from EVT:FEATURES_CALCULATED.
        
        Key = (symbol, tf_sec, bar_close_ts)
        """
        if not self.enabled:
            return
        
        payload = self._extract_payload(event)
        if not payload:
            return
        
        symbol = payload.get("symbol", "")
        features = payload.get("features", {})
        tf_sec = payload.get("tf_sec", 300)
        ts = payload.get("ts", 0)
        
        # Get bar_close_ts from bar or payload
        bar_raw = payload.get("bar")
        bar = bar_raw if isinstance(bar_raw, dict) else {}
        bar_close_ts = bar.get("close_ts") or bar.get("ts") or payload.get("bar_close_ts") or ts
        
        if not symbol or not features:
            return
        
        # Cache entry — normalize bar_close_ts to milliseconds
        bar_close_ts = self._normalize_timestamp(bar_close_ts)
        key = (symbol, tf_sec, bar_close_ts)
        self._feature_cache[key] = FeatureCacheEntry(
            symbol=symbol,
            tf_sec=tf_sec,
            bar_close_ts=bar_close_ts,
            features=features,
            ts=ts,
        )
        
        # Prune old entries for this symbol
        self._prune_cache(symbol)
        
        LOG.debug(f"[{symbol}] Cached features for bar_close_ts={bar_close_ts}")
    
    def _prune_cache(self, symbol: str) -> None:
        """Remove old cache entries for symbol, keep max_per_symbol."""
        symbol_keys = [k for k in self._feature_cache.keys() if k[0] == symbol]
        if len(symbol_keys) > self._cache_max:
            # Sort by bar_close_ts and remove oldest
            symbol_keys.sort(key=lambda k: k[2])
            for old_key in symbol_keys[:-self._cache_max]:
                del self._feature_cache[old_key]
    
    # =========================================================================
    # Phase 2: Score on CMD:PROCESS_STRATEGY
    # =========================================================================
    
    def _on_decision_score(self, event: Any, **kwargs) -> None:
        """
        Run scoring on CMD:PROCESS_STRATEGY using cached features.
        
        This is the decision boundary — same as Aurora.
        """
        if not self.enabled or not self.providers:
            return
        
        payload = self._extract_payload(event)
        if not payload:
            return
        
        symbol = payload.get("symbol", "")
        tf_sec = payload.get("tf_sec", 300)
        bar_close_ts = self._normalize_timestamp(payload.get("bar_close_ts", 0))
        
        if not symbol:
            return
        
        # Find cached features
        cache_key = (symbol, tf_sec, bar_close_ts)
        cache_entry = self._feature_cache.get(cache_key)
        
        if not cache_entry:
            # Try with fuzzy match if exact match fails
            cache_entry = self._find_best_cache_match(symbol, tf_sec, bar_close_ts)
        
        if not cache_entry:
            # Fail-closed: no features available
            self._cache_misses += 1
            for provider_id, cfg in self.provider_configs.items():
                if cfg.fail_closed and self._is_symbol_allowed(symbol, cfg):
                    self._emit_fail_closed_score(provider_id, symbol, tf_sec, bar_close_ts)
            return
        
        # Cache hit!
        self._cache_hits += 1
        features = cache_entry.features
        
        # Run each enabled provider
        for provider_id, model in self.providers.items():
            cfg = self.provider_configs[provider_id]
            
            # Check symbol allowlist
            if not self._is_symbol_allowed(symbol, cfg):
                continue
            
            # Get current price for virtual trader
            current_price = self._get_price_from_features(features)
            
            # Calculate score
            try:
                score = model.calculate_alpha(
                    symbol=symbol,
                    market_data={"close": current_price},
                    features=features,
                    context={"mode": "backtest", "shadow": self.shadow_mode}
                )
                
                self._process_score(
                    provider_id=provider_id,
                    symbol=symbol,
                    score=score,
                    threshold=cfg.threshold,
                    current_price=current_price,
                    current_ts=cache_entry.ts,
                    tf_sec=tf_sec,
                    bar_close_ts=bar_close_ts,
                )
                
            except Exception as e:
                LOG.warning(f"[{symbol}] Provider {provider_id} error: {e}")
                if cfg.fail_closed:
                    self._emit_fail_closed_score(provider_id, symbol, tf_sec, bar_close_ts)
    
    def _find_best_cache_match(
        self, 
        symbol: str, 
        tf_sec: int, 
        bar_close_ts: int
    ) -> Optional[FeatureCacheEntry]:
        """Find closest cache entry if exact match not found."""
        if self.config.cache.require_same_bar_close_ts:
            return None
        
        # Find entries for this symbol and tf_sec
        candidates = [
            (k, v) for k, v in self._feature_cache.items()
            if k[0] == symbol and k[1] == tf_sec
        ]
        
        if not candidates:
            return None
        
        # Return most recent
        candidates.sort(key=lambda x: x[0][2], reverse=True)
        return candidates[0][1]
    
    def _is_symbol_allowed(self, symbol: str, cfg: ProviderConfig) -> bool:
        """Check if symbol is in provider's allowlist."""
        if cfg.symbols is None:
            return True  # None means all symbols
        return symbol in cfg.symbols
    
    def _process_score(
        self,
        provider_id: str,
        symbol: str,
        score: AlphaScore,
        threshold: float,
        current_price: float,
        current_ts: int,
        tf_sec: int,
        bar_close_ts: int,
    ) -> None:
        """Process calculated score: emit event, update virtual trader."""
        stats = self.provider_stats[provider_id]
        stats.signals_generated += 1
        
        if score.score > Decimal(str(threshold)):
            stats.signals_long += 1
        elif score.score < Decimal(str(-threshold)):
            stats.signals_short += 1
        
        # Generate signal ID
        self._signal_counter += 1
        signal_id = f"{provider_id}_sig_{self._signal_counter}"
        
        # Emit event
        self._emit_score_event(
            provider_id=provider_id,
            symbol=symbol,
            score=score,
            threshold=threshold,
            tf_sec=tf_sec,
            bar_close_ts=bar_close_ts,
            signal_id=signal_id,
        )
        
        # Virtual trader logic
        if self.config.virtual_trader.enabled and current_price > 0:
            self._manage_virtual_positions(
                provider_id=provider_id,
                symbol=symbol,
                current_price=current_price,
                current_ts=current_ts,
            )
            
            # Entry logic
            if abs(score.score) > Decimal(str(threshold)):
                self._maybe_open_virtual_position(
                    provider_id=provider_id,
                    symbol=symbol,
                    score=score,
                    current_price=current_price,
                    current_ts=current_ts,
                    signal_id=signal_id,
                )
    
    def _emit_score_event(
        self,
        provider_id: str,
        symbol: str,
        score: AlphaScore,
        threshold: float,
        tf_sec: int,
        bar_close_ts: int,
        signal_id: str,
    ) -> None:
        """Emit EVT:ALPHA_SCORE_CALCULATED with provider_id."""
        payload = {
            "provider_id": provider_id,
            "model_name": score.model_name,
            "symbol": symbol,
            "tf_sec": tf_sec,
            "bar_close_ts": bar_close_ts,
            "score": float(score.score),
            "confidence": float(score.confidence),
            "threshold": threshold,
            "shadow": self.shadow_mode,
            "signal_id": signal_id,
            "why": score.why[:5],  # Limit why chain
            "features_used": score.features_used,
        }
        
        self.event_bus.emit(
            event_name=self.config.triggers.emit_event,
            payload=payload,
            why=f"alpha_search_{provider_id}"
        )
        
        LOG.debug(
            f"[{symbol}] {provider_id}: score={score.score:.4f} "
            f"conf={score.confidence:.4f} thr={threshold}"
        )
    
    def _emit_fail_closed_score(
        self, 
        provider_id: str, 
        symbol: str, 
        tf_sec: int, 
        bar_close_ts: int
    ) -> None:
        """Emit fail-closed score (score=0) when features unavailable."""
        payload = {
            "provider_id": provider_id,
            "model_name": f"{provider_id}_fail_closed",
            "symbol": symbol,
            "tf_sec": tf_sec,
            "bar_close_ts": bar_close_ts,
            "score": 0.0,
            "confidence": 0.0,
            "threshold": self.provider_configs[provider_id].threshold,
            "shadow": True,
            "signal_id": "",
            "why": ["fail_closed:missing_features_for_bar"],
            "features_used": [],
        }
        
        self.event_bus.emit(
            event_name=self.config.triggers.emit_event,
            payload=payload,
            why=f"alpha_search_{provider_id}_fail_closed"
        )
    
    # =========================================================================
    # Virtual Trader
    # =========================================================================
    
    def _manage_virtual_positions(
        self,
        provider_id: str,
        symbol: str,
        current_price: float,
        current_ts: int,
    ) -> None:
        """Check exits for open virtual positions."""
        positions = self.open_positions[provider_id]
        exit_cfg = self.config.virtual_trader.exit
        
        for i in range(len(positions) - 1, -1, -1):
            pos = positions[i]
            if pos.symbol != symbol:
                continue
            
            pos.bars_held += 1
            duration_sec = (current_ts - pos.entry_ts) / 1000.0
            
            # Exit conditions
            should_exit = (
                pos.bars_held >= exit_cfg.max_bars or 
                duration_sec >= exit_cfg.max_hold_sec
            )
            
            if should_exit:
                self._close_virtual_position(
                    provider_id=provider_id,
                    pos=pos,
                    exit_price=current_price,
                    exit_ts=current_ts,
                )
                positions.pop(i)
    
    def _maybe_open_virtual_position(
        self,
        provider_id: str,
        symbol: str,
        score: AlphaScore,
        current_price: float,
        current_ts: int,
        signal_id: str,
    ) -> None:
        """Open virtual position if allowed."""
        positions = self.open_positions[provider_id]
        max_per_symbol = self.config.virtual_trader.max_positions_per_symbol
        
        # Check existing positions for this symbol
        existing = sum(1 for p in positions if p.symbol == symbol)
        if existing >= max_per_symbol:
            return
        
        side = "BUY" if score.score > 0 else "SELL"
        
        positions.append(VirtualPosition(
            provider_id=provider_id,
            symbol=symbol,
            side=side,
            entry_price=current_price,
            entry_ts=current_ts,
            signal_id=signal_id,
        ))
        
        LOG.debug(f"[{symbol}] {provider_id} OPEN VIRTUAL {side} @ {current_price}")
    
    def _close_virtual_position(
        self,
        provider_id: str,
        pos: VirtualPosition,
        exit_price: float,
        exit_ts: int,
    ) -> None:
        """Close virtual position and record PnL."""
        # Calculate PnL
        if pos.side == "BUY":
            pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        else:
            pnl_pct = (pos.entry_price - exit_price) / pos.entry_price
        
        notional_pnl = pnl_pct * self.config.virtual_trader.notional_size
        
        # Update stats
        stats = self.provider_stats[provider_id]
        stats.total_pnl += notional_pnl
        stats.trades_closed += 1
        if notional_pnl > 0:
            stats.wins += 1
        
        # Record closed position
        closed_record = {
            "provider_id": provider_id,
            "symbol": pos.symbol,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "entry_ts": pos.entry_ts,
            "exit_ts": exit_ts,
            "bars_held": pos.bars_held,
            "pnl": notional_pnl,
            "signal_id": pos.signal_id,
        }
        self.closed_positions[provider_id].append(closed_record)
        
        LOG.debug(
            f"[{pos.symbol}] {provider_id} CLOSE VIRTUAL {pos.side} "
            f"PnL={notional_pnl:.2f} (held {pos.bars_held} bars)"
        )
    
    # =========================================================================
    # Trade Tracking (for correlation with real trades)
    # =========================================================================
    
    def _on_trade(self, event: Any, **kwargs) -> None:
        """Track actual trades for correlation analysis."""
        # This is informational — we don't modify virtual positions based on real trades
        pass
    
    # =========================================================================
    # Utilities
    # =========================================================================
    
    def _extract_payload(self, event: Any) -> Optional[Dict[str, Any]]:
        """Extract payload from event object."""
        if hasattr(event, "pld"):
            payload = event.pld
        else:
            payload = event
        
        if not isinstance(payload, dict):
            return None
        return payload
    
    def _get_price_from_features(self, features: Dict[str, Any]) -> float:
        """Extract price from features dict."""
        for key in ["close", "price", "last_price"]:
            if key in features and features[key]:
                try:
                    return float(features[key])
                except (ValueError, TypeError):
                    pass
        return 0.0
    
    def _normalize_timestamp(self, ts: int) -> int:
        """
        Normalize timestamp to milliseconds.
        
        Handles:
        - Already ms: ts >= 10^12 → return as-is
        - Seconds: ts < 10^12 → multiply by 1000
        """
        if ts <= 0:
            return ts
        if ts < 10**12:
            # Looks like seconds, convert to ms
            return ts * 1000
        return ts
    
    # =========================================================================
    # Summary / Stats
    # =========================================================================
    
    def get_summary(self) -> Dict[str, Any]:
        """Get plugin summary for backtest report."""
        provider_summaries = {}
        
        for name, stats in self.provider_stats.items():
            win_rate = stats.wins / stats.trades_closed if stats.trades_closed > 0 else 0.0
            provider_summaries[name] = {
                "signals_generated": stats.signals_generated,
                "signals_long": stats.signals_long,
                "signals_short": stats.signals_short,
                "signals_neutral": stats.signals_generated - stats.signals_long - stats.signals_short,
                "virtual_trader": {
                    "total_pnl": round(stats.total_pnl, 2),
                    "trades_closed": stats.trades_closed,
                    "win_rate": round(win_rate, 4),
                    "open_positions": len(self.open_positions.get(name, [])),
                },
            }
        
        # Cache stats with miss_rate_pct for validation
        total_cache_lookups = self._cache_hits + self._cache_misses
        miss_rate_pct = (
            round(self._cache_misses / total_cache_lookups * 100, 2) 
            if total_cache_lookups > 0 else 0.0
        )
        
        return {
            "enabled": self.enabled,
            "mode": "shadow" if self.shadow_mode else "live",
            "providers": list(self.providers.keys()),
            "provider_stats": provider_summaries,
            "cache": {
                "size": len(self._feature_cache),
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "miss_rate_pct": miss_rate_pct,
            },
        }
    
    def shutdown(self, run_dir: Optional[str] = None) -> None:
        """Cleanup on shutdown and optionally generate diagnostics."""
        total_signals = sum(s.signals_generated for s in self.provider_stats.values())
        total_pnl = sum(s.total_pnl for s in self.provider_stats.values())
        LOG.info(
            f"AlphaSearch shutdown: {total_signals} signals, "
            f"virtual PnL={total_pnl:.2f}, providers={list(self.providers.keys())}"
        )
        
        # DIAGNOSTICS-01: Generate post-run diagnostics if run_dir provided
        if run_dir:
            try:
                from tools.backtest_diagnostics import generate_backtest_diagnostics, save_diagnostics
                diagnostics = generate_backtest_diagnostics(run_dir)
                output_path = save_diagnostics(run_dir, diagnostics)
                LOG.info(f"Diagnostics saved to: {output_path}")
            except Exception as e:
                LOG.warning(f"Failed to generate diagnostics: {e}")


# Backwards compatibility: factory function
def create_plugin_from_config(
    event_bus: Any,
    config_path: str = "config/alpha_search.yaml",
) -> AlphaSearchBacktestPlugin:
    """Create plugin from config file path."""
    return AlphaSearchBacktestPlugin(event_bus=event_bus, config_path=config_path)
