"""
ReadinessGates — Warmup, features TTL, degraded context, and exposure pre-checks.

Extracted from decision_making.py (Phase 14A decomposition).
Stateless readiness checks that gate trade intent proposals.

LOC budget: <=500 (Constitution §3).
"""

import decimal
import logging
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .normalized_reject_reasons import NormalizedRejectReasons

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig
    from apps.reference.core.time.clock import Clock
    from .decision_context import DecisionContext

from vfoundation.core.protocol import truncate_why
from apps.reference.telemetry.metrics import inc_warmup_block


class ReadinessGates:
    """
    Readiness gates for DecisionMaking domain.

    Pure checks against caches and config. No FSM side effects.
    Callbacks (emit_intent_deferred_v1, record_blocked_intent) are injected
    from the facade to avoid circular dependency with IntentEmitter (STEP 5).
    """

    def __init__(
        self,
        clock: "Clock",
        config: "AuroraConfig",
        features_ttl_sec: int,
        symbol_states: dict,
        per_symbol_regimes: dict,
        get_portfolio: Callable[[], Optional[Dict]],
        get_exposure_cache: Callable[[], tuple],
        emit_intent_deferred_v1: Callable,
        record_blocked_intent: Callable[[str], None],
        fail_closed_on_degraded_context: bool,
        degraded_context_critical_keys: Optional[set],
        degraded_context_critical_keys_by_strategy: Optional[dict],
        logger: logging.Logger,
    ) -> None:
        self._clock = clock
        self.config = config
        self.features_ttl_sec = features_ttl_sec
        self._symbol_states = symbol_states
        self._per_symbol_regimes = per_symbol_regimes
        self._get_portfolio = get_portfolio
        self._get_exposure_cache = get_exposure_cache
        self._emit_intent_deferred_v1 = emit_intent_deferred_v1
        self._record_blocked_intent = record_blocked_intent
        self._fail_closed_on_degraded_context = fail_closed_on_degraded_context
        self._degraded_context_critical_keys = degraded_context_critical_keys
        self._degraded_context_critical_keys_by_strategy = degraded_context_critical_keys_by_strategy
        self.logger = logger

    # ── Utility ───────────────────────────────────────────────────────

    def _stable_retry_key(
        self,
        *,
        prefix: str,
        symbol: str,
        rid: str | None,
        side: str | None = None,
        ts_ms: int | None = None,
    ) -> str:
        if ts_ms is None:
            ts_ms = self._clock.now_ms()
        if side:
            return f"{prefix}:{symbol}:{side}:{ts_ms}"
        return f"{prefix}:{symbol}:{ts_ms}"

    # ── Warmup Gates ──────────────────────────────────────────────────

    def warmup_not_ready(self, symbol: str, reason: str, *, details: str | None = None) -> None:
        why = truncate_why(f"WARMUP_NOT_READY:{reason}")
        inc_warmup_block(domain="decision_making", reason=reason)
        if details:
            self.logger.warning(f"[{symbol}] {why} {details}")
        else:
            self.logger.warning(f"[{symbol}] {why}")

    def warmup_gate_before_trade_intent(
        self,
        *,
        symbol: str,
        rid: str,
        reduce_only: bool,
        context: str,
    ) -> bool:
        """
        TASK24.B: Fail-closed readiness gate.

        Contract: while NOT_READY -> no new TRADE_INTENT_PROPOSED (reduce_only closes allowed).
        """
        if reduce_only:
            return False

        # BYPASS IF WARN_ONLY (config-driven, not hardcoded)
        cfg_dm = self.config.domains.decision_making if hasattr(self.config.domains, "decision_making") else None
        if cfg_dm and hasattr(cfg_dm, "warmup") and cfg_dm.warmup.enforcement_mode == "warn_only":
            self.logger.debug(f"[{symbol}] WARMUP GATE BYPASS (warn_only mode)")
            return False

        portfolio = self._get_portfolio()
        if not portfolio:
            self.warmup_not_ready(symbol, "portfolio_missing", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True

        state = self._symbol_states.get(symbol) or {}
        features_evt = state.get("features") if isinstance(state, dict) else None
        if not isinstance(features_evt, dict):
            self.warmup_not_ready(symbol, "features_missing", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True
        if not self.features_ready(symbol, features_evt):
            self.warmup_not_ready(symbol, "features_stale", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True

        risk_evt = state.get("risk") if isinstance(state, dict) else None
        if risk_evt is None:
            self.warmup_not_ready(symbol, "risk_missing", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True

        warmup = None
        if symbol in self._per_symbol_regimes:
            warmup = self._per_symbol_regimes[symbol].get("warmup")

        warmup_dict = warmup if isinstance(warmup, dict) else None
        if warmup_dict is None:
            self.warmup_not_ready(symbol, "regime_warmup_missing", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True
        if not bool(warmup_dict["full_ready"] if "full_ready" in warmup_dict else False):
            ticks_seen = warmup_dict["ticks_seen"] if "ticks_seen" in warmup_dict else 0
            self.warmup_not_ready(
                symbol,
                "regime_not_ready",
                details=f"context={context} rid={rid} ticks_seen={ticks_seen}",
            )
            self._record_blocked_intent(symbol)
            return True

        # FeatureEngineering warmup contract (optional field in EVT:FEATURES_CALCULATED).
        fe_warmup = features_evt.get("warmup")
        fe_warmup_dict = fe_warmup if isinstance(fe_warmup, dict) else None
        if fe_warmup_dict is None:
            self.warmup_not_ready(symbol, "features_warmup_missing", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True
        if not bool(fe_warmup_dict["full_ready"] if "full_ready" in fe_warmup_dict else False):
            self.warmup_not_ready(symbol, "features_not_ready", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True

        return False

    # ── Features TTL ──────────────────────────────────────────────────

    def features_ready(self, symbol: str, features_data: dict) -> bool:
        """
        DM-BAR-TTL-PREEMIT-01: Check if features are fresh within TTL.

        Bar-aware logic (mirrors Gate 5):
        - For bars (tf_sec > 0): use bar_ttl_ms and bar_event_age_mode
        - For ticks (tf_sec == 0): use strict tick TTL (features_ttl_sec)

        Safety guard: even in "received" mode, reject bars older than
        max(tf_sec*1000, bar_ttl_ms) to prevent ancient bar leakage.
        """
        if not features_data or "ts" not in features_data:
            self.logger.debug(
                f"[{symbol}] _features_ready: no features_data or ts")
            return False

        now_ms = self._clock.now_ms()
        features_ts = features_data.get("ts", 0)
        tf_sec = int(features_data.get("tf_sec", 0) or 0)
        is_bar = tf_sec > 0

        if is_bar:
            # BAR-AWARE TTL: Use lenient bar_ttl_ms and age_mode
            sys_md = getattr(self.config.system, "market_data", None) if self.config.system else None
            if sys_md:
                bar_ttl_ms = float(getattr(sys_md, "bar_ttl_ms", 10000) or 10000)
                age_mode = str(getattr(sys_md, "bar_event_age_mode", "received") or "received")
            else:
                bar_ttl_ms = 10000.0
                age_mode = "received"

            ttl_ms = bar_ttl_ms

            # Select age calculation based on mode
            if age_mode == "received":
                start_ts = features_data.get("_received_ts", features_ts)
            else:
                start_ts = features_ts

            lag_ms = now_ms - start_ts
            is_ready = lag_ms <= ttl_ms

            # SAFETY GUARD: Reject ancient bars even in received mode
            bar_close_ts = features_data.get("bar_close_ts", features_ts)
            max_bar_age_ms = max(tf_sec * 1000, bar_ttl_ms)
            bar_actual_age_ms = now_ms - bar_close_ts

            if bar_actual_age_ms > max_bar_age_ms:
                self.logger.debug(
                    f"[{symbol}] _features_ready: BAR_TOO_OLD bar_age={bar_actual_age_ms:.0f}ms > max={max_bar_age_ms:.0f}ms"
                )
                is_ready = False

            self.logger.debug(
                f"[{symbol}] _features_ready: BAR tf={tf_sec}s mode={age_mode} "
                f"lag={lag_ms:.0f}ms ttl={ttl_ms:.0f}ms bar_age={bar_actual_age_ms:.0f}ms ready={is_ready}"
            )
        else:
            # TICK: Use strict tick TTL (features_ttl_sec)
            ttl_ms = self.features_ttl_sec * 1000
            lag_ms = now_ms - features_ts
            is_ready = lag_ms <= ttl_ms

            self.logger.debug(
                f"[{symbol}] _features_ready: TICK lag={lag_ms:.0f}ms ttl={ttl_ms:.0f}ms ready={is_ready}"
            )

        return is_ready

    # ── Degraded Context Gate ─────────────────────────────────────────

    def degraded_context_gate_should_defer(
        self,
        *,
        symbol: str,
        rid: str,
        ctx: "DecisionContext",
        features_evt: dict,
        strategy_id: str | None = None,
    ) -> bool:
        """Optionally defer when critical DecisionContext features are missing/invalid.

        This is intentionally opt-in to avoid changing live behavior unless explicitly enabled.
        Enable by setting `fail_closed_on_degraded_context = True`.
        """

        if not bool(self._fail_closed_on_degraded_context):
            return False

        default_critical_keys = {
            "price",
            "ema_bias",
            "obi",
            "tfi",
            "volatility_state",
            "depth_imbalance",
        }

        by_strategy = self._degraded_context_critical_keys_by_strategy or {}
        selected: set[str] | None = None
        if strategy_id and isinstance(by_strategy, dict):
            override = by_strategy.get(str(strategy_id))
            if override:
                selected = set(str(k) for k in override if str(k))

        if selected is None:
            global_keys = self._degraded_context_critical_keys
            if global_keys:
                selected = set(str(k) for k in global_keys if str(k))
            else:
                selected = set(default_critical_keys)

        critical_keys = selected

        # Force lazy parsing to populate missing_fields.
        _ = ctx.price
        _ = ctx.trend
        _ = ctx.flow
        _ = ctx.volatility
        _ = ctx.liquidity

        missing_critical = {k: v for k, v in (ctx.missing_fields or {}).items() if k in critical_keys}
        if not missing_critical:
            return False

        now_ms = self._clock.now_ms()
        features_ts = int(features_evt["ts"] if "ts" in features_evt else 0)
        retry_prefix = f"ctx:{strategy_id}" if strategy_id else "ctx"
        retry_key = self._stable_retry_key(prefix=retry_prefix, symbol=symbol, rid=rid, ts_ms=features_ts)

        self.logger.warning(
            f"[{symbol}] DEFER degraded DecisionContext: missing_critical={missing_critical}"
        )

        self._emit_intent_deferred_v1(
            symbol=symbol,
            reason=NormalizedRejectReasons.DATA_NOT_READY,
            retry_key=retry_key,
            next_allowed_ts=now_ms + 500,
            original_event_name="EVT:FEATURES_CALCULATED",
            original_payload_min={
                "symbol": symbol,
                "rid": rid,
                "features_ts": features_ts,
                "missing_critical": missing_critical,
            },
            attempt=1,
            max_attempts=5,
            why_chain=["fail_closed", "decision_context_degraded"],
            context="decision_making:_make_decision_for_symbol:degraded_context_gate",
        )
        self._record_blocked_intent(symbol)
        return True

    # PHASE-9-PURGE: shadow_compare_kernel() removed.
    # It was the pre-Quadratic shadow validation path (gated by shadow_mode_enabled),
    # which compared legacy AuroraScoringKernel (v2) results against the production score.
    # Quadratic Brain is now the live truth. The comparison path is obsolete.
    # If shadow comparison is needed in future, implement against QuadraticScoringKernel.

    # ── Exposure Cache Pre-check ──────────────────────────────────────

    def precheck_exposure_cache(self, symbol: str, side: str, notional_usd: float) -> bool:
        """
        Pre-check exposure limits using cached exposure summary.

        DM-SAFETY-BYPASSES-P1: FAIL-CLOSED behavior.
        Returns True if trade should be allowed, False if blocked.
        Missing/stale/error cache -> BLOCK (not allow).
        """
        exposure_cache, cache_timestamp = self._get_exposure_cache()

        if not exposure_cache:
            self.logger.warning(
                f"[{symbol}] EXPOSURE_CACHE_UNAVAILABLE: No cache, blocking trade"
            )
            return False

        try:
            cache_age = self._clock.now_sec() - cache_timestamp
            if cache_age > 30.0:
                self.logger.warning(
                    f"[{symbol}] EXPOSURE_CACHE_UNAVAILABLE: stale ({cache_age:.1f}s>30s)"
                )
                return False

            symbol_exposure = exposure_cache[symbol] if symbol in exposure_cache else {}
            current_exposure = symbol_exposure["current_exposure_usd"] if "current_exposure_usd" in symbol_exposure else 0.0
            max_exposure = symbol_exposure["max_exposure_usd"] if "max_exposure_usd" in symbol_exposure else float("inf")

            projected_exposure = current_exposure + notional_usd

            if projected_exposure > max_exposure:
                self.logger.info(
                    f"[{symbol}] EXPOSURE_CACHE_BLOCK: projected={projected_exposure:.2f} > max={max_exposure:.2f}, "
                    f"blocking {side.upper()} trade"
                )
                return False

            self.logger.debug(
                f"[{symbol}] EXPOSURE_CACHE_ALLOW: current={current_exposure:.2f}, "
                f"projected={projected_exposure:.2f}, max={max_exposure:.2f}"
            )
            return True

        except Exception as e:
            self.logger.warning(
                f"[{symbol}] EXPOSURE_CACHE_UNAVAILABLE: error ({e}), blocking trade"
            )
            return False
