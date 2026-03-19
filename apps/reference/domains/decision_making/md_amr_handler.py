"""
MD-AMR decision handler.

Strict-isolated strategy handler (does not modify legacy handlers).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import logging
import time
from collections import deque
from dataclasses import replace
from decimal import Decimal
from typing import Any, Dict, Optional, TYPE_CHECKING

from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    StrategyAnalyticsRestoreSnapshot,
    cold_restore_status,
    combine_restore_permissions_live_first,
    lookup_restore_status,
    merge_restore_readiness_live_first,
    restore_execution_blocking_tokens,
    restore_status_to_readiness_status,
    restored_restore_status,
    upgrade_cold_execution_restore_if_clean_start,
)
from apps.reference.bootstrap.startup_warmup import (
    apply_startup_warmup_permission_overlay,
    startup_warmup_gate_tokens,
)
from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    extract_canonical_bar_identity,
    extract_canonical_replay_identity,
)
from apps.reference.contracts.runtime_gap_policy import (
    attach_gap_status_payload,
    build_basis_bar_status_from_gap,
    build_trading_status_from_gap,
    extract_gap_status,
    gap_blocking_tokens,
    gap_blocks_open_new_risk,
)
from apps.reference.contracts.runtime_regime_layers import (
    is_structural_regime_payload,
    normalize_structural_regime_label,
)
from apps.reference.contracts.runtime_readiness import (
    RuntimeReadinessScope,
    cold_status,
    make_permissions,
    make_snapshot,
    partial_status,
    ready_status,
)
from vfoundation.core.protocol import Message
from apps.reference.core.time import get_clock
from apps.reference.domains.decision_making.strategy_bridge import MDAMRStrategyV11, MDAMRSignal
from apps.reference.config_models import AuroraConfig, MDAMRStrategyConfig
from apps.reference.domains.decision_making.position_queries import PositionQueries
from apps.reference.domains.regime_allowlist.contract import RegimeAllowlistContract
from apps.reference.telemetry.metrics import inc_decision_blocked, inc_warmup_block
from apps.reference.utils import get_domain_mode_from_mapping

if TYPE_CHECKING:
    from vfoundation.core import FSMCore

LOG = logging.getLogger(__name__)


def _maybe_build_position_queries(
    *,
    config: AuroraConfig,
    portfolio_getter,
    logger: logging.Logger,
) -> PositionQueries | None:
    """Build PositionQueries only when sizing SSOT is available and numeric."""
    try:
        dm_sizing_cfg = config.domains.decision_making.position_sizing
        min_position_size_usd = Decimal(
            str(dm_sizing_cfg.min_position_size_usd))
        liquidity_cap_usd = Decimal(str(dm_sizing_cfg.liquidity_based_cap_usd))
    except Exception as exc:
        logger.debug("PositionQueries unavailable during md_amr init: %s", exc)
        return None
    return PositionQueries(
        config,
        portfolio_getter,
        min_position_size_usd,
        liquidity_cap_usd,
        logger,
    )


class MDAMRHandler:
    """Event-driven handler for strategy_id=md_amr."""

    _REST_HYDRATION_LIMIT = 100
    _MANDATORY_LIVE_WARMUP_SEC = 7200
    _DIR_COMPONENTS_REQUIRED_BARS = 96
    _REGIME_ALIAS_MAP: Dict[str, str] = {
        "LOW_FLAT": "FLAT_LOW",
        "HIGH_FLAT": "FLAT_HIGH",
        "HIGHT_FLAT": "FLAT_HIGH",
        "NORMAL_FLAT": "FLAT_NORMAL",
        "HIGH_VOLATILYTY": "HIGH_VOLATILITY",
        "LOW_VOLATILYTY": "LOW_VOLATILITY",
        "HIGHT_VOLATILITY": "HIGH_VOLATILITY",
    }
    _REGIME_COMPATIBILITY_MAP: Dict[str, tuple[str, ...]] = {
        "FLAT_LOW": ("FLAT_LOW", "LOW_VOLATILITY"),
        "LOW_VOLATILITY": ("LOW_VOLATILITY", "FLAT_LOW"),
        "FLAT_NORMAL": ("FLAT_NORMAL", "MEAN_REVERSION"),
        "MEAN_REVERSION": ("MEAN_REVERSION", "FLAT_NORMAL"),
        "FLAT_HIGH": ("FLAT_HIGH", "HIGH_VOLATILITY"),
        "HIGH_VOLATILITY": ("HIGH_VOLATILITY", "FLAT_HIGH"),
    }

    def __init__(self, fsm: "FSMCore", config: AuroraConfig) -> None:
        self.fsm = fsm
        self.config = config
        self.logger = LOG.getChild("MDAMRHandler")
        self.mlog = logging.getLogger("domain_md_amr")

        self._cfg: Optional[MDAMRStrategyConfig] = None
        self._enabled = False
        self._enabled_symbols: set[str] = set()
        self._strategies: Dict[str, MDAMRStrategyV11] = {}
        self._last_features: Dict[str, Dict[str, Any]] = {}
        self._position_qty: Dict[str, Decimal] = {}
        self._bars_held: Dict[str, int] = {}
        self._deferred: Dict[str, Dict[str, Any]] = {}
        self._macro_block_until_ms: Dict[str, int] = {}
        self._regime: Dict[str, str] = {}
        self._regime_ts_ms: Dict[str, int] = {}
        self._regime_confidence: Dict[str, float] = {}
        self._rest_hydrated = False
        self._rest_last_bar_ts_ms: Dict[str, int] = {}
        # FIX:N-2 — Track bars seen per symbol since restart for cold-start gate
        self._bars_seen_since_restart: Dict[str, int] = {}
        self._last_ingested_bar_ts_ms: Dict[str, int] = {}
        self._pending_close: dict[str, bool] = {}
        self._last_close_ts: dict[str, int] = {}
        self._gtx_retries: dict[str, int] = {}
        self._entries_at_ts: Dict[int, int] = {}
        self.mandatory_warmup_until = 0
        self._latest_portfolio: Dict[str, Any] | None = None
        self._latest_exposure_summary: Dict[str, Any] | None = None
        self._objective_blocked_ts_ms: Dict[str, deque[int]] = {}
        self._objective_cancel_replace_ts_ms: Dict[str, deque[int]] = {}
        self._objective_reentry_ts_ms: Dict[str, deque[int]] = {}
        self._analytics_restore_snapshots: Dict[str,
                                                StrategyAnalyticsRestoreSnapshot] = {}
        # TICK-BAR-SPLIT-FIX-3: cooldown for tf_sec reject logging (300s per key)
        self._tf_sec_reject_cooldown: Dict[str, float] = {}
        self._TF_SEC_REJECT_COOLDOWN_SEC = 300
        self._signal_ready_logged: set[str] = set()

        self._position_queries = _maybe_build_position_queries(
            config=self.config,
            portfolio_getter=lambda: self._latest_portfolio,
            logger=self.logger,
        )

        self._parse_config()
        if self._enabled:
            self._init_strategies()

    def _core_signal_history_required_bars(self) -> int:
        if self._cfg is None:
            return self._DIR_COMPONENTS_REQUIRED_BARS
        atr_window = int(getattr(self._cfg, "atr_window", 14) or 14)
        atr_stats_window = int(
            getattr(self._cfg, "atr_stats_window", 64) or 64)
        channel_window_bars = int(
            getattr(self._cfg, "channel_window_bars", 12) or 12)
        return max(
            channel_window_bars,
            atr_window + atr_stats_window - 1,
            self._DIR_COMPONENTS_REQUIRED_BARS,
        )

    def _log_runtime_marker(self, marker: str, **payload: Any) -> None:
        base_payload: Dict[str, Any] = {
            "strategy_id": "md_amr",
            "tf_sec": int(self.timeframe_sec),
        }
        for key, value in payload.items():
            if value is not None:
                base_payload[key] = value
        self.mlog.info(
            "%s %s",
            marker,
            json.dumps(base_payload, ensure_ascii=False, default=str),
        )

    def _log_tf_sec_reject(self, symbol: str, stage: str, reason: str) -> None:
        """Log tf_sec rejection with 300s cooldown per (symbol, reason) to avoid log storm."""
        key = f"{symbol}:{stage}:{reason}"
        now = time.monotonic()
        last = self._tf_sec_reject_cooldown.get(key, 0.0)
        if now - last < self._TF_SEC_REJECT_COOLDOWN_SEC:
            return
        self._tf_sec_reject_cooldown[key] = now
        self.logger.warning(
            "REJECTED md_amr %s for %s: %s (cooldown=%ds)",
            stage, symbol, reason, self._TF_SEC_REJECT_COOLDOWN_SEC,
        )

    def apply_runtime_analytics_restore_snapshot(
        self,
        snapshot: StrategyAnalyticsRestoreSnapshot,
    ) -> None:
        if str(snapshot.strategy_id) != "md_amr":
            return
        self._analytics_restore_snapshots[str(snapshot.symbol)] = snapshot

    def get_runtime_analytics_restore_snapshot(
        self,
        symbol: str,
    ) -> StrategyAnalyticsRestoreSnapshot | None:
        return self._analytics_restore_snapshots.get(str(symbol))

    def describe_runtime_analytics_restore(
        self,
        symbol: str,
    ) -> dict[str, dict[str, object]]:
        symbol_key = str(symbol)
        last_ts = int(self._rest_last_bar_ts_ms.get(symbol_key, 0) or 0)
        if self._rest_hydrated and last_ts > 0:
            status = restored_restore_status(
                why=["md_amr_rest_hydration"],
                updated_at=last_ts,
                source="decision_making:md_amr_rest_hydration",
                evidence_ref=f"md_amr_rest:{symbol_key}:{last_ts}",
            )
        else:
            status = cold_restore_status(
                why=["md_amr_rest_hydration_missing"],
                updated_at=None,
                source="decision_making:md_amr_rest_hydration",
                evidence_ref=f"md_amr_rest:{symbol_key}:missing",
            )
        return {
            RuntimeAnalyticsRestoreScope.STRATEGY_LOCAL_STATE.value: status.to_payload(),
        }

    @property
    def timeframe_sec(self) -> int:
        return int(self._cfg.timeframe_sec) if self._cfg is not None else 900

    def seed_startup_bars(self, symbol: str, count: int) -> None:
        """Seed _bars_seen_since_restart counter after startup basis import.

        STARTUP-BASIS-HYDRATION: Called by startup executor after hydrate_basis_bars().
        Uses max() to avoid overwriting any live bars already counted in the counter.
        """
        if count > 0:
            current = self._bars_seen_since_restart.get(symbol, 0)
            self._bars_seen_since_restart[symbol] = max(current, count)
            self.mlog.info(
                "MD_AMR seed_startup_bars sym=%s bars_seen=%d (seeded=%d)",
                symbol, self._bars_seen_since_restart[symbol], count,
            )

    def get_readiness_diagnostics(self) -> list[dict[str, object]]:
        """Return per-symbol readiness diagnostics for operator visibility.

        Provides a machine-readable view of the cold-start readiness state
        for every enabled symbol tracked by this handler.
        """
        _basis_required = 0
        try:
            from apps.reference.contracts.strategy_compatibility_matrix import (
                get_active_strategy_profile,
            )
            _profile = get_active_strategy_profile(self.config, "md_amr")
            if _profile is None:
                _contract_error = "READINESS_CONTRACT_UNRESOLVED:PROFILE_NOT_FOUND"
                return [
                    {
                        "strategy": "md_amr",
                        "symbol": sym,
                        "tf_sec": self.timeframe_sec,
                        "bars_seen": self._bars_seen_since_restart.get(sym, 0),
                        "bars_required": None,
                        "ready": False,
                        "block_reason": _contract_error,
                    }
                    for sym in sorted(self._enabled_symbols)
                ]
            _basis_required = int(_profile.basis_required_bars)
        except Exception as _exc:
            _contract_error = f"READINESS_CONTRACT_UNRESOLVED:{type(_exc).__name__}"
            return [
                {
                    "strategy": "md_amr",
                    "symbol": sym,
                    "tf_sec": self.timeframe_sec,
                    "bars_seen": self._bars_seen_since_restart.get(sym, 0),
                    "bars_required": None,
                    "ready": False,
                    "block_reason": _contract_error,
                }
                for sym in sorted(self._enabled_symbols)
            ]
        results: list[dict[str, object]] = []
        for symbol in sorted(self._enabled_symbols):
            bars_seen = self._bars_seen_since_restart.get(symbol, 0)
            ready = bars_seen >= _basis_required
            results.append({
                "strategy": "md_amr",
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

    def register(self) -> None:
        if not self._enabled:
            self._log_runtime_marker(
                "MD_AMR_REGISTERED",
                enabled=False,
                events=[],
                enabled_symbols=sorted(self._enabled_symbols),
            )
            return
        self._hydrate_state_from_rest()
        events = [
            "CMD:PROCESS_STRATEGY",
            "EVT:FEATURES_CALCULATED",
            "EVT:REGIME_DETECTED",
            "EVT:TRADE_EXECUTED",
            "EVT:ORDER_REJECTED",
            "EVT:PORTFOLIO_STATE_UPDATED",
            "EVT:EXPOSURE_SUMMARY_UPDATED",
            "EVT:ORDER_STATE_CHANGED",
            "EVT:TRADE_INTENT_REJECTED",
        ]
        self.fsm.listen("CMD:PROCESS_STRATEGY", self._on_process_strategy)
        self.fsm.listen("EVT:FEATURES_CALCULATED",
                        self._on_features_calculated)
        self.fsm.listen("EVT:REGIME_DETECTED", self._on_regime_detected)
        self.fsm.listen("EVT:TRADE_EXECUTED", self._on_trade_executed)
        self.fsm.listen("EVT:ORDER_REJECTED", self._on_order_rejected)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED",
                        self._on_portfolio_state_updated)
        self.fsm.listen("EVT:EXPOSURE_SUMMARY_UPDATED",
                        self._on_exposure_summary_updated)
        self.fsm.listen("EVT:ORDER_STATE_CHANGED",
                        self._on_order_state_changed)
        self.fsm.listen("EVT:TRADE_INTENT_REJECTED",
                        self._on_trade_intent_rejected)
        self.logger.info(
            "MD_AMR registered events=%s symbols=%s tf=%s",
            ["CMD:PROCESS_STRATEGY", "EVT:FEATURES_CALCULATED",
                "EVT:REGIME_DETECTED", "EVT:TRADE_EXECUTED"],
            sorted(self._enabled_symbols),
            self.timeframe_sec,
        )
        self._log_runtime_marker(
            "MD_AMR_REGISTERED",
            enabled=True,
            enabled_symbols=sorted(self._enabled_symbols),
            events=events,
        )

    @staticmethod
    def _run_coro_blocking(coro: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(lambda: asyncio.run(coro))
            return fut.result(timeout=60)

    @staticmethod
    def _interval_for_tf(tf_sec: int) -> Optional[str]:
        mapping = {
            60: "1m",
            180: "3m",
            300: "5m",
            900: "15m",
            1800: "30m",
            3600: "1h",
            14400: "4h",
            86400: "1d",
        }
        return mapping.get(int(tf_sec))

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except Exception:
            return None

    def _extract_event_ts_ms(self, payload: Dict[str, Any]) -> Optional[int]:
        identity = extract_canonical_bar_identity(
            payload,
            default_source_mode=RuntimeBarSourceMode.LIVE,
        )
        if identity is not None:
            return int(identity.bar_end_ts_ms)
        keys = ("bar_close_ts", "ts_ms", "timestamp", "ts")
        for key in keys:
            ts = self._to_int(payload.get(key))
            if ts is not None and ts > 0:
                return ts
        bar = payload.get("bar")
        if isinstance(bar, dict):
            for key in ("end_ts_ms", "close_ts", "kline_close_time", "ts"):
                ts = self._to_int(bar.get(key))
                if ts is not None and ts > 0:
                    return ts
        return None

    def _is_duplicate_live_event(self, symbol: str, event_ts_ms: Optional[int]) -> bool:
        if event_ts_ms is None:
            return False
        rest_ts = int(self._rest_last_bar_ts_ms.get(symbol, 0) or 0)
        return rest_ts > 0 and int(event_ts_ms) <= rest_ts

    def _is_mandatory_live_warmup_active(self, now_ms: int) -> bool:
        return int(now_ms) < int(self.mandatory_warmup_until or 0)

    @classmethod
    def _normalize_regime_label(cls, regime: Any) -> str:
        return cls._REGIME_ALIAS_MAP.get(str(regime or "").strip().upper(), str(regime or "").strip().upper())

    @classmethod
    def _expand_allowed_regimes(cls, allowed_regimes: list[str]) -> list[str]:
        expanded: list[str] = []
        seen: set[str] = set()
        for raw_regime in allowed_regimes:
            normalized = cls._normalize_regime_label(raw_regime)
            compatible = cls._REGIME_COMPATIBILITY_MAP.get(
                normalized, (normalized,))
            for regime in compatible:
                if regime and regime not in seen:
                    seen.add(regime)
                    expanded.append(regime)
        return expanded

    @staticmethod
    def _kline_to_bar(kline: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(kline, (list, tuple)) or len(kline) < 7:
            return None
        start_ts = MDAMRHandler._to_int(kline[0])
        end_ts = MDAMRHandler._to_int(kline[6])
        if start_ts is None or end_ts is None:
            return None
        return {
            "open": str(kline[1]),
            "high": str(kline[2]),
            "low": str(kline[3]),
            "close": str(kline[4]),
            "volume": str(kline[5]),
            "start_ts_ms": int(start_ts),
            "end_ts_ms": int(end_ts),
        }

    def _resolve_rest_adapter(self) -> tuple[Any, bool]:
        md_domain = self.fsm.get_domain("market_data") if hasattr(
            self.fsm, "get_domain") else None
        adapter = getattr(md_domain, "adapter",
                          None) if md_domain is not None else None
        if adapter is not None and hasattr(adapter, "get_klines"):
            return adapter, False

        from apps.reference.adapters.binance_adapter import BinanceAdapter

        mode = str(get_domain_mode_from_mapping(
            self.config, "market_data")).lower()
        api_env = self.config.binance_api.live if mode == "live" else self.config.binance_api.testnet
        api_key = str(api_env.api_key or "")
        api_secret = str(api_env.api_secret or "")
        rest_url = str(api_env.rest_url or "")
        if not rest_url:
            raise RuntimeError(
                "REST hydration failed: binance_api.rest_url is empty")
        return (
            BinanceAdapter(
                api_key=api_key,
                api_secret=api_secret,
                rest_url=rest_url,
            ),
            True,
        )

    def _close_temp_adapter(self, adapter: Any) -> None:
        close_fn = getattr(adapter, "aclose", None)
        if not callable(close_fn):
            return
        try:
            self._run_coro_blocking(close_fn())
        except Exception:
            return

    async def _hydrate_state_from_rest_async(self, interval: str) -> int:
        adapter: Any = None
        temporary_adapter = False
        hydrated_symbols = 0
        try:
            adapter, temporary_adapter = self._resolve_rest_adapter()
            for symbol in sorted(self._enabled_symbols):
                strategy = self._strategies.get(symbol)
                if strategy is None:
                    continue
                try:
                    raw_klines = await adapter.get_klines(
                        symbol=symbol,
                        interval=interval,
                        limit=int(self._REST_HYDRATION_LIMIT),
                    )
                except Exception as exc:
                    self.logger.warning(
                        "MD_AMR hydration klines fetch failed symbol=%s err=%s", symbol, exc)
                    continue

                if not isinstance(raw_klines, list) or not raw_klines:
                    self.logger.warning(
                        "MD_AMR hydration empty klines symbol=%s", symbol)
                    continue

                bars: list[Dict[str, Any]] = []
                for row in raw_klines:
                    bar = self._kline_to_bar(row)
                    if bar is not None:
                        bars.append(bar)
                bars.sort(key=lambda b: int(b["end_ts_ms"]))
                if not bars:
                    self.logger.warning(
                        "MD_AMR hydration produced no valid bars symbol=%s", symbol)
                    continue

                for bar in bars:
                    strategy.on_bar(
                        bar=bar,
                        position_ctx={"qty_signed": 0.0, "bars_held": 0},
                        llm_blocked=False,
                    )

                last_ts = int(bars[-1]["end_ts_ms"])
                self._rest_last_bar_ts_ms[symbol] = last_ts
                self._last_ingested_bar_ts_ms[symbol] = last_ts
                hydrated_symbols += 1
        finally:
            if temporary_adapter and adapter is not None:
                close_fn = getattr(adapter, "aclose", None)
                if callable(close_fn):
                    try:
                        await close_fn()
                    except Exception:
                        pass
        return hydrated_symbols

    def _hydrate_state_from_rest(self) -> None:
        interval = self._interval_for_tf(self.timeframe_sec)
        now_ms = get_clock().now_ms()
        if interval is None:
            self.logger.warning(
                "MD_AMR hydration skipped: unsupported timeframe_sec=%s", self.timeframe_sec)
            self.mandatory_warmup_until = int(
                now_ms + self._MANDATORY_LIVE_WARMUP_SEC * 1000)
            return

        hydrated_symbols = 0
        try:
            hydrated_symbols = int(self._run_coro_blocking(
                self._hydrate_state_from_rest_async(interval)
            ) or 0)
        except Exception as exc:
            self.logger.warning("MD_AMR hydration failed: %s", exc)

        self._rest_hydrated = hydrated_symbols > 0
        self.mandatory_warmup_until = int(
            get_clock().now_ms() + self._MANDATORY_LIVE_WARMUP_SEC * 1000)
        self.mlog.info(
            "MD_AMR_HYDRATION %s",
            json.dumps(
                {
                    "hydrated_symbols": hydrated_symbols,
                    "enabled_symbols": sorted(self._enabled_symbols),
                    "rest_hydrated": self._rest_hydrated,
                    "mandatory_warmup_until_ms": int(self.mandatory_warmup_until),
                    "rest_last_bar_ts_ms": dict(self._rest_last_bar_ts_ms),
                },
                ensure_ascii=False,
            ),
        )

    def _get_assigned_symbols(self) -> set[str]:
        symbols: set[str] = set()
        sr = getattr(self.config, "strategies_registry", None)
        assignments = getattr(sr, "assignments", {}) if sr is not None else {}
        if isinstance(assignments, dict):
            for symbol, strategy_ids in assignments.items():
                if isinstance(strategy_ids, list) and "md_amr" in strategy_ids:
                    symbols.add(str(symbol))
        return symbols

    def _parse_config(self) -> None:
        assigned = self._get_assigned_symbols()
        cfg = getattr(self.config.strategies, "md_amr", None)
        if cfg is None:
            if assigned:
                raise ValueError(
                    f"CRITICAL: md_amr assigned to symbols {sorted(assigned)} but config.strategies.md_amr missing"
                )
            self._enabled = False
            return
        self._cfg = cfg
        if assigned and not bool(cfg.enabled):
            raise ValueError(
                f"CRITICAL: md_amr assigned to symbols {sorted(assigned)} but strategies.md_amr.enabled=false"
            )

        invalid_assigned: list[str] = []
        for symbol in sorted(assigned):
            asset_cfg = cfg.assets.get(symbol) if isinstance(
                cfg.assets, dict) else None
            if asset_cfg is None:
                invalid_assigned.append(
                    f"{symbol}:missing_asset_block"
                )
                continue
            if not bool(asset_cfg.enabled):
                invalid_assigned.append(f"{symbol}:enabled=false")
            if getattr(asset_cfg, "exit", None) is None:
                invalid_assigned.append(f"{symbol}:exit_missing")
            allowed_regimes = getattr(asset_cfg, "allowed_regimes", None)
            if not isinstance(allowed_regimes, list) or not any(str(x).strip() for x in allowed_regimes):
                invalid_assigned.append(f"{symbol}:allowed_regimes_missing")
        if invalid_assigned:
            raise ValueError(
                "CRITICAL: md_amr assigned symbols failed live contract: "
                + ", ".join(invalid_assigned)
            )

        for symbol, asset_cfg in cfg.assets.items():
            if bool(asset_cfg.enabled):
                self._enabled_symbols.add(str(symbol))

        self._enabled_symbols = self._enabled_symbols.intersection(
            assigned) if assigned else self._enabled_symbols
        self._enabled = bool(cfg.enabled) and bool(self._enabled_symbols)

        self.mlog.info(
            "MD_AMR_INIT %s",
            json.dumps(
                {
                    "strategy_id": "md_amr",
                    "enabled": self._enabled,
                    "assigned_symbols": sorted(assigned),
                    "enabled_symbols": sorted(self._enabled_symbols),
                    "timeframe_sec": self.timeframe_sec,
                    "defer_ttl_sec": int(cfg.defer_ttl_sec),
                    "signal_required_bars": self._core_signal_history_required_bars(),
                },
                ensure_ascii=False,
            ),
        )
        self._log_runtime_marker(
            "MD_AMR_ENABLED",
            enabled=self._enabled,
            assigned_symbols=sorted(assigned),
            enabled_symbols=sorted(self._enabled_symbols),
            signal_required_bars=self._core_signal_history_required_bars(),
        )

    def _init_strategies(self) -> None:
        assert self._cfg is not None
        for symbol in self._enabled_symbols:
            self._objective_blocked_ts_ms[symbol] = deque()
            self._objective_cancel_replace_ts_ms[symbol] = deque()
            self._objective_reentry_ts_ms[symbol] = deque()
            self._strategies[symbol] = MDAMRStrategyV11(
                channel_window_bars=int(self._cfg.channel_window_bars),
                hysteresis_mult=float(self._cfg.hysteresis_mult),
                threshold_z=float(self._cfg.threshold_z),
                volatility_dampening_factor=float(
                    self._cfg.volatility_dampening_factor),
                thr_base=float(self._cfg.thr_base),
                alpha=float(self._cfg.alpha),
                conf_min=float(self._cfg.conf_min),
                max_hold_bars=int(self._cfg.max_hold_bars),
                fee_bps=float(self._cfg.fee_bps),
                slippage_buffer_bps=float(self._cfg.slippage_buffer_bps),
                scaleout_fraction=float(self._cfg.scaleout_fraction),
                atr_zscore_clamp=float(self._cfg.atr_zscore_clamp),
                atr_std_floor_pct=float(self._cfg.atr_std_floor_pct),
                thr_floor=float(self._cfg.thr_floor),
                scaleout_cost_model=self._cfg.scaleout_cost_model,
                weights={
                    "d1": float(self._cfg.weights.d1),
                    "h1": float(self._cfg.weights.h1),
                    "m30": float(self._cfg.weights.m30),
                    "m15": float(self._cfg.weights.m15),
                },
                atr_window=int(self._cfg.atr_window),
                atr_stats_window=int(self._cfg.atr_stats_window),
            )

    def _emit_trade_intent_rejected_mandatory_warmup(
        self,
        *,
        symbol: str,
        side: str,
        rid: str,
        ts_ms: int,
    ) -> None:
        payload = {
            "symbol": symbol,
            "strategy_id": "md_amr",
            "side": str(side).lower(),
            "rid": str(rid),
            "reason_code": "MANDATORY_LIVE_WARMUP",
            "stage": "READINESS",
            "why": "mandatory_live_warmup",
            "context": "md_amr_handler:mandatory_live_warmup",
            "why_chain": ["mandatory_live_warmup"],
            "details": {"mandatory_warmup_until_ms": int(self.mandatory_warmup_until)},
            "ts_ms": int(ts_ms),
        }
        self.fsm.emit(
            "EVT:TRADE_INTENT_REJECTED",
            payload=payload,
            why="intent_rejected:MANDATORY_LIVE_WARMUP",
        )

    def _emit_trade_intent_rejected_gate(
        self,
        *,
        symbol: str,
        side: str,
        rid: str,
        ts_ms: int,
        reason_code: str,
        stage: str,
        why: str,
        why_chain: list[str],
        details: Dict[str, Any],
    ) -> None:
        payload = {
            "symbol": symbol,
            "strategy_id": "md_amr",
            "side": str(side).lower(),
            "rid": str(rid),
            "reason_code": str(reason_code),
            "stage": str(stage).upper(),
            "why": str(why),
            "context": str(why),
            "why_chain": list(why_chain),
            "details": details,
            "ts_ms": int(ts_ms),
        }
        self.fsm.emit(
            "EVT:TRADE_INTENT_REJECTED",
            payload=payload,
            why=f"intent_rejected:{reason_code}",
        )

    def _entry_regime_allowed(
        self,
        *,
        symbol: str,
        asset_cfg: Any,
    ) -> tuple[bool, Dict[str, Any]]:
        allowed_regimes = list(
            getattr(asset_cfg, "allowed_regimes", None) or [])
        effective_allowed_regimes = self._expand_allowed_regimes(
            allowed_regimes)
        regime = self._normalize_regime_label(self._regime.get(symbol))
        if not regime:
            return False, {
                "reason_code": "REGIME_GATE_BLOCKED",
                "why": "md_amr_handler:regime_missing",
                "why_chain": ["REGIME_GATE_BLOCKED", "REGIME_MISSING"],
                "details": {
                    "symbol": symbol,
                    "regime": None,
                    "allowed_regimes": allowed_regimes,
                    "effective_allowed_regimes": effective_allowed_regimes,
                },
            }
        if not RegimeAllowlistContract.is_regime_allowed(current_regime=str(regime), allowed_regimes=effective_allowed_regimes):
            return False, {
                "reason_code": "REGIME_GATE_BLOCKED",
                "why": "md_amr_handler:regime_not_allowlisted",
                "why_chain": ["REGIME_GATE_BLOCKED", f"REGIME={regime}"],
                "details": {
                    "symbol": symbol,
                    "regime": str(regime),
                    "allowed_regimes": allowed_regimes,
                    "effective_allowed_regimes": effective_allowed_regimes,
                },
            }
        return True, {
            "details": {
                "symbol": symbol,
                "regime": str(regime),
                "allowed_regimes": allowed_regimes,
                "effective_allowed_regimes": effective_allowed_regimes,
            }
        }

    def _on_features_calculated(self, event: Message) -> None:
        if not self._enabled:
            return
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return
        symbol = str(pld.get("symbol") or "")
        tf_sec = pld.get("tf_sec")
        if symbol not in self._enabled_symbols:
            return

        # TICK-BAR-SPLIT-FIX-3: explicit tf_sec guard with cooldown logging
        if tf_sec is None:
            self._log_tf_sec_reject(symbol, "features", "tf_sec_is_None")
            return
        try:
            tf_sec_int = int(tf_sec)
        except (TypeError, ValueError):
            self._log_tf_sec_reject(
                symbol, "features", f"tf_sec_invalid:{tf_sec!r}")
            return
        if tf_sec_int <= 0:
            self._log_tf_sec_reject(
                symbol, "features", f"tf_sec_non_positive:{tf_sec_int}")
            return

        if tf_sec_int != self.timeframe_sec:
            return
        event_ts_ms = self._extract_event_ts_ms(pld)
        if self._is_duplicate_live_event(symbol, event_ts_ms):
            return

        self._last_features[symbol] = pld.get(
            "features", {}) if isinstance(pld.get("features"), dict) else {}

        if not self._is_mandatory_live_warmup_active(get_clock().now_ms()):
            return

        bar = pld.get("bar")
        if not isinstance(bar, dict):
            return
        close_ts_ms = self._to_int(bar.get("end_ts_ms")) or event_ts_ms
        if close_ts_ms is None:
            return
        if close_ts_ms <= int(self._last_ingested_bar_ts_ms.get(symbol, 0) or 0):
            return
        if not all(bar.get(k) is not None for k in ("open", "high", "low", "close")):
            return
        strategy = self._strategies.get(symbol)
        if strategy is None:
            return
        pos_qty = self._position_qty.get(symbol, Decimal("0"))
        strategy.on_bar(
            bar=bar,
            position_ctx={"qty_signed": float(pos_qty), "bars_held": int(
                self._bars_held.get(symbol, 0))},
            llm_blocked=False,
        )
        self._last_ingested_bar_ts_ms[symbol] = int(close_ts_ms)

    def _on_regime_detected(self, event: Message) -> None:
        pld = event.pld or {}
        if not isinstance(pld, dict) or not is_structural_regime_payload(pld):
            return
        symbol = str(pld.get("symbol") or "")
        if symbol not in self._enabled_symbols:
            return
        regime = normalize_structural_regime_label(
            pld.get("regime") or pld.get("overall_regime"))
        if regime:
            self._regime[symbol] = str(regime)
            if pld.get("confidence") is not None:
                self._regime_confidence[symbol] = float(pld.get("confidence"))
            ts_ms = self._to_int(pld.get("ts_ms") or pld.get("ts"))
            if ts_ms is not None and ts_ms > 0:
                self._regime_ts_ms[symbol] = int(ts_ms)

    def _on_trade_executed(self, event: Message) -> None:
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return
        symbol = str(pld.get("symbol") or "")
        if symbol not in self._enabled_symbols:
            return
        qty_raw = pld.get("quantity")
        side = str(pld.get("side") or "").lower()
        try:
            qty = Decimal(str(qty_raw))
        except Exception:
            return
        if qty == 0:
            return

        if qty > 0 and side == "sell":
            qty = -qty
        if qty < 0 and side == "buy":
            qty = -qty

        prev = self._position_qty.get(symbol, Decimal("0"))
        now = prev + qty
        if prev == Decimal("0") and now != Decimal("0") and int(self._last_close_ts.get(symbol, 0) or 0) > 0:
            self._objective_reentry_ts_ms.setdefault(
                symbol, deque()).append(get_clock().now_ms())
        if abs(now) < Decimal("1e-9"):
            now = Decimal("0")
            self._bars_held[symbol] = 0
            self._pending_close[symbol] = False
            self._last_close_ts[symbol] = get_clock().now_ms()
        self._position_qty[symbol] = now

    def _on_portfolio_state_updated(self, event: Message) -> None:
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return
        self._latest_portfolio = pld

        positions_raw = pld.get("positions")
        if not isinstance(positions_raw, list):
            return

        ts_ms = int(pld.get("positions_last_ts_ms") or pld.get("ts") or 0)
        if ts_ms <= 0:
            ts_ms = get_clock().now_ms()

        active_symbols: set[str] = set()
        for pos in positions_raw:
            if not isinstance(pos, dict):
                continue
            sym = str(pos.get("symbol") or "").upper()
            try:
                qty = Decimal(str(pos.get("net_position") or "0"))
            except Exception:
                qty = Decimal("0")
            if abs(qty) > Decimal("1e-9"):
                active_symbols.add(sym)

        for symbol in self._enabled_symbols:
            sym_key = str(symbol).upper()
            if sym_key in active_symbols:
                continue

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
            self.mlog.info(
                "MD_AMR_CLEAN_START_UPGRADE %s",
                json.dumps(
                    {
                        "symbol": sym_key,
                        "strategy_id": "md_amr",
                        "ts_ms": ts_ms,
                        "source": "canonical_zero_positions",
                        "prev_execution_state": "COLD",
                        "new_execution_state": "RESTORED",
                    },
                    ensure_ascii=False,
                ),
            )

    def _on_exposure_summary_updated(self, event: Message) -> None:
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return
        exposure_summary = pld.get("exposure_summary")
        if isinstance(exposure_summary, dict):
            self._latest_exposure_summary = exposure_summary

    def _on_order_state_changed(self, event: Message) -> None:
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return
        symbol = str(pld.get("symbol") or "")
        if symbol not in self._enabled_symbols:
            return
        status = str(pld.get("status") or pld.get("state") or "").upper()
        if status in ("CANCELED", "EXPIRED", "REJECTED"):
            self._objective_cancel_replace_ts_ms.setdefault(symbol, deque()).append(
                int(pld.get("ts_ms") or get_clock().now_ms())
            )

    def _on_trade_intent_rejected(self, event: Message) -> None:
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return
        if str(pld.get("strategy_id") or "") != "md_amr":
            return
        symbol = str(pld.get("symbol") or "")
        if symbol not in self._enabled_symbols:
            return
        self._objective_blocked_ts_ms.setdefault(symbol, deque()).append(
            int(pld.get("ts_ms") or get_clock().now_ms())
        )

    def reconcile_position(self, symbol: str, exchange_qty: Decimal) -> None:
        cfg = self._cfg
        if cfg and not cfg.reconciliation.enabled:
            return
        tolerance = Decimal(
            str(cfg.reconciliation.drift_tolerance)) if cfg else Decimal("1e-6")
        local_qty = self._position_qty.get(symbol, Decimal("0"))
        if abs(local_qty - exchange_qty) > tolerance:
            self.mlog.warning(
                "MD_AMR_POSITION_DRIFT symbol=%s local=%s exchange=%s",
                symbol, local_qty, exchange_qty,
            )
            self._position_qty[symbol] = exchange_qty
            if abs(exchange_qty) < tolerance:
                self._bars_held[symbol] = 0

    @staticmethod
    def _normalize_order_reject_reason(pld: dict) -> str:
        """Canonical normalization for EVT:ORDER_REJECTED payload reason.

        Priority: reject_reason > reason > reason_code+reason_text.
        Returns UPPER-CASED trimmed string, or "" if unresolvable.
        Empty / malformed payloads yield "" which is fail-closed:
        no POST_ONLY/MAKER_ONLY substring match → no unsafe retry/fallback.
        """
        # 1. reject_reason (legacy / test contract)
        raw = pld.get("reject_reason")
        if raw is not None:
            val = str(raw).strip().upper()
            if val:
                return val

        # 2. reason (open_executor / binance_ws_client emitter)
        raw = pld.get("reason")
        if raw is not None:
            val = str(raw).strip().upper()
            if val:
                return val

        # 3. reason_code + reason_text (fsm.py ADAPTER_ERROR path)
        code = pld.get("reason_code")
        text = pld.get("reason_text")
        if code is not None:
            parts = [str(code).strip().upper()]
            if text is not None:
                parts.append(str(text).strip().upper())
            combined = ": ".join(p for p in parts if p)
            if combined:
                return combined

        return ""

    def _on_order_rejected(self, event: Message) -> None:
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return
        symbol = str(pld.get("symbol") or "")
        if symbol not in self._enabled_symbols:
            return
        self._objective_cancel_replace_ts_ms.setdefault(
            symbol, deque()).append(get_clock().now_ms())

        # Canonical normalization: reject_reason > reason > reason_code+reason_text
        reason = self._normalize_order_reject_reason(pld)
        if not reason:
            self.mlog.info(
                "ORDER_REJECTED_REASON_EMPTY symbol=%s pld_keys=%s — fail-closed, no retry",
                symbol, sorted(pld.keys()),
            )
        if "MAKER_ONLY" in reason or "POST_ONLY" in reason:
            retries = self._gtx_retries.get(symbol, 0)
            max_retries = self._cfg.execution.gtx_retry_max if self._cfg and hasattr(
                self._cfg, 'execution') else 0

            if retries < max_retries:
                self._gtx_retries[symbol] = retries + 1
                self.mlog.warning(
                    "MD_AMR_GTX_REJECT_RETRY symbol=%s reason=%s retry=%s max=%s",
                    symbol, reason, retries + 1, max_retries
                )
                # In a real system, we'd emit EVT:PROCESS_STRATEGY or signal re-eval here
                # For this step, we just track the metric/state as requested in Fix 7.
            elif self._cfg and hasattr(self._cfg, 'execution') and self._cfg.execution.gtx_fallback_to_market:
                self.mlog.warning(
                    "MD_AMR_GTX_FALLBACK symbol=%s max_retries=%s -> MARKET",
                    symbol, max_retries
                )
                # Fallback to market would be handled upstream by the signal intent
                self._gtx_retries[symbol] = 0
            else:
                self._gtx_retries[symbol] = 0

    def _rid(self, *, symbol: str, side: str, ts_ms: int, intent_kind: str) -> str:
        raw = f"{symbol}:{side}:{ts_ms}:{intent_kind}:md_amr"
        return f"mdamr-{hashlib.md5(raw.encode()).hexdigest()[:16]}"

    def _clear_defer(self, symbol: str) -> None:
        self._deferred.pop(symbol, None)

    def _register_defer(self, symbol: str, rid: str, missing_fields: list[str], now_ms: int) -> None:
        assert self._cfg is not None
        self._deferred[symbol] = {
            "rid": rid,
            "created_ts_ms": int(now_ms),
            "expires_ts_ms": int(now_ms + int(self._cfg.defer_ttl_sec) * 1000),
            "missing_fields": [str(x) for x in missing_fields],
        }
        self._log_runtime_marker(
            "MD_AMR_DEFER",
            symbol=symbol,
            rid=rid,
            missing_fields=[str(x) for x in missing_fields],
            defer_ttl_sec=int(self._cfg.defer_ttl_sec),
        )

    def _emit_feature_defer_expired(self, symbol: str, defer_state: Dict[str, Any], now_ms: int) -> None:
        assert self._cfg is not None
        payload = {
            "schema_version": 1,
            "strategy_id": "md_amr",
            "symbol": symbol,
            "rid": str(defer_state.get("rid") or f"mdamr-defer-{symbol}-{now_ms}"),
            "missing_fields": list(defer_state.get("missing_fields") or []),
            "defer_ttl_sec": int(self._cfg.defer_ttl_sec),
            "expired_at_ms": int(now_ms),
            "reason_code": "FEATURE_DEFER_EXPIRED",
        }
        self.fsm.emit("EVT:FEATURE_DEFER_EXPIRED", payload,
                      why="md_amr_feature_defer_expired")

    def _expire_defer_if_needed(self, symbol: str, now_ms: int) -> None:
        state = self._deferred.get(symbol)
        if not state:
            return
        expires = int(state.get("expires_ts_ms", 0) or 0)
        if expires > 0 and now_ms >= expires:
            self._emit_feature_defer_expired(symbol, state, now_ms)
            self._deferred.pop(symbol, None)

    def _on_process_strategy(self, event: Message) -> None:
        if not self._enabled:
            return
        pld = event.pld if hasattr(event, "pld") else event
        if not isinstance(pld, dict):
            return

        symbol = str(pld.get("symbol") or "")
        if symbol not in self._enabled_symbols:
            return
        tf_sec = pld.get("tf_sec")

        # TICK-BAR-SPLIT-FIX-3: explicit tf_sec guard with cooldown logging
        if tf_sec is None:
            self._log_tf_sec_reject(
                symbol, "process_strategy", "tf_sec_is_None")
            return
        try:
            tf_sec_int = int(tf_sec)
        except (TypeError, ValueError):
            self._log_tf_sec_reject(
                symbol, "process_strategy", f"tf_sec_invalid:{tf_sec!r}")
            return
        if tf_sec_int <= 0:
            self._log_tf_sec_reject(
                symbol, "process_strategy", f"tf_sec_non_positive:{tf_sec_int}")
            return

        if tf_sec_int != self.timeframe_sec:
            return

        bar_data = pld.get("bar")
        warmup = pld.get("warmup") if isinstance(
            pld.get("warmup"), dict) else {}
        if not isinstance(bar_data, dict):
            return

        bar_identity = extract_canonical_bar_identity(
            pld,
            default_symbol=symbol,
            default_timeframe_sec=int(tf_sec_int),
            default_source_mode=RuntimeBarSourceMode.LIVE,
        )
        replay_identity = extract_canonical_replay_identity(
            pld,
            default_symbol=symbol,
            default_timeframe_sec=int(tf_sec_int),
            default_source_mode=RuntimeBarSourceMode.LIVE,
        )
        gap_status = extract_gap_status(
            pld,
            default_source="market_data:payload_bridge",
            default_source_mode=RuntimeBarSourceMode.LIVE,
        )

        bar_close_ts = (
            int(bar_identity.bar_end_ts_ms)
            if bar_identity is not None
            else bar_data.get("end_ts_ms") or pld.get("bar_close_ts") or get_clock().now_ms()
        )
        try:
            bar_close_ts = int(bar_close_ts)
        except Exception:
            bar_close_ts = get_clock().now_ms()
        if self._is_duplicate_live_event(symbol, bar_close_ts):
            return

        # FIX:N-2 — Increment bars-seen counter for cold-start gate
        self._bars_seen_since_restart[symbol] = self._bars_seen_since_restart.get(
            symbol, 0) + 1

        if self._pending_close.get(symbol, False):
            self.mlog.debug(
                "MD_AMR_CLOSE_PENDING sym=%s, skip bar processing", symbol)
            return

        now_ms = get_clock().now_ms()
        self._expire_defer_if_needed(symbol, now_ms)

        features = pld.get("features", {}) if isinstance(
            pld.get("features"), dict) else {}
        sentiment_state = features.get("sentiment_state")
        llm_blocked = False
        if self._cfg and self._cfg.llm_gate.enabled:
            if sentiment_state is not None:
                try:
                    sent_val = float(sentiment_state)
                    if sent_val < float(self._cfg.llm_gate.sentiment_block_threshold):
                        self._macro_block_until_ms[symbol] = now_ms + \
                            int(self._cfg.llm_gate.block_ttl_sec) * 1000
                except Exception:
                    pass
            blocked_until = int(self._macro_block_until_ms.get(symbol, 0) or 0)
            llm_blocked = now_ms < blocked_until

        pos_qty = self._position_qty.get(symbol, Decimal("0"))
        if abs(pos_qty) > Decimal("1e-9"):
            self._bars_held[symbol] = int(self._bars_held.get(symbol, 0)) + 1
        else:
            self._bars_held[symbol] = 0

        strategy = self._strategies.get(symbol)
        if strategy is None:
            return

        should_ingest_bar = bar_close_ts > int(
            self._last_ingested_bar_ts_ms.get(symbol, 0) or 0)
        if should_ingest_bar:
            result = strategy.on_bar(
                bar=bar_data,
                position_ctx={"qty_signed": float(pos_qty), "bars_held": int(
                    self._bars_held.get(symbol, 0))},
                llm_blocked=llm_blocked,
            )
            self._last_ingested_bar_ts_ms[symbol] = int(bar_close_ts)
        else:
            result = {"status": "NOOP"}

        if self._is_mandatory_live_warmup_active(now_ms):
            if result.get("status") == "SIGNAL":
                signal = result.get("signal")
                if isinstance(signal, MDAMRSignal):
                    rid = self._rid(symbol=symbol, side=signal.side,
                                    ts_ms=bar_close_ts, intent_kind=signal.intent_kind)
                    self._emit_trade_intent_rejected_mandatory_warmup(
                        symbol=symbol,
                        side=signal.side,
                        rid=rid,
                        ts_ms=now_ms,
                    )
                    inc_warmup_block(domain="decision_making",
                                     reason="md_amr_mandatory_live_warmup")
            return

        if warmup.get("full_ready") is not True:
            self._log_runtime_marker(
                "MD_AMR_WARMUP_NOT_READY",
                symbol=symbol,
                bars_seen=self._bars_seen_since_restart.get(symbol, 0),
                warmup_full_ready=warmup.get("full_ready"),
            )
            rid = self._rid(symbol=symbol, side="BUY",
                            ts_ms=bar_close_ts, intent_kind="ENTRY")
            self._emit_trade_intent_rejected_gate(
                symbol=symbol,
                side="BUY",
                rid=rid,
                ts_ms=now_ms,
                reason_code="READINESS_WARMUP_NOT_OK",
                stage="READINESS",
                why="md_amr_handler:warmup_not_ready",
                why_chain=["READINESS", "warmup_not_ready"],
                details={"warmup": dict(warmup)},
            )
            inc_warmup_block(domain="decision_making",
                             reason="md_amr_warmup_not_ready")
            return

        # FIX:N-2 — Cold-start bars_required gate: block signal emission until
        # handler has received enough bars to produce meaningful features.
        _bars_seen = self._bars_seen_since_restart.get(symbol, 0)
        _basis_required = 0
        _readiness_contract_error: str | None = None
        _signal_required = self._core_signal_history_required_bars()
        try:
            from apps.reference.contracts.strategy_compatibility_matrix import (
                get_active_strategy_profile,
            )
            _profile = get_active_strategy_profile(self.config, "md_amr")
            if _profile is None:
                _readiness_contract_error = "READINESS_CONTRACT_UNRESOLVED:PROFILE_NOT_FOUND"
                _basis_required = 0
            else:
                _basis_required = int(_profile.basis_required_bars)
        except Exception as _exc:
            _readiness_contract_error = f"READINESS_CONTRACT_UNRESOLVED:{type(_exc).__name__}"
        if _bars_seen <= max(_basis_required, _signal_required):
            self._log_runtime_marker(
                "MD_AMR_BARS_PROGRESS",
                symbol=symbol,
                bars_seen=_bars_seen,
                basis_required_bars=_basis_required,
                signal_required_bars=_signal_required,
            )
        if _readiness_contract_error:
            self.mlog.error(
                "MD_AMR sym=%s READINESS_CONTRACT_UNRESOLVED — blocking: %s",
                symbol, _readiness_contract_error,
            )
            rid = self._rid(symbol=symbol, side="BUY",
                            ts_ms=bar_close_ts, intent_kind="ENTRY")
            self._emit_trade_intent_rejected_gate(
                symbol=symbol,
                side="BUY",
                rid=rid,
                ts_ms=now_ms,
                reason_code="READINESS_CONTRACT_UNRESOLVED",
                stage="READINESS",
                why="md_amr_handler:readiness_contract_unresolved",
                why_chain=["READINESS", "READINESS_CONTRACT_UNRESOLVED"],
                details={"error": _readiness_contract_error},
            )
            return
        if _basis_required and _bars_seen < _basis_required:
            self.mlog.info(
                "MD_AMR_BARS_REQUIRED sym=%s bars=%d/%d — blocking (quadratic/signal path NOT reached)",
                symbol, _bars_seen, _basis_required,
            )
            rid = self._rid(symbol=symbol, side="BUY",
                            ts_ms=bar_close_ts, intent_kind="ENTRY")
            self._emit_trade_intent_rejected_gate(
                symbol=symbol,
                side="BUY",
                rid=rid,
                ts_ms=now_ms,
                reason_code="BARS_REQUIRED_COLD_START",
                stage="STRATEGY",
                why=f"Cold-start: {_bars_seen}/{_basis_required} bars seen",
                why_chain=["READINESS", "BARS_REQUIRED",
                           f"bars_seen:{_bars_seen}",
                           f"basis_required:{_basis_required}"],
                details={"bars_seen": _bars_seen,
                         "basis_required_bars": _basis_required},
            )
            return

        if result.get("status") == "DEFER":
            rid = self._rid(symbol=symbol, side="BUY",
                            ts_ms=bar_close_ts, intent_kind="DEFER")
            self._register_defer(symbol, rid, list(result.get(
                "missing_fields") or ["feature_context"]), now_ms)
            return

        self._clear_defer(symbol)
        if symbol not in self._signal_ready_logged:
            self._signal_ready_logged.add(symbol)
            self._log_runtime_marker(
                "MD_AMR_SIGNAL_READY",
                symbol=symbol,
                bars_seen=_bars_seen,
                basis_required_bars=_basis_required,
                signal_required_bars=_signal_required,
                result_status=str(result.get("status") or "NOOP"),
            )

        if result.get("status") != "SIGNAL":
            return

        signal = result.get("signal")
        if not isinstance(signal, MDAMRSignal):
            return

        if signal.intent_kind == "ENTRY":
            asset_cfg = self._cfg.assets.get(symbol) if self._cfg else None
            if asset_cfg is None:
                rid = self._rid(symbol=symbol, side=signal.side,
                                ts_ms=bar_close_ts, intent_kind=signal.intent_kind)
                self._emit_trade_intent_rejected_gate(
                    symbol=symbol,
                    side=signal.side,
                    rid=rid,
                    ts_ms=now_ms,
                    reason_code="CONFIG_ASSET_MISSING",
                    stage="STRATEGY",
                    why="md_amr_handler:asset_config_missing",
                    why_chain=["CONFIG", "asset_config_missing"],
                    details={"symbol": symbol},
                )
                inc_decision_blocked(
                    stage="strategy", reason_code="CONFIG_ASSET_MISSING")
                return

            regime_allowed, regime_info = self._entry_regime_allowed(
                symbol=symbol,
                asset_cfg=asset_cfg,
            )
            if not regime_allowed:
                rid = self._rid(symbol=symbol, side=signal.side,
                                ts_ms=bar_close_ts, intent_kind=signal.intent_kind)
                self._emit_trade_intent_rejected_gate(
                    symbol=symbol,
                    side=signal.side,
                    rid=rid,
                    ts_ms=now_ms,
                    reason_code=str(regime_info.get(
                        "reason_code") or "REGIME_GATE_BLOCKED"),
                    stage="STRATEGY",
                    why=str(regime_info.get("why")
                            or "md_amr_handler:regime_gate_blocked"),
                    why_chain=list(regime_info.get("why_chain")
                                   or ["REGIME_GATE_BLOCKED"]),
                    details=dict(regime_info.get("details") or {}),
                )
                inc_decision_blocked(
                    stage="strategy", reason_code="REGIME_GATE_BLOCKED")
                self.mlog.info(
                    "MD_AMR_REGIME_GATE_BLOCKED %s",
                    json.dumps(regime_info.get("details") or {
                               "symbol": symbol}, ensure_ascii=False),
                )
                return

            cooldown_ms = (asset_cfg.cooldown_sec if asset_cfg else 60) * 1000
            if bar_close_ts - self._last_close_ts.get(symbol, 0) < cooldown_ms:
                rid = self._rid(symbol=symbol, side=signal.side,
                                ts_ms=bar_close_ts, intent_kind="DEFER")
                self._register_defer(
                    symbol, rid, ["anti_churn_cooldown"], now_ms)
                return

            if self._cfg and self._cfg.concentration_guard.enabled:
                entries_this_bar = self._entries_at_ts.get(bar_close_ts, 0)
                if entries_this_bar >= self._cfg.concentration_guard.max_simultaneous_entries_per_bar:
                    rid = self._rid(symbol=symbol, side=signal.side,
                                    ts_ms=bar_close_ts, intent_kind="DEFER")
                    self._register_defer(
                        symbol, rid, ["concentration_guard"], now_ms)
                    return
                self._entries_at_ts[bar_close_ts] = entries_this_bar + 1

        if signal.intent_kind in ("FULL_CLOSE", "PARTIAL_CLOSE"):
            self._pending_close[symbol] = True

        trace = dict(signal.trace)
        trace.setdefault("qty_base", abs(float(pos_qty))
                         if abs(pos_qty) > Decimal("1e-9") else 1.0)
        trace.setdefault("qty_new", trace.get("qty_base", 1.0))
        trace.setdefault("conf_ratio", float(signal.conf_ratio))

        rid = self._rid(symbol=symbol, side=signal.side,
                        ts_ms=bar_close_ts, intent_kind=signal.intent_kind)

        # MD-AMR-TPSL-01: Compute regime-based TP/SL for ENTRY signals only
        tpsl_result = None
        if str(signal.intent_kind) == "ENTRY":
            try:
                _entry_price = Decimal(str(signal.price_ref))
                _asset_cfg = self._cfg.assets.get(
                    symbol) if self._cfg else None
                _regime = self._regime.get(symbol, "DEFAULT")
                _side = str(signal.side).upper()
                tpsl_result = self._compute_tpsl(
                    symbol, _entry_price, _side, _regime, _asset_cfg)
            except Exception as _tpsl_err:
                self.logger.debug(
                    f"[{symbol}] MD-AMR-TPSL: computation error: {_tpsl_err}")

        # Objective Engine Integration
        if str(signal.intent_kind) == "ENTRY":
            domain_cfg = getattr(getattr(self.config, "domains", None),
                                 "objective_engine", None)
            strategy_cfg = getattr(
                self._cfg, "objective", None) if self._cfg else None
            try:
                from apps.reference.domains.objective_engine.adapters import (
                    build_behavior_input,
                    build_execution_input,
                    build_exposure_input,
                    build_market_input,
                    build_objective_input,
                    build_signal_input,
                    build_structure_input_from_prices,
                    compute_projected_order_notional,
                    compute_readiness_completeness,
                )
                from apps.reference.domains.objective_engine.engine import evaluate_objective

                if domain_cfg and strategy_cfg and domain_cfg.enabled and strategy_cfg.enabled:
                    cost_cfg = domain_cfg.components.get("cost")
                    behavior_cfg = domain_cfg.components.get("behavior")

                    if cost_cfg is None or not cost_cfg.enabled:
                        raise ValueError("OBJECTIVE_COMPONENT_MISSING:cost")
                    if behavior_cfg is None or not behavior_cfg.enabled:
                        raise ValueError(
                            "OBJECTIVE_COMPONENT_MISSING:behavior")
                    if not isinstance(self._latest_portfolio, dict):
                        raise ValueError("OBJECTIVE_PORTFOLIO_MISSING")
                    if not isinstance(self._latest_exposure_summary, dict):
                        raise ValueError("OBJECTIVE_EXPOSURE_SUMMARY_MISSING")

                    _regime = self._regime.get(symbol)
                    if not _regime:
                        raise ValueError("OBJECTIVE_REGIME_MISSING")
                    regime_ts_ms = int(self._regime_ts_ms.get(symbol, 0) or 0)
                    if regime_ts_ms <= 0:
                        raise ValueError("OBJECTIVE_REGIME_TS_MISSING")
                    regime_confidence = self._regime_confidence.get(symbol)
                    if regime_confidence is None:
                        raise ValueError("OBJECTIVE_REGIME_CONFIDENCE_MISSING")
                    if tpsl_result is None:
                        raise ValueError("OBJECTIVE_TPSL_MISSING")
                    if trace.get("thr_buy") is None or trace.get("thr_sell") is None:
                        raise ValueError("OBJECTIVE_TRACE_THRESHOLD_MISSING")

                    # Inject top-level atr from signal for objective engine
                    # (FE emits atr nested under features["volatility"]["atr_14"])
                    features.setdefault("atr", float(signal.atr))
                    objective_market = build_market_input(features=features)
                    signal_input = build_signal_input(
                        strategy_id="md_amr",
                        symbol=symbol,
                        signal_score=float(signal.signal_score),
                        signal_direction=1 if signal.side.upper() == "BUY" else -1,
                        regime=_regime,
                        regime_age_sec=max(0.0, float(
                            (now_ms - regime_ts_ms) / 1000.0)),
                        regime_confidence=float(regime_confidence),
                        readiness_completeness=compute_readiness_completeness(
                            warmup.get("ready", {}) if isinstance(
                                warmup.get("ready"), dict) else warmup
                        ),
                    )
                    structure_input = build_structure_input_from_prices(
                        signal_score=float(signal.signal_score),
                        active_threshold=float(
                            trace["thr_buy"] if signal.side.upper() == "BUY" else trace["thr_sell"]),
                        entry_price=Decimal(str(signal.price_ref)),
                        stop_price=Decimal(str(tpsl_result["stop_price"])),
                        target_price=Decimal(str(tpsl_result["target_price"])),
                        atr=Decimal(str(signal.atr)),
                    )
                    projected_notional_usd = compute_projected_order_notional(
                        symbol=symbol,
                        side=str(signal.side).upper(),
                        entry_price=Decimal(str(signal.price_ref)),
                        position_queries=self._position_queries,
                        portfolio=self._latest_portfolio,
                        features_payload=features,
                    )
                    exposure_input = build_exposure_input(
                        config=self.config,
                        portfolio=self._latest_portfolio,
                        exposure_summary=self._latest_exposure_summary,
                        projected_order_notional_usd=projected_notional_usd,
                    )
                    behavior_input = build_behavior_input(
                        now_ms=now_ms,
                        window_sec=float(
                            behavior_cfg.parameters["window_sec"]),
                        cancel_replace_ts_ms=self._objective_cancel_replace_ts_ms.setdefault(
                            symbol, deque()),
                        blocked_intent_ts_ms=self._objective_blocked_ts_ms.setdefault(
                            symbol, deque()),
                        reentry_ts_ms=self._objective_reentry_ts_ms.setdefault(
                            symbol, deque()),
                    )
                    execution_input = build_execution_input(
                        expected_fee_bps=float(
                            cost_cfg.parameters["base_fee_bps"]),
                        expected_slippage_bps=objective_market.spread_bps *
                        float(
                            cost_cfg.parameters["slippage_from_spread_ratio"]),
                    )
                    obj_input = build_objective_input(
                        signal=signal_input,
                        market=objective_market,
                        structure=structure_input,
                        exposure=exposure_input,
                        behavior=behavior_input,
                        execution=execution_input,
                    )
                    obj_score = evaluate_objective(
                        obj_input, domain_cfg, strategy_cfg)

                    if obj_score.is_blocked:
                        self._emit_trade_intent_rejected_gate(
                            symbol=symbol,
                            side=signal.side,
                            rid=rid,
                            ts_ms=now_ms,
                            reason_code="OBJECTIVE_GATE_BLOCKED",
                            stage="STRATEGY",
                            why=str(
                                obj_score.block_reason or "OBJECTIVE_ENGINE_BLOCKED"),
                            why_chain=["OBJECTIVE_ENGINE",
                                       str(obj_score.block_reason)],
                            details={
                                "objective_score": obj_score.objective_score}
                        )
                        inc_decision_blocked(
                            stage="strategy", reason_code="OBJECTIVE_GATE_BLOCKED")
                        return

                    # MDAMRSignal is frozen; replace it so trace and payload stay aligned.
                    signal = replace(
                        signal,
                        conf_ratio=float(signal.conf_ratio) *
                        obj_score.multiplier,
                        signal_score=obj_score.objective_score,
                    )

                    trace["conf_ratio"] = float(signal.conf_ratio)
                    trace["objective"] = obj_score.trace.model_dump()

            except Exception as e:
                if domain_cfg and getattr(domain_cfg.data_requirements, "strict_fail_closed", True):
                    self._emit_trade_intent_rejected_gate(
                        symbol=symbol,
                        side=signal.side,
                        rid=rid,
                        ts_ms=now_ms,
                        reason_code="OBJECTIVE_ENGINE_FAIL_CLOSED",
                        stage="STRATEGY",
                        why=str(e),
                        why_chain=["OBJECTIVE_ENGINE", "FAIL_CLOSED"],
                        details={"error": str(e)}
                    )
                    inc_decision_blocked(
                        stage="strategy", reason_code="OBJECTIVE_ENGINE_FAIL_CLOSED")
                    return

        payload = {
            "schema_version": 1,
            "strategy_id": "md_amr",
            "symbol": symbol,
            "tf_sec": int(self.timeframe_sec),
            "side": str(signal.side).upper(),
            "intent_kind": str(signal.intent_kind),
            "exit_reason_code": str(signal.reason_code) if signal.intent_kind != "ENTRY" else None,
            "scaleout_fraction": float(signal.scaleout_fraction) if signal.scaleout_fraction is not None else None,
            "bar_close_ts": int(bar_close_ts),
            "readiness": {"warmup_ok": True},
            "score": float(abs(signal.signal_score)),
            "why": str(signal.reason_code),
            "why_chain": [str(signal.reason_code)],
            "ts_ms": int(bar_close_ts),
            "rid": rid,
            "source_mode": (
                bar_identity.source_mode.value
                if bar_identity is not None
                else str(pld.get("source_mode") or RuntimeBarSourceMode.LIVE.value)
            ),
            "price_ctx": {
                "entry_price": str(signal.price_ref),
                "price_ref": str(signal.price_ref),
            },
            "regime": self._regime.get(symbol, "UNKNOWN"),
            "volatility": {"atr_14": float(signal.atr), "atr_ready": True},
            "liquidity": self._extract_liquidity(features),
            "dir_score": float(signal.dir_score),
            "channel_state": dict(signal.channel_state),
            "trace": trace,
            "scoring": {
                "score": float(abs(signal.signal_score)),
                "objective": trace.get("objective"),
                "regime": self._regime.get(symbol, "UNKNOWN"),
            },
        }
        if bar_identity is not None:
            payload["bar_identity"] = bar_identity.to_payload()
            payload["close_boundary_ts_ms"] = int(
                bar_identity.close_boundary_ts_ms)
        if replay_identity is not None:
            payload["replay_identity"] = replay_identity.to_payload()
            payload["replay_generation"] = int(
                replay_identity.replay_generation)
        restore_snapshot = self.get_runtime_analytics_restore_snapshot(symbol)
        base_can_open_new_risk = str(signal.intent_kind) == "ENTRY"
        base_runtime_permissions = make_permissions(
            can_manage_existing_risk=True,
            can_open_new_risk=base_can_open_new_risk and not gap_blocks_open_new_risk(
                gap_status),
        )
        runtime_permissions = combine_restore_permissions_live_first(
            base_runtime_permissions,
            restore_snapshot,
        )
        blocking_reason_chain = list(gap_blocking_tokens(gap_status)) + list(
            restore_execution_blocking_tokens(restore_snapshot)
        )
        blocking_reason_chain = list(dict.fromkeys(blocking_reason_chain))
        if runtime_permissions.can_manage_existing_risk and (not runtime_permissions.can_open_new_risk):
            blocking_reason_chain.append("protect_only")
            blocking_reason_chain = list(dict.fromkeys(blocking_reason_chain))
        runtime_scopes = {
            RuntimeReadinessScope.BASIS_BAR_READY.value: build_basis_bar_status_from_gap(
                gap_status,
                updated_at=int(bar_close_ts),
                source="market_data:payload_bridge",
                evidence_ref=(bar_identity.to_ref()
                              if bar_identity is not None else None),
            ),
            RuntimeReadinessScope.MICROSTRUCTURE_READY.value: (
                ready_status(
                    why=["fe_warmup_full_ready"],
                    updated_at=int(bar_close_ts),
                    source="feature_engineering:payload_bridge",
                    evidence_ref=f"warmup:{symbol}:{int(bar_close_ts)}",
                )
                if warmup.get("full_ready") is True
                else cold_status(
                    why=["fe_warmup_not_ready"],
                    updated_at=int(bar_close_ts),
                    source="feature_engineering:payload_bridge",
                    evidence_ref=f"warmup:{symbol}:{int(bar_close_ts)}",
                )
            ),
            RuntimeReadinessScope.STRATEGY_READY_PER_SYMBOL.value: ready_status(
                why=[f"signal_emitted:{str(signal.intent_kind).lower()}"],
                updated_at=int(bar_close_ts),
                source="decision_making:md_amr",
                evidence_ref=rid,
            ),
            RuntimeReadinessScope.TRADING_READY.value: build_trading_status_from_gap(
                gap_status,
                updated_at=int(bar_close_ts),
                source="decision_making:md_amr",
                evidence_ref=rid,
                allow_open_new_risk=runtime_permissions.can_open_new_risk,
                open_ready_why=["open_new_risk_allowed"],
                blocked_why=blocking_reason_chain,
            ),
        }
        runtime_scopes[RuntimeReadinessScope.REGIME_READY.value] = (
            ready_status(
                why=["regime_heartbeat_present"],
                updated_at=int(self._regime_ts_ms.get(
                    symbol, bar_close_ts) or bar_close_ts),
                source="regime_detector:payload_bridge",
                evidence_ref=f"regime:{symbol}:{int(self._regime_ts_ms.get(symbol, bar_close_ts) or bar_close_ts)}",
            )
            if self._regime.get(symbol) and int(self._regime_ts_ms.get(symbol, 0) or 0) > 0
            else partial_status(
                why=["regime_heartbeat_missing"],
                updated_at=int(bar_close_ts),
                source="regime_detector:payload_bridge",
                evidence_ref=f"regime:{symbol}:{int(bar_close_ts)}",
            )
        )
        if restore_snapshot is not None:
            runtime_scopes[RuntimeReadinessScope.EXECUTION_CONTEXT_READY.value] = restore_status_to_readiness_status(
                lookup_restore_status(
                    restore_snapshot,
                    RuntimeAnalyticsRestoreScope.EXECUTION_STATE,
                ),
                updated_at=int(bar_close_ts),
                source="execution_position:startup_restore",
                evidence_ref=rid,
            )
            runtime_scopes[RuntimeReadinessScope.MICROSTRUCTURE_READY.value] = merge_restore_readiness_live_first(
                lookup_restore_status(
                    restore_snapshot,
                    RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_CACHE,
                ),
                live_status=runtime_scopes[RuntimeReadinessScope.MICROSTRUCTURE_READY.value],
                updated_at=int(bar_close_ts),
                source="feature_engineering:startup_restore",
                evidence_ref=rid,
                live_evidence_present=True,
            )
            runtime_scopes[RuntimeReadinessScope.REGIME_READY.value] = merge_restore_readiness_live_first(
                lookup_restore_status(
                    restore_snapshot,
                    RuntimeAnalyticsRestoreScope.REGIME_DETECTOR_STATE,
                ),
                live_status=runtime_scopes[RuntimeReadinessScope.REGIME_READY.value],
                updated_at=int(bar_close_ts),
                source="regime_detector:startup_restore",
                evidence_ref=rid,
                live_evidence_present=True,
            )
            runtime_scopes[RuntimeReadinessScope.STRATEGY_READY_PER_SYMBOL.value] = merge_restore_readiness_live_first(
                lookup_restore_status(
                    restore_snapshot,
                    RuntimeAnalyticsRestoreScope.STRATEGY_LOCAL_STATE,
                ),
                live_status=runtime_scopes[RuntimeReadinessScope.STRATEGY_READY_PER_SYMBOL.value],
                updated_at=int(bar_close_ts),
                source="decision_making:md_amr",
                evidence_ref=rid,
                restored_why=[
                    f"signal_emitted:{str(signal.intent_kind).lower()}"],
                live_evidence_present=True,
            )
            runtime_scopes[RuntimeReadinessScope.TRADING_READY.value] = build_trading_status_from_gap(
                gap_status,
                updated_at=int(bar_close_ts),
                source="decision_making:md_amr",
                evidence_ref=rid,
                allow_open_new_risk=runtime_permissions.can_open_new_risk,
                open_ready_why=["open_new_risk_allowed"],
                blocked_why=blocking_reason_chain,
            )
        runtime_permissions = apply_startup_warmup_permission_overlay(
            runtime_permissions,
        )
        blocking_reason_chain.extend(startup_warmup_gate_tokens())
        blocking_reason_chain = list(dict.fromkeys(blocking_reason_chain))
        runtime_scopes[RuntimeReadinessScope.TRADING_READY.value] = build_trading_status_from_gap(
            gap_status,
            updated_at=int(bar_close_ts),
            source="decision_making:md_amr",
            evidence_ref=rid,
            allow_open_new_risk=runtime_permissions.can_open_new_risk,
            open_ready_why=["open_new_risk_allowed"],
            blocked_why=blocking_reason_chain,
        )
        if runtime_permissions.can_manage_existing_risk and (not runtime_permissions.can_open_new_risk):
            blocking_reason_chain.append("protect_only")
            blocking_reason_chain = list(dict.fromkeys(blocking_reason_chain))
            runtime_scopes[RuntimeReadinessScope.TRADING_READY.value] = build_trading_status_from_gap(
                gap_status,
                updated_at=int(bar_close_ts),
                source="decision_making:md_amr",
                evidence_ref=rid,
                allow_open_new_risk=runtime_permissions.can_open_new_risk,
                open_ready_why=["open_new_risk_allowed"],
                blocked_why=blocking_reason_chain,
            )
        runtime_snapshot = make_snapshot(
            strategy_id="md_amr",
            symbol=symbol,
            updated_at=int(bar_close_ts),
            scopes=runtime_scopes,
            source="decision_making:md_amr",
            permissions=runtime_permissions,
            blocking_reason_chain=blocking_reason_chain,
        )
        payload["runtime_permissions"] = runtime_permissions.to_payload()
        payload["runtime_readiness"] = runtime_snapshot.to_payload()
        if gap_status is not None:
            attach_gap_status_payload(
                payload, gap=gap_status, attach_nested_bar=False)
        if restore_snapshot is not None:
            payload["analytics_restore"] = restore_snapshot.to_payload()

        # MD-AMR-TPSL-01: Inject TP/SL into price_ctx (same contract as aurora handler)
        if tpsl_result is not None:
            payload["price_ctx"]["stop_price"] = str(tpsl_result["stop_price"])
            payload["price_ctx"]["target_price"] = str(
                tpsl_result["target_price"])
            payload["tpsl_ctx"] = tpsl_result["tpsl_ctx"]
            _ctx = tpsl_result["tpsl_ctx"]
            payload["why_chain"].append(
                f"tpsl:regime={_ctx['regime_used']} sl_pct={_ctx['sl_pct_eff']:.4f} rr={_ctx['tp_rr_eff']:.2f}"
            )
            self.logger.info(
                f"[{symbol}] MD-AMR-TPSL: stop={tpsl_result['stop_price']:.6f} "
                f"target={tpsl_result['target_price']:.6f} regime={_ctx['regime_used']}"
            )

        self.fsm.emit(
            "EVT:STRATEGY_SIGNAL_PRODUCED",
            payload=payload,
            why=f"strategy_signal:md_amr:{signal.intent_kind}",
            data_ref=[f"md_amr_{rid}"],
        )
        self._log_runtime_marker(
            "MD_AMR_SIGNAL_EMITTED",
            symbol=symbol,
            rid=rid,
            intent_kind=str(signal.intent_kind),
            side=str(signal.side).upper(),
            reason_code=str(signal.reason_code),
            bars_seen=_bars_seen,
        )
        self.mlog.info(
            "MD_AMR_SIGNAL %s",
            json.dumps(
                {
                    "symbol": symbol,
                    "intent_kind": signal.intent_kind,
                    "side": signal.side,
                    "reason_code": signal.reason_code,
                    "conf_ratio": signal.conf_ratio,
                    "rid": rid,
                    "trace": trace,
                },
                ensure_ascii=False,
            ),
        )

    @staticmethod
    def _extract_liquidity(features: Dict[str, Any]) -> Dict[str, Any]:
        liq = features.get("liquidity")
        if isinstance(liq, dict):
            return liq
        res = {}
        if "obi_close" in features:
            res["obi_close"] = features.get("obi_close")
        return res

    # -------------------------------------------------------------------------
    # MD-AMR-TPSL-01: Regime-based TP/SL computation
    # -------------------------------------------------------------------------

    def _compute_tpsl(
        self,
        symbol: str,
        entry_price: Decimal,
        side: str,
        regime: str,
        asset_cfg: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        MD-AMR-TPSL-01: Compute regime-based TP/SL for ENTRY signals (pct_mult mode).

        Formula:
          sl_pct_eff   = exit.sl_pct  × sl_mult[regime]
          tp_dist_pct  = sl_pct_eff   × exit.tp_rr × tp_mult[regime]
          BUY:  stop = entry × (1 − sl_pct_eff),  target = entry × (1 + tp_dist_pct)
          SELL: stop = entry × (1 + sl_pct_eff),  target = entry × (1 − tp_dist_pct)

        Returns dict with stop_price, target_price, tpsl_ctx — or None if config absent/disabled.
        fail-open: exceptions are caught by caller.
        """
        import decimal as _dec
        if asset_cfg is None:
            return None
        exit_cfg = getattr(asset_cfg, "exit", None)
        if exit_cfg is None:
            return None
        tpsl_cfg = getattr(exit_cfg, "regime_tpsl", None)
        if tpsl_cfg is None or not getattr(tpsl_cfg, "enabled", False):
            return None

        sl_pct_raw = getattr(exit_cfg, "sl_pct", None)
        tp_rr_raw = getattr(exit_cfg, "tp_rr",  None)
        if sl_pct_raw is None or tp_rr_raw is None:
            self.logger.error(
                f"[{symbol}] MD-AMR-TPSL: exit.sl_pct and exit.tp_rr are required"
            )
            return None

        sl_pct_base = float(sl_pct_raw)
        tp_rr_base = float(tp_rr_raw)

        sl_mult_map = dict(getattr(tpsl_cfg, "sl_mult", None) or {})
        tp_mult_map = dict(getattr(tpsl_cfg, "tp_mult", None) or {})

        regime_used = regime if regime not in (
            "UNKNOWN", "", None) else "DEFAULT"
        sl_mult = float(sl_mult_map.get(
            regime_used, sl_mult_map.get("DEFAULT", 1.0)))
        tp_mult = float(tp_mult_map.get(
            regime_used, tp_mult_map.get("DEFAULT", 1.0)))

        sl_pct_eff = sl_pct_base * sl_mult
        tp_rr_eff = tp_rr_base * tp_mult

        sl_dec = _dec.Decimal(str(sl_pct_eff))
        tp_dist_dec = sl_dec * _dec.Decimal(str(tp_rr_eff))

        if side.upper() == "BUY":
            stop_price = entry_price * (1 - sl_dec)
            target_price = entry_price * (1 + tp_dist_dec)
        elif side.upper() == "SELL":
            stop_price = entry_price * (1 + sl_dec)
            target_price = entry_price * (1 - tp_dist_dec)
        else:
            return None

        result = {
            "stop_price":   stop_price,
            "target_price": target_price,
            "tpsl_ctx": {
                "mode":        "pct_mult",
                "regime_used": regime_used,
                "sl_pct_base": sl_pct_base,
                "sl_mult":     sl_mult,
                "sl_pct_eff":  sl_pct_eff,
                "tp_rr_base":  tp_rr_base,
                "tp_mult":     tp_mult,
                "tp_rr_eff":   tp_rr_eff,
            },
        }
        return self._apply_tpsl_guardrails(symbol, entry_price, side, result, tpsl_cfg)

    def _apply_tpsl_guardrails(
        self,
        symbol: str,
        entry_price: Decimal,
        side: str,
        result: Dict[str, Any],
        tpsl_cfg: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        MD-AMR-TPSL-01: Apply guardrails to computed TP/SL.
        Clamps SL% and TP RR to configured min/max.
        Fail-closed on wrong-side or min_dist_bps violations.
        """
        import decimal as _dec
        stop_price = result["stop_price"]
        target_price = result["target_price"]
        tpsl_ctx = result["tpsl_ctx"]

        min_sl_pct = _dec.Decimal(
            str(getattr(tpsl_cfg, "min_sl_pct",   0.003)))
        max_sl_pct = _dec.Decimal(
            str(getattr(tpsl_cfg, "max_sl_pct",   0.060)))
        min_tp_rr = _dec.Decimal(str(getattr(tpsl_cfg, "min_tp_rr",    0.3)))
        max_tp_rr = _dec.Decimal(str(getattr(tpsl_cfg, "max_tp_rr",    3.0)))
        min_dist_bps = int(getattr(tpsl_cfg, "min_dist_bps", 15))

        if side.upper() == "BUY":
            sl_dist_pct = (entry_price - stop_price) / entry_price
            tp_dist_pct = (target_price - entry_price) / entry_price
        else:
            sl_dist_pct = (stop_price - entry_price) / entry_price
            tp_dist_pct = (entry_price - target_price) / entry_price

        # Fail-closed: wrong side
        if sl_dist_pct <= 0:
            self.logger.error(
                f"[{symbol}] MD-AMR-TPSL: SL on wrong side, aborting")
            return None
        if tp_dist_pct <= 0:
            self.logger.error(
                f"[{symbol}] MD-AMR-TPSL: TP on wrong side, aborting")
            return None

        # Clamp SL
        if sl_dist_pct < min_sl_pct:
            self.logger.warning(
                f"[{symbol}] MD-AMR-TPSL: SL clamped up to min_sl_pct")
            sl_dist_pct = min_sl_pct
            stop_price = entry_price * (1 - sl_dist_pct) if side.upper() == "BUY" \
                else entry_price * (1 + sl_dist_pct)
            tpsl_ctx["guardrail_sl_clamp"] = "min"
        elif sl_dist_pct > max_sl_pct:
            self.logger.warning(
                f"[{symbol}] MD-AMR-TPSL: SL clamped down to max_sl_pct")
            sl_dist_pct = max_sl_pct
            stop_price = entry_price * (1 - sl_dist_pct) if side.upper() == "BUY" \
                else entry_price * (1 + sl_dist_pct)
            tpsl_ctx["guardrail_sl_clamp"] = "max"

        # Clamp TP RR
        actual_rr = tp_dist_pct / \
            sl_dist_pct if sl_dist_pct > 0 else _dec.Decimal("0")
        if actual_rr < min_tp_rr:
            self.logger.warning(
                f"[{symbol}] MD-AMR-TPSL: TP RR clamped up to min_tp_rr")
            tp_dist_pct = sl_dist_pct * min_tp_rr
            target_price = entry_price * (1 + tp_dist_pct) if side.upper() == "BUY" \
                else entry_price * (1 - tp_dist_pct)
            tpsl_ctx["guardrail_tp_clamp"] = "min"
        elif actual_rr > max_tp_rr:
            self.logger.warning(
                f"[{symbol}] MD-AMR-TPSL: TP RR clamped down to max_tp_rr")
            tp_dist_pct = sl_dist_pct * max_tp_rr
            target_price = entry_price * (1 + tp_dist_pct) if side.upper() == "BUY" \
                else entry_price * (1 - tp_dist_pct)
            tpsl_ctx["guardrail_tp_clamp"] = "max"

        # Fail-closed: min distance in bps
        min_dist = entry_price * \
            _dec.Decimal(str(min_dist_bps)) / _dec.Decimal("10000")
        if abs(entry_price - stop_price) < min_dist or abs(entry_price - target_price) < min_dist:
            self.logger.error(
                f"[{symbol}] MD-AMR-TPSL: SL or TP below min_dist_bps={min_dist_bps}, aborting"
            )
            return None

        tpsl_ctx["sl_pct_post"] = float(sl_dist_pct)
        tpsl_ctx["rr_post"] = float(actual_rr)
        return {"stop_price": stop_price, "target_price": target_price, "tpsl_ctx": tpsl_ctx}
