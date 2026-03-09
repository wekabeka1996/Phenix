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
    AlphaSearchSystemConfig,
    ProviderConfig,
    load_alpha_search_config,
    load_system_config,
    get_default_config,
    get_default_system_config,
)
from .alpha_search_log_adapter import AlphaSearchLog

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
        system_config: Optional[AlphaSearchSystemConfig] = None,
        system_config_path: Optional[str] = None,
        shadow_book: Optional[Any] = None,
    ):
        """
        Initialize multi-provider plugin.

        Args:
            event_bus: LocalBus or compatible for event subscription
            config: Pre-loaded AlphaSearchConfig (or loads from config_path)
            config_path: Path to alpha_search.yaml (if config not provided)
            system_config: Pre-loaded system config (model tuning params)
            system_config_path: Path to alpha_search_system.yaml
        """
        self.event_bus = event_bus

        # Load config
        if config:
            self.config = config
        elif config_path:
            try:
                self.config = load_alpha_search_config(config_path)
            except Exception as e:
                LOG.warning(
                    f"Failed to load alpha_search config: {e}. Using defaults.")
                self.config = get_default_config()
        else:
            self.config = get_default_config()

        # Load system config (model tuning params)
        if system_config:
            self.system_config = system_config
        elif system_config_path:
            try:
                self.system_config = load_system_config(system_config_path)
            except Exception as e:
                LOG.warning(
                    f"Failed to load system config: {e}. Using defaults.")
                self.system_config = get_default_system_config()
        else:
            # Auto-discover system config next to main config
            self.system_config = self._auto_load_system_config(config_path)

        self.enabled = self.config.enabled
        self.shadow_mode = self.config.shadow_mode

        # ShadowBook reference (optional, injected by ScenarioManager)
        self._shadow_book = shadow_book

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
        # Cooldown after close: (provider_id, symbol) → bars_remaining
        # Prevents immediate re-entry after close (VirtualTraderExitConfig.cooldown_bars_after_close)
        self._open_cooldowns: Dict[Tuple[str, str], int] = {}
        self.closed_positions: Dict[str, List[Dict[str, Any]]] = {
            name: [] for name in self.providers
        }

        # Signal counter for IDs
        self._signal_counter = 0

        # Cache hit/miss tracking (for validation)
        self._cache_hits = 0
        self._cache_misses = 0

        # Dedicated structured log for alpha_search events
        self.dlog = AlphaSearchLog()

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

    def _auto_load_system_config(self, config_path: Optional[str]) -> AlphaSearchSystemConfig:
        """Try to load system config from same directory as main config."""
        if config_path:
            from pathlib import Path
            system_path = Path(config_path).parent / "alpha_search_system.yaml"
            if system_path.exists():
                try:
                    return load_system_config(str(system_path))
                except Exception as e:
                    LOG.debug(f"Failed to auto-load system config: {e}")
        return get_default_system_config()

    def _create_provider_model(self, name: str, cfg: ProviderConfig) -> Optional[AlphaModel]:
        """Create alpha model for a provider."""
        if cfg.adapter:
            # Aurora adapter — all scoring params from alpha_search.yaml
            from .models.aurora_adapter import AuroraAlphaAdapter
            adapter_cfg = cfg.adapter
            return AuroraAlphaAdapter(
                essential_features=adapter_cfg.essential_features,
                scoring_version=adapter_cfg.scoring_version,
                signal_weights=adapter_cfg.signal_weights,
                feature_neutrals=adapter_cfg.feature_neutrals,
                direction_strength_cfg=adapter_cfg.direction_strength.model_dump(),
                regime_thresholds=adapter_cfg.regime_thresholds,
                base_threshold=adapter_cfg.base_threshold,
                delta_price_cap_pct=adapter_cfg.delta_price_cap_pct,
            )
        elif cfg.ensemble:
            # TA ensemble
            from .ensemble import EnsembleModel, EnsembleConfig
            from .models.momentum import MomentumAlphaModel
            from .models.mean_reversion import MeanReversionAlphaModel
            from .models.volatility import VolatilityAlphaModel

            sys_cfg = self.system_config

            models = {}
            model_map = {
                "mean_reversion_v1": (MeanReversionAlphaModel, sys_cfg.mean_reversion.model_dump()),
                "momentum_v1": (MomentumAlphaModel, sys_cfg.momentum.model_dump()),
                "volatility_v1": (VolatilityAlphaModel, sys_cfg.volatility.model_dump()),
            }

            for model_name, model_cfg in cfg.ensemble.models.items():
                if model_cfg.enabled and model_name in model_map:
                    model_class, model_params = model_map[model_name]
                    models[model_name] = model_class(config=model_params)

            if not models:
                LOG.warning(f"No enabled models for ensemble '{name}'")
                return None

            ensemble_cfg = EnsembleConfig(
                rebalance_frequency_days=cfg.ensemble.rebalance_frequency_days,
                performance_window_days=cfg.ensemble.performance_window_days,
                risk_adjustment=cfg.ensemble.risk_adjustment,
            )
            ensemble = EnsembleModel(config=ensemble_cfg, models=models)
            # Pass ensemble system params
            ensemble._system_config = sys_cfg.ensemble
            return ensemble
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
        tf_sec = payload.get(
            "tf_sec", self.system_config.plugin.default_tf_sec)
        ts = payload.get("ts", 0)

        # Get bar_close_ts from bar or payload
        bar = payload.get("bar") or {}
        bar_close_ts = bar.get("close_ts") or bar.get(
            "ts") or payload.get("bar_close_ts") or ts

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

        LOG.debug(
            f"[{symbol}] Cached features for bar_close_ts={bar_close_ts}")

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
        tf_sec = payload.get(
            "tf_sec", self.system_config.plugin.default_tf_sec)
        bar_close_ts = self._normalize_timestamp(
            payload.get("bar_close_ts", 0))

        if not symbol:
            return

        # Find cached features
        cache_key = (symbol, tf_sec, bar_close_ts)
        cache_entry = self._feature_cache.get(cache_key)

        if not cache_entry:
            # Try with fuzzy match if exact match fails
            cache_entry = self._find_best_cache_match(
                symbol, tf_sec, bar_close_ts)

        if not cache_entry:
            # Fail-closed: no features available
            self._cache_misses += 1
            for provider_id, cfg in self.provider_configs.items():
                if cfg.fail_closed and self._is_symbol_allowed(symbol, cfg):
                    self._emit_fail_closed_score(
                        provider_id, symbol, tf_sec, bar_close_ts)
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

            # Skip provider if bar timeframe is below its minimum (e.g. ta_ensemble needs 5m)
            if cfg.min_tf_sec is not None and cache_entry.tf_sec < cfg.min_tf_sec:
                LOG.debug(
                    f"[{symbol}] Skipping {provider_id}: tf_sec={cache_entry.tf_sec} "
                    f"< min_tf_sec={cfg.min_tf_sec}"
                )
                continue

            # Skip provider if ALL of its required features are absent
            # (e.g. ta_ensemble needs rsi_14/bb_position/macd — absent on tick data)
            if hasattr(model, "get_required_features"):
                _required = model.get_required_features()
                missing_required = [f for f in _required if f not in features]
                if _required and missing_required:
                    model_name = ""
                    try:
                        model_name = str(model.get_model_name())
                    except Exception:
                        model_name = ""
                    is_ensemble_provider = provider_id == "ta_ensemble" or "ensemble" in model_name
                    LOG.warning(
                        f"[{symbol}] Skipping {provider_id}: "
                        f"missing required features={missing_required[:6]} (tf_sec={cache_entry.tf_sec})"
                    )
                    self.dlog.write(
                        event="PROVIDER_SKIPPED_MISSING_FEATURES",
                        provider_id=provider_id,
                        symbol=symbol,
                        payload={
                            "missing_features": missing_required[:10],
                            "required_count": len(_required),
                            "present_count": len(features),
                            "tf_sec": cache_entry.tf_sec,
                        },
                    )
                    if is_ensemble_provider:
                        continue
                    if cfg.fail_closed:
                        self._emit_fail_closed_score(
                            provider_id, symbol, tf_sec, bar_close_ts)
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
                    self._emit_fail_closed_score(
                        provider_id, symbol, tf_sec, bar_close_ts)

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
            # Limit why chain
            "why": score.why[:self.system_config.plugin.why_chain_limit],
            "features_used": score.features_used,
        }

        self.event_bus.emit(
            event_name=self.config.triggers.emit_event,
            payload=payload,
            why=f"alpha_search_{provider_id}"
        )

        self.dlog.write(
            event="SCORE_EMITTED",
            provider_id=provider_id,
            symbol=symbol,
            payload={
                "model_name": score.model_name,
                "score": float(score.score),
                "confidence": float(score.confidence),
                "threshold": threshold,
                "shadow": self.shadow_mode,
                "features_used": score.features_used,
            },
            signal_id=signal_id,
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

        self.dlog.write(
            event="FAIL_CLOSED",
            provider_id=provider_id,
            symbol=symbol,
            payload={"reason": "missing_features_for_bar",
                     "tf_sec": tf_sec, "bar_close_ts": bar_close_ts},
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
        cooldown_n = int(getattr(exit_cfg, "cooldown_bars_after_close", 0))

        # Tick down cooldowns for this provider (called once per bar per provider)
        if cooldown_n > 0:
            for k in list(self._open_cooldowns):
                if k[0] == provider_id:
                    self._open_cooldowns[k] -= 1
                    if self._open_cooldowns[k] <= 0:
                        del self._open_cooldowns[k]

        for i in range(len(positions) - 1, -1, -1):
            pos = positions[i]
            if pos.symbol != symbol:
                continue

            pos.bars_held += 1
            duration_sec = (current_ts - pos.entry_ts) / 1000.0

            exit_reason: Optional[str] = None
            exit_meta: Dict[str, Any] = {}

            # Per-trade adverse-move stop (percentage from entry).
            dd_stop_pct = getattr(exit_cfg, "max_drawdown_exit", None)
            if dd_stop_pct is not None and pos.entry_price > 0:
                if pos.side == "BUY":
                    adverse_move_pct = (
                        (pos.entry_price - current_price) / pos.entry_price
                    ) * 100.0
                else:
                    adverse_move_pct = (
                        (current_price - pos.entry_price) / pos.entry_price
                    ) * 100.0
                adverse_move_pct = max(0.0, adverse_move_pct)

                if adverse_move_pct >= float(dd_stop_pct):
                    exit_reason = "drawdown_exit"
                    exit_meta = {
                        "adverse_move_pct": round(adverse_move_pct, 4),
                        "max_drawdown_exit": float(dd_stop_pct),
                    }

            if exit_reason is None and pos.bars_held >= exit_cfg.max_bars:
                exit_reason = "max_bars"
                exit_meta = {"max_bars": int(exit_cfg.max_bars)}

            if exit_reason is None and duration_sec >= exit_cfg.max_hold_sec:
                exit_reason = "max_hold_sec"
                exit_meta = {
                    "duration_sec": round(duration_sec, 2),
                    "max_hold_sec": int(exit_cfg.max_hold_sec),
                }

            if exit_reason is not None:
                self._close_virtual_position(
                    provider_id=provider_id,
                    pos=pos,
                    exit_price=current_price,
                    exit_ts=current_ts,
                    exit_reason=exit_reason,
                    exit_meta=exit_meta,
                )
                positions.pop(i)
                # Set cooldown so next entry for this symbol is blocked
                if cooldown_n > 0:
                    self._open_cooldowns[(
                        provider_id, pos.symbol)] = cooldown_n

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

        # Check cooldown guard (post-close re-entry block)
        if self._open_cooldowns.get((provider_id, symbol), 0) > 0:
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

        self.dlog.write(
            event="VIRTUAL_OPEN",
            provider_id=provider_id,
            symbol=symbol,
            payload={"side": side, "entry_price": current_price},
            signal_id=signal_id,
        )

        LOG.debug(
            f"[{symbol}] {provider_id} OPEN VIRTUAL {side} @ {current_price}")

    def _close_virtual_position(
        self,
        provider_id: str,
        pos: VirtualPosition,
        exit_price: float,
        exit_ts: int,
        exit_reason: str,
        exit_meta: Optional[Dict[str, Any]] = None,
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
            "exit_reason": exit_reason,
            "exit_meta": exit_meta or {},
        }
        self.closed_positions[provider_id].append(closed_record)

        close_payload = {
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "bars_held": pos.bars_held,
            "pnl": round(notional_pnl, 4),
            "exit_reason": exit_reason,
        }
        if exit_meta:
            close_payload.update(exit_meta)

        self.dlog.write(
            event="VIRTUAL_CLOSE",
            provider_id=provider_id,
            symbol=pos.symbol,
            payload=close_payload,
            signal_id=pos.signal_id,
        )

        # Feed completed trade to ShadowBook for Sharpe/DD tracking
        if self._shadow_book is not None:
            self._shadow_book.record_trade(
                symbol=pos.symbol,
                side=pos.side,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                entry_ts=pos.entry_ts,
                exit_ts=exit_ts,
                bars_held=pos.bars_held,
                provider_id=provider_id,
            )

        LOG.debug(
            f"[{pos.symbol}] {provider_id} CLOSE VIRTUAL {pos.side} "
            f"PnL={notional_pnl:.2f} (held {pos.bars_held} bars)"
        )

    # =========================================================================
    # Trade Tracking (for correlation with real trades)
    # =========================================================================

    def _on_trade(self, event: Any, **kwargs) -> None:
        """Track actual trades and feed PnL back to ensemble models."""
        if not self.enabled:
            return

        payload = self._extract_payload(event)
        if not payload:
            return

        pnl = payload.get("pnl_usdt_net", payload.get("pnl", 0))
        symbol = payload.get("symbol", "")

        if not symbol or pnl == 0:
            return

        # Feed PnL to ensemble models that support on_trade_result
        for provider_id, model in self.providers.items():
            if not hasattr(model, "on_trade_result"):
                continue

            closed = self.closed_positions.get(provider_id, [])
            for pos in closed:
                if pos.get("symbol") == symbol:
                    signal_id = pos.get("signal_id", "")
                    if signal_id:
                        try:
                            model.on_trade_result(
                                signal_id=signal_id, pnl=float(pnl))
                            LOG.debug(
                                f"[{symbol}] Feedback to {provider_id}: "
                                f"signal={signal_id} pnl={pnl:.2f}"
                            )
                        except Exception as e:
                            LOG.debug(f"Feedback error for {provider_id}: {e}")
                        break  # One feedback per provider per trade

    # =========================================================================
    # Utilities
    # =========================================================================

    def _extract_payload(self, event: Any) -> Optional[Dict[str, Any]]:
        """Extract payload from event object (Message attr or LocalBus dict)."""
        if hasattr(event, "pld"):
            payload = event.pld
        elif isinstance(event, dict) and "pld" in event:
            payload = event["pld"]
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
        total_signals = sum(
            s.signals_generated for s in self.provider_stats.values())
        total_pnl = sum(s.total_pnl for s in self.provider_stats.values())
        LOG.info(
            f"AlphaSearch shutdown: {total_signals} signals, "
            f"virtual PnL={total_pnl:.2f}, providers={list(self.providers.keys())}"
        )

        self.dlog.write(
            event="SHUTDOWN_SUMMARY",
            provider_id="__all__",
            symbol="__all__",
            payload={
                "total_signals": total_signals,
                "total_virtual_pnl": round(total_pnl, 2),
                "providers": list(self.providers.keys()),
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "per_provider": {
                    name: {
                        "signals": s.signals_generated,
                        "long": s.signals_long,
                        "short": s.signals_short,
                        "pnl": round(s.total_pnl, 2),
                        "trades_closed": s.trades_closed,
                        "win_rate": round(s.wins / s.trades_closed, 4) if s.trades_closed > 0 else 0.0,
                    }
                    for name, s in self.provider_stats.items()
                },
            },
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

            # ALPHA-REPORT: Auto-generate alpha search performance report
            try:
                from tools.alpha_search_report import generate_alpha_report, save_report
                report = generate_alpha_report(run_dir)
                output_path = save_report(run_dir, report)
                LOG.info(f"Alpha search report saved to: {output_path}")
            except Exception as e:
                LOG.warning(f"Failed to generate alpha report: {e}")


# Backwards compatibility: factory function
def create_plugin_from_config(
    event_bus: Any,
    config_path: str = "config/alpha_search.yaml",
) -> AlphaSearchBacktestPlugin:
    """Create plugin from config file path."""
    return AlphaSearchBacktestPlugin(event_bus=event_bus, config_path=config_path)
