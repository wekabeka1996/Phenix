from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Tuple

from apps.reference.config.strategies.alpha_ta_ensemble import (
    AlphaTaEnsembleProfileConfig,
    AlphaTaEnsembleStrategyConfig,
)
from apps.reference.config_models import AuroraConfig
from apps.reference.domains.decision_making.contracts.core_models import ProcessStrategyCmd
from apps.reference.core.time import get_clock


LOG = logging.getLogger(__name__)


class AlphaTaEnsembleHandler:
    """Runtime handler for the alpha_ta_ensemble strategy.

    It subscribes to:
    - EVT:TA_FEATURES_CALCULATED: to update a local cache of TA features per (symbol, tf_sec, bar_close_ts)
    - CMD:PROCESS_STRATEGY: to evaluate decision signals
    """

    strategy_id = "alpha_ta_ensemble"

    def __init__(self, *, fsm: Any, config: AuroraConfig) -> None:
        self.fsm = fsm
        self.config = config
        cfg = getattr(getattr(config, "strategies", None), self.strategy_id, None)
        if cfg is None:
            raise ValueError("strategies.alpha_ta_ensemble config is required")
        self.cfg: AlphaTaEnsembleStrategyConfig = cfg

        # Local cache: (symbol, tf_sec, bar_close_ts) -> (ta_features_dict, received_ts_ms)
        self._ta_cache: Dict[Tuple[str, int, int], Tuple[Dict[str, Any], int]] = {}

        # Cooldown trace: symbol -> last_signal_ts_ms
        self._last_signal_ts_ms: Dict[str, int] = {}
        # Hourly intent counter: symbol -> (hour_bucket, count)
        self._intent_hour: Dict[str, Tuple[int, int]] = {}

    def register(self) -> None:
        if self.cfg.mode == "disabled" or not self.cfg.enabled:
            LOG.warning("alpha_ta_ensemble disabled: no event listeners registered")
            return
        self.fsm.listen("EVT:TA_FEATURES_CALCULATED", self.on_ta_features)
        self.fsm.listen("CMD:PROCESS_STRATEGY", self.on_process_strategy)
        LOG.info("alpha_ta_ensemble strategy handler registered listeners successfully")

    def on_ta_features(self, event: Any) -> None:
        """Handle incoming TA features from the TAFeaturesEngine event bus."""
        payload = event
        if hasattr(event, "pld"):
            payload = event.pld
        if not isinstance(payload, dict):
            return

        symbol = payload.get("symbol")
        tf_sec = payload.get("tf_sec")
        bar_close_ts = payload.get("bar_close_ts") or payload.get("ts")
        if symbol is None or tf_sec is None or bar_close_ts is None:
            return

        try:
            tf_sec = int(tf_sec)
            bar_close_ts = int(bar_close_ts)
        except (TypeError, ValueError):
            return

        # Extract features vector
        from apps.reference.domains.ta_features.contracts import extract_ta_feature_vector
        ta_features = extract_ta_feature_vector(payload)
        if not ta_features:
            return

        # Add is_warm metadata
        ta_features["is_warm"] = bool(payload.get("is_warm", payload.get("warmup", {}).get("full_ready", False)))

        now_ms = int(get_clock().now_ms())
        key = (symbol, tf_sec, bar_close_ts)
        self._ta_cache[key] = (ta_features, now_ms)

        # Evict old cache items to prevent memory leak
        symbol_keys = [k for k in self._ta_cache.keys() if k[0] == symbol and k[1] == tf_sec]
        if len(symbol_keys) > 20:
            symbol_keys.sort()
            for old_key in symbol_keys[:-20]:
                self._ta_cache.pop(old_key, None)

    def on_process_strategy(self, event: Any) -> None:
        """Process strategy evaluation triggered by FeatureEngineering."""
        cmd = event
        if hasattr(event, "pld"):
            from apps.reference.domains.decision_making.contracts.boundary_models import ProcessStrategyBoundary
            from apps.reference.domains.decision_making.contracts.boundary_mappers import map_process_strategy_boundary_to_cmd

            raw = dict(event.pld) if isinstance(event.pld, dict) else {}
            cmd = map_process_strategy_boundary_to_cmd(
                ProcessStrategyBoundary.model_validate(event.pld),
                raw=raw,
            )
        if not isinstance(cmd, ProcessStrategyCmd):
            LOG.warning("alpha_ta_ensemble rejected non ProcessStrategyCmd payload")
            return

        symbol = str(cmd.symbol)
        ts_ms = self._cmd_ts_ms(cmd)

        # 1. Validate if asset is active
        asset_cfg = self.cfg.assets.get(symbol)
        if not asset_cfg or not asset_cfg.enabled:
            self._emit_trace_log(
                symbol=symbol,
                profile_id="UNKNOWN",
                ts_ms=ts_ms,
                feature_ts=0,
                present_features=[],
                missing_features=[],
                component_scores={},
                weights_dict={},
                combined_score=0.0,
                side="NEUTRAL",
                threshold=self.cfg.threshold,
                regime="UNKNOWN",
                suppression_reason="symbol_disabled_or_not_assigned",
                decision_route="suppressed",
            )
            return

        profile_id = asset_cfg.profile_id
        profile = self.cfg.profiles.get(profile_id)
        if not profile:
            self._emit_trace_log(
                symbol=symbol,
                profile_id=profile_id,
                ts_ms=ts_ms,
                feature_ts=0,
                present_features=[],
                missing_features=[],
                component_scores={},
                weights_dict={},
                combined_score=0.0,
                side="NEUTRAL",
                threshold=self.cfg.threshold,
                regime="UNKNOWN",
                suppression_reason="configured_profile_not_found",
                decision_route="suppressed",
            )
            return

        # 2. Check timeframe
        if cmd.tf_sec != self.cfg.timeframe_sec:
            self._emit_trace_log(
                symbol=symbol,
                profile_id=profile_id,
                ts_ms=ts_ms,
                feature_ts=0,
                present_features=[],
                missing_features=[],
                component_scores={},
                weights_dict={},
                combined_score=0.0,
                side="NEUTRAL",
                threshold=profile.entry_threshold,
                regime="UNKNOWN",
                suppression_reason=f"tf_mismatch:{cmd.tf_sec}!={self.cfg.timeframe_sec}",
                decision_route="suppressed",
            )
            return

        # 3. Check regime safety constraints
        regime = cmd.structural_regime
        if self.cfg.safety.forbid_uncertain and regime == "UNCERTAIN":
            self._emit_trace_log(
                symbol=symbol,
                profile_id=profile_id,
                ts_ms=ts_ms,
                feature_ts=0,
                present_features=[],
                missing_features=[],
                component_scores={},
                weights_dict={},
                combined_score=0.0,
                side="NEUTRAL",
                threshold=profile.entry_threshold,
                regime=regime,
                suppression_reason="regime_uncertain_forbidden",
                decision_route="suppressed",
            )
            return

        if regime not in self.cfg.safety.allowed_regimes or regime not in profile.allowed_regimes:
            self._emit_trace_log(
                symbol=symbol,
                profile_id=profile_id,
                ts_ms=ts_ms,
                feature_ts=0,
                present_features=[],
                missing_features=[],
                component_scores={},
                weights_dict={},
                combined_score=0.0,
                side="NEUTRAL",
                threshold=profile.entry_threshold,
                regime=regime,
                suppression_reason="regime_not_allowed",
                decision_route="suppressed",
            )
            return

        # 4. Check cooldown
        cooldown_left = self._cooldown_left_ms(symbol, ts_ms)
        if cooldown_left > 0:
            self._emit_trace_log(
                symbol=symbol,
                profile_id=profile_id,
                ts_ms=ts_ms,
                feature_ts=0,
                present_features=[],
                missing_features=[],
                component_scores={},
                weights_dict={},
                combined_score=0.0,
                side="NEUTRAL",
                threshold=profile.entry_threshold,
                regime=regime,
                suppression_reason=f"cooldown_active:{cooldown_left}ms_remaining",
                decision_route="suppressed",
            )
            return

        # 5. Retrieve cached TA features
        bar_close_ts = cmd.bar_close_ts or ts_ms
        cache_key = (symbol, self.cfg.timeframe_sec, bar_close_ts)
        cache_entry = self._ta_cache.get(cache_key)

        if not cache_entry:
            self._emit_trace_log(
                symbol=symbol,
                profile_id=profile_id,
                ts_ms=ts_ms,
                feature_ts=0,
                present_features=[],
                missing_features=[],
                component_scores={},
                weights_dict={},
                combined_score=0.0,
                side="NEUTRAL",
                threshold=profile.entry_threshold,
                regime=regime,
                suppression_reason="ta_features_missing_for_bar",
                decision_route="suppressed",
            )
            return

        ta_features, cached_time_ms = cache_entry

        # 6. Verify freshness
        freshness_ms = abs(ts_ms - cached_time_ms)
        max_freshness_ms = self.cfg.safety.min_feature_freshness_sec * 1000
        if freshness_ms > max_freshness_ms:
            self._emit_trace_log(
                symbol=symbol,
                profile_id=profile_id,
                ts_ms=ts_ms,
                feature_ts=cached_time_ms,
                present_features=list(ta_features.keys()),
                missing_features=[],
                component_scores={},
                weights_dict={},
                combined_score=0.0,
                side="NEUTRAL",
                threshold=profile.entry_threshold,
                regime=regime,
                suppression_reason=f"ta_features_stale:{freshness_ms}ms_old",
                decision_route="suppressed",
            )
            return

        # Merge standard features and cached TA features
        merged_features = dict(cmd.features)
        merged_features.update(ta_features)

        # Normalize features (add default fallbacks and type conversion)
        normalized = self._normalize_features(merged_features)

        # 7. Initialize Ensemble model
        try:
            ensemble_model = self._build_ensemble_for_profile(profile)
        except Exception as exc:
            LOG.exception("Failed to build ensemble model: %s", exc)
            self._emit_trace_log(
                symbol=symbol,
                profile_id=profile_id,
                ts_ms=ts_ms,
                feature_ts=cached_time_ms,
                present_features=list(normalized.keys()),
                missing_features=[],
                component_scores={},
                weights_dict={},
                combined_score=0.0,
                side="NEUTRAL",
                threshold=profile.entry_threshold,
                regime=regime,
                suppression_reason="ensemble_model_init_failed",
                decision_route="suppressed",
            )
            return

        # Verify required features are present
        missing_features = [f for f in ensemble_model.get_required_features() if f not in normalized]
        if missing_features:
            self._emit_trace_log(
                symbol=symbol,
                profile_id=profile_id,
                ts_ms=ts_ms,
                feature_ts=cached_time_ms,
                present_features=[f for f in ensemble_model.get_required_features() if f in normalized],
                missing_features=missing_features,
                component_scores={},
                weights_dict={},
                combined_score=0.0,
                side="NEUTRAL",
                threshold=profile.entry_threshold,
                regime=regime,
                suppression_reason=f"missing_features:{','.join(missing_features)}",
                decision_route="suppressed",
            )
            return

        # 8. Score calculation
        try:
            price = self._extract_price(normalized)
            score_res = ensemble_model.calculate_alpha(
                symbol=symbol,
                market_data={"close": price},
                features=normalized,
                context={
                    "mode": "live",
                    "shadow": self.cfg.mode == "shadow",
                    "regime": regime,
                    "warmup_readiness": cmd.warmup.ready if cmd.warmup else {},
                }
            )
        except Exception as exc:
            LOG.exception("Error running ensemble scorer for %s: %s", symbol, exc)
            self._emit_trace_log(
                symbol=symbol,
                profile_id=profile_id,
                ts_ms=ts_ms,
                feature_ts=cached_time_ms,
                present_features=list(normalized.keys()),
                missing_features=[],
                component_scores={},
                weights_dict={},
                combined_score=0.0,
                side="NEUTRAL",
                threshold=profile.entry_threshold,
                regime=regime,
                suppression_reason=f"scorer_execution_failed:{str(exc)}",
                decision_route="suppressed",
            )
            return

        final_score = float(score_res.score)
        confidence = float(score_res.confidence)
        threshold = profile.entry_threshold

        # Determine side based on threshold
        side = "NEUTRAL"
        if final_score > threshold:
            side = "BUY"
        elif final_score < -threshold:
            side = "SELL"

        # Validate allowed sides
        if side != "NEUTRAL" and side not in profile.allowed_sides:
            suppressed_side = side
            side = "NEUTRAL"
            suppression_reason = f"side_not_allowed:{suppressed_side}_only_allows_{profile.allowed_sides}"
        else:
            suppression_reason = "threshold_not_breached" if side == "NEUTRAL" else None

        # Build weights and components diagnostic view
        weights_dict = {k: float(v) for k, v in ensemble_model.weights.model_weights.items()}
        contributions = ensemble_model.get_model_contributions()
        component_scores = {k: float(v) for k, v in contributions.get("performance_scores", {}).items()}

        # 9. Handle mode specific actions
        if self.cfg.mode == "shadow" or side == "NEUTRAL":
            self._emit_trace_log(
                symbol=symbol,
                profile_id=profile_id,
                ts_ms=ts_ms,
                feature_ts=cached_time_ms,
                present_features=list(normalized.keys()),
                missing_features=[],
                component_scores=component_scores,
                weights_dict=weights_dict,
                combined_score=final_score,
                side=side,
                threshold=threshold,
                regime=regime,
                suppression_reason=suppression_reason or ("shadow_only" if self.cfg.mode == "shadow" else None),
                decision_route="suppressed" if side == "NEUTRAL" else "shadow_trace",
            )
            if side != "NEUTRAL":
                self._last_signal_ts_ms[symbol] = ts_ms
            return

        if self.cfg.mode == "testnet_candidate":
            if not self._testnet_candidate_allowed():
                self._emit_trace_log(
                    symbol=symbol,
                    profile_id=profile_id,
                    ts_ms=ts_ms,
                    feature_ts=cached_time_ms,
                    present_features=list(normalized.keys()),
                    missing_features=[],
                    component_scores=component_scores,
                    weights_dict=weights_dict,
                    combined_score=final_score,
                    side=side,
                    threshold=threshold,
                    regime=regime,
                    suppression_reason=f"testnet_candidate_blocked_in_trading_mode:{self.config.trading_mode}",
                    decision_route="suppressed",
                )
                return

            if not self._hourly_intent_allowed(symbol, ts_ms):
                self._emit_trace_log(
                    symbol=symbol,
                    profile_id=profile_id,
                    ts_ms=ts_ms,
                    feature_ts=cached_time_ms,
                    present_features=list(normalized.keys()),
                    missing_features=[],
                    component_scores=component_scores,
                    weights_dict=weights_dict,
                    combined_score=final_score,
                    side=side,
                    threshold=threshold,
                    regime=regime,
                    suppression_reason="max_intents_per_symbol_hour_reached",
                    decision_route="suppressed",
                )
                return

            # Emit normal signal
            self._emit_strategy_signal(
                cmd=cmd,
                side=side,
                score=final_score,
                confidence=confidence,
                profile_id=profile_id,
                regime=regime,
                why="; ".join(score_res.why),
            )
            self._last_signal_ts_ms[symbol] = ts_ms

    def _emit_strategy_signal(
        self,
        *,
        cmd: ProcessStrategyCmd,
        side: str,
        score: float,
        confidence: float,
        profile_id: str,
        regime: str,
        why: str,
    ) -> None:
        symbol = str(cmd.symbol)
        ts_ms = self._cmd_ts_ms(cmd)
        rid = self._rid(symbol=symbol, side=side, ts_ms=ts_ms)

        payload = {
            "schema_version": 1,
            "strategy_id": self.strategy_id,
            "source_scenario_id": profile_id,
            "strategy_version": self.cfg.strategy_version,
            "symbol": symbol,
            "tf_sec": self.cfg.timeframe_sec,
            "side": side,
            "bar_close_ts": int(cmd.bar_close_ts or ts_ms),
            "readiness": {"warmup_ok": True},
            "runtime_permissions": {
                "can_open_new_risk": True,
                "can_manage_existing_risk": False,
            },
            "score": float(score),
            "confidence": float(confidence),
            "why": why,
            "ts_ms": ts_ms,
            "rid": rid,
            "valid_for_ms": int(self.cfg.safety.signal_ttl_ms),
            "why_chain": [self.strategy_id, profile_id, why],
            "source_mode": "live",
            "regime": regime,
            "volatility": cmd.features.get("volatility"),
            "liquidity": cmd.features.get("liquidity"),
            "scoring": {
                "score": float(score),
                "confidence": float(confidence),
                "side": side,
                "threshold": float(self.cfg.threshold),
                "regime": regime,
                "source_scenario_id": profile_id,
            },
        }

        self.fsm.emit(
            "EVT:STRATEGY_SIGNAL_PRODUCED",
            payload=payload,
            why=f"strategy_signal:{self.strategy_id}:{side}",
        )
        LOG.info(
            "ALPHA_TA_ENSEMBLE testnet_candidate signal produced for %s: side=%s, score=%.4f",
            symbol,
            side,
            score,
        )

    def _emit_trace_log(
        self,
        *,
        symbol: str,
        profile_id: str,
        ts_ms: int,
        feature_ts: int,
        present_features: list[str],
        missing_features: list[str],
        component_scores: Dict[str, float],
        weights_dict: Dict[str, float],
        combined_score: float,
        side: str,
        threshold: float,
        regime: str,
        suppression_reason: Optional[str],
        decision_route: str,
    ) -> None:
        payload = {
            "strategy_id": self.strategy_id,
            "profile_id": profile_id,
            "symbol": symbol,
            "timestamp": int(ts_ms),
            "source_ts": int(ts_ms),
            "feature_ts": int(feature_ts),
            "feature_freshness_ms": int(ts_ms - feature_ts) if feature_ts > 0 else 0,
            "required_features_present": present_features,
            "required_features_missing": missing_features,
            "component_scores": component_scores,
            "weights": weights_dict,
            "combined_score": float(combined_score),
            "side": side,
            "threshold": float(threshold),
            "mode": self.cfg.mode,
            "regime": regime,
            "suppression_reason": suppression_reason,
            "decision_route": decision_route,
            "direct_execution_allowed": False,
        }
        LOG.info("ALPHA_TA_ENSEMBLE_TRACE %s", json.dumps(payload, sort_keys=True, default=str))

    def _build_ensemble_for_profile(self, profile: AlphaTaEnsembleProfileConfig) -> Any:
        """Instantiate the EnsembleModel with overrides dynamic merging."""
        # 1. Start with copy of base configs from self.cfg
        mom_cfg = self.cfg.momentum.model_dump()
        mr_cfg = self.cfg.mean_reversion.model_dump()
        vol_cfg = self.cfg.volatility.model_dump()
        ens_settings = self.cfg.ensemble.model_dump()

        # 2. Apply score overrides from profile
        for key, value in profile.score_overrides.items():
            parts = key.split(".")
            if parts[0] == "momentum":
                self._set_nested(mom_cfg, parts[1:], value)
            elif parts[0] == "mean_reversion":
                self._set_nested(mr_cfg, parts[1:], value)
            elif parts[0] == "volatility":
                self._set_nested(vol_cfg, parts[1:], value)
            elif parts[0] == "ensemble":
                self._set_nested(ens_settings, parts[1:], value)

        # 3. Instantiate the sub-models
        from apps.reference.domains.alpha_search.ensemble import EnsembleConfig, EnsembleModel
        from apps.reference.domains.alpha_search.models.mean_reversion import MeanReversionAlphaModel
        from apps.reference.domains.alpha_search.models.momentum import MomentumAlphaModel
        from apps.reference.domains.alpha_search.models.volatility import VolatilityAlphaModel

        models = {}
        model_map = {
            "mean_reversion_v1": MeanReversionAlphaModel,
            "momentum_v1": MomentumAlphaModel,
            "volatility_v1": VolatilityAlphaModel,
        }

        for model_name, model_cfg in ens_settings["models"].items():
            if model_cfg["enabled"] and model_name in model_map:
                if model_name == "mean_reversion_v1":
                    cfg_dict = mr_cfg
                elif model_name == "momentum_v1":
                    cfg_dict = mom_cfg
                else:
                    cfg_dict = vol_cfg

                models[model_name] = model_map[model_name](config=cfg_dict)

        # Resolve initial weights
        initial_weights = {}
        for model_name, model_cfg in ens_settings["models"].items():
            if model_cfg["enabled"]:
                initial_weights[model_name] = model_cfg.get("weight") or 0.0

        ensemble_cfg = EnsembleConfig(
            rebalance_frequency_days=ens_settings["rebalance_frequency_days"],
            performance_window_days=ens_settings["performance_window_days"],
            risk_adjustment=ens_settings["risk_adjustment"],
            objective_feedback_enabled=False,
        )

        return EnsembleModel(
            config=ensemble_cfg,
            models=models,
            initial_weights=initial_weights,
            system_config=None,
        )

    @staticmethod
    def _set_nested(d: dict, path: list[str], value: Any) -> None:
        """Set a value in a nested dictionary path, e.g. path=['weights', 'bb']."""
        for part in path[:-1]:
            # Convert to dict if setting nested structure
            if part not in d or not isinstance(d[part], dict):
                d[part] = {}
            d = d[part]
        d[path[-1]] = value

    @staticmethod
    def _normalize_features(features: Dict[str, Any]) -> Dict[str, Any]:
        """Apply feature mapping, defaults, and normalizations for sub-models."""
        normalized = {k: v for k, v in features.items()}

        # Map string representation of decimals/floats to numbers
        for k, v in list(normalized.items()):
            if isinstance(v, str):
                try:
                    normalized[k] = float(v)
                except ValueError:
                    pass

        # Volatility fallbacks
        if "range_pct" not in normalized and "price_range_ratio" in normalized:
            try:
                # price_range_ratio is 1.0 + range_pct
                normalized["range_pct"] = float(normalized["price_range_ratio"]) - 1.0
            except (TypeError, ValueError):
                pass

        if "realized_volatility_1h" not in normalized and "realized_volatility" in normalized:
            normalized["realized_volatility_1h"] = normalized["realized_volatility"]
        if "realized_volatility_1d" not in normalized and "realized_volatility" in normalized:
            normalized["realized_volatility_1d"] = normalized["realized_volatility"]
        if "bb_width_change" not in normalized:
            normalized["bb_width_change"] = 0.0
        if "volume_volatility_ratio" not in normalized:
            fallback_volume_ratio = normalized.get("volume_sma_ratio", normalized.get("volume_ratio", 1.0))
            normalized["volume_volatility_ratio"] = fallback_volume_ratio

        return normalized

    def _cmd_ts_ms(self, cmd: ProcessStrategyCmd) -> int:
        if cmd.bar_close_ts is not None:
            return int(cmd.bar_close_ts)
        raw_ts = cmd.raw.get("ts_ms") if isinstance(cmd.raw, Mapping) else None
        if raw_ts is not None:
            try:
                return int(float(raw_ts))
            except Exception:
                pass
        return int(get_clock().now_ms())

    def _cooldown_left_ms(self, symbol: str, ts_ms: int) -> int:
        previous = self._last_signal_ts_ms.get(symbol)
        if previous is None:
            return 0
        cooldown_ms = int(self.cfg.safety.cooldown_sec) * 1000
        elapsed = int(ts_ms) - int(previous)
        return max(0, cooldown_ms - elapsed)

    def _hourly_intent_allowed(self, symbol: str, ts_ms: int) -> bool:
        limit = self.cfg.safety.max_intents_per_symbol_hour
        if limit is None:
            return True
        hour_bucket = int(ts_ms // 3_600_000)
        prev_bucket, count = self._intent_hour.get(symbol, (hour_bucket, 0))
        if prev_bucket != hour_bucket:
            self._intent_hour[symbol] = (hour_bucket, 1)
            return True
        if count >= int(limit):
            return False
        self._intent_hour[symbol] = (hour_bucket, count + 1)
        return True

    def _testnet_candidate_allowed(self) -> bool:
        return str(getattr(self.config, "trading_mode", "")).lower() in {
            "testnet",
            "hybrid_live_data_testnet_exec",
        }

    @staticmethod
    def _extract_price(features: Dict[str, Any]) -> float:
        for key in ("price", "close", "last_price", "mark_price"):
            val = features.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return 0.0

    @staticmethod
    def _rid(*, symbol: str, side: str, ts_ms: int) -> str:
        raw = f"alpha_ta_ensemble:{symbol}:{side}:{ts_ms}"
        return f"alpha-ta-ensemble-{hashlib.md5(raw.encode()).hexdigest()[:16]}"
