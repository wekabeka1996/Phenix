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

from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    attach_canonical_bar_payload,
    build_canonical_bar_identity,
    extract_canonical_bar_identity,
    extract_canonical_replay_identity,
)
from apps.reference.contracts.runtime_gap_policy import (
    attach_gap_status_payload,
    extract_gap_status,
)
from apps.reference.contracts.runtime_regime_layers import (
    is_structural_regime_payload,
)

# FTR-04: Import types from types.py
from apps.reference.domains.feature_engineering.types import (
    HotState,
    ColdState,
    SymbolFeatureState,
    FeatureEngineeringConfig,
    BarVolatilityState,  # EP-01.1: Bar-based ATR tracking
    PillarState,
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
        # P0-1 wiring compatibility: keep explicit alias expected by some call sites.
        self.calc_engine = self._engine

        # TF-BAR-SSOT-003: per-(symbol, tf_sec) last bar for multi-TF safety
        self.last_bar: Dict[Tuple[str, int], Any] = {}
        
        # State tracking
        self.last_tick_data: Dict[str, dict] = {}
        self.symbol_states: Dict[str, SymbolFeatureState] = {}
        self._pillar_states: Dict[str, PillarState] = {}
        
        # Anchor price buffers for macro_sync
        self.anchor_prices: Dict[str, deque] = {
            anchor: deque(maxlen=self.cfg.macro_sync_window)
            for anchor in self.cfg.macro_sync_anchors
        }
        self._anchor_last_ts_ms: Dict[str, int] = {anchor: 0 for anchor in self.cfg.macro_sync_anchors}
        self._macro_sync_runtime_bin_ms: int = int(self.cfg.macro_sync_bin_ms)
        self._macro_sync_gap_bins_override: Optional[int] = None
        try:
            trading_mode = str(getattr(config, "trading_mode", "") or "").strip().lower()
        except Exception:
            trading_mode = ""
        emit_ticks = str(os.getenv("BACKTEST_EMIT_MARKET_TICKS", "0")).strip() == "1"
        if trading_mode == "backtest" and not emit_ticks:
            # Bar-only backtest can legitimately have 1 update per bar (e.g. 5m),
            # which is sparse relative to macro_sync.bin_ms (often a few seconds).
            # Also adapt runtime bin_ms to bar cadence; otherwise returns_by_bin has no contiguous bins.
            tf_candidates = [
                int(tf)
                for tf in (self.cfg.enabled_timeframes_sec or [])
                if int(tf) >= 60
            ]
            basis_tf_sec = 300 if 300 in tf_candidates else (min(tf_candidates) if tf_candidates else 300)
            self._macro_sync_runtime_bin_ms = max(
                int(self.cfg.macro_sync_bin_ms),
                int(basis_tf_sec) * 1000,
            )
            bins_per_bar = max(
                1,
                (int(basis_tf_sec) * 1000 + int(self._macro_sync_runtime_bin_ms) - 1)
                // int(self._macro_sync_runtime_bin_ms),
            )
            self._macro_sync_gap_bins_override = max(
                int(self.cfg.macro_sync_max_gap_bins),
                int(bins_per_bar) + 1,
            )
            self.logger.info(
                "Macro-sync bar-only override: bin_ms=%s (base=%s), max_gap_bins=%s (base=%s), basis_tf_sec=%s",
                int(self._macro_sync_runtime_bin_ms),
                int(self.cfg.macro_sync_bin_ms),
                self._macro_sync_gap_bins_override,
                int(self.cfg.macro_sync_max_gap_bins),
                int(basis_tf_sec),
            )
        self._macro_sync_resampler = MacroSyncResampler(
            bin_ms=self._macro_sync_runtime_bin_ms,
            window_bins=self.cfg.macro_sync_window,
            min_bins=self.cfg.macro_sync_min_buffer,
            ttl_ms=self.cfg.macro_sync_ttl_ms,
            max_gap_bins=self.cfg.macro_sync_max_gap_bins,
            eps=self.cfg.macro_sync_eps,
            max_late_ms=self.cfg.macro_sync_max_late_ms,
        )
        self._macro_sync_anchor_ts_missing: bool = False

        # Warmup/readiness tracking
        self._ticks_seen: dict[str, int] = defaultdict(int)
        self._last_tick_ts_ms: int = 0
        self._last_warmup_full_ready: dict[str, bool] = {}
        self._last_warmup_reasons_sig: dict[str, str] = {}
        self._last_macro_resid_ready: dict[str, bool] = {}
        self._last_macro_resid_reason: dict[str, str | None] = {}
        
        # EP-01.1: Bar Volatility State (per symbol,tf_sec for ATR)
        self._bar_volatility_states: Dict[Tuple[str, int], BarVolatilityState] = {}
        self._emit_timeframes_sec = {
            int(tf) for tf in (self.cfg.enabled_timeframes_sec or []) if int(tf) >= 60
        }
        pillar_tf_cfg = self.cfg.pillar_timeframes_sec
        pillar_label_map = {"tactician": "m15", "operator": "h4", "strategist": "d1"}
        self._pillar_timeframe_to_label: Dict[int, str] = {}
        for pillar_name, tf in pillar_tf_cfg.items():
            tf_int = int(tf)
            if tf_int >= 60:
                tf_label = pillar_label_map.get(str(pillar_name))
                if tf_label:
                    self._pillar_timeframe_to_label[tf_int] = tf_label
        self._calculation_timeframes_sec = set(self._emit_timeframes_sec) | set(
            self._pillar_timeframe_to_label.keys()
        )
        
        # EP-01.1: Last OBI snapshot per symbol (for bar close snapshot)
        self._last_obi: Dict[str, decimal.Decimal] = {}
        
        # Register event listener
        self.fsm.listen("EVT:MARKET_TICK_RECEIVED", self.on_market_tick)
        
        # REG-FIX-01: Regime cache for CMD injection
        self.last_regime: Dict[str, Dict] = {}
        self.fsm.listen("EVT:REGIME_DETECTED", self.on_regime_detected)
        
        # BAR-FEATURES-001: Listen for bar events to emit bar-based features
        self.fsm.listen("EVT:BAR_CLOSED", self.on_bar_closed)
        
        # HTF-WARMUP: Listen for API-backfilled HTF candles to prime pillars instantly
        self.fsm.listen("EVT:HTF_BARS_IMPORTED", self._on_htf_bars_imported)
        
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
        self._legacy_features_log_mode = self.cfg.legacy_features_log_mode
        self._legacy_features_log_sample_every_n = max(
            1, int(self.cfg.legacy_features_log_sample_every_n)
        )
        self._legacy_features_log_counter: Dict[str, int] = defaultdict(int)

    def _log_features_to_file(self, symbol: str, features: dict) -> None:
        """
        Log raw feature JSON to a dedicated file for the symbol.
        Format: JSON string (no prefix)
        Path: logs/features/{symbol}.log
        """
        if self._legacy_features_log_mode == "off":
            return
        if self._legacy_features_log_mode == "sample":
            self._legacy_features_log_counter[symbol] += 1
            if (
                self._legacy_features_log_sample_every_n > 1
                and self._legacy_features_log_counter[symbol]
                % self._legacy_features_log_sample_every_n
                != 0
            ):
                return
        try:
            file_path = os.path.join(self._feature_logs_dir, f"{symbol}.log")
            with open(file_path, "a", encoding="utf-8") as f:
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
            self._macro_sync_resampler.update_anchor(
                anchor,
                ts_ms=int(ts_ms),
                price=float(decimal.Decimal(price)),
                max_gap_bins=self._macro_sync_effective_max_gap_bins(),
            )
            self._macro_sync_anchor_ts_missing = False
            self.logger.debug(f"Updated anchor {anchor} price: {price}")

    def _macro_sync_effective_max_gap_bins(self, tf_sec: Optional[int] = None) -> int:
        """Compute runtime max_gap_bins for macro_sync (live default, bar-only backtest override)."""
        if self._macro_sync_gap_bins_override is None:
            return int(self.cfg.macro_sync_max_gap_bins)
        if tf_sec is not None and int(tf_sec) > 0:
            bins_per_tf = max(
                1,
                (int(tf_sec) * 1000 + int(self._macro_sync_runtime_bin_ms) - 1)
                // int(self._macro_sync_runtime_bin_ms),
            )
            return max(int(self._macro_sync_gap_bins_override), int(bins_per_tf) + 1)
        return int(self._macro_sync_gap_bins_override)

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

    def _compute_macro_sync(self, symbol: str, *, current_ts_ms: int) -> decimal.Decimal:
        """Compute macro_sync = correlation with anchor returns, normalized to [0,1]."""
        state = self._get_symbol_state(symbol).hot
        if current_ts_ms <= 0:
            inc_config_contract_violation(path="market_data.tick.ts", symbol=str(symbol))
            state.macro_sync_ready = False
            state.macro_sync_not_ready_reason = "tick_ts_missing"
            return self.cfg.neutral_value
        if self._macro_sync_anchor_ts_missing:
            state.macro_sync_ready = False
            state.macro_sync_not_ready_reason = "anchor_ts_missing"
            return self.cfg.neutral_value

        # FIX 2 (P0): Causality guard.
        # Never mix anchor updates from the future (relative to this tick) into macro features.
        for anchor in self.cfg.macro_sync_anchors:
            anchor_ts = int((self._anchor_last_ts_ms.get(anchor, 0) or 0))
            if anchor_ts > 0 and anchor_ts > int(current_ts_ms):
                state.macro_sync_ready = False
                state.macro_sync_not_ready_reason = f"anchor_from_future:{anchor}"
                inc_data_quality_drop(domain="feature_engineering", reason="macro_anchor_future")
                return self.cfg.neutral_value
        return self._engine.compute_macro_sync_v2(
            state,
            self._macro_sync_resampler,
            symbol=symbol,
            anchors=self.cfg.macro_sync_anchors,
            current_ts_ms=int(current_ts_ms),
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

    def on_regime_detected(self, event: Message) -> None:
        """
        Handle EVT:REGIME_DETECTED.
        Cache regime state to inject into CMD:PROCESS_STRATEGY.
        """
        try:
            pld = event.pld if hasattr(event, 'pld') else event
            if not isinstance(pld, dict) or not is_structural_regime_payload(pld):
                return
            symbol = pld.get("symbol")
            if symbol:
                self.last_regime[symbol] = pld
        except Exception as e:
            self.logger.error(f"Error handling regime: {e}")

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

        current_tick = event.pld
        last_tick = self.last_tick_data.get(symbol)

        # First tick initializes state (no feature calc) but MUST be stored.
        if not last_tick:
            self.last_tick_data[symbol] = current_tick

            # Update anchor prices if this is an anchor and config allows tick-based updates.
            # Default (anchor_update_from_ticks=false): anchors are updated via EVT:ANCHOR_UPDATED only.
            if self.cfg.macro_sync_anchor_update_from_ticks and symbol in self.cfg.macro_sync_anchors:
                price = decimal.Decimal(str(current_tick.get("price", 0)))
                self.anchor_prices[symbol].append(price)
                self._anchor_last_ts_ms[symbol] = int(ts_pld)
                if price > 0:
                    self._macro_sync_resampler.update_anchor(
                        symbol,
                        ts_ms=int(ts_pld),
                        price=float(price),
                        max_gap_bins=self._macro_sync_effective_max_gap_bins(),
                    )

            self.logger.debug(f"No previous tick for {symbol}, skipping feature calculation")
            return

        # FIX 1 (P0): Only advance last_tick_data when the tick is accepted.
        accepted = self._calculate_and_emit_features(symbol, current_tick, last_tick)
        if not accepted:
            return

        self.last_tick_data[symbol] = current_tick

        # If this is an anchor and tick-based updates are enabled, update anchor buffers ONLY on accepted ticks.
        if self.cfg.macro_sync_anchor_update_from_ticks and symbol in self.cfg.macro_sync_anchors:
            price = decimal.Decimal(str(current_tick.get("price", 0)))
            self.anchor_prices[symbol].append(price)
            self._anchor_last_ts_ms[symbol] = int(ts_pld)
            if price > 0:
                self._macro_sync_resampler.update_anchor(
                    symbol,
                    ts_ms=int(ts_pld),
                    price=float(price),
                    max_gap_bins=self._macro_sync_effective_max_gap_bins(),
                )

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
        try:
            tf_sec = int(tf_sec)
        except (TypeError, ValueError):
            self.logger.debug(f"on_bar_closed: invalid tf_sec={tf_sec!r}")
            return

        calc_timeframes = getattr(self, "_calculation_timeframes_sec", None)
        if calc_timeframes and tf_sec not in calc_timeframes:
            self.logger.debug(
                f"on_bar_closed: skipping tf_sec={tf_sec} (not in calculation_timeframes={sorted(calc_timeframes)})"
            )
            return
        emit_timeframes = getattr(self, "_emit_timeframes_sec", None)
        emit_events = True if not emit_timeframes else (tf_sec in emit_timeframes)
        bar_identity = extract_canonical_bar_identity(
            pld if isinstance(pld, dict) else {"bar": bar_data, "symbol": symbol, "tf_sec": tf_sec},
            default_symbol=symbol,
            default_timeframe_sec=tf_sec,
            default_source_mode=RuntimeBarSourceMode.LIVE,
        )
        
        # Store bar for reference
        self.last_bar[(symbol, tf_sec)] = bar_data

        if isinstance(bar_data, dict):
            close_price = bar_data.get("close")
            bar_ts = (
                int(bar_identity.bar_end_ts_ms)
                if bar_identity is not None
                else bar_data.get("end_ts_ms")
            )
            bar_open = bar_data.get("open")
            bar_get = bar_data.get
        else:
            close_price = getattr(bar_data, "close", None)
            bar_ts = (
                int(bar_identity.bar_end_ts_ms)
                if bar_identity is not None
                else getattr(bar_data, "end_ts_ms", None)
            )
            bar_open = getattr(bar_data, "open", None)
            bar_get = lambda key, default=None: getattr(bar_data, key, default)

        if close_price is None or bar_ts is None:
            self.logger.debug(f"on_bar_closed: missing close={close_price} or ts={bar_ts}")
            return

        # Bar-only mode: derive feature seed directly from bar payload.
        seed_tick = self.last_tick_data.get(symbol, {})
        bar_tick = {
            "symbol": symbol,
            "ts": int(bar_ts),
            "price": str(close_price),
            "bid_size": str(bar_get("bid_size", seed_tick.get("bid_size", "0"))),
            "ask_size": str(bar_get("ask_size", seed_tick.get("ask_size", "0"))),
            "buy_volume": str(bar_get("buy_volume", seed_tick.get("buy_volume", "0"))),
            "sell_volume": str(bar_get("sell_volume", seed_tick.get("sell_volume", "0"))),
            "buy_count": bar_get("buy_count", seed_tick.get("buy_count", 0)),
            "sell_count": bar_get("sell_count", seed_tick.get("sell_count", 0)),
            "buy_notional": str(bar_get("buy_notional", seed_tick.get("buy_notional", "0"))),
            "sell_notional": str(bar_get("sell_notional", seed_tick.get("sell_notional", "0"))),
            "trades_dropped_out_of_order": bar_get("trades_dropped_out_of_order", 0),
            "bid": str(bar_get("bid", seed_tick.get("bid", close_price))),
            "ask": str(bar_get("ask", seed_tick.get("ask", close_price))),
        }

        # ALPHA-SEARCH SUPPORT: pass through augmented keys from bar payload (or last seed as fallback)
        aug_keys = [
            "macd_line", "macd_signal", "macd_histogram",
            "stochastic_k", "stochastic_d",
            "price_momentum_5m", "price_momentum_1h", "price_momentum_1d",
            "volume_momentum_5m", "rsi_14", "bb_percent_b", "is_candidate",
        ]
        for k in aug_keys:
            v = bar_get(k, seed_tick.get(k))
            if v is not None:
                bar_tick[k] = v

        bar_open_dec = decimal.Decimal(str(bar_open)) if bar_open is not None else None
        bar_last_tick = self._create_synthetic_tick_for_bar_close(bar_tick, int(bar_ts), bar_open_dec)

        if emit_events:
            self.logger.info(f"📊 on_bar_closed: emitting bar-features for {symbol} tf_sec={tf_sec}")
        else:
            self.logger.debug(f"[{symbol}] on_bar_closed internal-only tf_sec={tf_sec} (pillars update, no emit)")
        try:
            accepted = self._calculate_and_emit_features_for_tf(
                symbol,
                tf_sec=tf_sec,
                current_tick=bar_tick,
                last_tick=bar_last_tick,
                bar_data=bar_data,
                emit_events=emit_events,
            )
        except TypeError:
            # Backward compatibility for tests/mocks monkeypatching old signature.
            accepted = self._calculate_and_emit_features_for_tf(
                symbol,
                tf_sec=tf_sec,
                current_tick=bar_tick,
                last_tick=bar_last_tick,
                bar_data=bar_data,
            )
        if accepted:
            self.last_tick_data[symbol] = bar_tick

    def _on_htf_bars_imported(self, event: "Message") -> None:
        """
        Handle EVT:HTF_BARS_IMPORTED.
        
        Directly hydrates the PillarState without triggering TTL age checks
        or standard delta computation logic. Used strictly for startup warmup.
        """
        pld = getattr(event, "pld", {}) if not isinstance(event, dict) else event.get("pld", {})
        if not pld:
            return

        symbol = pld.get("symbol")
        tf_sec = pld.get("tf_sec")
        bars = pld.get("bars", [])
        
        if not symbol or not tf_sec or not bars:
            self.logger.warning("HTF_BARS_IMPORTED missing required fields.")
            return

        try:
            tf_sec = int(tf_sec)
        except ValueError:
            return

        tf_map = getattr(self, "_pillar_timeframe_to_label", None) or {900: "m15", 14400: "h4", 86400: "d1"}
        tf_label = tf_map.get(tf_sec)
        
        if not tf_label:
            self.logger.debug(f"[{symbol}] Ignoring imported bars for tf_sec={tf_sec} (not a configured pillar tf)")
            return

        state = self._pillar_states.get(symbol)
        if state is None:
            # Type imported from .calculation_engine or inferred.
            # Using dynamic creation similar to _compute_pillars_for_emit
            from apps.reference.domains.feature_engineering.calculation_engine import PillarState
            state = PillarState()
            self._pillar_states[symbol] = state

        calc_engine = getattr(self, "calc_engine", None) or getattr(self, "_engine", None)
        if not calc_engine or not hasattr(calc_engine, "update_pillar_candle"):
            self.logger.error("FeatureCalculationEngine does not support update_pillar_candle.")
            return

        processed = 0
        for bar in bars:
            try:
                if not isinstance(bar, dict):
                    continue
                identity = extract_canonical_bar_identity(
                    {"symbol": symbol, "tf_sec": tf_sec, "bar": bar, "source_mode": "warmup_import"},
                    default_symbol=symbol,
                    default_timeframe_sec=tf_sec,
                    default_source_mode=RuntimeBarSourceMode.WARMUP_IMPORT,
                )
                if identity is None:
                    open_ts = int(bar["open_ts"])
                    identity = build_canonical_bar_identity(
                        symbol=symbol,
                        timeframe_sec=int(tf_sec),
                        bar_start_ts_ms=int(open_ts),
                        close_boundary_ts_ms=int(open_ts) + int(tf_sec) * 1000,
                        source_mode=RuntimeBarSourceMode.WARMUP_IMPORT,
                    )
                attach_canonical_bar_payload(
                    {"bar": bar, "symbol": symbol, "tf_sec": tf_sec},
                    identity=identity,
                    replay_generation=int(bar.get("replay_generation", 0) or 0),
                )
                
                calc_engine.update_pillar_candle(
                    state,
                    timeframe=tf_label,
                    close=float(bar["c"]),
                    high=float(bar["h"]),
                    low=float(bar["l"]),
                    bar_ts_ms=int(identity.bar_end_ts_ms),
                )
                processed += 1
            except Exception as e:
                self.logger.debug(f"[{symbol}] Malformed imported bar skipped: {e}")

        self.logger.info(
            f"✅ [{symbol}] Successfully hydrated PillarState with {processed} historical {tf_label} candles "
            f"(Anchor: {pld.get('as_of_ms', 0)})"
        )

    def _create_synthetic_tick_for_bar_close(
        self, 
        last_tick: Dict[str, Any], 
        bar_ts: int, 
        bar_open: Optional[decimal.Decimal]
    ) -> Dict[str, Any]:
        """Create synthetic 'previous tick' for bar-feature calculation.
        
        Problem: When calculating bar-features, time_diff = current_ts - last_ts.
        If last_tick.ts == bar_ts (same millisecond), time_diff = 0 → rejected by guard.
        
        Solution: Offset last_tick.ts by -1ms to ensure time_diff > 0.
        This is safe because bar-features use OHLC data, not tick-level timing.
        
        Additionally, use bar's OPEN price as prev_price for delta_price calculation,
        ensuring delta_price = (close - open), not (close - last_tick_price).
        
        Args:
            last_tick: Last real tick data for this symbol
            bar_ts: Bar close timestamp (end_ts_ms)
            bar_open: Bar's opening price (for delta_price calculation)
        
        Returns:
            Synthetic tick dict with ts=bar_ts-1 and price=bar_open
        """
        synthetic_tick = dict(last_tick)
        synthetic_tick["ts"] = bar_ts - 1  # 1ms before bar close
        
        if bar_open is not None:
            synthetic_tick["price"] = str(bar_open)
        
        return synthetic_tick

    def _calculate_and_emit_features(self, symbol: str, current_tick: dict, last_tick: dict) -> bool:
        """Calculate tick-features and emit EVT:FEATURES_CALCULATED.
        
        FIX-TICK-FE-GATE-001: Tick-features do NOT depend on bars.
        Bar-features (OHLC-based) will be a separate pipeline (BAR-FEATURES-001).
        """
        # Tick-features: emit immediately, tf_sec=0 indicates tick-level data
        return self._calculate_and_emit_features_for_tf(symbol, tf_sec=0, current_tick=current_tick, last_tick=last_tick)

    @staticmethod
    def _pillar_json_scalar(value: Any) -> Optional[float]:
        """Convert pillar value to JSON-safe float (handles Decimal / numpy scalars)."""
        if value is None:
            return None
        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                pass
        try:
            as_float = float(value)
        except Exception:
            return None
        if as_float != as_float:  # NaN
            return None
        if as_float == float("inf") or as_float == float("-inf"):
            return None
        return as_float

    def _compute_pillars_for_emit(
        self,
        symbol: str,
        tf_sec: int,
        bar_data: Optional[Dict],
    ) -> Optional[Dict[str, Any]]:
        """
        Compute and normalize pillar payload for feature emission.

        Adapter supports both signatures:
        - compute_pillars(bars, symbol, tf_sec)
        - compute_pillars(state)
        """
        if int(tf_sec or 0) < 60:
            return None

        calc_engine = getattr(self, "calc_engine", None) or getattr(self, "_engine", None)
        if calc_engine is None or not hasattr(calc_engine, "compute_pillars"):
            return None

        bars = bar_data if bar_data is not None else self.last_bar.get((symbol, tf_sec))
        raw = None
        try:
            raw = calc_engine.compute_pillars(bars, symbol, tf_sec)
        except TypeError as sig_err:
            self.logger.debug(
                f"[{symbol}] compute_pillars signature fallback engaged (tf_sec={tf_sec}): {sig_err}"
            )
            state = self._pillar_states.get(symbol)
            if state is None:
                state = PillarState()
                self._pillar_states[symbol] = state

            if bars is not None and hasattr(calc_engine, "update_pillar_candle"):
                if isinstance(bars, dict):
                    bar_close = bars.get("close")
                    bar_high = bars.get("high", bar_close)
                    bar_low = bars.get("low", bar_close)
                    bar_ts_ms = bars.get("end_ts_ms") or bars.get("close_ts") or bars.get("kline_close_time")
                else:
                    bar_close = getattr(bars, "close", None)
                    bar_high = getattr(bars, "high", bar_close)
                    bar_low = getattr(bars, "low", bar_close)
                    bar_ts_ms = (
                        getattr(bars, "end_ts_ms", None)
                        or getattr(bars, "close_ts", None)
                        or getattr(bars, "kline_close_time", None)
                    )

                tf_map = getattr(self, "_pillar_timeframe_to_label", None)
                if not isinstance(tf_map, dict) or not tf_map:
                    tf_map = {900: "m15", 14400: "h4", 86400: "d1"}
                tf_label = tf_map.get(int(tf_sec))
                if tf_label and bar_close is not None and bar_ts_ms is not None:
                    try:
                        calc_engine.update_pillar_candle(
                            state,
                            timeframe=tf_label,
                            close=float(bar_close),
                            high=float(bar_high if bar_high is not None else bar_close),
                            low=float(bar_low if bar_low is not None else bar_close),
                            bar_ts_ms=int(bar_ts_ms),
                        )
                    except Exception as e:
                        self.logger.debug(f"[{symbol}] Pillar candle update skipped: {e}")

            raw = calc_engine.compute_pillars(state)

        if raw is None:
            return None

        if isinstance(raw, dict):
            pillar_sum = raw.get("pillar_sum")
            pillar_tactician = raw.get("pillar_tactician", raw.get("tactician"))
            pillar_operator = raw.get("pillar_operator", raw.get("operator"))
            pillar_strategist = raw.get("pillar_strategist", raw.get("strategist"))
            pillar_contribs = raw.get("pillar_contribs", {})
        else:
            pillar_sum = getattr(raw, "pillar_sum", None)
            pillar_tactician = getattr(raw, "pillar_tactician", getattr(raw, "tactician", None))
            pillar_operator = getattr(raw, "pillar_operator", getattr(raw, "operator", None))
            pillar_strategist = getattr(raw, "pillar_strategist", getattr(raw, "strategist", None))
            pillar_contribs = getattr(raw, "pillar_contribs", {})

        if pillar_sum is None:
            self.logger.debug(
                f"[{symbol}] pillar_sum is missing from calc_engine output (pillars not ready). tactician={pillar_tactician}, operator={pillar_operator}, strategist={pillar_strategist}"
            )
            return None

        safe_contribs: Dict[str, float] = {}
        if isinstance(pillar_contribs, dict):
            for key, value in pillar_contribs.items():
                safe_val = self._pillar_json_scalar(value)
                if safe_val is not None:
                    safe_contribs[str(key)] = safe_val

        safe_sum = self._pillar_json_scalar(pillar_sum)
        if safe_sum is None:
            return None

        return {
            "pillar_sum": safe_sum,
            "pillar_tactician": self._pillar_json_scalar(pillar_tactician),
            "pillar_operator": self._pillar_json_scalar(pillar_operator),
            "pillar_strategist": self._pillar_json_scalar(pillar_strategist),
            "pillar_contribs": safe_contribs,
        }

    def _calculate_and_emit_features_for_tf(
        self,
        symbol: str,
        tf_sec: int,
        current_tick: dict,
        last_tick: dict,
        bar_data: Optional[Dict] = None,
        emit_events: bool = True,
    ) -> bool:
        """Calculate all features for a specific tf_sec and emit EVT:FEATURES_CALCULATED (and CMD:PROCESS_STRATEGY if bar)."""
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
            current_ts_ms = int((current_tick["ts"] if "ts" in current_tick else 0) or 0)
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
                if emit_events:
                    self.fsm.emit("EVT:FEATURES_CALCULATED", payload=payload_bad_dt, why="features_degraded_bad_dt")
                self.logger.warning(f"[{symbol}] Dropping tick: time_diff={time_diff}ms (out-of-order or duplicate)")
                return False

            # Update last tick timestamp ONLY after validation.
            self._last_tick_ts_ms = current_ts_ms

            if self._last_tick_ts_ms > 0 and price > 0:
                self._macro_sync_resampler.update_symbol(
                    symbol,
                    ts_ms=self._last_tick_ts_ms,
                    price=float(price),
                    max_gap_bins=self._macro_sync_effective_max_gap_bins(tf_sec=tf_sec),
                )
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
            
            # EP-01.1: Cache OBI for bar close snapshot
            self._last_obi[symbol] = obi

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
                # In Phase 3, this might be overwritten later by the augmented pass-through 
                # if running in backtest. In live mode, it calculates normally.
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
                features["macro_sync"] = str(self._compute_macro_sync(symbol, current_ts_ms=int(current_ts_ms)))
                
                # ================================================================
                # R1 (P1): MACRO RESID — Beta-Adjusted Residual
                # ================================================================
                # Replaces macro_sync for direction scoring (SIGNED, neutral=0)
                if self.cfg.macro_resid_enabled:
                    # FIX 2 (P0): Causality guard.
                    # Never use anchor data from the future relative to this tick.
                    btc_anchor_ts = int((self._anchor_last_ts_ms.get("BTCUSDT", 0) or 0))
                    if btc_anchor_ts > 0 and btc_anchor_ts > int(current_ts_ms):
                        hot.macro_resid_ready = False
                        hot.macro_resid_not_ready_reason = "anchor_from_future:BTCUSDT"
                        inc_data_quality_drop(domain="feature_engineering", reason="macro_anchor_future")
                        macro_resid_val = self.cfg.zero_value
                        macro_resid_ready = False
                        macro_resid_reason = hot.macro_resid_not_ready_reason
                    else:
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
                        # reason_str = str(macro_resid_reason) if macro_resid_reason is not None else None
                        pass
                    except Exception:
                        pass
            
            # ================================================================
            # ALPHA-SEARCH SUPPORT: AUGMENTED FEATURE PASS-THROUGH
            # ================================================================
            # In backtest mode, BacktestEngine injects TA features (RSI, MACD etc) 
            # into the tick payload. FeatureEngineering natively ignores unknown keys.
            # We explicitly pass them through here to ensure AlphaSearch receives them.
            aug_keys = [
                "macd_line", "macd_signal", "macd_histogram",
                "stochastic_k", "stochastic_d",
                "price_momentum_5m", "price_momentum_1h", "price_momentum_1d",
                "volume_momentum_5m", "rsi_14", "atr_pct", "ema_bias"
            ]
            for k in aug_keys:
                if k in current_tick and current_tick[k] is not None:
                    # Keep as string to match FE string-heavy contract, or native float?
                    # Alpha models cast strictly, so string is safest for parity with FE.
                    features[k] = str(current_tick[k])

            # ================================================================
            # EMISSION
            # ================================================================
            # NOTE: macro_resid disabled-path was here but removed (bug).
            # When macro_resid_enabled=False, `hot.macro_resid_ready=False`
            # and reason should be set inside `if self.cfg.macro_resid_enabled: ... else:`.
            # That else is already INSIDE the `if enable_new_metrics:` block correctly.

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
                if self.cfg.large_trade_imbalance_enabled:
                    features["large_trade_imbalance"] = str(self._compute_large_trade_imbalance(symbol, current_tick))
                else:
                    hot.large_trade_imbalance_ready = True
                    hot.large_trade_imbalance_not_ready_reason = None
                    hot.large_trade_imbalance_trades_used = 0
                    hot.large_trade_imbalance_dropped_out_of_order = 0
                    features["large_trade_imbalance"] = str(self.cfg.neutral_value)
                
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
                    "large_trade_imbalance": bool(hot.large_trade_imbalance_ready)
                    if self.cfg.large_trade_imbalance_enabled
                    else True,
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
                if (
                    self.cfg.large_trade_imbalance_enabled
                    and (not hot.large_trade_imbalance_ready)
                    and hot.large_trade_imbalance_not_ready_reason
                ):
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
                warmup["full_ready"] = self.cfg.compute_warmup_full_ready_for_symbol(symbol=symbol, ready_map=ready_map)
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
                warmup["full_ready"] = self.cfg.compute_warmup_full_ready_for_symbol(symbol=symbol, ready_map=ready_map)

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
                    warmup["full_ready"] = self.cfg.compute_warmup_full_ready_for_symbol(symbol=symbol, ready_map=ready_map)
                    existing_reasons = list(warmup.get("reasons", []))
                    existing_reasons.append(f"spread_bps:{book_reason}")
                    warmup["reasons"] = existing_reasons
                    inc_data_quality_drop(domain="feature_engineering", reason="book_unhealthy")

            # P0-1: Wire pillars into the same TF payload consumed by decision flow.
            pillars = self._compute_pillars_for_emit(symbol=symbol, tf_sec=int(tf_sec), bar_data=bar_data)
            if pillars is not None:
                pillar_keys = (
                    "pillar_sum",
                    "pillar_tactician",
                    "pillar_operator",
                    "pillar_strategist",
                    "pillar_contribs",
                )
                collisions = [k for k in pillar_keys if k in features]
                if collisions:
                    self.logger.warning(
                        f"[{symbol}] Pillar wiring collision detected; keeping existing keys: {collisions}"
                    )
                else:
                    features["pillar_sum"] = pillars["pillar_sum"]
                    features["pillar_tactician"] = pillars["pillar_tactician"]
                    features["pillar_operator"] = pillars["pillar_operator"]
                    features["pillar_strategist"] = pillars["pillar_strategist"]
                    features["pillar_contribs"] = pillars.get("pillar_contribs", {})

            if not emit_events:
                self.logger.debug(
                    f"[{symbol}] Internal TF processed without event emission (tf_sec={tf_sec})"
                )
                return True

            bar_identity = extract_canonical_bar_identity(
                {"symbol": symbol, "tf_sec": tf_sec, "bar": bar_data},
                default_symbol=symbol,
                default_timeframe_sec=tf_sec,
                default_source_mode=RuntimeBarSourceMode.LIVE,
            )
            replay_identity = extract_canonical_replay_identity(
                {"symbol": symbol, "tf_sec": tf_sec, "bar": bar_data},
                default_symbol=symbol,
                default_timeframe_sec=tf_sec,
                default_source_mode=RuntimeBarSourceMode.LIVE,
            )
            source_mode = (
                bar_identity.source_mode.value
                if bar_identity is not None
                else RuntimeBarSourceMode.LIVE.value
            )
            gap_status = extract_gap_status(
                {
                    "symbol": symbol,
                    "tf_sec": tf_sec,
                    "bar": bar_data,
                    "source_mode": source_mode,
                    "bar_identity": (
                        bar_identity.to_payload()
                        if bar_identity is not None
                        else None
                    ),
                },
                default_source="market_data:payload_bridge",
                default_source_mode=RuntimeBarSourceMode.LIVE,
            )

            # Build payload
            features_payload = {
                "ts": current_tick["ts"],
                "symbol": symbol,
                "tf_sec": tf_sec,
                "features": features,
                "warmup": warmup,
                "price_motion": pm_block,
                "bar": bar_data,  # DATA-RECORDER-01: Inject raw bar (OHLCV) for recording
                "source_mode": source_mode,
            }
            if bar_identity is not None:
                features_payload["bar_identity"] = bar_identity.to_payload()
                features_payload["close_boundary_ts_ms"] = int(bar_identity.close_boundary_ts_ms)
            if replay_identity is not None:
                features_payload["replay_identity"] = replay_identity.to_payload()
                features_payload["replay_generation"] = int(replay_identity.replay_generation)
            if gap_status is not None:
                attach_gap_status_payload(features_payload, gap=gap_status)

            # FTR-10: Dynamic logging for all features (no manual f-string updates needed)
            self.logger.info(f"Calculated features for {symbol}: {json.dumps(features, default=str)}")
            
            # Log separate cleaner file for user inspection
            self._log_features_to_file(symbol, features)

            # Emit event
            self.fsm.emit("EVT:FEATURES_CALCULATED", payload=features_payload, why="features_calculated")

            # T2B-03 + REC-01-FIX: EMIT CMD:PROCESS_STRATEGY (Bar-Driven Trigger)
            # FAIL-CLOSED CONDITIONS:
            # 1. bar_data must exist
            # 2. tf_sec >= 60 (real bars only, not tick-level)
            # 3. warmup must exist and full_ready == True
            # 4. bar_close_ts must be present in bar_data
            # 5. bar must have OHLCV fields
            def _emit_cmd_blocked(reason_code: str, reason: str) -> None:
                try:
                    self.fsm.emit(
                        "EVT:PROCESS_STRATEGY_BLOCKED",
                        payload={
                            "symbol": symbol,
                            "tf_sec": tf_sec,
                            "reason_code": reason_code,
                            "reason": reason,
                            "ts": current_tick.get("ts"),
                        },
                        why="cmd_blocked",
                    )
                except Exception:
                    pass
            
            # Gate 1: bar_data presence
            if not bar_data:
                pass  # Tick-level features, no CMD emission expected
            # Gate 2: tf_sec >= 60 (REC-01-FIX: was > 0)
            elif not tf_sec or tf_sec < 60:
                self.logger.warning(
                    f"[{symbol}] CMD:PROCESS_STRATEGY rejected: tf_sec={tf_sec} < 60"
                )
                _emit_cmd_blocked("TF_SEC_LT_60", "tf_sec below 60")
            # Gate 3: warmup fail-closed (REC-01-FIX: no default True)
            elif warmup is None:
                self.logger.warning(
                    f"[{symbol}] CMD:PROCESS_STRATEGY rejected: warmup missing"
                )
                _emit_cmd_blocked("WARMUP_MISSING", "warmup missing")
            elif bar_data.get("_warmup_bar") is True:
                # PRE-SIMULATION WARMUP BAR: state-only pass, no decision.
                pass
            elif bar_data.get("is_candidate") is False:

                # SPARSE DECISION LOOP (Phase 2):
                # Skip emitting CMD:PROCESS_STRATEGY for non-candidate bars.
                # Do not emit blocked reason as this is a high-frequency expected shortcut.
                pass
            else:
                warmup_mode = str(self.cfg.warmup_enforcement_mode or "fail_fast")
                warmup_full_ready = warmup.get("full_ready") is True
                if not warmup_full_ready:
                    msg = (
                        f"[{symbol}] CMD:PROCESS_STRATEGY warmup not full_ready "
                        f"(full_ready={warmup.get('full_ready')}, reasons={warmup.get('reasons', [])}, "
                        f"enforcement_mode={warmup_mode})"
                    )
                    if warmup_mode == "fail_fast":
                        self.logger.warning(f"{msg} -> rejected")
                        _emit_cmd_blocked("WARMUP_NOT_FULL_READY", "warmup full_ready=false")
                        return
                    # warn_only / disabled: allow strategy processing to proceed
                    self.logger.warning(f"{msg} -> allowed")

                # Gate 4: Extract bar_close_ts from canonical bar identity.
                # Legacy bridge keeps bar_close_ts mapped to bar_end_ts_ms.
                bar_close_ts = (
                    int(bar_identity.bar_end_ts_ms)
                    if bar_identity is not None
                    else bar_data.get("end_ts_ms") or bar_data.get("close_ts") or bar_data.get("kline_close_time")
                )
                
                if not bar_close_ts:
                    self.logger.warning(
                        f"[{symbol}] CMD:PROCESS_STRATEGY rejected: bar_close_ts missing in bar_data"
                    )
                    _emit_cmd_blocked("BAR_CLOSE_TS_MISSING", "bar close timestamp missing")
                # Gate 5: Validate bar has OHLCV fields (REC-01-FIX: bar structure check)
                elif not all(bar_data.get(f) is not None for f in ("open", "high", "low", "close", "volume")):
                    missing = [f for f in ("open", "high", "low", "close", "volume") if bar_data.get(f) is None]
                    self.logger.warning(
                        f"[{symbol}] CMD:PROCESS_STRATEGY rejected: bar fields missing ({missing})"
                    )
                    _emit_cmd_blocked("BAR_FIELDS_MISSING", f"bar missing fields {missing}")
                else:
                    # All gates passed — compute EP-01.1 features and emit CMD
                    
                    # =========================================================
                    # EP-01.1: BAR VOLATILITY FEATURES
                    # =========================================================
                    bar_open = decimal.Decimal(str(bar_data.get("open")))
                    bar_high = decimal.Decimal(str(bar_data.get("high")))
                    bar_low = decimal.Decimal(str(bar_data.get("low")))
                    bar_close = decimal.Decimal(str(bar_data.get("close")))
                    
                    # bar_range = high - low
                    bar_range = bar_high - bar_low
                    
                    # bar_body = |close - open|
                    bar_body = abs(bar_close - bar_open)
                    
                    # Get/create bar volatility state for this (symbol, tf_sec)
                    vol_key = (symbol, tf_sec)
                    if vol_key not in self._bar_volatility_states:
                        self._bar_volatility_states[vol_key] = BarVolatilityState(atr_window=14)
                    vol_state = self._bar_volatility_states[vol_key]
                    
                    # True Range calculation
                    # TR = max(H - L, |H - prev_close|, |L - prev_close|)
                    if vol_state.prev_close is not None:
                        tr_hl = bar_high - bar_low
                        tr_hc = abs(bar_high - vol_state.prev_close)
                        tr_lc = abs(bar_low - vol_state.prev_close)
                        true_range = max(tr_hl, tr_hc, tr_lc)
                    else:
                        # First bar: use H - L only
                        true_range = bar_high - bar_low
                    
                    # Update prev_close for next bar
                    vol_state.prev_close = bar_close
                    
                    # Update TR buffer and compute ATR
                    vol_state.update_tr(float(true_range))
                    
                    # Normalized values (% of price)
                    eps = decimal.Decimal("0.00000001")
                    close_safe = max(bar_close, eps)
                    range_pct = float(bar_range / close_safe)
                    
                    # Phase 3 Vectorized Warmup
                    # Try to use precomputed atr_pct from the augmented backtest feed
                    if "atr_pct" in bar_data and bar_data["atr_pct"] is not None:
                        atr_pct = float(bar_data["atr_pct"])
                        vol_state.atr_ready = True  # Mock ready for downstream
                        vol_state.last_atr = atr_pct * float(close_safe) # Update state for downstream dependency
                    else:
                        atr_pct = float(vol_state.last_atr / float(close_safe)) if vol_state.atr_ready and vol_state.last_atr else None
                    
                    # =========================================================
                    # EP-01.1: OBI SNAPSHOT AT BAR CLOSE
                    # =========================================================
                    obi_close = self._last_obi.get(symbol)
                    obi_close_str = str(obi_close) if obi_close is not None else None
                    
                    # =========================================================
                    # EP-01.1: INJECT INTO FEATURES
                    # =========================================================
                    features["volatility"] = {
                        "bar_range": str(bar_range),
                        "bar_body": str(bar_body),
                        "true_range": str(true_range),
                        "atr_14": vol_state.last_atr,  # None if not ready
                        "range_pct": range_pct,
                        "atr_pct": atr_pct,  # None if not ready
                        "atr_ready": vol_state.atr_ready,
                    }
                    features["liquidity"] = {
                        "obi_close": obi_close_str,
                    }
                    
                    cmd_payload = {
                        "symbol": symbol,
                        "tf_sec": tf_sec,                        # T2B-03: Required for strategy routing
                        "bar_close_ts": int(bar_close_ts),       # T2B-03: Required for dedup/idempotency
                        "bar": bar_data,                         # T2B-05: Real Bar SSOT
                        "features": features,                    # Calculated features + EP-01.1
                        "warmup": warmup,                        # T2B-03: Readiness snapshot
                        "regime": self.last_regime.get(symbol),  # REG-FIX-01: Injected regime
                        "source_mode": source_mode,
                    }
                    if bar_identity is not None:
                        cmd_payload["bar_identity"] = bar_identity.to_payload()
                        cmd_payload["close_boundary_ts_ms"] = int(bar_identity.close_boundary_ts_ms)
                    if replay_identity is not None:
                        cmd_payload["replay_identity"] = replay_identity.to_payload()
                        cmd_payload["replay_generation"] = int(replay_identity.replay_generation)
                    if gap_status is not None:
                        attach_gap_status_payload(cmd_payload, gap=gap_status)
                    self.fsm.emit("CMD:PROCESS_STRATEGY", payload=cmd_payload, why="bar_closed_trigger")
                    self.logger.debug(f"[{symbol}] Emitted CMD:PROCESS_STRATEGY (tf={tf_sec}s, bar_close_ts={bar_close_ts}, atr_ready={vol_state.atr_ready})")

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

            return True

        except Exception as e:
            self.logger.error(f"Error calculating features for {symbol}: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return False

    def start(self) -> None:
        """Start the feature engineering component."""
        self.logger.info("FeatureEngineering (Phase 1) started")

    def stop(self) -> None:
        """Stop the feature engineering component."""
        self.logger.info("FeatureEngineering stopped")
