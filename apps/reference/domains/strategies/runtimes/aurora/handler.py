"""Stateful runtime facade for the Aurora strategy pipeline.

AuroraBuiltinPlugin wires this handler into the FSM. This module owns the
mutable per-symbol caches and the thin event/command handlers that feed the
Aurora mixin stack. The actual decision logic lives in AuroraDecisionMixin;
AuroraHandler provides the state, readiness guards, and cache updates around
that mixin-driven core.
"""
from __future__ import annotations

import decimal
import json
import logging

# get_clock() backs the default time providers when tests do not inject them.
from apps.reference.core.time import get_clock
from apps.reference.contracts.runtime_analytics_restore import (
    StrategyAnalyticsRestoreSnapshot,
    upgrade_cold_execution_restore_if_clean_start,
)
from apps.reference.contracts.runtime_regime_layers import (
    build_regime_provenance_fields,
    is_structural_regime_payload,
    normalize_structural_regime_label,
)
from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    extract_canonical_bar_identity,
)
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable

from apps.reference.shared.decision_primitives.scoring_kernel import (
    QuadraticScoringKernel,
    ScoringResult,
    SideBiasState,
)
from apps.reference.shared.decision_primitives.shields.null_shield import NullShield
from apps.reference.shared.decision_primitives.shields.base import ShieldCascade
from apps.reference.domains.strategies.runtimes.aurora.tpsl import AuroraTpslMixin
from apps.reference.domains.strategies.runtimes.aurora.scoring_helpers import AuroraScoringHelpersMixin
from apps.reference.domains.strategies.runtimes.aurora.decision import AuroraDecisionMixin
from apps.reference.domains.strategies.runtimes.aurora.config_loader import AuroraConfigLoaderMixin
from apps.reference.domains.strategies.runtimes.aurora.holding_period import AuroraHoldingPeriodMixin
from apps.reference.shared.decision_primitives.shields.context_shield import ContextShield
from apps.reference.shared.decision_primitives.shields.memory_shield import MemoryShield
from apps.reference.shared.decision_primitives.shields.danger_zone import DangerZoneShield
from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
from apps.reference.domains.decision_making.gates.execution_gate import ExecutionGate
from apps.reference.shared.decision_primitives.exit_manager import ExitManager
from apps.reference.shared.decision_primitives.entry_plan import EntryPlan, EntryPlanParams, EntryPlanResult, ObiMissingPolicy
from apps.reference.config_models import (
    ExitManagerConfig,
    OperationalMode,
    DashboardConfig,
)
from apps.reference.domains.decision_making.intent.truth_artifacts import (
    write_strategy_decision_blocked,
)
from apps.reference.domains.decision_making.intent.reject_wal import (
    write_trade_intent_rejected,
)
from apps.reference.domains.regime_allowlist.contract import RegimeAllowlistContract
from apps.reference.domains.decision_making.primitives.operational_mode import ModeManager
from apps.reference.domains.decision_making.observability.dashboard import DashboardMetrics, TradeOutcome
from apps.reference.shared.decision_primitives.instrument_quantizer import (
    quantize_exposure,
    InstrumentSpec as QuantizerSpec,
)
from apps.reference.domains.decision_making.primitives.position_queries import PositionQueries


logger = logging.getLogger("aurora_handler")


def _maybe_build_position_queries(
    *,
    config: Any,
    portfolio_getter: Callable[[], Dict[str, Any] | None],
    logger_: logging.Logger,
) -> PositionQueries | None:
    """Build PositionQueries only when sizing SSOT is available and numeric."""
    try:
        dm_sizing_cfg = config.domains.decision_making.position_sizing
        min_position_size_usd = decimal.Decimal(
            str(dm_sizing_cfg.min_position_size_usd))
        liquidity_cap_usd = decimal.Decimal(
            str(dm_sizing_cfg.liquidity_based_cap_usd))
    except Exception as exc:
        logger_.debug(
            "PositionQueries unavailable during handler init: %s", exc)
        return None
    return PositionQueries(
        config,
        portfolio_getter,
        min_position_size_usd,
        liquidity_cap_usd,
        logger_,
    )


@dataclass
class SymbolState:
    """Mutable per-symbol cache shared across Aurora event and decision paths."""

    def __init__(self):
        # Regime cache populated from EVT:REGIME_DETECTED.
        self.regime = None
        self.regime_raw_event = None
        self.regime_confidence = None
        self.regime_ts_ms = 0
        self.regime_event_ts_ms = 0
        self.regime_source = None
        self.regime_same_bar = None
        self.regime_provenance_reason = None
        self.regime_structural_regime_ref = None
        self.regime_changed = None
        self.regime_raw_confidence = None
        self.regime_last_update_ts_ms = 0
        self.regime_cache_write_ts_ms = 0

        self.system_stress_state = "NORMAL"

        # Anti-churn regime inertia uses the monotonic timebase.
        self.regime_raw = None
        self.regime_effective = None
        self.regime_raw_change_ts = None

        # Heartbeat evidence consumed by the fail-closed regime liveness guard.
        self.last_regime_heartbeat_ms = None

        # Warmup state mirrored from CMD:PROCESS_STRATEGY for diagnostics.
        self.warmup_full_ready = False
        self.warmup_ticks_seen = 0

        # Side-bias history uses timestamp lists windowed later by config.
        self.buy_timestamps = []
        self.sell_timestamps = []

        # Last emitted signal state.
        self.last_signal_ts_ms = 0
        self.last_signal_side = ""

        # Holding-period / anti-ping-pong state.
        self.entry_timestamp = None
        self.position_side = ""

        # MFE tracking supports trailing-stop updates.
        self.mfe_price = None  # Decimal: highest price for LONG, lowest for SHORT

        # Re-entry cooldown starts when the last exit is recorded.
        self.last_exit_timestamp = None

        # Cached FEATURES price_motion because CMD:PROCESS_STRATEGY omits it.
        self.cached_price_motion = None

        # Objective-engine counters are event-fed and windowed later by config.
        self.objective_blocked_ts_ms = deque()
        self.objective_cancel_replace_ts_ms = deque()
        self.objective_reentry_ts_ms = deque()


class AuroraHandler(AuroraTpslMixin, AuroraScoringHelpersMixin, AuroraDecisionMixin, AuroraConfigLoaderMixin, AuroraHoldingPeriodMixin):
    """Stateful Aurora facade around the mixin-based decision pipeline.

    This class does not implement the full scoring algorithm locally. Instead,
    it owns the shared handler state and the external entry points that feed
    validated data into AuroraDecisionMixin and the other helper mixins.

    Proven responsibilities in this file:
    - cache regime, portfolio, exposure, and restore-snapshot state;
    - validate CMD:PROCESS_STRATEGY envelopes before decision processing;
    - track cold-start/readiness counters and objective-engine timestamps;
    - expose compatibility handlers for data-only feature updates.
    """

    def __init__(
        self,
        *,
        config: Any,
        emit_fn: Callable[[str, Dict[str, Any]], None],
        strategy_id: str = "aurora",
        monotonic_fn: Callable[[], float] | None = None,
        wall_time_fn: Callable[[], float] | None = None,
    ):
        """Initialize handler state and load Aurora configuration.

        Args:
            config: Strategy configuration tree or test double.
            emit_fn: Event-emission callback supplied by the FSM wrapper.
            strategy_id: Strategy identifier attached to emitted payloads.
            monotonic_fn: Optional monotonic clock for durations and cooldowns.
            wall_time_fn: Optional wall clock for epoch-based timestamps.
        """
        self.config = config
        self.emit_fn = emit_fn
        self.strategy_id = strategy_id
        self.logger = logging.getLogger(f"aurora_handler.{strategy_id}")

        # Timebase separation:
        # - monotonic_fn(): durations / cooldowns / holding windows
        # - wall_time_fn(): epoch-based timestamps (ts_ms)
        # DET-BT-FIX-01: Deterministic monotonic fallback via get_clock()
        self.monotonic_fn: Callable[[], float] = monotonic_fn or (
            lambda: get_clock().monotonic())
        self.wall_time_fn: Callable[[], float] = wall_time_fn or (
            lambda: get_clock().now_sec())

        # Injected collaborators and rollout state shared with mixins.
        self.scoring_kernel_cls = QuadraticScoringKernel
        self._shield_fn = None  # Phase 9: set during _load_config if quadratic
        self._scoring_engine_cfg = None  # Phase 9: ScoringEngineConfig
        self._aurora_requested_scoring_version = "quadratic"
        self._aurora_effective_scoring_version = "quadratic"
        self._quadratic_shadow_requested = False
        self._quadratic_shadow_shield_fn = None
        self._quadratic_rollback_armed = False
        self._quadratic_rollback_reason_chain: tuple[str, ...] = ()

        # Per-symbol state
        self._symbol_states: Dict[str, SymbolState] = defaultdict(SymbolState)
        self._latest_portfolio: Dict[str, Any] | None = None
        self._latest_exposure_summary: Dict[str, Any] | None = None
        self._analytics_restore_snapshots: Dict[str,
                                                StrategyAnalyticsRestoreSnapshot] = {}
        # Cold-start gate counts bars seen after this process last started.
        self._bars_seen_since_restart: Dict[str, int] = defaultdict(int)

        self._position_queries = _maybe_build_position_queries(
            config=self.config,
            portfolio_getter=lambda: self._latest_portfolio,
            logger_=self.logger,
        )

        # Historical name preserved; currently counts rejected strategy commands.
        self._tick_path_rejections: int = 0

        # Config extraction
        self._load_config()
        self._enabled_symbols = self._resolve_enabled_symbols()

        # The wrapper enforces enablement at registration time; the handler
        # repeats the check here so direct instantiation still fails closed.
        aurora_cfg = getattr(self.config.strategies, "aurora", None) if hasattr(
            self.config, "strategies") else None
        self._is_enabled = getattr(
            aurora_cfg, "enabled", True) if aurora_cfg else False

    def apply_runtime_analytics_restore_snapshot(
        self,
        snapshot: StrategyAnalyticsRestoreSnapshot,
    ) -> None:
        """Store a restore snapshot only when it matches this strategy instance."""
        if str(snapshot.strategy_id) != str(self.strategy_id):
            return
        self._analytics_restore_snapshots[str(snapshot.symbol)] = snapshot

    def get_runtime_analytics_restore_snapshot(
        self,
        symbol: str,
    ) -> StrategyAnalyticsRestoreSnapshot | None:
        """Return the cached restore snapshot for one symbol, if any."""
        return self._analytics_restore_snapshots.get(str(symbol))

    def _resolve_enabled_symbols(self) -> set[str]:
        """Resolve the symbol universe this handler should track.

        Registry assignments win when they exist. The legacy aurora.assets map
        is consulted only when the registry did not yield any symbol.
        """
        explicit_symbols = getattr(self, "_enabled_symbols", None)
        if explicit_symbols is not None:
            # Tests may inject a narrowed universe directly on the instance.
            return {
                str(symbol).strip().upper()
                for symbol in explicit_symbols
                if str(symbol).strip()
            }

        resolved: set[str] = set()
        registry = getattr(self.config, "strategies_registry", None)
        assignments = getattr(registry, "assignments", {}) if registry else {}
        if isinstance(assignments, dict):
            for symbol, strategies in assignments.items():
                if not isinstance(strategies, (list, tuple, set)):
                    continue
                normalized = {str(strategy).strip()
                              for strategy in strategies if str(strategy).strip()}
                if self.strategy_id in normalized:
                    resolved.add(str(symbol).strip().upper())

        if not resolved:
            aurora_cfg = getattr(getattr(self.config, "strategies", None),
                                 "aurora", None)
            assets = getattr(aurora_cfg, "assets", {}) if aurora_cfg else {}
            if isinstance(assets, dict):
                for symbol, asset_cfg in assets.items():
                    if bool(getattr(asset_cfg, "enabled", True)):
                        resolved.add(str(symbol).strip().upper())

        self._enabled_symbols = resolved
        return resolved

    def seed_startup_bars(self, symbol: str, count: int) -> None:
        """Seed _bars_seen_since_restart counter after startup basis import.

        STARTUP-BASIS-HYDRATION: Called by startup executor after hydrate_basis_bars().
        Uses max() to avoid overwriting any live bars already counted in the counter.
        """
        if count > 0:
            current = self._bars_seen_since_restart.get(symbol, 0)
            self._bars_seen_since_restart[symbol] = max(current, count)
            self.logger.info(
                "[%s] seed_startup_bars: _bars_seen_since_restart=%d (seeded=%d)",
                symbol, self._bars_seen_since_restart[symbol], count,
            )

    def get_readiness_diagnostics(self) -> list[dict[str, object]]:
        """Return per-symbol readiness diagnostics for operator visibility.

        Provides a machine-readable view of the cold-start readiness state
        for every enabled symbol tracked by this handler.
        """
        _basis_required = getattr(self, "_basis_required_bars_override", None)
        if _basis_required is None:
            try:
                from apps.reference.contracts.strategy_compatibility_matrix import (
                    get_active_strategy_profile,
                )
                _profile = get_active_strategy_profile(
                    self.config, self.strategy_id)
                if _profile is None:
                    _contract_error = "READINESS_CONTRACT_UNRESOLVED:PROFILE_NOT_FOUND"
                    return [
                        {
                            "strategy": self.strategy_id,
                            "symbol": sym,
                            "tf_sec": self.timeframe_sec,
                            "bars_seen": self._bars_seen_since_restart.get(sym, 0),
                            "bars_required": None,
                            "ready": False,
                            "block_reason": _contract_error,
                        }
                        for sym in sorted(self._resolve_enabled_symbols())
                    ]
                _basis_required = int(_profile.basis_required_bars)
            except Exception as _exc:
                _contract_error = f"READINESS_CONTRACT_UNRESOLVED:{type(_exc).__name__}"
                return [
                    {
                        "strategy": self.strategy_id,
                        "symbol": sym,
                        "tf_sec": self.timeframe_sec,
                        "bars_seen": self._bars_seen_since_restart.get(sym, 0),
                        "bars_required": None,
                        "ready": False,
                        "block_reason": _contract_error,
                    }
                    for sym in sorted(self._resolve_enabled_symbols())
                ]
        results: list[dict[str, object]] = []
        for symbol in sorted(self._resolve_enabled_symbols()):
            bars_seen = self._bars_seen_since_restart.get(symbol, 0)
            ready = bars_seen >= _basis_required
            results.append({
                "strategy": self.strategy_id,
                "symbol": symbol,
                "tf_sec": self.timeframe_sec,
                "bars_seen": bars_seen,
                "bars_required": _basis_required,
                "ready": ready,
                "block_reason": (
                    None if ready
                    else f"BARS_REQUIRED_COLD_START:{bars_seen}/{_basis_required}"
                ),
            })
        return results

    # _load_config → moved to AuroraConfigLoaderMixin (see aurora_config_loader.py)

    def _get_time_multiplier(self, regime: Optional[str]) -> float:
        """Return the anti-churn time multiplier for a regime or 1.0 on invalid config."""
        if not getattr(self, "anti_churn_enabled", False):
            return 1.0
        if not regime:
            return 1.0
        try:
            return float(self.time_multipliers.get(regime, 1.0))
        except (TypeError, ValueError):
            return 1.0

    def _get_regime_severity(self, regime: Optional[str]) -> int:
        """Return the configured regime severity used by inertia comparisons."""
        if not regime:
            return 0
        try:
            return int(self.regime_severity_map.get(regime, 0))
        except (TypeError, ValueError):
            return 0

    def _update_effective_regime(self, symbol: str, raw_regime: Optional[str]) -> None:
        """Apply regime inertia with immediate risk-off and delayed risk-on.

        The raw detector label is cached immediately. The effective label moves
        later when the configured confirmation windows permit it.
        """
        state = self._symbol_states[symbol]
        now = float(self.monotonic_fn())

        if state.regime_raw is None and state.regime_effective is None:
            state.regime_raw = raw_regime
            state.regime_effective = raw_regime
            state.regime_raw_change_ts = now
            return

        if raw_regime != state.regime_raw:
            state.regime_raw = raw_regime
            state.regime_raw_change_ts = now

        if not getattr(self, "anti_churn_enabled", False) or self.regime_inertia_confirm_window_sec <= 0.0:
            state.regime_effective = state.regime_raw
            return

        current_eff = state.regime_effective
        raw = state.regime_raw
        if raw == current_eff:
            return

        eff_sev = self._get_regime_severity(current_eff)
        raw_sev = self._get_regime_severity(raw)

        if self.regime_inertia_immediate_risk_off and raw_sev > eff_sev:
            state.regime_effective = raw
            return

        if raw_sev == eff_sev and self.regime_inertia_confirm_window_same_severity_sec > 0.0:
            raw_change_ts = state.regime_raw_change_ts
            if raw_change_ts is None:
                state.regime_effective = raw
                return
            if (now - raw_change_ts) >= self.regime_inertia_confirm_window_same_severity_sec:
                state.regime_effective = raw
            return

        raw_change_ts = state.regime_raw_change_ts
        if raw_change_ts is None:
            state.regime_effective = raw
            return
        if (now - raw_change_ts) >= self.regime_inertia_confirm_window_sec:
            state.regime_effective = raw

    def _check_regime_liveness(
        self,
        symbol: str,
        state: SymbolState,
    ) -> Optional[Dict[str, Any]]:
        """Validate that regime-detector heartbeat evidence is still fresh.

        Missing heartbeat evidence blocks immediately. When config does not
        expose basis_tf_sec or liveness_factor, the guard logs and falls back to
        conservative defaults instead of disabling itself.
        """
        # Missing heartbeat is treated as missing detector evidence, not as safe.
        if state.last_regime_heartbeat_ms is None:
            details = build_regime_provenance_fields(
                {
                    "regime": state.regime,
                    "regime_event_ts_ms": state.regime_event_ts_ms or state.regime_ts_ms,
                },
                missing_heartbeat=True,
            )
            details["last_regime_heartbeat_ms"] = None
            return {
                "reason_code": "NRR-REGIME-NO-HEARTBEAT",
                "why": "Regime detector heartbeat never received (fail-closed)",
                "details": details,
            }

        # Prefer config-provided limits; partial mocks fall back to conservative defaults.
        try:
            basis_tf_sec = int(self.config.basis_tf_sec)
            liveness_factor = int(getattr(self.config, "liveness_factor", 3))
        except (AttributeError, TypeError):
            basis_tf_sec = 300
            liveness_factor = 3
            self.logger.warning(
                f"[{symbol}] Liveness guard using fallback: basis_tf_sec={basis_tf_sec}, factor={liveness_factor}"
            )

        max_delay_ms = basis_tf_sec * 1000 * liveness_factor
        now_ms = int(self.monotonic_fn() * 1000)
        delta_ms = now_ms - state.last_regime_heartbeat_ms

        if delta_ms > max_delay_ms:
            self.logger.warning(
                f"[{symbol}] LIVENESS BLOCK: Regime heartbeat stale - "
                f"delta={delta_ms}ms > max={max_delay_ms}ms (basis={basis_tf_sec}s * factor={liveness_factor})"
            )
            return {
                "reason_code": "NRR-REGIME-DETECTOR-DEAD",
                "why": f"Regime detector heartbeat stale: {delta_ms}ms > {max_delay_ms}ms",
                "details": {
                    "last_regime_heartbeat_ms": state.last_regime_heartbeat_ms,
                    "delta_ms": delta_ms,
                    "max_delay_ms": max_delay_ms,
                    "basis_tf_sec": basis_tf_sec,
                    "liveness_factor": liveness_factor,
                },
            }

        return None

    def _emit_strategy_blocked(
        self,
        *,
        symbol: str,
        reason_code: str,
        reason: str,
        context: str,
        rid: str | None = None,
        why: str | None = None,
        details: dict | None = None,
        why_chain: list[str] | None = None,
        tf_sec: int | None = None,
        bar_close_ts: int | None = None,
        span_id: str | None = None,
    ) -> None:
        """Emit EVT:STRATEGY_DECISION_BLOCKED and mirror it into objective counters."""
        ts_ms = int(self.wall_time_fn() * 1000)
        payload = write_strategy_decision_blocked(
            strategy_id=self.strategy_id,
            symbol=symbol,
            reason_code=reason_code,
            reason=reason,
            context=context,
            src="aurora_handler:_emit_strategy_blocked",
            ts_ms=ts_ms,
            rid=rid,
            why=why,
            why_chain=why_chain,
            details=details,
            tf_sec=tf_sec,
            bar_close_ts=bar_close_ts,
            span_id=span_id,
        )
        state = self._symbol_states[symbol]
        # Objective scoring windows reuse the same blocked timestamps emitted downstream.
        state.objective_blocked_ts_ms.append(ts_ms)
        self.emit_fn("EVT:STRATEGY_DECISION_BLOCKED", payload)

    def on_regime_detected(self, event: Any) -> None:
        """Cache normalized regime state and refresh the detector heartbeat.

        Accepts either a raw dict payload (test/legacy path) or a typed
        RegimeEvent (production path from aurora_builtin boundary parsing).
        When a dict is received, it is parsed through RegimeDetectedBoundary
        and mapped to RegimeEvent before processing. This ensures identical
        semantics on both paths.

        Malformed dict payloads (ValidationError) are logged and dropped —
        the handler makes no state mutation on invalid regime evidence.
        """
        from apps.reference.domains.decision_making.contracts.core_models import RegimeEvent  # noqa: PLC0415

        if not isinstance(event, RegimeEvent):
            # Dict-sourced call (tests or legacy wiring): parse at handler boundary.
            if not isinstance(event, dict):
                return
            try:
                from apps.reference.domains.decision_making.contracts.boundary_models import (  # noqa: PLC0415
                    RegimeDetectedBoundary,
                )
                from apps.reference.domains.decision_making.contracts.boundary_mappers import (  # noqa: PLC0415
                    map_regime_boundary_to_event,
                )
                boundary = RegimeDetectedBoundary.model_validate(event)
                event = map_regime_boundary_to_event(boundary, raw=dict(event))
            except Exception as exc:  # ValidationError or mapping error
                symbol_raw = event.get("symbol", "unknown") if isinstance(
                    event, dict) else "unknown"
                self.logger.warning(
                    "[%s] EVT:REGIME_DETECTED boundary rejected in handler: %s",
                    symbol_raw,
                    exc,
                )
                return

        # event is now RegimeEvent regardless of which path entered.
        evt = event  # type: RegimeEvent

        if not is_structural_regime_payload(evt.raw):
            return
        symbol = evt.symbol
        if not symbol:
            return
        state = self._symbol_states[symbol]

        # Use pre-normalized regime label from the mapper.
        state.regime = evt.regime
        # raw_regime is a diagnostic field not promoted to RegimeEvent core;
        # read it from the raw transport payload.
        state.regime_raw_event = normalize_structural_regime_label(
            str(evt.raw.get("raw_regime") or "")
        )
        # confidence is float-resolved by the mapper.
        state.regime_confidence = evt.confidence
        state.regime_ts_ms = evt.ts_ms or int(self.wall_time_fn() * 1000)
        state.regime_structural_regime_ref = evt.structural_regime_ref
        state.regime_changed = evt.changed
        # raw_confidence: preserve original transport string/value so that
        # operator-facing fields and existing tests receive the raw form.
        state.regime_raw_confidence = evt.raw.get("raw_confidence")
        state.regime_last_update_ts_ms = evt.last_update_ts_ms
        state.last_regime_heartbeat_ms = evt.last_update_ts_ms
        state.regime_cache_write_ts_ms = int(self.wall_time_fn() * 1000)

        # Provenance helpers need the full raw payload (dict-like access).
        provenance = build_regime_provenance_fields(
            evt.raw,
            bar_close_ts_ms=evt.raw.get("bar_close_ts_ms"),
        )
        state.regime_event_ts_ms = int(
            provenance.get("regime_event_ts_ms") or state.regime_ts_ms or 0
        )
        state.regime_source = provenance.get("regime_source")
        state.regime_same_bar = provenance.get("regime_same_bar")
        state.regime_provenance_reason = provenance.get(
            "regime_provenance_reason")

        # Prefer detector-provided heartbeat; stamp arrival on monotonic clock
        # when not present.
        if evt.last_update_ts_ms:
            state.last_regime_heartbeat_ms = evt.last_update_ts_ms
        else:
            state.last_regime_heartbeat_ms = int(self.monotonic_fn() * 1000)

        if getattr(self, "anti_churn_enabled", False):
            self._update_effective_regime(symbol, state.regime)

        # Some producers omit changed on heartbeat-only updates.
        changed = evt.changed if evt.changed is not None else True
        confidence_text = (
            f"{state.regime_confidence:.2f}"
            if state.regime_confidence is not None
            else "missing"
        )
        self.logger.debug(
            f"[{symbol}] Regime cached: {state.regime} (confidence={confidence_text}, changed={changed})"
        )

    def on_portfolio_state(self, event: Dict[str, Any]) -> None:
        """Cache portfolio state and upgrade cold snapshots on flat-position evidence.

        Invalid net_position values are skipped rather than treated as zero so a
        malformed payload cannot fake a clean-start transition.
        """
        if not isinstance(event, dict):
            return
        self._latest_portfolio = event

        positions_raw = event.get("positions")
        if not isinstance(positions_raw, list):
            return

        ts_ms = int(event.get("positions_last_ts_ms") or event.get("ts") or 0)
        if ts_ms <= 0:
            ts_ms = int(self.wall_time_fn() * 1000)

        # Only numerically proven non-zero positions count as active.
        active_symbols: set[str] = set()
        for pos in positions_raw:
            if not isinstance(pos, dict):
                continue
            sym = str(pos.get("symbol") or "").upper()
            try:
                qty = decimal.Decimal(str(pos.get("net_position") or "0"))
            except (decimal.InvalidOperation, TypeError, ValueError):
                self.logger.warning(
                    "Invalid net_position for %s: %r — skipping (not treating as flat)",
                    sym, pos.get("net_position"),
                )
                continue
            if abs(qty) > decimal.Decimal("1e-9"):
                active_symbols.add(sym)

        for symbol in self._resolve_enabled_symbols():
            sym_key = str(symbol).upper()
            if sym_key in active_symbols:
                continue

            # The upgrade helper decides whether absence from the active set is
            # sufficient evidence for a clean-start restore transition.
            snapshot = self._analytics_restore_snapshots.get(sym_key)
            if snapshot is None:
                continue

            upgraded = upgrade_cold_execution_restore_if_clean_start(
                snapshot,
                updated_at=ts_ms,
                source="position_tracking:canonical_zero_positions",
                evidence_ref=f"portfolio_state:{sym_key}:{ts_ms}:zero_positions",
            )
            if upgraded is None:
                continue

            self._analytics_restore_snapshots[sym_key] = upgraded
            self.logger.info(
                "[CLEAN_START_UPGRADE] %s execution restore upgraded "
                "COLD->RESTORED via canonical position-tracking "
                "zero-positions confirmation (ts_ms=%d)",
                sym_key,
                ts_ms,
            )
            self.logger.info(
                "AURORA_CLEAN_START_UPGRADE %s",
                json.dumps(
                    {
                        "symbol": sym_key,
                        "strategy_id": self.strategy_id,
                        "ts_ms": ts_ms,
                        "source": "canonical_zero_positions",
                        "prev_execution_state": "COLD",
                        "new_execution_state": "RESTORED",
                    },
                    ensure_ascii=False,
                ),
            )

    def on_exposure_summary(self, event: Dict[str, Any]) -> None:
        """Cache the latest exposure summary used by objective preconditions."""
        if not isinstance(event, dict):
            return
        payload = event.get("exposure_summary")
        if isinstance(payload, dict):
            self._latest_exposure_summary = payload

    def on_order_state_changed(self, event: Dict[str, Any]) -> None:
        """Record cancel/expire/reject timestamps for objective behavior windows."""
        if not isinstance(event, dict):
            return
        symbol = event.get("symbol")
        if not symbol:
            return
        status = str(event.get("status") or event.get("state") or "").upper()
        if status in ("CANCELED", "EXPIRED", "REJECTED"):
            self._symbol_states[str(symbol)].objective_cancel_replace_ts_ms.append(
                int(event.get("ts_ms") or int(self.wall_time_fn() * 1000))
            )

    def on_trade_intent_rejected(self, event: Dict[str, Any]) -> None:
        """Record rejected-intent timestamps for this strategy only."""
        if not isinstance(event, dict):
            return
        if str(event.get("strategy_id") or "") != self.strategy_id:
            return
        symbol = event.get("symbol")
        if not symbol:
            return
        self._symbol_states[str(symbol)].objective_blocked_ts_ms.append(
            int(event.get("ts_ms") or int(self.wall_time_fn() * 1000))
        )

    def on_system_stress(self, event: Dict[str, Any]) -> None:
        """Cache the latest per-symbol system-stress state for later gates."""
        if not isinstance(event, dict):
            return
        symbol = event.get("symbol")
        state_str = event.get("state")
        if symbol and state_str:
            self._symbol_states[symbol].system_stress_state = state_str
            self.logger.debug(f"[{symbol}] System stress cached: {state_str}")

    # =========================================================================
    # T2B-03: CMD:PROCESS_STRATEGY - Primary Entry Point
    # =========================================================================

    def on_process_strategy(self, cmd: Any) -> None:
        """Validate CMD:PROCESS_STRATEGY and route accepted bars to decision logic.

        Accepts either a ProcessStrategyCmd (production path from aurora_builtin
        boundary parsing) or a raw dict (test/legacy path). Dict inputs are
        parsed through ProcessStrategyBoundary and mapped to ProcessStrategyCmd
        at the top of this method, ensuring identical semantics on both paths.

        Malformed dict payloads (ValidationError) are logged and dropped. Payloads
        that pass boundary parsing but fail business-gate checks still emit
        structured WAL records (Gates 0–4 below).

        Note: this method does NOT emit TRADE_INTENT_REJECTED for boundary
        failures. A boundary failure means no real strategy intent was formed yet.
        Gate-level rejections (disabled, missing tf_sec, etc.) do emit WAL records
        because they represent strategy-scope decisions.
        """
        from apps.reference.domains.decision_making.contracts.core_models import ProcessStrategyCmd  # noqa: PLC0415

        if not isinstance(cmd, ProcessStrategyCmd):
            # Dict-sourced call (tests or legacy wiring): parse at handler boundary.
            if not isinstance(cmd, dict):
                return
            try:
                from apps.reference.domains.decision_making.contracts.boundary_models import (  # noqa: PLC0415
                    ProcessStrategyBoundary,
                )
                from apps.reference.domains.decision_making.contracts.boundary_mappers import (  # noqa: PLC0415
                    map_process_strategy_boundary_to_cmd,
                )
                boundary = ProcessStrategyBoundary.model_validate(cmd)
                cmd = map_process_strategy_boundary_to_cmd(
                    boundary, raw=dict(cmd))
            except Exception as exc:  # ValidationError or mapping error
                symbol_raw = cmd.get("symbol", "unknown") if isinstance(
                    cmd, dict) else "unknown"
                self.logger.warning(
                    "[%s] CMD:PROCESS_STRATEGY boundary rejected in handler: %s",
                    symbol_raw,
                    exc,
                )
                return

        # cmd is now ProcessStrategyCmd regardless of which path entered.
        symbol = cmd.symbol
        if not symbol:
            return

        tf_sec = cmd.tf_sec

        # Gate 0: disabled strategy instances emit an explicit reject record.
        if not self._is_enabled:
            self._tick_path_rejections += 1
            self.logger.warning(
                f"REJECTED: Aurora CMD for {symbol}: Strategy is globally disabled (Killswitch)"
            )
            write_trade_intent_rejected(
                symbol=symbol,
                tf_sec=int(tf_sec) if tf_sec is not None else 0,
                bar_close_ts=cmd.bar_close_ts,
                reason_code="STRATEGY_DISABLED",
                stage="STRATEGY",
                why="CMD:PROCESS_STRATEGY rejected: Aurora is globally disabled",
                src="aurora_handler",
                ts_ms=cmd.bar_close_ts,
                rid=cmd.rid,
            )
            return

        # Gate 1: missing timeframe is a malformed command, not a no-op.
        if tf_sec is None:
            self._tick_path_rejections += 1
            self.logger.warning(
                f"REJECTED: Aurora CMD for {symbol}: tf_sec is None (missing)"
            )
            write_trade_intent_rejected(
                symbol=symbol,
                tf_sec=None,
                bar_close_ts=cmd.bar_close_ts,
                reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                stage="STRATEGY",
                why="CMD:PROCESS_STRATEGY missing tf_sec (fail-closed)",
                src="aurora_handler",
                ts_ms=cmd.bar_close_ts,
                rid=cmd.rid,
            )
            return

        # Gate 2: CMD bars must never arrive on the tick timeframe.
        if tf_sec == 0:
            self._tick_path_rejections += 1
            write_trade_intent_rejected(
                symbol=symbol,
                tf_sec=0,
                bar_close_ts=cmd.bar_close_ts,
                reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                stage="STRATEGY",
                why="CMD:PROCESS_STRATEGY tf_sec=0 forbidden (fail-closed)",
                src="aurora_handler",
                ts_ms=cmd.bar_close_ts,
                rid=cmd.rid,
            )
            return

        # Gate 3: wrong timeframe is ignored here so another strategy handler can own it.
        if tf_sec != self.timeframe_sec:
            return

        # Canonical bar identity is the stronger source of bar_close_ts when present.
        # Pass cmd.raw (full transport payload) to the utility which needs dict-like access.
        bar_identity = extract_canonical_bar_identity(
            cmd.raw,
            default_symbol=symbol,
            default_timeframe_sec=int(tf_sec) if tf_sec is not None else None,
            default_source_mode=RuntimeBarSourceMode.LIVE,
        )
        bar_close_ts = (
            int(bar_identity.bar_end_ts_ms)
            if bar_identity is not None
            else cmd.bar_close_ts
        )
        if not bar_close_ts:
            self._tick_path_rejections += 1
            self.logger.warning(
                f"REJECTED: Aurora CMD for {symbol}: bar_close_ts missing"
            )
            write_trade_intent_rejected(
                symbol=symbol,
                tf_sec=int(tf_sec) if tf_sec is not None else None,
                bar_close_ts=None,
                reason_code=NormalizedRejectReasons.DATA_NOT_READY,
                stage="STRATEGY",
                why="CMD:PROCESS_STRATEGY missing bar_close_ts (fail-closed)",
                src="aurora_handler",
                rid=cmd.rid,
            )
            return

        # Count the bar only after the command passed the handler envelope checks.
        self._bars_seen_since_restart[symbol] += 1
        self._process_decision(symbol, cmd)

    def on_features_data_only(self, event: Dict[str, Any]) -> None:
        """Cache non-trigger feature data from EVT:FEATURES_CALCULATED.

        This path does not update warmup and does not trigger decision logic. It
        only preserves auxiliary data blocks that CMD:PROCESS_STRATEGY omits.
        """
        symbol = event.get("symbol")
        if not symbol:
            return

        state = self._symbol_states[symbol]

        # price_motion is consumed later by volatility-adjusted gates.
        price_motion = event.get("price_motion")
        if price_motion:
            state.cached_price_motion = price_motion

    def on_features_calculated(self, event: Dict[str, Any]) -> None:
        """Compatibility wrapper for EVT:FEATURES_CALCULATED.

        The event remains a data-only alias to on_features_data_only(); command
        triggering stays on CMD:PROCESS_STRATEGY.
        """
        self.on_features_data_only(event)

    # _process_decision → moved to AuroraDecisionMixin (see aurora_decision.py)

    def _is_symbol_enabled(self, symbol: str) -> bool:
        """Return whether Aurora may act on this symbol.

        Per-symbol registry assignments override the legacy aurora.assets map.
        A symbol absent from both sources is treated as disabled.
        """
        # Registry assignments, when present for this symbol, are authoritative.
        registry = getattr(self.config, "strategies_registry", None)
        if registry:
            assignments = getattr(registry, "assignments", {}) or {}
            symbol_strategies = assignments.get(symbol, [])
            if symbol_strategies:
                return "aurora" in symbol_strategies

        # Fall back to the legacy per-asset enable flag when no registry entry exists.
        aurora = getattr(self.config.strategies, "aurora", None)
        if not aurora:
            return False
        assets = getattr(aurora, "assets", {})
        if symbol not in assets:
            return False
        asset_cfg = assets[symbol]
        return bool(getattr(asset_cfg, "enabled", True))

    def _get_instrument_config(self, symbol: str) -> Any:
        """Return the per-symbol Aurora asset config, if the strategy defines one."""
        aurora = getattr(self.config.strategies, "aurora", None)
        if not aurora:
            return None
        assets = getattr(aurora, "assets", {})
        return assets.get(symbol)

    # Holding period methods → moved to AuroraHoldingPeriodMixin (see aurora_holding_period.py)

    # =========================================================================
    # VOL-ADJ GATES METHODS (Anti-Flat / Anti-FOMO)
    # =========================================================================
    # _get_motion_norm_sigma, _apply_vol_adj_gates, _get_signal_weights,
    # _build_shield_cascade, _get_regime_thresholds, _check_liquidity_gate,
    # _get_feature_neutrals, _get_essential_features, _get_side_bias_state,
    # _update_side_bias → moved to AuroraScoringHelpersMixin
    # (see aurora_scoring_helpers.py)

    # _emit_signal → moved to AuroraDecisionMixin (see aurora_decision.py)
