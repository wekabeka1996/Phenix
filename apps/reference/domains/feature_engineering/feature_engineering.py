"""
FeatureEngineering FSM Handler - Thin Event Handler.

FTR-04: Refactored for Separation of Concerns.

This module contains:
- FeatureEngineering: FSM event handler class
- Event listening, state management, feature emission
- Delegates all calculations to FeatureCalculationEngine

Architecture (FTR-04 Split):
- types.py: HotState, ColdState, SymbolFeatureState, FeatureEngineeringConfig
- calculation_engine.py: FeatureCalculationEngine with all _update_* and _compute_*
- feature_engineering.py (THIS FILE): Thin FSM handler only

Features computed (9 base + 3 V2):
- Base: OBI, TFI, delta_price, liquidity_kappa, absorption (placeholder)
- Phase 1: ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync
- V2 (FTR-03): volume_zscore, large_trade_imbalance, spread_bps
"""

import decimal
import json
import logging
from typing import Dict, Any, TYPE_CHECKING, Optional
from collections import deque

from vfoundation.core.protocol import Message

# FTR-04: Import types from types.py
from apps.reference.domains.feature_engineering.types import (
    HotState,
    ColdState,
    SymbolFeatureState,
    FeatureEngineeringConfig,
)

# FTR-04: Import calculation engine
from apps.reference.domains.feature_engineering.calculation_engine import (
    FeatureCalculationEngine,
)

if TYPE_CHECKING:
    from vfoundation.core import FSMCore
    from apps.reference.config_models import (
        AuroraConfig,
        FeatureEngineeringDomainConfig,
    )
    from apps.reference.domain_config import DomainConfigResolver


class FeatureEngineering:
    """
    Feature Engineering domain component.
    
    FTR-04: Thin FSM handler. All calculations delegated to FeatureCalculationEngine.
    
    Transforms raw market tick data into normalized features for downstream
    decision making and risk assessment.
    """
    
    def __init__(
        self, 
        fsm: "FSMCore", 
        config: Any,
        feature_store: Optional[Any] = None
    ) -> None:
        """
        Initialize FeatureEngineering.
        
        Args:
            fsm: FSM core for event handling
            config: Configuration (DomainConfigResolver, AuroraConfig, or dict)
            feature_store: Optional feature storage backend
        """
        self.fsm = fsm
        self.feature_store = feature_store
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Initialize typed config wrapper (replaces 100+ lines of try/except!)
        self.cfg = FeatureEngineeringConfig(config)
        
        # FTR-04: Initialize calculation engine
        self._engine = FeatureCalculationEngine(self.cfg)
        
        # State tracking
        self.last_tick_data: Dict[str, dict] = {}
        self.symbol_states: Dict[str, SymbolFeatureState] = {}
        
        # Anchor price buffers for macro_sync
        self.anchor_prices: Dict[str, deque] = {
            anchor: deque(maxlen=self.cfg.macro_sync_window)
            for anchor in self.cfg.macro_sync_anchors
        }
        
        # Register event listener
        self.fsm.listen("EVT:MARKET_TICK_RECEIVED", self.on_market_tick)
        
        # FTR-05: Register Futures event listeners (config-gated)
        if self.cfg.futures_enabled:
            self.fsm.listen("EVT:FUNDING_UPDATE", self._on_funding_update)
            self.fsm.listen("EVT:OI_UPDATE", self._on_oi_update)
            self.logger.info("Futures features enabled: listening for EVT:FUNDING_UPDATE, EVT:OI_UPDATE")
        
        self.logger.info(
            f"FeatureEngineering initialized: "
            f"new_metrics={self.cfg.enable_new_metrics}, "
            f"ema={self.cfg.ema_period_short}/{self.cfg.ema_period_long}, "
            f"macro_sync={self.cfg.macro_sync_enabled}, "
            f"futures={self.cfg.futures_enabled}"
        )

    def update_anchor_price(self, anchor: str, price: str) -> None:
        """Update anchor price buffer directly from MarketData."""
        try:
            if anchor in self.anchor_prices:
                self.anchor_prices[anchor].append(decimal.Decimal(price))
                self.logger.debug(f"Updated anchor {anchor} price: {price}")
        except Exception as e:
            self.logger.error(f"Error updating anchor price {anchor}: {e}")

    def _get_symbol_state(self, symbol: str) -> SymbolFeatureState:
        """
        Get or create state for a symbol.
        
        Returns the SymbolFeatureState, initializing it if needed.
        """
        if symbol not in self.symbol_states:
            # Create HotState with proper deque maxlen
            hot = HotState(
                ema_short=None,
                ema_long=None,
                ema_short_alpha=self.cfg.ema_short_alpha,
                ema_long_alpha=self.cfg.ema_long_alpha,
                vol_window_start_ts=None,
                vol_current_ts=None,
                vol_window_trades=0.0,
                vol_hist=deque(maxlen=self.cfg.volume_sma_length),
                vol_stats=(0, 0.0, 0.0),  # FTR-03: Welford stats
                range_window_start_ts=None,
                range_min=None,
                range_max=None,
                range_hist=deque(maxlen=self.cfg.volatility_sma_length),  # Now float for Welford
                range_stats=(0, 0.0, 0.0),  # FTR-03: Welford stats
                returns_buffer=deque(maxlen=self.cfg.macro_sync_window),
                prev_price=None,
            )
            cold = ColdState()
            self.symbol_states[symbol] = SymbolFeatureState(hot=hot, cold=cold)
        
        return self.symbol_states[symbol]

    def _init_symbol_state(self, symbol: str) -> None:
        """Initialize state for a new symbol (backward compat wrapper)."""
        self._get_symbol_state(symbol)

    # =========================================================================
    # DELEGATED METHODS (FTR-04: Keep old names for backward compatibility)
    # These call calculation engine methods with appropriate state
    # =========================================================================

    def _update_ema(self, symbol: str, price: decimal.Decimal) -> None:
        """Update EMA values for the symbol."""
        state = self._get_symbol_state(symbol).hot
        self._engine.update_ema(state, price)

    def _compute_ema_bias(self, symbol: str) -> decimal.Decimal:
        """Compute EMA bias = (EMA_short - EMA_long) / EMA_long, normalized to [0,1]."""
        state = self._get_symbol_state(symbol).hot
        return self._engine.compute_ema_bias(state)

    def _update_volume_spike(self, symbol: str, current_tick: dict) -> None:
        """Update volume window with real volumes."""
        state = self._get_symbol_state(symbol).hot
        self._engine.update_volume_spike(state, current_tick)

    def _compute_volume_spike(self, symbol: str) -> decimal.Decimal:
        """Compute volume spike = vol_window / mean(vol), normalized to [0,1]."""
        state = self._get_symbol_state(symbol).hot
        return self._engine.compute_volume_spike(state)
    
    def _compute_volume_zscore(self, symbol: str) -> decimal.Decimal:
        """Compute volume Z-score, normalized via tanh."""
        state = self._get_symbol_state(symbol).hot
        return self._engine.compute_volume_zscore(state)

    def _update_volatility_state(self, symbol: str, price: decimal.Decimal, current_tick: dict) -> None:
        """Update volatility range window."""
        state = self._get_symbol_state(symbol).hot
        self._engine.update_volatility_state(state, price, current_tick)

    def _compute_volatility_state(self, symbol: str) -> decimal.Decimal:
        """Compute volatility state = range / mean(range), normalized to [0,1]."""
        state = self._get_symbol_state(symbol).hot
        return self._engine.compute_volatility_state(state)

    def _compute_spread_bps(
        self, 
        best_bid: decimal.Decimal, 
        best_ask: decimal.Decimal,
        mid_price: decimal.Decimal,
    ) -> decimal.Decimal:
        """Compute bid-ask spread in basis points."""
        return self._engine.compute_spread_bps(best_bid, best_ask, mid_price)
    
    def _compute_large_trade_imbalance(self, current_tick: dict) -> decimal.Decimal:
        """Compute large trade imbalance from buy/sell trade counts."""
        return self._engine.compute_large_trade_imbalance(current_tick)

    def _compute_depth_imbalance(self, bid_size: decimal.Decimal, ask_size: decimal.Decimal) -> decimal.Decimal:
        """Compute depth imbalance with Laplace smoothing, normalized to [0,1]."""
        return self._engine.compute_depth_imbalance(bid_size, ask_size)

    def _update_macro_sync_buffer(self, symbol: str, price: decimal.Decimal, time_diff_ms: int) -> None:
        """Update return for macro_sync correlation."""
        state = self._get_symbol_state(symbol).hot
        self._engine.update_macro_sync_buffer(state, price, time_diff_ms)

    def _compute_macro_sync(self, symbol: str) -> decimal.Decimal:
        """Compute macro_sync = correlation with anchor returns, normalized to [0,1]."""
        state = self._get_symbol_state(symbol).hot
        return self._engine.compute_macro_sync(state, self.anchor_prices)

    @staticmethod
    def _pearson_correlation(x: list, y: list) -> float:
        """Compute Pearson correlation coefficient."""
        return FeatureCalculationEngine._pearson_correlation(x, y)

    # =========================================================================
    # FTR-05: FUTURES EVENT HANDLERS
    # =========================================================================

    def _on_funding_update(self, event: Message) -> None:
        """
        Handle EVT:FUNDING_UPDATE event.
        
        FTR-05: Updates ColdState funding_rate. Features included in next tick.
        
        Expected payload:
            {
                "symbol": "BTCUSDT",
                "funding_rate": "0.0001",  # 0.01%
                "next_funding_ts": 1234567890000  # optional
            }
        """
        try:
            symbol = event.pld.get("symbol")
            if not symbol:
                self.logger.warning("EVT:FUNDING_UPDATE missing symbol")
                return
            
            funding_rate_str = event.pld.get("funding_rate", "0")
            funding_rate = decimal.Decimal(str(funding_rate_str))
            next_funding_ts = int(event.pld.get("next_funding_ts", 0))
            
            # Get or create symbol state
            state = self._get_symbol_state(symbol)
            
            # Delegate to engine
            self._engine.update_funding(state.cold, funding_rate, next_funding_ts)
            
            self.logger.debug(f"Updated funding for {symbol}: {funding_rate} (next: {next_funding_ts})")
            
        except Exception as e:
            self.logger.error(f"Error processing EVT:FUNDING_UPDATE: {e}")

    def _on_oi_update(self, event: Message) -> None:
        """
        Handle EVT:OI_UPDATE event.
        
        FTR-05: Updates ColdState open_interest with history for delta calculation.
        
        Expected payload:
            {
                "symbol": "BTCUSDT",
                "open_interest": "50000.5",  # contracts or USD
                "ts": 1234567890000  # optional
            }
        """
        try:
            symbol = event.pld.get("symbol")
            if not symbol:
                self.logger.warning("EVT:OI_UPDATE missing symbol")
                return
            
            oi_str = event.pld.get("open_interest", "0")
            open_interest = decimal.Decimal(str(oi_str))
            ts = int(event.pld.get("ts", 0))
            
            # Get or create symbol state
            state = self._get_symbol_state(symbol)
            
            # Delegate to engine
            self._engine.update_open_interest(state.cold, open_interest, ts)
            
            self.logger.debug(f"Updated OI for {symbol}: {open_interest}")
            
        except Exception as e:
            self.logger.error(f"Error processing EVT:OI_UPDATE: {e}")

    # =========================================================================
    # FSM EVENT HANDLERS
    # =========================================================================

    def on_market_tick(self, event: Message) -> None:
        """Handle incoming market tick event."""
        self.logger.debug(f"event.pld = {event.pld}")
        symbol = event.pld.get("symbol")
        if not symbol:
            return

        # Update anchor prices if this is an anchor
        if symbol in self.cfg.macro_sync_anchors:
            price = decimal.Decimal(str(event.pld.get("price", 0)))
            self.anchor_prices[symbol].append(price)

        current_tick = event.pld
        last_tick = self.last_tick_data.get(symbol)
        self.last_tick_data[symbol] = current_tick

        if not last_tick:
            self.logger.debug(f"No previous tick for {symbol}, skipping feature calculation")
            return

        self._calculate_and_emit_features(symbol, current_tick, last_tick)

    def _calculate_and_emit_features(self, symbol: str, current_tick: dict, last_tick: dict) -> None:
        """Calculate all features and emit EVT:FEATURES_CALCULATED."""
        try:
            # Initialize symbol state if needed
            if symbol not in self.symbol_states:
                self._init_symbol_state(symbol)

            # Parse tick data
            bid_size = decimal.Decimal(str(current_tick.get("bid_size", 0)))
            ask_size = decimal.Decimal(str(current_tick.get("ask_size", 0)))
            buy_volume = decimal.Decimal(str(current_tick.get("buy_volume", 0)))
            sell_volume = decimal.Decimal(str(current_tick.get("sell_volume", 0)))
            price = decimal.Decimal(str(current_tick.get("price", 0)))
            prev_price = decimal.Decimal(str(last_tick.get("price", 0)))
            time_diff = current_tick["ts"] - last_tick["ts"]

            # ================================================================
            # BASE FEATURES (always computed)
            # ================================================================
            
            # OBI (Order Book Imbalance) [-1, 1]
            depth = bid_size + ask_size
            obi = (bid_size - ask_size) / depth if depth > 0 else decimal.Decimal(0)

            # TFI (Trade Flow Imbalance) [-1, 1]
            total_flow = buy_volume + sell_volume
            tfi = (buy_volume - sell_volume) / total_flow if total_flow > 0 else decimal.Decimal(0)

            # Delta Price (with spike filter)
            delta_price = (
                price - prev_price 
                if time_diff < self.cfg.delta_price_spike_filter_ms 
                else decimal.Decimal(0)
            )

            # Liquidity Kappa [kappa_min, kappa_max]
            liq_ratio = depth / (depth + self.cfg.depth_half) if (depth + self.cfg.depth_half) > 0 else decimal.Decimal(0)
            liq_ratio = max(decimal.Decimal(0), min(decimal.Decimal(1), liq_ratio))
            liq_kappa = max(self.cfg.kappa_min, min(self.cfg.kappa_max, liq_ratio))

            features = {
                "obi": str(obi),
                "tfi": str(tfi),
                "delta_price": str(delta_price),
                "absorption": str(self.cfg.zero_value),  # Placeholder - using configured default
                "price": str(price),
                "liquidity_kappa": str(liq_kappa),
            }

            # ================================================================
            # PHASE 1 FEATURES (conditional)
            # ================================================================
            if self.cfg.enable_new_metrics:
                # EMA Bias
                self._update_ema(symbol, price)
                features["ema_bias"] = str(self._compute_ema_bias(symbol))

                # Volume Spike
                self._update_volume_spike(symbol, current_tick)
                features["volume_spike"] = str(self._compute_volume_spike(symbol))

                # Volatility State
                self._update_volatility_state(symbol, price, current_tick)
                features["volatility_state"] = str(self._compute_volatility_state(symbol))

                # Depth Imbalance
                features["depth_imbalance"] = str(self._compute_depth_imbalance(bid_size, ask_size))

                # Macro Sync
                self._update_macro_sync_buffer(symbol, price, time_diff)
                features["macro_sync"] = str(self._compute_macro_sync(symbol))
                
                # ================================================================
                # V2 FEATURES (FTR-03: Additive)
                # ================================================================
                
                # Volume Z-Score (normalized via tanh)
                features["volume_zscore"] = str(self._compute_volume_zscore(symbol))
                
                # Large Trade Imbalance
                features["large_trade_imbalance"] = str(self._compute_large_trade_imbalance(current_tick))
                
                # Spread in basis points
                best_bid = decimal.Decimal(str(current_tick.get("best_bid", current_tick.get("bid", price))))
                best_ask = decimal.Decimal(str(current_tick.get("best_ask", current_tick.get("ask", price))))
                mid_price = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else price
                features["spread_bps"] = str(self._compute_spread_bps(best_bid, best_ask, mid_price))

                # ================================================================
                # FUTURES FEATURES (FTR-05: Config-Gated)
                # ================================================================
                if self.cfg.futures_enabled:
                    state = self._get_symbol_state(symbol)
                    
                    # Funding Rate Normalized [-1, 1]
                    funding_norm = self._engine.compute_funding_normalized(state.cold)
                    if funding_norm is not None:
                        features["funding_rate_normalized"] = str(funding_norm)
                        features["funding_rate"] = str(state.cold.funding_rate)
                    
                    # OI Delta Percentage
                    oi_delta = self._engine.compute_oi_delta_pct(state.cold)
                    if oi_delta is not None:
                        features["oi_delta_pct"] = str(oi_delta)

            # Build payload
            features_payload = {
                "ts": current_tick["ts"],
                "symbol": symbol,
                "features": features,
            }

            # FTR-10: Dynamic logging for all features (no manual f-string updates needed)
            self.logger.info(f"Calculated features for {symbol}: {json.dumps(features, default=str)}")

            # Emit event
            self.fsm.emit("EVT:FEATURES_CALCULATED", payload=features_payload, why="features_calculated")

            # Store features
            if self.feature_store:
                try:
                    self.feature_store.store_features(features_payload)
                    try:
                        self.feature_store.aggregate_all_timeframes(symbol)
                    except Exception as agg_e:
                        self.logger.warning(f"Failed to aggregate timeframes for {symbol}: {agg_e}")
                except Exception as e:
                    self.logger.error(f"Error storing features: {e}")

        except Exception as e:
            self.logger.error(f"Error calculating features for {symbol}: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")

    def start(self) -> None:
        """Start the feature engineering component."""
        self.logger.info("FeatureEngineering (Phase 1) started")

    def stop(self) -> None:
        """Stop the feature engineering component."""
        self.logger.info("FeatureEngineering stopped")
