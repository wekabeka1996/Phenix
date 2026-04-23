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

from apps.reference.domains.ta_features.contracts import (
    TA_WARMUP_KEY,
    extract_ta_feature_vector,
    has_ta_feature_vector,
)

from .alpha_model import AlphaModel, AlphaScore
from .config_models import (
    AlphaSearchConfig,
    ProviderConfig,
    load_alpha_search_config,
    get_default_config,
)
from .judge.experts.expert_output_bridge import (
    alpha_score_to_expert_output,
    write_jsonl_chamber_log,
    write_jsonl_envelope_log,
    write_jsonl_shadow_log,
    write_jsonl_verdict_log,
)
from .judge.chamber import ChamberAggregator
from .judge.envelope import assemble_evidence_envelope
from .judge.verdict import synthesize_verdict

LOG = logging.getLogger(__name__)


@dataclass
class FeatureCacheEntry:
    """Cached features for a single bar."""
    symbol: str
    tf_sec: int
    bar_close_ts: int
    features: Dict[str, Any]
    ts: int
    price: float = 0.0
    warmup_status: Dict[str, bool] = field(default_factory=dict)
    ta_features_ready: Optional[bool] = None
    source_events: List[str] = field(default_factory=list)


@dataclass
class VirtualPosition:
    """Virtual position for PnL tracking."""
    provider_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    entry_price: float
    entry_ts: int
    signal_id: str
    model_signal_id: Optional[str] = None
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
    objective_feedback_events: int = 0
    objective_feedback_total: float = 0.0


class AlphaSearchBacktestPlugin:
    """
    Multi-provider backtest plugin for alpha search.

        Architecture (A3):
        - Listens to EVT:FEATURES_CALCULATED and optional EVT:TA_FEATURES_CALCULATED supplements
            → caches/merges features by (symbol, tf_sec, bar_close_ts)
    - Listens to CMD:PROCESS_STRATEGY → reads cache, runs all enabled providers
    - Emits EVT:ALPHA_SCORE_CALCULATED with provider_id
    - Per-provider virtual trader for clean PnL feedback
    """

    def __init__(
        self,
        event_bus: Any,
        config: Optional[AlphaSearchConfig] = None,
        config_path: Optional[str] = None,
        system_config: Optional[Any] = None,
        shadow_book: Optional[Any] = None,
    ):
        """
        Initialize multi-provider plugin.

        Args:
            event_bus: LocalBus or compatible for event subscription
            config: Pre-loaded AlphaSearchConfig (or loads from config_path)
            config_path: Path to alpha_search.yaml (if config not provided)
        """
        self.event_bus = event_bus
        self.system_config = system_config
        self.shadow_book = shadow_book

        # Load config
        if config:
            if isinstance(config, dict):
                try:
                    self.config = AlphaSearchConfig(**config)
                except Exception as e:
                    LOG.warning(
                        f"Failed to parse dict config for AlphaSearch: {e}. Using defaults.")
                    self.config = get_default_config()
            else:
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
        self._signal_provider: Dict[str, str] = {}
        self._pending_objective_events: Dict[str, Dict[str, Any]] = {}

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
            direction_strength_cfg = None
            if cfg.adapter.direction_strength is not None:
                direction_strength_cfg = cfg.adapter.direction_strength.model_dump()
            return AuroraAlphaAdapter(
                essential_features=cfg.adapter.essential_features,
                scoring_version=cfg.adapter.scoring_version,
                signal_weights=dict(cfg.adapter.signal_weights),
                feature_neutrals=dict(cfg.adapter.feature_neutrals),
                direction_strength_cfg=direction_strength_cfg,
                regime_thresholds=dict(cfg.adapter.regime_thresholds),
                base_threshold=cfg.adapter.base_threshold,
                delta_price_cap_pct=cfg.adapter.delta_price_cap_pct,
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
                min_weight=(
                    float(self.config.objective_feedback.min_provider_weight)
                    if self.config.objective_feedback.enabled and self.config.objective_feedback.min_provider_weight is not None
                    else 0.0
                ),
                max_weight=(
                    float(self.config.objective_feedback.max_provider_weight)
                    if self.config.objective_feedback.enabled and self.config.objective_feedback.max_provider_weight is not None
                    else 1.0
                ),
                performance_window_days=cfg.ensemble.performance_window_days,
                risk_adjustment=cfg.ensemble.risk_adjustment,
                objective_feedback_enabled=bool(
                    self.config.objective_feedback.enabled),
                objective_feedback_window_trades=(
                    int(self.config.objective_feedback.window_trades)
                    if self.config.objective_feedback.enabled and self.config.objective_feedback.window_trades is not None
                    else None
                ),
                objective_feedback_rebalance_every_closed_trades=(
                    int(self.config.objective_feedback.rebalance_every_closed_trades)
                    if self.config.objective_feedback.enabled and self.config.objective_feedback.rebalance_every_closed_trades is not None
                    else None
                ),
            )
            return EnsembleModel(config=ensemble_cfg, models=models)
        elif cfg.judge_expert:
            # Judge expert (Phase 2 shadow expert)
            return self._create_judge_expert(name, cfg)
        else:
            LOG.warning(f"Provider '{name}' has no adapter or ensemble config")
            return None

    def _create_judge_expert(self, name: str, cfg: ProviderConfig) -> Optional[AlphaModel]:
        """Create a judge expert model from judge config.

        Reads expert config from self.config.judge.experts and instantiates
        the appropriate expert class.
        """
        judge_cfg = self.config.judge
        if judge_cfg is None or judge_cfg.mode == "off":
            LOG.debug(f"Judge mode is off, skipping judge expert '{name}'")
            return None

        experts_cfg = judge_cfg.experts
        if experts_cfg is None:
            LOG.warning(f"Judge experts config is None, skipping '{name}'")
            return None

        expert_type = cfg.judge_expert.expert_type
        if expert_type == "signal_weights":
            if not experts_cfg.signal_weights.enabled:
                LOG.debug(f"signal_weights expert disabled, skipping '{name}'")
                return None
            from .judge.experts.signal_weights_expert import SignalWeightsExpert
            return SignalWeightsExpert(experts_cfg.signal_weights)
        elif expert_type == "feature_neutrals":
            if not experts_cfg.feature_neutrals.enabled:
                LOG.debug(
                    f"feature_neutrals expert disabled, skipping '{name}'")
                return None
            from .judge.experts.feature_neutrals_expert import FeatureNeutralsExpert
            return FeatureNeutralsExpert(experts_cfg.feature_neutrals)
        else:
            LOG.warning(
                f"Unknown judge expert type '{expert_type}' for '{name}'")
            return None

    def _register_listeners(self) -> None:
        """Register event listeners for two-phase bridge."""
        if hasattr(self.event_bus, "listen"):
            feature_events = [self.config.triggers.feature_event]
            if self._should_cache_ta_features():
                ta_feature_event = self.config.triggers.ta_feature_event
                if ta_feature_event and ta_feature_event not in feature_events:
                    feature_events.append(ta_feature_event)

            for feature_event in feature_events:
                self.event_bus.listen(
                    feature_event,
                    lambda event, _event_name=feature_event, **kwargs: self._on_features_cache(
                        event,
                        source_event=_event_name,
                        **kwargs,
                    ),
                )
            # Phase 2: Score on decision event
            self.event_bus.listen(
                self.config.triggers.decision_event,
                self._on_decision_score
            )
            # Trade tracking for virtual PnL
            self.event_bus.listen("EVT:TRADE_EXECUTED", self._on_trade)
            if self.config.objective_feedback.enabled:
                self.event_bus.listen(
                    "EVT:OBJECTIVE_REALIZED_V1", self._on_objective_realized)

            LOG.debug(
                f"AlphaSearch listeners: {','.join(feature_events)} → cache, "
                f"{self.config.triggers.decision_event} → score"
            )

    def _should_cache_ta_features(self) -> bool:
        """Return True when ta_ensemble provider needs the separate TA event plane."""
        cfg = self.config.providers.get("ta_ensemble")
        return bool(cfg and cfg.enabled)

    # =========================================================================
    # Phase 1: Cache features on feature events
    # =========================================================================

    def _on_features_cache(
        self,
        event: Any,
        *,
        source_event: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Cache features from the configured feature events.

        Key = (symbol, tf_sec, bar_close_ts)
        """
        if not self.enabled:
            return

        payload = self._extract_payload(event)
        if not payload:
            return

        snapshot = self._normalize_feature_snapshot(
            payload,
            source_event=source_event,
        )
        if snapshot is None:
            return

        # Cache entry — normalize bar_close_ts to milliseconds
        key = (
            snapshot["symbol"],
            snapshot["tf_sec"],
            snapshot["bar_close_ts"],
        )
        existing = self._feature_cache.get(key)
        if existing is None:
            self._feature_cache[key] = FeatureCacheEntry(
                symbol=snapshot["symbol"],
                tf_sec=snapshot["tf_sec"],
                bar_close_ts=snapshot["bar_close_ts"],
                features=dict(snapshot["features"]),
                ts=snapshot["ts"],
                price=snapshot["price"],
                warmup_status=dict(snapshot["warmup_status"]),
                ta_features_ready=snapshot["ta_features_ready"],
                source_events=[snapshot["source_event"]],
            )
        else:
            merged_features = dict(existing.features)
            merged_features.update(snapshot["features"])
            merged_warmup = dict(existing.warmup_status)
            merged_warmup.update(snapshot["warmup_status"])
            merged_sources = list(existing.source_events)
            if snapshot["source_event"] not in merged_sources:
                merged_sources.append(snapshot["source_event"])
            ta_features_ready = existing.ta_features_ready
            if snapshot["ta_features_ready"] is not None:
                ta_features_ready = snapshot["ta_features_ready"]

            self._feature_cache[key] = FeatureCacheEntry(
                symbol=existing.symbol,
                tf_sec=existing.tf_sec,
                bar_close_ts=existing.bar_close_ts,
                features=merged_features,
                ts=max(existing.ts, snapshot["ts"]),
                price=snapshot["price"] or existing.price,
                warmup_status=merged_warmup,
                ta_features_ready=ta_features_ready,
                source_events=merged_sources,
            )

        # Prune old entries for this symbol
        self._prune_cache(snapshot["symbol"])

        LOG.debug(
            "[%s] Cached %s for bar_close_ts=%s",
            snapshot["symbol"],
            snapshot["source_event"],
            snapshot["bar_close_ts"],
        )

    def _normalize_feature_snapshot(
        self,
        payload: Dict[str, Any],
        *,
        source_event: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Normalize FE and TA payloads into a single cacheable shape."""
        source_name = source_event or self.config.triggers.feature_event
        symbol = payload.get("symbol", "")
        tf_sec = int(payload.get("tf_sec", 300))

        if not symbol:
            return None

        if self._is_ta_feature_payload(payload, source_event=source_event):
            features = extract_ta_feature_vector(payload)
            if not features:
                return None
            ts = int(payload.get("ts") or payload.get("bar_close_ts") or 0)
            bar_close_ts = self._normalize_timestamp(
                int(payload.get("bar_close_ts") or ts)
            )
            return {
                "symbol": symbol,
                "tf_sec": tf_sec,
                "bar_close_ts": bar_close_ts,
                "features": features,
                "ts": ts,
                "price": self._extract_price_from_payload(payload, features),
                "warmup_status": {
                    TA_WARMUP_KEY: bool(payload.get("is_warm", False))
                },
                "ta_features_ready": bool(payload.get("is_warm", False)),
                "source_event": source_name,
            }

        features = payload.get("features", {})
        if not features:
            return None

        ts = int(payload.get("ts", 0) or 0)
        bar_raw = payload.get("bar")
        bar = bar_raw if isinstance(bar_raw, dict) else {}
        bar_close_ts = self._normalize_timestamp(
            int(bar.get("close_ts") or bar.get("ts")
                or payload.get("bar_close_ts") or ts)
        )
        return {
            "symbol": symbol,
            "tf_sec": tf_sec,
            "bar_close_ts": bar_close_ts,
            "features": dict(features),
            "ts": ts,
            "price": self._extract_price_from_payload(payload, features),
            "warmup_status": self._extract_warmup_status(payload),
            "ta_features_ready": None,
            "source_event": source_name,
        }

    def _is_ta_feature_payload(
        self,
        payload: Dict[str, Any],
        *,
        source_event: Optional[str],
    ) -> bool:
        """Detect whether a payload belongs to the separate TA event plane."""
        return (
            source_event == self.config.triggers.ta_feature_event
            or payload.get("source") == "ta_features"
            or (
                not isinstance(payload.get("features"), dict)
                and has_ta_feature_vector(payload)
            )
        )

    def _extract_warmup_status(self, payload: Dict[str, Any]) -> Dict[str, bool]:
        """Normalize warmup readiness payload variants into a bool dict."""
        if isinstance(payload.get("warmup_status"), dict):
            return {
                str(key): bool(value)
                for key, value in payload["warmup_status"].items()
            }
        if isinstance(payload.get("warmup_readiness"), dict):
            return {
                str(key): bool(value)
                for key, value in payload["warmup_readiness"].items()
            }

        warmup = payload.get("warmup")
        ready = warmup.get("ready") if isinstance(warmup, dict) else None
        if isinstance(ready, dict):
            return {str(key): bool(value) for key, value in ready.items()}
        return {}

    def _extract_price_from_payload(
        self,
        payload: Dict[str, Any],
        features: Dict[str, Any],
    ) -> float:
        """Best-effort price extraction across FE and TA payload shapes."""
        price = self._get_price_from_features(features)
        if price > 0:
            return price

        for key in ("close", "price", "last_price"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue

        bar_raw = payload.get("bar")
        bar = bar_raw if isinstance(bar_raw, dict) else {}
        for key in ("close", "close_price"):
            value = bar.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return 0.0

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

        # Phase 3: Build solicited expert roster and output collection
        solicited_expert_ids = []
        judge_expert_outputs = []
        for pid, pcfg in self.provider_configs.items():
            if pcfg.judge_expert is not None and self._is_symbol_allowed(symbol, pcfg):
                # Resolve expert_id from judge expert config block
                expert_id = self._resolve_judge_expert_id(
                    pcfg.judge_expert.expert_type)
                if expert_id:
                    solicited_expert_ids.append(expert_id)

        # Run each enabled provider
        for provider_id, model in self.providers.items():
            cfg = self.provider_configs[provider_id]

            # Check symbol allowlist
            if not self._is_symbol_allowed(symbol, cfg):
                continue
            if cfg.min_tf_sec is not None and tf_sec < cfg.min_tf_sec:
                continue
            if self._provider_requires_ta_source(provider_id=provider_id, model=model):
                if self.config.triggers.ta_feature_event not in cache_entry.source_events:
                    LOG.warning(
                        "[%s] Provider %s skipped: missing %s for bar_close_ts=%s",
                        symbol,
                        provider_id,
                        self.config.triggers.ta_feature_event,
                        bar_close_ts,
                    )
                    if cfg.fail_closed:
                        self._emit_fail_closed_score(
                            provider_id,
                            symbol,
                            tf_sec,
                            bar_close_ts,
                            reason="ta_features_missing_for_bar",
                        )
                    continue
                if cache_entry.ta_features_ready is False:
                    LOG.warning(
                        "[%s] Provider %s skipped: ta_features not warm for bar_close_ts=%s",
                        symbol,
                        provider_id,
                        bar_close_ts,
                    )
                    if cfg.fail_closed:
                        self._emit_fail_closed_score(
                            provider_id,
                            symbol,
                            tf_sec,
                            bar_close_ts,
                            reason="ta_features_not_warm",
                        )
                    continue

            normalized_features = self._normalize_features_for_provider(
                provider_id=provider_id,
                model=model,
                features=features,
            )
            missing_required = self._missing_required_features(
                provider_id=provider_id,
                model=model,
                features=normalized_features,
            )
            if missing_required:
                LOG.warning(
                    "[%s] Provider %s skipped: missing required features: %s",
                    symbol,
                    provider_id,
                    ",".join(missing_required[:8]),
                )
                if cfg.fail_closed:
                    self._emit_fail_closed_score(
                        provider_id, symbol, tf_sec, bar_close_ts)
                continue

            # Get current price for virtual trader
            current_price = cache_entry.price or self._get_price_from_features(
                normalized_features
            )

            # Calculate score
            try:
                score = model.calculate_alpha(
                    symbol=symbol,
                    market_data={"close": current_price},
                    features=normalized_features,
                    context={"mode": "backtest", "shadow": self.shadow_mode}
                )

                expert_output = self._process_score(
                    provider_id=provider_id,
                    symbol=symbol,
                    score=score,
                    threshold=cfg.threshold,
                    current_price=current_price,
                    current_ts=cache_entry.ts,
                    tf_sec=tf_sec,
                    bar_close_ts=bar_close_ts,
                )
                if expert_output is not None:
                    judge_expert_outputs.append(expert_output)

            except Exception as e:
                LOG.warning(f"[{symbol}] Provider {provider_id} error: {e}")
                if cfg.fail_closed:
                    self._emit_fail_closed_score(
                        provider_id, symbol, tf_sec, bar_close_ts)

        # Phase 3: Chamber aggregation after provider loop
        if solicited_expert_ids:
            self._run_chamber_aggregation(
                symbol=symbol,
                tf_sec=tf_sec,
                bar_close_ts=bar_close_ts,
                solicited_expert_ids=solicited_expert_ids,
                judge_expert_outputs=judge_expert_outputs,
                features=cache_entry.features if cache_entry else {},
            )

    def _normalize_features_for_provider(
        self,
        *,
        provider_id: str,
        model: AlphaModel,
        features: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply additive feature aliases expected by legacy TA ensemble models."""
        normalized = dict(features or {})

        # Legacy/current FE naming bridge for ta_ensemble models.
        if "bb_position" not in normalized and "bb_percent_b" in normalized:
            normalized["bb_position"] = normalized["bb_percent_b"]
        if "volume_sma_ratio" not in normalized and "volume_ratio" in normalized:
            normalized["volume_sma_ratio"] = normalized["volume_ratio"]
        if "stoch_k" not in normalized and "stochastic_k" in normalized:
            normalized["stoch_k"] = normalized["stochastic_k"]
        if "stoch_d" not in normalized and "stochastic_d" in normalized:
            normalized["stoch_d"] = normalized["stochastic_d"]
        if "price_momentum_5m" not in normalized and "momentum_5" in normalized:
            normalized["price_momentum_5m"] = normalized["momentum_5"]
        if "price_momentum_1h" not in normalized and "momentum_60" in normalized:
            normalized["price_momentum_1h"] = normalized["momentum_60"]
        if "price_momentum_1d" not in normalized and "momentum_1440" in normalized:
            normalized["price_momentum_1d"] = normalized["momentum_1440"]
        if "volume_momentum_5m" not in normalized and "volume_momentum" in normalized:
            normalized["volume_momentum_5m"] = normalized["volume_momentum"]
        if "macd_signal" not in normalized and "macd_histogram" in normalized:
            normalized["macd_signal"] = normalized["macd_histogram"]
        if "atr_ratio" not in normalized and "atr_pct" in normalized:
            try:
                normalized["atr_ratio"] = 1.0 + float(normalized["atr_pct"])
            except (TypeError, ValueError):
                pass
        if "price_range_ratio" not in normalized and "range_pct" in normalized:
            try:
                normalized["price_range_ratio"] = 1.0 + \
                    float(normalized["range_pct"])
            except (TypeError, ValueError):
                pass
        if "realized_volatility_1h" not in normalized and "realized_volatility" in normalized:
            normalized["realized_volatility_1h"] = normalized["realized_volatility"]
        if "realized_volatility_1d" not in normalized and "realized_volatility" in normalized:
            normalized["realized_volatility_1d"] = normalized["realized_volatility"]
        if "bb_width_change" not in normalized:
            normalized["bb_width_change"] = 0.0
        if "volume_volatility_ratio" not in normalized:
            fallback_volume_ratio = normalized.get(
                "volume_sma_ratio", normalized.get("volume_ratio", 1.0))
            normalized["volume_volatility_ratio"] = fallback_volume_ratio

        required_features = []
        try:
            required_features = self._get_required_features(model)
        except Exception:
            required_features = []

        return normalized

    def _get_required_features(self, model: AlphaModel) -> List[str]:
        """Resolve required features for plain models and ensembles."""
        if hasattr(model, "get_required_features"):
            try:
                required = list(model.get_required_features())
                if required:
                    return required
            except Exception:
                pass

        nested_models = getattr(model, "models", None)
        if isinstance(nested_models, dict):
            merged: list[str] = []
            for nested in nested_models.values():
                for feature_name in self._get_required_features(nested):
                    if feature_name not in merged:
                        merged.append(feature_name)
            return merged

        return []

    def _missing_required_features(
        self,
        *,
        provider_id: str,
        model: AlphaModel,
        features: Dict[str, Any],
    ) -> List[str]:
        """Return missing required features for providers that declare strict inputs."""
        required = self._get_required_features(model)
        if not required:
            return []

        model_name = ""
        try:
            model_name = str(model.get_model_name())
        except Exception:
            model_name = ""

        is_ensemble_provider = provider_id == "ta_ensemble" or "ensemble" in model_name
        if not is_ensemble_provider:
            return []

        return [name for name in required if name not in features]

    def _provider_requires_ta_source(
        self,
        *,
        provider_id: str,
        model: AlphaModel,
    ) -> bool:
        """Return True when the provider must consume the explicit TA event plane."""
        model_name = ""
        try:
            model_name = str(model.get_model_name())
        except Exception:
            model_name = ""
        return provider_id == "ta_ensemble" or "ensemble" in model_name

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

    def _extract_model_signal_id(self, score: AlphaScore) -> Optional[str]:
        """Extract underlying model signal_id from why-chain when available."""
        for reason in score.why:
            if isinstance(reason, str) and reason.startswith("signal_id="):
                signal_id = reason.split("=", 1)[1].strip()
                if signal_id:
                    return signal_id
        return None

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
    ) -> Optional["ExpertOutput"]:
        """Process calculated score: emit event, update virtual trader.

        Returns ExpertOutput for judge expert providers (Phase 3 chamber
        collection), None for all others.
        """
        stats = self.provider_stats[provider_id]
        stats.signals_generated += 1

        if score.score > Decimal(str(threshold)):
            stats.signals_long += 1
        elif score.score < Decimal(str(-threshold)):
            stats.signals_short += 1

        # Generate signal ID
        self._signal_counter += 1
        signal_id = f"{provider_id}_sig_{self._signal_counter}"
        self._signal_provider[signal_id] = provider_id
        model_signal_id = self._extract_model_signal_id(score)

        # Emit event — judge experts use dedicated shadow path
        expert_output = None
        cfg = self.provider_configs[provider_id]
        if cfg.judge_expert is not None:
            expert_output = self._process_judge_expert_score(
                provider_id=provider_id,
                symbol=symbol,
                score=score,
                tf_sec=tf_sec,
                bar_close_ts=bar_close_ts,
            )
        else:
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
                    model_signal_id=model_signal_id,
                )

        return expert_output

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

    def _process_judge_expert_score(
        self,
        provider_id: str,
        symbol: str,
        score: AlphaScore,
        tf_sec: int,
        bar_close_ts: int,
    ) -> Optional["ExpertOutput"]:
        """Phase 2+3 shadow path for judge expert outputs.

        Layer 2 integration:
        1. Translate AlphaScore → ExpertOutput via bridge
        2. Emit EVT:JUDGE_EXPERT_PRODUCED_V1
        3. Write JSONL shadow log when enabled
        4. Return ExpertOutput for Phase 3 chamber collection
        Does NOT emit EVT:ALPHA_SCORE_CALCULATED.
        """
        cfg = self.provider_configs[provider_id]
        judge_cfg = self.config.judge

        # Resolve expert_version from judge expert config
        expert_type = cfg.judge_expert.expert_type
        expert_version = "1.0.0"
        signal_threshold = self._resolve_judge_expert_signal_threshold(expert_type)
        if judge_cfg and judge_cfg.experts:
            if expert_type == "signal_weights":
                expert_version = judge_cfg.experts.signal_weights.expert_version
            elif expert_type == "feature_neutrals":
                expert_version = judge_cfg.experts.feature_neutrals.expert_version

        # 1. Bridge: AlphaScore → ExpertOutput
        expert_output = alpha_score_to_expert_output(
            score,
            expert_version=expert_version,
            signal_threshold=signal_threshold,
            tf_sec=tf_sec,
            ts_ms=bar_close_ts,
        )

        # 2. Emit EVT:JUDGE_EXPERT_PRODUCED_V1
        self.event_bus.emit(
            event_name="EVT:JUDGE_EXPERT_PRODUCED_V1",
            payload=expert_output.model_dump(),
            why=f"judge_expert_{provider_id}",
        )

        # 3. Write JSONL shadow log when enabled
        if (
            judge_cfg
            and judge_cfg.shadow_log
            and judge_cfg.shadow_log.enabled
        ):
            try:
                write_jsonl_shadow_log(
                    expert_output,
                    log_dir=judge_cfg.shadow_log.log_dir,
                )
            except Exception:
                LOG.exception(
                    "[%s] Failed to write judge shadow log for %s",
                    symbol,
                    provider_id,
                )

        LOG.debug(
            "[%s] %s: judge expert → %s conf=%.4f (shadow)",
            symbol,
            provider_id,
            expert_output.entry_verdict,
            expert_output.confidence,
        )

        # 4. Return for Phase 3 chamber collection
        return expert_output

    def _resolve_judge_expert_id(self, expert_type: str) -> Optional[str]:
        """Resolve expert_id from the judge expert config block by expert_type."""
        judge_cfg = self.config.judge
        if not judge_cfg or not judge_cfg.experts:
            return None
        if expert_type == "signal_weights":
            return judge_cfg.experts.signal_weights.expert_id
        elif expert_type == "feature_neutrals":
            return judge_cfg.experts.feature_neutrals.expert_id
        return None

    def _resolve_judge_expert_signal_threshold(self, expert_type: str) -> float:
        """Resolve the authoritative signal_threshold from the judge expert config."""
        judge_cfg = self.config.judge
        if not judge_cfg or not judge_cfg.experts:
            raise ValueError(
                "Judge expert provider requires judge.experts config to be present"
            )
        if expert_type == "signal_weights":
            return judge_cfg.experts.signal_weights.signal_threshold
        if expert_type == "feature_neutrals":
            return judge_cfg.experts.feature_neutrals.signal_threshold
        raise ValueError(f"Unsupported judge expert_type '{expert_type}'")

    def _run_chamber_aggregation(
        self,
        symbol: str,
        tf_sec: int,
        bar_close_ts: int,
        solicited_expert_ids: list,
        judge_expert_outputs: list,
        features: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Phase 3+4: Run chamber aggregation and verdict synthesis.

        Aggregates collected expert outputs, emits chamber event,
        writes chamber JSONL log. Then assembles evidence envelope and
        synthesizes verdict (Phase 4). Shadow-only — never consumed by
        decision_making or execution_position.
        """
        judge_cfg = self.config.judge
        if not judge_cfg or judge_cfg.mode != "shadow":
            return
        chamber_cfg = judge_cfg.chamber
        if not chamber_cfg:
            return

        # Entry chamber
        if chamber_cfg.entry_enabled:
            entry_agg = ChamberAggregator("ENTRY", chamber_cfg)
            entry_result = entry_agg.aggregate(
                judge_expert_outputs,
                expected_expert_ids=solicited_expert_ids,
                symbol=symbol,
                tf_sec=tf_sec,
                ts_ms=bar_close_ts,
            )
            self.event_bus.emit(
                event_name="EVT:JUDGE_CHAMBER_AGGREGATED_V1",
                payload=entry_result.model_dump(),
                why=f"judge_chamber_entry_{symbol}",
            )
            if judge_cfg.shadow_log and judge_cfg.shadow_log.enabled:
                try:
                    write_jsonl_chamber_log(
                        entry_result,
                        log_dir=judge_cfg.shadow_log.log_dir,
                    )
                except Exception:
                    LOG.exception(
                        "[%s] Failed to write chamber log", symbol
                    )
            LOG.debug(
                "[%s] Entry chamber: %s experts, %s responding, %s → %s (shadow)",
                symbol,
                entry_result.expert_count,
                entry_result.responding_count,
                entry_result.admissibility,
                entry_result.consensus_direction,
            )

            # Phase 4: Entry verdict path
            if judge_cfg.verdict and judge_cfg.verdict.entry_enabled:
                self._assemble_and_emit_verdict(
                    chamber_result=entry_result,
                    judge_cfg=judge_cfg,
                    bar_close_ts=bar_close_ts,
                    features=features,
                    verdict_event="EVT:JUDGE_ENTRY_VERDICT_V1",
                )

        # Lifecycle chamber stub (only when explicitly enabled)
        if chamber_cfg.lifecycle_enabled:
            lifecycle_agg = ChamberAggregator("LIFECYCLE", chamber_cfg)
            lifecycle_result = lifecycle_agg.aggregate(
                [],
                expected_expert_ids=[],
                symbol=symbol,
                tf_sec=tf_sec,
                ts_ms=bar_close_ts,
            )
            self.event_bus.emit(
                event_name="EVT:JUDGE_CHAMBER_AGGREGATED_V1",
                payload=lifecycle_result.model_dump(),
                why=f"judge_chamber_lifecycle_{symbol}",
            )
            if judge_cfg.shadow_log and judge_cfg.shadow_log.enabled:
                try:
                    write_jsonl_chamber_log(
                        lifecycle_result,
                        log_dir=judge_cfg.shadow_log.log_dir,
                    )
                except Exception:
                    LOG.exception(
                        "[%s] Failed to write lifecycle chamber log", symbol
                    )

            # Phase 4: Lifecycle verdict path
            if judge_cfg.verdict and judge_cfg.verdict.lifecycle_enabled:
                self._assemble_and_emit_verdict(
                    chamber_result=lifecycle_result,
                    judge_cfg=judge_cfg,
                    bar_close_ts=bar_close_ts,
                    features=features,
                    verdict_event="EVT:JUDGE_LIFECYCLE_VERDICT_V1",
                )

    def _assemble_and_emit_verdict(
        self,
        chamber_result,
        judge_cfg,
        bar_close_ts: int,
        features: Optional[Dict[str, Any]],
        verdict_event: str,
    ) -> None:
        """Phase 4: Assemble evidence envelope and synthesize verdict.

        Fail-closed: if envelope assembly or verdict synthesis fails,
        log WARNING and do NOT emit. The chamber event was already emitted.

        Authority: docs/LLM_JUDGE/LLM_JUDGE_PHASE4_IMPLEMENTATION_BLUEPRINT.md §12, §13.4
        """
        symbol = chamber_result.symbol
        try:
            # Extract regime metadata (optional enrichment, §13.2.1)
            regime = None
            regime_confidence = None
            if features:
                regime = features.get("regime")
                raw_rc = features.get("regime_confidence")
                if raw_rc is not None:
                    try:
                        regime_confidence = float(raw_rc)
                    except (TypeError, ValueError):
                        regime_confidence = None

            # Build features_ref
            features_ref = f"bar:{symbol}:{chamber_result.tf_sec}:{bar_close_ts}"

            # Assemble envelope
            envelope = assemble_evidence_envelope(
                chamber_result,
                verdict_config=judge_cfg.verdict,
                chamber_config=judge_cfg.chamber,
                features_ref=features_ref,
                regime=regime,
                regime_confidence=regime_confidence,
            )

            # Emit envelope event
            self.event_bus.emit(
                event_name="EVT:JUDGE_EVIDENCE_ASSEMBLED_V1",
                payload=envelope.model_dump(),
                why=f"judge_envelope_{chamber_result.verdict_scope.lower()}_{symbol}",
            )

            # Envelope JSONL
            if judge_cfg.shadow_log and judge_cfg.shadow_log.enabled:
                try:
                    write_jsonl_envelope_log(
                        envelope,
                        log_dir=judge_cfg.shadow_log.log_dir,
                    )
                except Exception:
                    LOG.exception("[%s] Failed to write envelope log", symbol)

            # Synthesize verdict
            verdict = synthesize_verdict(
                envelope,
                verdict_config=judge_cfg.verdict,
            )

            # Emit verdict event
            self.event_bus.emit(
                event_name=verdict_event,
                payload=verdict.model_dump(),
                why=f"judge_verdict_{chamber_result.verdict_scope.lower()}_{symbol}",
            )

            # Verdict JSONL
            if judge_cfg.shadow_log and judge_cfg.shadow_log.enabled:
                try:
                    write_jsonl_verdict_log(
                        verdict,
                        log_dir=judge_cfg.shadow_log.log_dir,
                    )
                except Exception:
                    LOG.exception("[%s] Failed to write verdict log", symbol)

            LOG.debug(
                "[%s] %s verdict: %s conf=%.4f dissent=%s (shadow)",
                symbol,
                chamber_result.verdict_scope,
                verdict.entry_verdict or verdict.lifecycle_verdict,
                verdict.confidence,
                verdict.dissent_noted,
            )

        except Exception:
            LOG.warning(
                "[%s] Phase 4 verdict assembly failed for %s chamber (fail-closed)",
                symbol,
                chamber_result.verdict_scope,
                exc_info=True,
            )

    def _emit_fail_closed_score(
        self,
        provider_id: str,
        symbol: str,
        tf_sec: int,
        bar_close_ts: int,
        reason: str = "missing_features_for_bar",
    ) -> None:
        """Emit fail-closed score (score=0) when features unavailable.

        Judge expert providers are silently suppressed — they must not leak
        into the generic EVT:ALPHA_SCORE_CALCULATED stream.
        """
        cfg = self.provider_configs.get(provider_id)
        if cfg and cfg.judge_expert is not None:
            LOG.debug(
                "[%s] Judge expert %s fail-closed suppressed: %s",
                symbol, provider_id, reason,
            )
            return

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
            "why": [f"fail_closed:{reason}"],
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

            drawdown_exit = getattr(exit_cfg, "max_drawdown_exit", None)
            drawdown_hit = False
            if drawdown_exit is not None and pos.entry_price > 0:
                if pos.side == "BUY":
                    adverse_move_pct = (
                        pos.entry_price - current_price) / pos.entry_price * 100.0
                else:
                    adverse_move_pct = (
                        current_price - pos.entry_price) / pos.entry_price * 100.0
                drawdown_hit = adverse_move_pct >= drawdown_exit

            # Exit conditions
            should_exit = (
                pos.bars_held >= exit_cfg.max_bars or
                duration_sec >= exit_cfg.max_hold_sec or
                drawdown_hit
            )

            if should_exit:
                self._close_virtual_position(
                    provider_id=provider_id,
                    pos=pos,
                    exit_price=current_price,
                    exit_ts=current_ts,
                    exit_reason="drawdown_exit" if drawdown_hit else "time_exit",
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
        model_signal_id: Optional[str],
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
            model_signal_id=model_signal_id,
        ))

        LOG.debug(
            f"[{symbol}] {provider_id} OPEN VIRTUAL {side} @ {current_price}")

    def _close_virtual_position(
        self,
        provider_id: str,
        pos: VirtualPosition,
        exit_price: float,
        exit_ts: int,
        exit_reason: str = "time_exit",
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
            "model_signal_id": pos.model_signal_id,
            "exit_reason": exit_reason,
        }
        self.closed_positions[provider_id].append(closed_record)
        pending_event = self._pending_objective_events.pop(pos.signal_id, None)
        if pending_event is not None:
            self._attach_objective_feedback(
                provider_id=provider_id,
                signal_id=pos.signal_id,
                payload=pending_event,
            )
        elif self.config.objective_feedback.enabled:
            self.event_bus.emit(
                event_name="EVT:OBJECTIVE_REALIZED_V1",
                payload=self._build_virtual_objective_payload(
                    provider_id=provider_id,
                    position=pos,
                    exit_price=exit_price,
                    exit_ts=exit_ts,
                    exit_reason=exit_reason,
                    realized_pnl=notional_pnl,
                ),
                why="alpha_search_virtual_objective_realized",
            )

        LOG.debug(
            f"[{pos.symbol}] {provider_id} CLOSE VIRTUAL {pos.side} "
            f"PnL={notional_pnl:.2f} (held {pos.bars_held} bars)"
        )

    def _find_closed_record(
        self,
        *,
        provider_id: str,
        signal_id: str,
    ) -> Optional[Dict[str, Any]]:
        for record in reversed(self.closed_positions.get(provider_id, [])):
            if record.get("signal_id") == signal_id:
                return record
        return None

    def _clip_unit(self, value: float) -> float:
        return max(-1.0, min(1.0, float(value)))

    def _build_virtual_objective_payload(
        self,
        *,
        provider_id: str,
        position: VirtualPosition,
        exit_price: float,
        exit_ts: int,
        exit_reason: str,
        realized_pnl: float,
    ) -> Dict[str, Any]:
        duration_sec = max(0.0, (exit_ts - position.entry_ts) / 1000.0)
        pnl_scale = float(self.config.virtual_trader.notional_size)
        pnl_efficiency = self._clip_unit(realized_pnl / pnl_scale)
        max_hold_sec = float(self.config.virtual_trader.exit.max_hold_sec)
        duration_efficiency = self._clip_unit(
            1.0 - (duration_sec / max_hold_sec))
        realized_quality_score = (pnl_efficiency + duration_efficiency) / 2.0
        return {
            "strategy_id": "alpha_search_virtual",
            "symbol": position.symbol,
            "entry_rid": position.signal_id,
            "close_rid": f"{position.signal_id}:close",
            "regime_entry": "UNKNOWN",
            "regime_exit": "UNKNOWN",
            "pretrade_objective_trace": {},
            "realized_components": {
                "realized_pnl_efficiency": pnl_efficiency,
                "duration_efficiency": duration_efficiency,
            },
            "realized_quality_score": realized_quality_score,
            "realized_pnl": realized_pnl,
            "fees": 0.0,
            "duration_sec": duration_sec,
            "mae": 0.0,
            "mfe": 0.0,
            "close_reason": exit_reason,
            "signal_id": position.signal_id,
        }

    def _compute_objective_feedback_score(self, payload: Dict[str, Any]) -> float:
        cfg = self.config.objective_feedback
        if not cfg.enabled:
            raise ValueError("objective_feedback disabled")
        components = payload.get("realized_components")
        if not isinstance(components, dict):
            raise ValueError(
                "objective feedback payload requires realized_components")

        metrics: Dict[str, float] = {}
        metrics["realized_quality_score"] = float(
            payload["realized_quality_score"])
        metrics["realized_pnl"] = self._clip_unit(
            float(payload["realized_pnl"]) /
            float(self.config.virtual_trader.notional_size)
        )
        for key, value in components.items():
            metrics[str(key)] = float(value)

        assert cfg.quality_metric_weights is not None
        missing = [name for name in cfg.quality_metric_weights.keys()
                   if name not in metrics]
        if missing:
            raise ValueError(
                "objective feedback payload missing metrics: " +
                ",".join(sorted(missing))
            )
        denom = sum(abs(float(weight))
                    for weight in cfg.quality_metric_weights.values())
        if denom <= 0.0:
            raise ValueError(
                "objective feedback weights must have non-zero mass")
        weighted_sum = sum(
            float(cfg.quality_metric_weights[name]) * metrics[name]
            for name in cfg.quality_metric_weights.keys()
        )
        return self._clip_unit(weighted_sum / denom)

    def _attach_objective_feedback(
        self,
        *,
        provider_id: str,
        signal_id: str,
        payload: Dict[str, Any],
    ) -> None:
        closed_record = self._find_closed_record(
            provider_id=provider_id, signal_id=signal_id)
        if closed_record is None:
            self._pending_objective_events[signal_id] = payload
            return

        feedback_score = self._compute_objective_feedback_score(payload)
        closed_record["objective_realized"] = payload
        closed_record["objective_feedback_score"] = feedback_score

        stats = self.provider_stats.get(provider_id)
        if stats is not None:
            stats.objective_feedback_events += 1
            stats.objective_feedback_total += feedback_score

        provider_model = self.providers.get(provider_id)
        model_signal_id = closed_record.get("model_signal_id")
        if provider_model is not None and hasattr(provider_model, "on_trade_result") and model_signal_id:
            provider_model.on_trade_result(
                signal_id=str(model_signal_id),
                pnl=float(closed_record["pnl"]),
                feedback_score=feedback_score,
                pnl_scale=float(self.config.virtual_trader.notional_size),
                feedback_trace=payload,
            )

    def _on_objective_realized(self, event: Any, **kwargs) -> None:
        payload = self._extract_payload(event)
        if not payload or not self.config.objective_feedback.enabled:
            return
        signal_id = str(payload.get("signal_id")
                        or payload.get("entry_rid") or "").strip()
        if not signal_id:
            return
        provider_id = self._signal_provider.get(signal_id)
        if provider_id is None and "_sig_" in signal_id:
            provider_id = signal_id.split("_sig_", 1)[0]
        if provider_id is None:
            self._pending_objective_events[signal_id] = payload
            return
        try:
            self._attach_objective_feedback(
                provider_id=provider_id,
                signal_id=signal_id,
                payload=payload,
            )
        except Exception as exc:
            LOG.warning(
                "Failed to attach objective feedback for %s: %s", signal_id, exc)

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
        if "pld" in payload and isinstance(payload["pld"], dict):
            return payload["pld"]
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
                "objective_feedback": {
                    "events": stats.objective_feedback_events,
                    "avg_feedback_score": round(
                        stats.objective_feedback_total / stats.objective_feedback_events, 4
                    ) if stats.objective_feedback_events > 0 else 0.0,
                },
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

        # DIAGNOSTICS-01: Generate post-run diagnostics if run_dir provided
        if run_dir:
            try:
                from tools.backtest_diagnostics import generate_backtest_diagnostics, save_diagnostics
                diagnostics = generate_backtest_diagnostics(run_dir)
                output_path = save_diagnostics(run_dir, diagnostics)
                LOG.info(f"Diagnostics saved to: {output_path}")
            except Exception as e:
                LOG.warning(f"Failed to generate diagnostics: {e}")

        # PHASE5-5G: Simulator shutdown auto-export
        self._run_simulator_shutdown_export()

    def _run_simulator_shutdown_export(self) -> None:
        """Phase 5 Package 5G — bounded simulator invocation on shutdown.

        Config-gated: does nothing when simulator_shutdown_export is None or
        disabled.  When enabled, loads SimulatorConfig from the referenced
        YAML file, runs the simulator once via the existing 5F run_from_config
        path, and writes calibration + summary artifacts via existing 5D/5E
        writers.  Fails closed: any error is logged and does not crash the
        broader shutdown sequence.
        """
        export_cfg = getattr(self.config, "simulator_shutdown_export", None)
        if export_cfg is None or not export_cfg.enabled:
            return

        LOG.info("PHASE5_5G: simulator shutdown export enabled, starting...")

        try:
            from .judge.simulator.cli import load_simulator_config, run_from_config
        except ImportError as exc:
            LOG.error(f"PHASE5_5G: failed to import simulator modules: {exc}")
            return

        # 1. Load simulator config
        try:
            sim_config = load_simulator_config(export_cfg.config_path)
        except (FileNotFoundError, ValueError) as exc:
            LOG.error(
                f"PHASE5_5G: invalid simulator config "
                f"(path={export_cfg.config_path!r}): {exc}"
            )
            return
        except Exception as exc:
            LOG.error(f"PHASE5_5G: unexpected config load error: {exc}")
            return

        if not sim_config.enabled:
            LOG.info(
                "PHASE5_5G: simulator config loaded but simulator "
                "enabled=False in judge_simulator.yaml, skipping."
            )
            return

        # 2. Run simulation + write outputs (reuses 5F run_from_config)
        try:
            result = run_from_config(sim_config)
        except Exception as exc:
            LOG.error(f"PHASE5_5G: simulation/export failed: {exc}")
            return

        LOG.info(
            f"PHASE5_5G: done — "
            f"verdicts={result.total_verdict_records_loaded} "
            f"outcomes={result.total_outcome_records_loaded} "
            f"matched={result.matched_count} "
            f"calibration={sim_config.calibration_dataset_path} "
            f"summary={sim_config.summary_report_path}"
        )


# Backwards compatibility: factory function
def create_plugin_from_config(
    event_bus: Any,
    config_path: str = "config/alpha_search.yaml",
) -> AlphaSearchBacktestPlugin:
    """Create plugin from config file path."""
    return AlphaSearchBacktestPlugin(event_bus=event_bus, config_path=config_path)
