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
import time
from typing import Dict, Any, TYPE_CHECKING, Optional
from collections import deque, defaultdict
import os

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
from apps.reference.domains.feature_engineering.macro_sync_resampler import MacroSyncResampler

# TASK24: Data-quality metrics (explicit; no silent degrade)
from apps.reference.telemetry.metrics import inc_data_quality_bad_dt, inc_data_quality_drop
from apps.reference.telemetry.metrics import inc_config_contract_violation
from apps.reference.config_contract import ConfigContractError

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
        self._anchor_last_ts_ms: Dict[str, int] = {anchor: 0 for anchor in self.cfg.macro_sync_anchors}
        self._macro_sync_resampler = MacroSyncResampler(
            bin_ms=self.cfg.macro_sync_bin_ms,
            window_bins=self.cfg.macro_sync_window,
            min_bins=self.cfg.macro_sync_min_buffer,
            ttl_ms=self.cfg.macro_sync_ttl_ms,
            max_gap_bins=self.cfg.macro_sync_max_gap_bins,
            eps=self.cfg.macro_sync_eps,
        )
        self._macro_sync_anchor_ts_missing: bool = False

        # Warmup/readiness tracking
        self._ticks_seen: dict[str, int] = defaultdict(int)
        self._last_tick_ts_ms: int = 0
        
        # Register event listener
        self.fsm.listen("EVT:MARKET_TICK_RECEIVED", self.on_market_tick)
        
        # FTR-05: Register Futures event listeners (config-gated)
        if self.cfg.futures_enabled:
            self.fsm.listen("EVT:FUNDING_UPDATE", self._on_funding_update)
            self.fsm.listen("EVT:OI_UPDATE", self._on_oi_update)
            self.logger.info("Futures features enabled: listening for EVT:FUNDING_UPDATE, EVT:OI_UPDATE")
        
        # FSMP-ARCH-01: Register anchor update listener (replaces direct method call)
        self.fsm.listen("EVT:ANCHOR_UPDATED", self._on_anchor_updated_event)
        
        self.logger.info(
            f"FeatureEngineering initialized: "
            f"new_metrics={self.cfg.enable_new_metrics}, "
            f"ema={self.cfg.ema_period_short}/{self.cfg.ema_period_long}, "
            f"macro_sync={self.cfg.macro_sync_enabled}, "
            f"futures={self.cfg.futures_enabled}"
        )
        
        # Ensure feature logs directory exists
        self._feature_logs_dir = os.path.join("logs", "features")
        os.makedirs(self._feature_logs_dir, exist_ok=True)

    def _log_features_to_file(self, symbol: str, features: dict) -> None:
        """
        Log raw feature JSON to a dedicated file for the symbol.
        Format: JSON string (no prefix)
        Path: logs/features/{symbol}.log
        """
        try:
            file_path = os.path.join(self._feature_logs_dir, f"{symbol}.log")
            with open(file_path, "a") as f:
                f.write(json.dumps(features, default=str) + "\n")
        except Exception as e:
            self.logger.error(f"Error logging features to file for {symbol}: {e}")

    def update_anchor_price(self, anchor: str, price: str, ts_ms: int | None = None) -> None:
        """Update anchor price buffer directly from MarketData."""
        if ts_ms is None or int(ts_ms) <= 0:
            inc_config_contract_violation(path="market_data.anchor.ts_ms", symbol=str(anchor))
            self._macro_sync_anchor_ts_missing = True
            raise ConfigContractError(
                path="market_data.anchor.ts_ms",
                symbol=str(anchor),
                why="Missing exchange-derived ts_ms for EVT:ANCHOR_UPDATED (wallclock fallback forbidden)",
            )
        if anchor in self.anchor_prices:
            self.anchor_prices[anchor].append(decimal.Decimal(price))
            self._anchor_last_ts_ms[anchor] = int(ts_ms)
            self._macro_sync_resampler.update_anchor(anchor, ts_ms=int(ts_ms), price=float(decimal.Decimal(price)))
            self._macro_sync_anchor_ts_missing = False
            self.logger.debug(f"Updated anchor {anchor} price: {price}")

    def _on_anchor_updated_event(self, event: Message) -> None:
        """
        Handle EVT:ANCHOR_UPDATED event from MarketData.
        
        FSMP-ARCH-01: Replaces direct method call from MarketDataConnector.
        This enables loose coupling and multiprocess-safe anchor updates.
        """
        try:
            anchor = event.pld.get("anchor")
            price = event.pld.get("price")
            ts_ms = event.pld.get("ts_ms")
            if anchor and price:
                self.update_anchor_price(anchor, price, int(ts_ms) if ts_ms else None)
        except Exception as e:
            self.logger.error(f"Error processing EVT:ANCHOR_UPDATED: {e}")

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
                volume_rate_hist=deque(maxlen=self.cfg.volume_spike_sma_len),
                volume_rate_current=None,
                volume_spike_ready=False,
                volume_spike_not_ready_reason=None,
                range_window_start_ts=None,
                range_min=None,
                range_max=None,
                range_hist=deque(maxlen=self.cfg.volatility_sma_length),  # Now float for Welford
                range_stats=(0, 0.0, 0.0),  # FTR-03: Welford stats
                volatility_state_ready=False,
                volatility_state_not_ready_reason=None,
                returns_buffer=deque(maxlen=self.cfg.macro_sync_window),
                prev_price=None,
                macro_sync_ready=False,
                macro_sync_not_ready_reason=None,
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

    def _update_volume_spike(self, symbol: str, volume: decimal.Decimal, time_diff_ms: int) -> None:
        """TASK24.C2: Update time-normalized volume spike rate samples."""
        state = self._get_symbol_state(symbol).hot
        self._engine.update_volume_spike(state, volume=volume, time_diff_ms=time_diff_ms)

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
    
    def _compute_large_trade_imbalance(self, symbol: str, current_tick: dict) -> decimal.Decimal:
        """Compute large trade imbalance (TASK31, explicit readiness)."""
        state = self._get_symbol_state(symbol).hot
        return self._engine.compute_large_trade_imbalance(current_tick, state=state)

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
        if self._last_tick_ts_ms <= 0:
            inc_config_contract_violation(path="market_data.tick.ts", symbol=str(symbol))
            state.macro_sync_ready = False
            state.macro_sync_not_ready_reason = "tick_ts_missing"
            return self.cfg.neutral_value
        if self._macro_sync_anchor_ts_missing:
            state.macro_sync_ready = False
            state.macro_sync_not_ready_reason = "anchor_ts_missing"
            return self.cfg.neutral_value
        return self._engine.compute_macro_sync_v2(
            state,
            self._macro_sync_resampler,
            symbol=symbol,
            anchors=self.cfg.macro_sync_anchors,
            current_ts_ms=int(self._last_tick_ts_ms),
        )

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
            
            funding_rate_str = event.pld["funding_rate"] if "funding_rate" in event.pld else "0"
            funding_rate = decimal.Decimal(str(funding_rate_str))
            next_funding_ts = int(event.pld["next_funding_ts"] if "next_funding_ts" in event.pld else 0)
            
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
            
            oi_str = event.pld["open_interest"] if "open_interest" in event.pld else "0"
            open_interest = decimal.Decimal(str(oi_str))
            ts = int(event.pld["ts"] if "ts" in event.pld else 0)
            
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
        ts_pld = event.pld.get("ts")
        if ts_pld is None:
            inc_config_contract_violation(path="market_data.tick.ts", symbol=str(symbol))
            inc_data_quality_drop(domain="feature_engineering", reason="tick_ts_missing")
            return

        # Update anchor prices if this is an anchor and config allows tick-based updates.
        # Default (anchor_update_from_ticks=false): anchors are updated via EVT:ANCHOR_UPDATED only.
        if self.cfg.macro_sync_anchor_update_from_ticks and symbol in self.cfg.macro_sync_anchors:
            price = decimal.Decimal(str(event.pld["price"] if "price" in event.pld else 0))
            self.anchor_prices[symbol].append(price)
            self._anchor_last_ts_ms[symbol] = int(ts_pld)
            if price > 0:
                self._macro_sync_resampler.update_anchor(symbol, ts_ms=int(ts_pld), price=float(price))

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
            bid_size = decimal.Decimal(str(current_tick["bid_size"] if "bid_size" in current_tick else 0))
            ask_size = decimal.Decimal(str(current_tick["ask_size"] if "ask_size" in current_tick else 0))
            buy_volume = decimal.Decimal(str(current_tick["buy_volume"] if "buy_volume" in current_tick else 0))
            sell_volume = decimal.Decimal(str(current_tick["sell_volume"] if "sell_volume" in current_tick else 0))
            price = decimal.Decimal(str(current_tick["price"] if "price" in current_tick else 0))
            prev_price = decimal.Decimal(str(last_tick["price"] if "price" in last_tick else 0))
            time_diff = current_tick["ts"] - last_tick["ts"]
            self._last_tick_ts_ms = int((current_tick["ts"] if "ts" in current_tick else 0) or 0)
            self._ticks_seen[symbol] += 1
            if self._last_tick_ts_ms > 0 and price > 0:
                self._macro_sync_resampler.update_symbol(symbol, ts_ms=self._last_tick_ts_ms, price=float(price))

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
            # FTR-FIX: Convert depth to USD to match depth_half (1000 USD)
            depth_usd = depth * price
            liq_ratio = depth_usd / (depth_usd + self.cfg.depth_half) if (depth_usd + self.cfg.depth_half) > 0 else decimal.Decimal(0)
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

                # Volume Spike (TASK24.C2: time-normalized, dt-aware)
                if time_diff <= 0:
                    inc_data_quality_bad_dt(domain="feature_engineering")
                else:
                    self._update_volume_spike(symbol, buy_volume + sell_volume, int(time_diff))
                features["volume_spike"] = str(self._compute_volume_spike(symbol))

                # Volatility State
                self._update_volatility_state(symbol, price, current_tick)
                features["volatility_state"] = str(self._compute_volatility_state(symbol))

                # Depth Imbalance (Convert to USD for smoothing consistency)
                features["depth_imbalance"] = str(self._compute_depth_imbalance(bid_size * price, ask_size * price))

                # Macro Sync
                features["macro_sync"] = str(self._compute_macro_sync(symbol))
                
                # ================================================================
                # V2 FEATURES (FTR-03: Additive)
                # ================================================================
                
                # Volume Z-Score (normalized via tanh)
                features["volume_zscore"] = str(self._compute_volume_zscore(symbol))
                
                # Large Trade Imbalance (TASK31)
                features["large_trade_imbalance"] = str(self._compute_large_trade_imbalance(symbol, current_tick))
                
                # Spread in basis points
                best_bid_raw = (
                    current_tick["best_bid"]
                    if "best_bid" in current_tick
                    else (current_tick["bid"] if "bid" in current_tick else price)
                )
                best_ask_raw = (
                    current_tick["best_ask"]
                    if "best_ask" in current_tick
                    else (current_tick["ask"] if "ask" in current_tick else price)
                )
                best_bid = decimal.Decimal(str(best_bid_raw))
                best_ask = decimal.Decimal(str(best_ask_raw))
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

            # Warmup/readiness contract (TASK24.B/C): explicit; DecisionMaking blocks trading until full_ready.
            warmup: dict[str, object] = {
                "ticks_seen": int(self._ticks_seen[symbol] if symbol in self._ticks_seen else 0),
                "full_ready": True,
                "ready": {},
                "reasons": [],
            }
            if self.cfg.enable_new_metrics:
                hot = self._get_symbol_state(symbol).hot
                ready_map = {
                    "ema_bias": bool(hot.ema_long is not None and hot.ema_short is not None and hot.ema_long > 0),
                    "volume_spike": bool(hot.volume_spike_ready),
                    "volatility_state": bool(hot.volatility_state_ready),
                    "macro_sync": bool(hot.macro_sync_ready) if self.cfg.macro_sync_enabled else True,
                }
                reasons: list[str] = []
                if not hot.volume_spike_ready and hot.volume_spike_not_ready_reason:
                    reasons.append(f"volume_spike:{hot.volume_spike_not_ready_reason}")
                    inc_data_quality_drop(domain="feature_engineering", reason="volume_spike_not_ready")
                if not hot.volatility_state_ready and hot.volatility_state_not_ready_reason:
                    reasons.append(f"volatility_state:{hot.volatility_state_not_ready_reason}")
                    inc_data_quality_drop(domain="feature_engineering", reason="volatility_state_not_ready")
                if self.cfg.macro_sync_enabled and (not hot.macro_sync_ready) and hot.macro_sync_not_ready_reason:
                    reasons.append(f"macro_sync:{hot.macro_sync_not_ready_reason}")
                    inc_data_quality_drop(domain="feature_engineering", reason="macro_sync_not_ready")
                if (not hot.large_trade_imbalance_ready) and hot.large_trade_imbalance_not_ready_reason:
                    reasons.append(f"large_trade_imbalance:{hot.large_trade_imbalance_not_ready_reason}")
                    inc_data_quality_drop(domain="feature_engineering", reason="large_trade_imbalance_not_ready")

                warmup["ready"] = ready_map
                warmup["reasons"] = reasons
                warmup["full_ready"] = all(ready_map.values())
                warmup["large_trade_imbalance_ready"] = bool(hot.large_trade_imbalance_ready)
                warmup["large_trade_imbalance_not_ready_reason"] = hot.large_trade_imbalance_not_ready_reason
                warmup["large_trade_imbalance_trades_used"] = int(hot.large_trade_imbalance_trades_used)
                warmup["large_trade_imbalance_dropped_out_of_order"] = int(hot.large_trade_imbalance_dropped_out_of_order)

            # Build payload
            features_payload = {
                "ts": current_tick["ts"],
                "symbol": symbol,
                "features": features,
                "warmup": warmup,
            }

            # FTR-10: Dynamic logging for all features (no manual f-string updates needed)
            self.logger.info(f"Calculated features for {symbol}: {json.dumps(features, default=str)}")
            
            # Log separate cleaner file for user inspection
            self._log_features_to_file(symbol, features)

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
