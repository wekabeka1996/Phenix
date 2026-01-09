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
from typing import Dict, Any, TYPE_CHECKING, Optional, Tuple
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
from apps.reference.domains.feature_engineering.price_motion import compute_price_motion_block

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

        # PRICE-MOTION-SSOT-STRICT-01: DecisionMaking price_motion_sanity is SSOT-required.
        # FeatureEngineering computes price_motion block using these parameters.
        try:
            from apps.reference.domain_config import DomainConfigResolver
            from apps.reference.config_models import AuroraConfig

            if isinstance(config, DomainConfigResolver):
                resolver = config
            elif isinstance(config, AuroraConfig):
                resolver = DomainConfigResolver(config)
            else:
                raise TypeError(f"Unsupported config type for price_motion_sanity: {type(config)}")

            self._price_motion_sanity_cfg = resolver.get_decision_making().price_motion_sanity
        except Exception as e:
            raise ConfigContractError(
                path="domains.decision_making.price_motion_sanity",
                why="Missing/invalid SSOT price_motion_sanity config (required for LIVE).",
            ) from e
        
        # FTR-04: Initialize calculation engine
        self._engine = FeatureCalculationEngine(self.cfg)

        # TF-BAR-SSOT-003: per-(symbol, tf_sec) last bar for multi-TF safety
        self.last_bar: Dict[Tuple[str, int], Any] = {}
        
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
        self._last_warmup_full_ready: dict[str, bool] = {}
        self._last_warmup_reasons_sig: dict[str, str] = {}
        self._last_macro_resid_ready: dict[str, bool] = {}
        self._last_macro_resid_reason: dict[str, str | None] = {}
        
        # Register event listener
        self.fsm.listen("EVT:MARKET_TICK_RECEIVED", self.on_market_tick)
        
        # BAR-FEATURES-001: Listen for bar events to emit bar-based features
        self.fsm.listen("EVT:BAR_CLOSED", self.on_bar_closed)
        
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

    def on_bar_closed(self, event: Message) -> None:
        """Handle bar closed event - emit bar-features for MR strategy.
        
        BAR-FEATURES-001: When a bar closes, emit FEATURES_CALCULATED with
        the bar's tf_sec so MR strategy can receive them.
        """
        pld = event.pld if hasattr(event, 'pld') else event
        bar_data = pld.get("bar") if isinstance(pld, dict) else None
        
        if not bar_data:
            self.logger.debug("on_bar_closed: no bar in payload")
            return
        
        # Bar can be dict or object
        if isinstance(bar_data, dict):
            symbol = bar_data.get("symbol")
            tf_sec = bar_data.get("timeframe_sec")
        else:
            symbol = getattr(bar_data, "symbol", None)
            tf_sec = getattr(bar_data, "timeframe_sec", None)
        
        if not symbol or not tf_sec:
            self.logger.debug(f"on_bar_closed: missing symbol={symbol} or tf_sec={tf_sec}")
            return
        
        # Store bar for reference
        self.last_bar[(symbol, tf_sec)] = bar_data
        
        # Get last tick for this symbol to calculate bar-features
        last_tick = self.last_tick_data.get(symbol)
        if not last_tick:
            self.logger.debug(f"on_bar_closed: no last_tick for {symbol}, can't emit bar-features yet")
            return
        
        # Create synthetic "current tick" from bar close for feature calculation
        if isinstance(bar_data, dict):
            close_price = bar_data.get("close")
            bar_ts = bar_data.get("end_ts_ms")
        else:
            close_price = getattr(bar_data, "close", None)
            bar_ts = getattr(bar_data, "end_ts_ms", None)
        
        if close_price is None or bar_ts is None:
            self.logger.debug(f"on_bar_closed: missing close={close_price} or ts={bar_ts}")
            return
        
        # Emit bar-features with bar's tf_sec
        # For bar-features, create a synthetic "previous tick" that matches bar timing
        # to avoid time_diff <= 0 rejection in _calculate_and_emit_features_for_tf
        bar_tick = {
            "symbol": symbol,
            "ts": bar_ts,
            "price": str(close_price),
            "bid_size": last_tick.get("bid_size", "0"),
            "ask_size": last_tick.get("ask_size", "0"),
            "buy_volume": last_tick.get("buy_volume", "0"),
            "sell_volume": last_tick.get("sell_volume", "0"),
            "bid": last_tick.get("bid"),
            "ask": last_tick.get("ask"),
        }
        
        # Create synthetic last_tick with ts slightly before bar_ts
        # to ensure time_diff > 0 in feature calculation
        bar_last_tick = dict(last_tick)
        bar_last_tick["ts"] = bar_ts - 1  # 1ms before bar close
        
        self.logger.info(f"📊 on_bar_closed: emitting bar-features for {symbol} tf_sec={tf_sec}")
        self._calculate_and_emit_features_for_tf(symbol, tf_sec=tf_sec, current_tick=bar_tick, last_tick=bar_last_tick)

    def _calculate_and_emit_features(self, symbol: str, current_tick: dict, last_tick: dict) -> None:
        """Calculate tick-features and emit EVT:FEATURES_CALCULATED.
        
        FIX-TICK-FE-GATE-001: Tick-features do NOT depend on bars.
        Bar-features (OHLC-based) will be a separate pipeline (BAR-FEATURES-001).
        """
        # Tick-features: emit immediately, tf_sec=0 indicates tick-level data
        self._calculate_and_emit_features_for_tf(symbol, tf_sec=0, current_tick=current_tick, last_tick=last_tick)

    def _calculate_and_emit_features_for_tf(self, symbol: str, tf_sec: int, current_tick: dict, last_tick: dict) -> None:
        """Calculate all features for a specific tf_sec and emit EVT:FEATURES_CALCULATED."""
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

            # P1-1 FIX: Early return on bad time_diff (out-of-order or duplicate tick)
            # Do NOT update any state with bad dt - emit degraded features and return
            if time_diff <= 0:
                inc_data_quality_bad_dt(domain="feature_engineering")
                inc_data_quality_drop(domain="feature_engineering", reason="bad_dt")
                warmup_bad_dt = {
                    "ticks_seen": int(self._ticks_seen[symbol]),
                    "full_ready": False,
                    "ready": {},
                    "reasons": ["bad_dt:out_of_order_or_duplicate"],
                }
                features_bad_dt = {
                    "price": str(price),
                    "obi": str(self.cfg.zero_value),
                    "tfi": str(self.cfg.zero_value),
                    "delta_price": str(self.cfg.zero_value),
                    "absorption": str(self.cfg.zero_value),
                    "liquidity_kappa": str(self.cfg.neutral_value),
                }
                payload_bad_dt = {
                    "ts": current_tick.get("ts", 0),
                    "symbol": symbol,
                    "tf_sec": tf_sec,
                    "features": features_bad_dt,
                    "warmup": warmup_bad_dt,
                    "data_quality": {"drops": ["bad_dt"], "notes": []},
                }
                self.fsm.emit("EVT:FEATURES_CALCULATED", payload=payload_bad_dt, why="features_degraded_bad_dt")
                self.logger.warning(f"[{symbol}] Dropping tick: time_diff={time_diff}ms (out-of-order or duplicate)")
                return

            if self._last_tick_ts_ms > 0 and price > 0:
                self._macro_sync_resampler.update_symbol(symbol, ts_ms=self._last_tick_ts_ms, price=float(price))
                # R1 (P1): macro_resid depends on anchor_prices["BTCUSDT"] history.
                # In live mode, anchors are typically part of the trading symbols list, so they
                # arrive via normal ticks. When anchor_update_from_ticks is disabled, we still
                # need to maintain anchor_prices for anchor symbols to avoid permanent warmup
                # deadlock (macro_resid never becomes ready => FE warmup.full_ready stays false).
                if (not self.cfg.macro_sync_anchor_update_from_ticks) and symbol in self.cfg.macro_sync_anchors:
                    if symbol in self.anchor_prices:
                        self.anchor_prices[symbol].append(price)
                        self._anchor_last_ts_ms[symbol] = int(self._last_tick_ts_ms)

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
                # Get hot state early for spread tracking
                hot = self._get_symbol_state(symbol).hot
                
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

                # Macro Sync (legacy, kept for telemetry)
                features["macro_sync"] = str(self._compute_macro_sync(symbol))
                
                # ================================================================
                # R1 (P1): MACRO RESID — Beta-Adjusted Residual
                # ================================================================
                # Replaces macro_sync for direction scoring (SIGNED, neutral=0)
                if self.cfg.macro_resid_enabled:
                    # Get BTC price for anchor return
                    btc_price_hist = self.anchor_prices.get("BTCUSDT", None)
                    if btc_price_hist and len(btc_price_hist) >= 2 and prev_price > 0:
                        # Calculate returns
                        asset_return = float((price - prev_price) / prev_price) if prev_price > 0 else 0.0
                        btc_prev = btc_price_hist[-2] if len(btc_price_hist) >= 2 else btc_price_hist[-1]
                        btc_curr = btc_price_hist[-1]
                        anchor_return = float((btc_curr - btc_prev) / btc_prev) if btc_prev > 0 else 0.0
                        
                        # Update buffers
                        self._engine.update_macro_resid(hot, asset_return, anchor_return)
                    
                    # Compute
                    macro_resid_val, macro_resid_ready, macro_resid_reason = self._engine.compute_macro_resid(hot)
                    
                    # FIX-AUDITED-ISSUES-01 (Part C): Fail-closed emission.
                    # If not ready (warmup or missing anchor), emit None instead of 0.0 (neutral).
                    if macro_resid_ready:
                        features["macro_resid"] = str(macro_resid_val)
                    else:
                        features["macro_resid"] = None
                    # MacroResid readiness trace (diagnostic): log only on state/reason changes.
                    try:
                        prev_ready = self._last_macro_resid_ready.get(symbol)
                        prev_reason = self._last_macro_resid_reason.get(symbol)
                        reason_str = str(macro_resid_reason) if macro_resid_reason is not None else None
                        if (prev_ready is None) or (bool(prev_ready) != bool(macro_resid_ready)) or (prev_reason != reason_str):
                            self.logger.info(
                                f"[{symbol}] MACRO_RESID_WARMUP: ready={bool(macro_resid_ready)} "
                                f"reason={reason_str} value={str(macro_resid_val)}"
                            )
                            self._last_macro_resid_ready[symbol] = bool(macro_resid_ready)
                            self._last_macro_resid_reason[symbol] = reason_str
                    except Exception:
                        pass
                else:
                    # Disabled: emit neutral, mark not ready
                    features["macro_resid"] = str(self.cfg.zero_value)
                    hot.macro_resid_ready = False
                    hot.macro_resid_not_ready_reason = "disabled_in_config"
                
                # ================================================================
                # R2 (P2): ABSORPTION — Experimental (Default OFF)
                # ================================================================
                absorption_mode = self.cfg.absorption_mode
                if absorption_mode != "disabled":
                    # Update absorption buffers
                    tfi_val = float(features.get("tfi", 0))
                    self._engine.update_absorption(
                        hot,
                        buy_vol=float(buy_volume),
                        sell_vol=float(sell_volume),
                        tfi=tfi_val,
                    )
                    
                    # Compute
                    absorption_val, absorption_ready, absorption_reason = self._engine.compute_absorption(hot)
                    features["absorption"] = str(absorption_val)
                else:
                    # Disabled: emit neutral, mark not ready (excluded from scoring)
                    features["absorption"] = str(self.cfg.zero_value)
                    hot.absorption_ready = False
                    hot.absorption_not_ready_reason = "mode_disabled"
                
                # ================================================================
                # V2 FEATURES (FTR-03: Additive)
                # ================================================================
                
                # Volume Z-Score (normalized via tanh)
                features["volume_zscore"] = str(self._compute_volume_zscore(symbol))
                
                # Large Trade Imbalance (TASK31)
                features["large_trade_imbalance"] = str(self._compute_large_trade_imbalance(symbol, current_tick))
                
                # Spread in basis points
                # P1-2 FIX: Track spread_ready - if bid/ask missing, spread is unreliable
                spread_ready = True
                spread_missing = False
                
                if "best_bid" in current_tick:
                    best_bid_raw = current_tick["best_bid"]
                elif "bid" in current_tick:
                    best_bid_raw = current_tick["bid"]
                else:
                    best_bid_raw = None
                    spread_missing = True
                
                if "best_ask" in current_tick:
                    best_ask_raw = current_tick["best_ask"]
                elif "ask" in current_tick:
                    best_ask_raw = current_tick["ask"]
                else:
                    best_ask_raw = None
                    spread_missing = True
                
                if spread_missing:
                    # Do NOT fallback to price=0 spread - use neutral and mark not ready
                    spread_ready = False
                    best_bid = price
                    best_ask = price
                    mid_price = price
                    inc_data_quality_drop(domain="feature_engineering", reason="spread_missing")
                else:
                    best_bid = decimal.Decimal(str(best_bid_raw))
                    best_ask = decimal.Decimal(str(best_ask_raw))
                    mid_price = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else price
                
                features["spread_bps"] = str(self._compute_spread_bps(best_bid, best_ask, mid_price))
                
                # Store spread readiness for warmup
                hot.spread_ready = spread_ready
                hot.spread_missing = spread_missing

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
                    # Basic instant features (always ready from first tick)
                    "obi": True,
                    "tfi": True,
                    "delta_price": True,
                    "depth_imbalance": True,
                    "liquidity_kappa": True,
                    # Warmup-dependent features (require history accumulation)
                    "ema_bias": bool(hot.ema_long is not None and hot.ema_short is not None and hot.ema_long > 0),
                    "volume_spike": bool(hot.volume_spike_ready),
                    "volatility_state": bool(hot.volatility_state_ready),
                    "macro_sync": bool(hot.macro_sync_ready) if self.cfg.macro_sync_enabled else True,
                    "spread_bps": bool(hot.spread_ready),  # P1-2 FIX: Include spread readiness
                    "large_trade_imbalance": bool(hot.large_trade_imbalance_ready),
                    "volume_zscore": True,  # Computed each tick
                    # R1: Macro Resid (SIGNED, neutral=0)
                    "macro_resid": bool(hot.macro_resid_ready) if self.cfg.macro_resid_enabled else True,
                    # R2: Absorption (experimental, default OFF = not_ready)
                    "absorption": bool(hot.absorption_ready) if self.cfg.absorption_mode != "disabled" else False,
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
                # R1: macro_resid not ready
                if self.cfg.macro_resid_enabled and (not hot.macro_resid_ready) and hot.macro_resid_not_ready_reason:
                    reasons.append(f"macro_resid:{hot.macro_resid_not_ready_reason}")
                    inc_data_quality_drop(domain="feature_engineering", reason="macro_resid_not_ready")
                # R2: absorption not ready (or dedup muted)
                if self.cfg.absorption_mode != "disabled" and (not hot.absorption_ready) and hot.absorption_not_ready_reason:
                    reasons.append(f"absorption:{hot.absorption_not_ready_reason}")
                    inc_data_quality_drop(domain="feature_engineering", reason="absorption_not_ready")
                # P1-2 FIX: Add spread_missing to reasons
                if hot.spread_missing:
                    reasons.append("spread_bps:spread_missing")

                warmup["ready"] = ready_map
                warmup["reasons"] = reasons
                warmup["full_ready"] = self.cfg.compute_warmup_full_ready(ready_map)
                warmup["large_trade_imbalance_ready"] = bool(hot.large_trade_imbalance_ready)
                warmup["large_trade_imbalance_not_ready_reason"] = hot.large_trade_imbalance_not_ready_reason
                warmup["large_trade_imbalance_trades_used"] = int(hot.large_trade_imbalance_trades_used)
                warmup["large_trade_imbalance_dropped_out_of_order"] = int(hot.large_trade_imbalance_dropped_out_of_order)

                # Log warmup state transitions (helps diagnose "trading never starts" cases).
                # NOTE: this is separate from feature value logging and focuses on readiness.
                try:
                    full_ready = bool(warmup.get("full_ready"))
                    reasons_list = list(warmup.get("reasons", [])) if isinstance(warmup.get("reasons"), list) else []
                    reasons_sig = "|".join(sorted(str(r) for r in reasons_list))
                    last_full_ready = self._last_warmup_full_ready.get(symbol)
                    last_sig = self._last_warmup_reasons_sig.get(symbol)
                    if (last_full_ready is None) or (last_full_ready != full_ready) or (last_sig != reasons_sig):
                        shown = reasons_list[:8]
                        extra = max(0, len(reasons_list) - len(shown))
                        extra_sfx = f" (+{extra} more)" if extra else ""
                        self.logger.info(
                            f"[{symbol}] FE_WARMUP: full_ready={full_ready} "
                            f"reasons={shown}{extra_sfx}"
                        )
                        self._last_warmup_full_ready[symbol] = full_ready
                        self._last_warmup_reasons_sig[symbol] = reasons_sig
                except Exception:
                    # Monitoring-only
                    pass

            # PRICE-MOTION-V1: Multi-window returns/vol proxy and normalized motion.
            try:
                hot = self._get_symbol_state(symbol).hot
                pm_block = compute_price_motion_block(
                    hot.price_history,
                    ts_ms=int(current_tick.get("ts", 0) or 0),
                    price=price,
                    k_vol=float(getattr(self._price_motion_sanity_cfg, "k_vol")),
                    # VOL-ADJ-GATES-CLIP-CONFIG-01: config-driven pm_norm clipping
                    clip_abs=float(getattr(self._price_motion_sanity_cfg, "pm_norm_clip_abs", 10.0)),
                )
            except Exception:
                pm_block = {
                    "ret_10s": None,
                    "ret_60s": None,
                    "ret_300s": None,
                    "vol_pct_10s": None,
                    "vol_pct_60s": None,
                    "vol_pct_300s": None,
                    "pm_norm_10s": None,
                    "pm_norm_60s": None,
                    "pm_norm_300s": None,
                }

            # ================================================================
            # P0-3: FEATURE SANITY FIREWALL (before emit)
            # ================================================================
            # Apply central sanity check to all features
            sanitized_features, sanity_readiness, sanity_reasons = self._engine.sanitize_features_dict(features)
            features = sanitized_features
            
            # Merge sanity readiness into warmup.ready
            if self.cfg.enable_new_metrics:
                ready_map = warmup.get("ready", {})
                for fname, is_ready in sanity_readiness.items():
                    if fname in ready_map:
                        # AND with existing readiness - both must be true
                        ready_map[fname] = ready_map[fname] and is_ready
                    else:
                        ready_map[fname] = is_ready
                warmup["ready"] = ready_map
                
                # Add sanity reasons
                existing_reasons = list(warmup.get("reasons", []))
                existing_reasons.extend(sanity_reasons)
                warmup["reasons"] = existing_reasons
                
                # Recalculate full_ready after sanity
                warmup["full_ready"] = self.cfg.compute_warmup_full_ready(ready_map)

            # ================================================================
            # P0-2: BOOK HEALTH CHECK (spread truth validation)
            # ================================================================
            if self.cfg.enable_new_metrics and self.cfg.spread_health_gate_enabled:
                current_ts_ms = int(current_tick.get("ts", 0) or 0)
                
                # Update book health tracking (tick has both book and trade data)
                self._engine.update_book_health(
                    symbol=symbol,
                    ts_ms=current_ts_ms,
                    is_book_update=not spread_missing,  # Book update if bid/ask present
                    is_trade=True,  # Tick always includes trade
                )
                
                # Check book health
                book_healthy, book_reason = self._engine.check_book_health(symbol, current_ts_ms)
                if not book_healthy:
                    # Mark spread_bps as not ready if book unhealthy
                    ready_map = warmup.get("ready", {})
                    ready_map["spread_bps"] = False
                    warmup["ready"] = ready_map
                    warmup["full_ready"] = self.cfg.compute_warmup_full_ready(ready_map)
                    existing_reasons = list(warmup.get("reasons", []))
                    existing_reasons.append(f"spread_bps:{book_reason}")
                    warmup["reasons"] = existing_reasons
                    inc_data_quality_drop(domain="feature_engineering", reason="book_unhealthy")

            # Build payload
            features_payload = {
                "ts": current_tick["ts"],
                "symbol": symbol,
                "tf_sec": tf_sec,
                "features": features,
                "warmup": warmup,
                "price_motion": pm_block,
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
