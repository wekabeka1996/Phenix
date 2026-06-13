from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from typing import Any, Mapping

from pydantic import ValidationError

from apps.reference.config.strategies.alpha_mr_s01 import AlphaMrS01StrategyConfig
from apps.reference.config_models import AuroraConfig
from apps.reference.domains.decision_making.contracts.core_models import ProcessStrategyCmd
from apps.reference.domains.strategies.scoring.weighted_mean_reversion import (
    WeightedMeanReversionConfig,
    WeightedMeanReversionResult,
    WeightedMeanReversionScorer,
)
from apps.reference.core.time import get_clock

LOG = logging.getLogger(__name__)


class AlphaMrS01Handler:
    """S01 weighted mean-reversion strategy runtime.

    The handler never talks to execution directly. In testnet_candidate mode it
    emits the normal EVT:STRATEGY_SIGNAL_PRODUCED event for DecisionMaking.
    """

    strategy_id = "alpha_mr_s01"

    def __init__(self, *, fsm: Any, config: AuroraConfig) -> None:
        self.fsm = fsm
        self.config = config
        cfg = getattr(getattr(config, "strategies", None), self.strategy_id, None)
        if cfg is None:
            raise ValueError("strategies.alpha_mr_s01 config is required")
        self.cfg: AlphaMrS01StrategyConfig = cfg
        self.scorer = WeightedMeanReversionScorer(_scorer_config_from_strategy(cfg))
        self._last_signal_ts_ms: dict[str, int] = {}
        self._last_signal_monotonic_ms: dict[str, int] = {}
        self._intent_hour: dict[str, tuple[int, int]] = {}

    def register(self) -> None:
        if self.cfg.mode == "disabled" or not self.cfg.enabled:
            LOG.warning("alpha_mr_s01 disabled: no event listeners registered")
            return
        self.fsm.listen("CMD:PROCESS_STRATEGY", self.on_process_strategy)

    def on_process_strategy(self, event: Any) -> None:
        cmd = event
        if hasattr(event, "pld"):
            # Tests may call the handler directly with raw FSM messages.
            from apps.reference.domains.decision_making.contracts.boundary_models import ProcessStrategyBoundary
            from apps.reference.domains.decision_making.contracts.boundary_mappers import map_process_strategy_boundary_to_cmd

            raw = dict(event.pld) if isinstance(event.pld, dict) else {}
            try:
                cmd = map_process_strategy_boundary_to_cmd(
                    ProcessStrategyBoundary.model_validate(event.pld),
                    raw=raw,
                )
            except ValidationError as exc:
                LOG.warning("alpha_mr_s01 rejected invalid CMD:PROCESS_STRATEGY boundary: %s", exc)
                return
        if not isinstance(cmd, ProcessStrategyCmd):
            LOG.warning("alpha_mr_s01 rejected non ProcessStrategyCmd payload")
            return

        symbol = str(cmd.symbol)
        trace_base = {
            "strategy_id": self.strategy_id,
            "symbol": symbol,
            "source_scenario_id": self.cfg.source_scenario_id,
            "strategy_version": self.cfg.strategy_version,
        }

        if not self._symbol_enabled(symbol):
            self._emit_shadow_trace(
                symbol=symbol,
                ts_ms=self._cmd_ts_ms(cmd),
                reason="symbol_disabled",
                result=None,
                extra=trace_base,
            )
            return
        if cmd.tf_sec != self.cfg.timeframe_sec:
            self._emit_shadow_trace(
                symbol=symbol,
                ts_ms=self._cmd_ts_ms(cmd),
                reason=f"tf_mismatch:{cmd.tf_sec}!={self.cfg.timeframe_sec}",
                result=None,
                extra=trace_base,
            )
            return

        regime = self._resolve_regime(cmd)
        if self.cfg.safety.forbid_uncertain and regime == "UNCERTAIN":
            self._emit_shadow_trace(
                symbol=symbol,
                ts_ms=self._cmd_ts_ms(cmd),
                reason="regime_uncertain_forbidden",
                result=None,
                extra={**trace_base, "regime": regime},
            )
            return
        if regime not in set(self.cfg.safety.allowed_regimes):
            self._emit_shadow_trace(
                symbol=symbol,
                ts_ms=self._cmd_ts_ms(cmd),
                reason=f"regime_not_allowed:{regime}",
                result=None,
                extra={**trace_base, "regime": regime},
            )
            return

        ts_ms = self._cmd_ts_ms(cmd)
        monotonic_ms = self._monotonic_ms()
        cooldown_left = self._cooldown_left_ms(symbol, monotonic_ms)
        if cooldown_left > 0:
            self._emit_shadow_trace(
                symbol=symbol,
                ts_ms=ts_ms,
                reason=f"cooldown:{cooldown_left}ms",
                result=None,
                extra={**trace_base, "regime": regime},
            )
            return

        entry_price = self._entry_price_from_cmd(cmd)
        if entry_price is None:
            self._emit_shadow_trace(
                symbol=symbol,
                ts_ms=ts_ms,
                reason="missing_entry_price",
                result=None,
                extra={**trace_base, "regime": regime},
            )
            return

        result = self.scorer.score(cmd.features)
        if not result.allowed:
            self._emit_shadow_trace(
                symbol=symbol,
                ts_ms=ts_ms,
                reason=result.reason,
                result=result,
                extra={**trace_base, "regime": regime},
            )
            return

        if self.cfg.mode == "shadow":
            self._emit_shadow_trace(
                symbol=symbol,
                ts_ms=ts_ms,
                reason="shadow_signal",
                result=result,
                extra={**trace_base, "regime": regime},
            )
            self._last_signal_ts_ms[symbol] = ts_ms
            self._last_signal_monotonic_ms[symbol] = monotonic_ms
            return

        if self.cfg.mode == "testnet_candidate":
            if not self._testnet_candidate_allowed():
                self._emit_shadow_trace(
                    symbol=symbol,
                    ts_ms=ts_ms,
                    reason=f"testnet_candidate_mode_blocked:{getattr(self.config, 'trading_mode', None)}",
                    result=result,
                    extra={**trace_base, "regime": regime},
                )
                return
            if not self._hourly_intent_allowed(symbol, ts_ms):
                self._emit_shadow_trace(
                    symbol=symbol,
                    ts_ms=ts_ms,
                    reason="max_intents_per_symbol_hour",
                    result=result,
                    extra={**trace_base, "regime": regime},
                )
                return
            self._emit_strategy_signal(cmd=cmd, result=result, regime=regime, entry_price=entry_price)
            self._last_signal_ts_ms[symbol] = ts_ms
            self._last_signal_monotonic_ms[symbol] = monotonic_ms

    def _emit_strategy_signal(
        self,
        *,
        cmd: ProcessStrategyCmd,
        result: WeightedMeanReversionResult,
        regime: str,
        entry_price: Decimal,
    ) -> None:
        symbol = str(cmd.symbol)
        ts_ms = self._cmd_ts_ms(cmd)
        rid = self._rid(symbol=symbol, side=result.side, ts_ms=ts_ms)
        payload = {
            "schema_version": 1,
            "strategy_id": self.strategy_id,
            "source_scenario_id": self.cfg.source_scenario_id,
            "strategy_version": self.cfg.strategy_version,
            "symbol": symbol,
            "tf_sec": self.cfg.timeframe_sec,
            "side": result.side,
            "bar_close_ts": int(cmd.bar_close_ts or ts_ms),
            "readiness": {"warmup_ok": True},
            "runtime_permissions": {
                "can_open_new_risk": True,
                "can_manage_existing_risk": False,
            },
            "score": float(result.final_score),
            "confidence": float(result.confidence),
            "why": result.reason,
            "ts_ms": ts_ms,
            "rid": rid,
            "valid_for_ms": int(self.cfg.safety.signal_ttl_ms),
            "why_chain": [self.cfg.source_scenario_id, result.reason],
            "source_mode": "live",
            "price_ctx": {
                "entry_price": str(entry_price),
                "stop_price": None,
                "target_price": None,
            },
            "regime": regime,
            "volatility": cmd.features.get("volatility"),
            "liquidity": cmd.features.get("liquidity"),
            "scoring": self._scoring_payload(result=result, regime=regime),
        }
        self.fsm.emit(
            "EVT:STRATEGY_SIGNAL_PRODUCED",
            payload=payload,
            why=f"strategy_signal:{self.strategy_id}:{result.side}",
        )

    def _emit_shadow_trace(
        self,
        *,
        symbol: str,
        ts_ms: int,
        reason: str,
        result: WeightedMeanReversionResult | None,
        extra: Mapping[str, Any],
    ) -> None:
        payload = {
            **dict(extra),
            "event_name": "EVT:ALPHA_MR_S01_TRACE",
            "mode": self.cfg.mode,
            "ts_ms": int(ts_ms),
            "reason": str(reason),
            "trace": self._scoring_payload(result=result, regime=str(extra.get("regime") or "UNKNOWN")),
        }
        LOG.info("ALPHA_MR_S01_TRACE %s", json.dumps(payload, sort_keys=True, default=str))

    def _scoring_payload(
        self,
        *,
        result: WeightedMeanReversionResult | None,
        regime: str,
    ) -> dict[str, Any]:
        if result is None:
            return {
                "score": 0.0,
                "side": "NEUTRAL",
                "threshold": float(self.cfg.threshold),
                "regime": regime,
                "source_scenario_id": self.cfg.source_scenario_id,
            }
        return {
            "score": float(result.final_score),
            "combined_score": float(result.combined_score),
            "confidence": float(result.confidence),
            "side": result.side,
            "threshold": float(self.cfg.threshold),
            "reason": result.reason,
            "regime": regime,
            "source_scenario_id": self.cfg.source_scenario_id,
            "components": {k: float(v) for k, v in result.components.items()},
            "weights": {k: float(v) for k, v in result.weights.items()},
            "multipliers": {k: float(v) for k, v in result.multipliers.items()},
        }

    def _resolve_regime(self, cmd: ProcessStrategyCmd) -> str:
        raw = cmd.raw
        candidates = [
            raw.get("regime") if isinstance(raw, Mapping) else None,
            raw.get("structural_regime") if isinstance(raw, Mapping) else None,
        ]
        regime_ctx = raw.get("regime_ctx") if isinstance(raw, Mapping) else None
        if isinstance(regime_ctx, Mapping):
            candidates.extend([regime_ctx.get("regime"), regime_ctx.get("flat_regime")])
        for candidate in candidates:
            if candidate:
                return str(candidate).strip().upper()
        return "UNCERTAIN"

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

    def _symbol_enabled(self, symbol: str) -> bool:
        asset = self.cfg.assets.get(symbol)
        return bool(asset and asset.enabled)

    def _cooldown_left_ms(self, symbol: str, monotonic_ms: int) -> int:
        previous = self._last_signal_monotonic_ms.get(symbol)
        if previous is None:
            return 0
        cooldown_ms = int(self.cfg.safety.cooldown_sec) * 1000
        elapsed = int(monotonic_ms) - int(previous)
        return max(0, cooldown_ms - elapsed)

    def _entry_price_from_cmd(self, cmd: ProcessStrategyCmd) -> Decimal | None:
        if not isinstance(cmd.features, Mapping):
            return None
        price = cmd.features.get("price")
        if price in (None, "", "0", 0):
            return None
        try:
            entry_price = Decimal(str(price))
        except Exception:
            return None
        if entry_price <= 0:
            return None
        return entry_price

    @staticmethod
    def _monotonic_ms() -> int:
        return int(get_clock().monotonic() * 1000)

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
    def _rid(*, symbol: str, side: str, ts_ms: int) -> str:
        raw = f"alpha_mr_s01:{symbol}:{side}:{ts_ms}"
        return f"alpha-mr-s01-{hashlib.md5(raw.encode()).hexdigest()[:16]}"


def _scorer_config_from_strategy(cfg: AlphaMrS01StrategyConfig) -> WeightedMeanReversionConfig:
    return WeightedMeanReversionConfig(
        bb_weight=Decimal(str(cfg.weights.bb)),
        rsi_weight=Decimal(str(cfg.weights.rsi)),
        sma_weight=Decimal(str(cfg.weights.sma)),
        stoch_weight=Decimal(str(cfg.weights.stoch)),
        threshold=Decimal(str(cfg.threshold)),
        rsi_oversold=Decimal(str(cfg.rsi.oversold)),
        rsi_overbought=Decimal(str(cfg.rsi.overbought)),
        sma_deviation_normalizer=Decimal(str(cfg.sma.deviation_normalizer)),
        stoch_oversold_zone=Decimal(str(cfg.stochastic.oversold_zone)),
        stoch_overbought_zone=Decimal(str(cfg.stochastic.overbought_zone)),
        stoch_signal_strength=Decimal(str(cfg.stochastic.signal_strength)),
        volume_enabled=bool(cfg.volume.enabled),
        volume_confirm_multiplier=Decimal(str(cfg.volume.confirm_multiplier)),
        volume_contradict_multiplier=Decimal(str(cfg.volume.contradict_multiplier)),
        volume_high_threshold=Decimal(str(cfg.volume.high_threshold)),
        volume_low_threshold=Decimal(str(cfg.volume.low_threshold)),
        bb_min_width=Decimal(str(cfg.bb_width.min_width)),
        bb_max_width=Decimal(str(cfg.bb_width.max_width)),
        bb_narrow_penalty_enabled=bool(cfg.bb_width.narrow_penalty_enabled),
        bb_narrow_threshold=Decimal(str(cfg.bb_width.narrow_threshold)),
        bb_narrow_penalty=Decimal(str(cfg.bb_width.narrow_penalty)),
        bb_wide_boost_enabled=bool(cfg.bb_width.wide_boost_enabled),
        bb_wide_threshold=Decimal(str(cfg.bb_width.wide_threshold)),
        bb_max_multiplier=Decimal(str(cfg.bb_width.max_multiplier)),
    )
