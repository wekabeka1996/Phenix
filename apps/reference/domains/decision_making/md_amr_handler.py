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
from decimal import Decimal
from typing import Any, Dict, Optional, TYPE_CHECKING

from vfoundation.core.protocol import Message
from apps.reference.core.time import get_clock
from apps.reference.domains.feature_engineering.md_amr_strategy import MDAMRStrategyV11, MDAMRSignal
from apps.reference.config_models import AuroraConfig, MDAMRStrategyConfig
from apps.reference.utils import get_domain_mode_from_mapping

if TYPE_CHECKING:
    from vfoundation.core import FSMCore

LOG = logging.getLogger(__name__)


class MDAMRHandler:
    """Event-driven handler for strategy_id=md_amr."""

    _REST_HYDRATION_LIMIT = 100
    _MANDATORY_LIVE_WARMUP_SEC = 7200

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
        self._rest_hydrated = False
        self._rest_last_bar_ts_ms: Dict[str, int] = {}
        self._last_ingested_bar_ts_ms: Dict[str, int] = {}
        self._pending_close: dict[str, bool] = {}
        self._last_close_ts: dict[str, int] = {}
        self._gtx_retries: dict[str, int] = {}
        self._entries_at_ts: Dict[int, int] = {}
        self.mandatory_warmup_until = 0

        self._parse_config()
        if self._enabled:
            self._init_strategies()

    @property
    def timeframe_sec(self) -> int:
        return int(self._cfg.timeframe_sec) if self._cfg is not None else 900

    def register(self) -> None:
        if not self._enabled:
            return
        self._hydrate_state_from_rest()
        self.fsm.listen("CMD:PROCESS_STRATEGY", self._on_process_strategy)
        self.fsm.listen("EVT:FEATURES_CALCULATED", self._on_features_calculated)
        self.fsm.listen("EVT:REGIME_DETECTED", self._on_regime_detected)
        self.fsm.listen("EVT:TRADE_EXECUTED", self._on_trade_executed)
        self.fsm.listen("EVT:ORDER_REJECTED", self._on_order_rejected)
        self.logger.info(
            "MD_AMR registered events=%s symbols=%s tf=%s",
            ["CMD:PROCESS_STRATEGY", "EVT:FEATURES_CALCULATED", "EVT:REGIME_DETECTED", "EVT:TRADE_EXECUTED"],
            sorted(self._enabled_symbols),
            self.timeframe_sec,
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
        md_domain = self.fsm.get_domain("market_data") if hasattr(self.fsm, "get_domain") else None
        adapter = getattr(md_domain, "adapter", None) if md_domain is not None else None
        if adapter is not None and hasattr(adapter, "get_klines"):
            return adapter, False

        from apps.reference.adapters.binance_adapter import BinanceAdapter

        mode = str(get_domain_mode_from_mapping(self.config, "market_data")).lower()
        api_env = self.config.binance_api.live if mode == "live" else self.config.binance_api.testnet
        api_key = str(api_env.api_key or "")
        api_secret = str(api_env.api_secret or "")
        rest_url = str(api_env.rest_url or "")
        if not rest_url:
            raise RuntimeError("REST hydration failed: binance_api.rest_url is empty")
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

    def _hydrate_state_from_rest(self) -> None:
        interval = self._interval_for_tf(self.timeframe_sec)
        now_ms = get_clock().now_ms()
        if interval is None:
            self.logger.warning("MD_AMR hydration skipped: unsupported timeframe_sec=%s", self.timeframe_sec)
            self.mandatory_warmup_until = int(now_ms + self._MANDATORY_LIVE_WARMUP_SEC * 1000)
            return

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
                    raw_klines = self._run_coro_blocking(
                        adapter.get_klines(
                            symbol=symbol,
                            interval=interval,
                            limit=int(self._REST_HYDRATION_LIMIT),
                        )
                    )
                except Exception as exc:
                    self.logger.warning("MD_AMR hydration klines fetch failed symbol=%s err=%s", symbol, exc)
                    continue

                if not isinstance(raw_klines, list) or not raw_klines:
                    self.logger.warning("MD_AMR hydration empty klines symbol=%s", symbol)
                    continue

                bars: list[Dict[str, Any]] = []
                for row in raw_klines:
                    bar = self._kline_to_bar(row)
                    if bar is not None:
                        bars.append(bar)
                bars.sort(key=lambda b: int(b["end_ts_ms"]))
                if not bars:
                    self.logger.warning("MD_AMR hydration produced no valid bars symbol=%s", symbol)
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
        except Exception as exc:
            self.logger.warning("MD_AMR hydration failed: %s", exc)
        finally:
            if temporary_adapter and adapter is not None:
                self._close_temp_adapter(adapter)

        self._rest_hydrated = hydrated_symbols > 0
        self.mandatory_warmup_until = int(get_clock().now_ms() + self._MANDATORY_LIVE_WARMUP_SEC * 1000)
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

        for symbol, asset_cfg in cfg.assets.items():
            if bool(asset_cfg.enabled):
                self._enabled_symbols.add(str(symbol))

        self._enabled_symbols = self._enabled_symbols.intersection(assigned) if assigned else self._enabled_symbols
        self._enabled = bool(cfg.enabled) and bool(self._enabled_symbols)

        self.mlog.info(
            "MD_AMR_INIT %s",
            json.dumps(
                {
                    "strategy_id": "md_amr",
                    "enabled": self._enabled,
                    "enabled_symbols": sorted(self._enabled_symbols),
                    "timeframe_sec": self.timeframe_sec,
                    "defer_ttl_sec": int(cfg.defer_ttl_sec),
                },
                ensure_ascii=False,
            ),
            )

    def _init_strategies(self) -> None:
        assert self._cfg is not None
        for symbol in self._enabled_symbols:
            self._strategies[symbol] = MDAMRStrategyV11(
                channel_window_bars=int(self._cfg.channel_window_bars),
                hysteresis_mult=float(self._cfg.hysteresis_mult),
                threshold_z=float(self._cfg.threshold_z),
                volatility_dampening_factor=float(self._cfg.volatility_dampening_factor),
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
        try:
            tf_sec_int = int(tf_sec)
        except Exception:
            return
        if tf_sec_int != self.timeframe_sec:
            return
        event_ts_ms = self._extract_event_ts_ms(pld)
        if self._is_duplicate_live_event(symbol, event_ts_ms):
            return

        self._last_features[symbol] = pld.get("features", {}) if isinstance(pld.get("features"), dict) else {}

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
            position_ctx={"qty_signed": float(pos_qty), "bars_held": int(self._bars_held.get(symbol, 0))},
            llm_blocked=False,
        )
        self._last_ingested_bar_ts_ms[symbol] = int(close_ts_ms)

    def _on_regime_detected(self, event: Message) -> None:
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return
        symbol = str(pld.get("symbol") or "")
        if symbol not in self._enabled_symbols:
            return
        regime = pld.get("regime") or pld.get("overall_regime")
        if regime:
            self._regime[symbol] = str(regime)

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
        if abs(now) < Decimal("1e-9"):
            now = Decimal("0")
            self._bars_held[symbol] = 0
            self._pending_close[symbol] = False
            self._last_close_ts[symbol] = get_clock().now_ms()
        self._position_qty[symbol] = now

    def reconcile_position(self, symbol: str, exchange_qty: Decimal) -> None:
        cfg = self._cfg
        if cfg and not cfg.reconciliation.enabled:
            return
        tolerance = Decimal(str(cfg.reconciliation.drift_tolerance)) if cfg else Decimal("1e-6")
        local_qty = self._position_qty.get(symbol, Decimal("0"))
        if abs(local_qty - exchange_qty) > tolerance:
            self.mlog.warning(
                "MD_AMR_POSITION_DRIFT symbol=%s local=%s exchange=%s",
                symbol, local_qty, exchange_qty,
            )
            self._position_qty[symbol] = exchange_qty
            if abs(exchange_qty) < tolerance:
                self._bars_held[symbol] = 0

    def _on_order_rejected(self, event: Message) -> None:
        pld = event.pld or {}
        if not isinstance(pld, dict):
            return
        symbol = str(pld.get("symbol") or "")
        if symbol not in self._enabled_symbols:
            return

        # Simple retry logic tracking mechanism for GTX Rejects
        reason = str(pld.get("reject_reason", "")).upper()
        if "MAKER_ONLY" in reason or "POST_ONLY" in reason:
            retries = self._gtx_retries.get(symbol, 0)
            max_retries = self._cfg.execution.gtx_retry_max if self._cfg and hasattr(self._cfg, 'execution') else 0
            
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
        self.fsm.emit("EVT:FEATURE_DEFER_EXPIRED", payload, why="md_amr_feature_defer_expired")

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
        try:
            tf_sec_int = int(tf_sec)
        except Exception:
            return
        if tf_sec_int != self.timeframe_sec:
            return

        bar_data = pld.get("bar")
        warmup = pld.get("warmup") if isinstance(pld.get("warmup"), dict) else {}
        if not isinstance(bar_data, dict):
            return

        bar_close_ts = bar_data.get("end_ts_ms") or pld.get("bar_close_ts") or get_clock().now_ms()
        try:
            bar_close_ts = int(bar_close_ts)
        except Exception:
            bar_close_ts = get_clock().now_ms()
        if self._is_duplicate_live_event(symbol, bar_close_ts):
            return

        if self._pending_close.get(symbol, False):
            self.mlog.debug("MD_AMR_CLOSE_PENDING sym=%s, skip bar processing", symbol)
            return

        now_ms = get_clock().now_ms()
        self._expire_defer_if_needed(symbol, now_ms)

        features = pld.get("features", {}) if isinstance(pld.get("features"), dict) else {}
        sentiment_state = features.get("sentiment_state")
        llm_blocked = False
        if self._cfg and self._cfg.llm_gate.enabled:
            if sentiment_state is not None:
                try:
                    sent_val = float(sentiment_state)
                    if sent_val < float(self._cfg.llm_gate.sentiment_block_threshold):
                        self._macro_block_until_ms[symbol] = now_ms + int(self._cfg.llm_gate.block_ttl_sec) * 1000
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

        should_ingest_bar = bar_close_ts > int(self._last_ingested_bar_ts_ms.get(symbol, 0) or 0)
        if should_ingest_bar:
            result = strategy.on_bar(
                bar=bar_data,
                position_ctx={"qty_signed": float(pos_qty), "bars_held": int(self._bars_held.get(symbol, 0))},
                llm_blocked=llm_blocked,
            )
            self._last_ingested_bar_ts_ms[symbol] = int(bar_close_ts)
        else:
            result = {"status": "NOOP"}

        if self._is_mandatory_live_warmup_active(now_ms):
            if result.get("status") == "SIGNAL":
                signal = result.get("signal")
                if isinstance(signal, MDAMRSignal):
                    rid = self._rid(symbol=symbol, side=signal.side, ts_ms=bar_close_ts, intent_kind=signal.intent_kind)
                    self._emit_trade_intent_rejected_mandatory_warmup(
                        symbol=symbol,
                        side=signal.side,
                        rid=rid,
                        ts_ms=now_ms,
                    )
            return

        if warmup.get("full_ready") is not True:
            rid = self._rid(symbol=symbol, side="BUY", ts_ms=bar_close_ts, intent_kind="DEFER")
            self._register_defer(symbol, rid, ["warmup.full_ready"], now_ms)
            return

        if result.get("status") == "DEFER":
            rid = self._rid(symbol=symbol, side="BUY", ts_ms=bar_close_ts, intent_kind="DEFER")
            self._register_defer(symbol, rid, list(result.get("missing_fields") or ["feature_context"]), now_ms)
            return

        self._clear_defer(symbol)

        if result.get("status") != "SIGNAL":
            return

        signal = result.get("signal")
        if not isinstance(signal, MDAMRSignal):
            return

        if signal.intent_kind == "ENTRY":
            asset_cfg = self._cfg.assets.get(symbol) if self._cfg else None
            cooldown_ms = (asset_cfg.cooldown_sec if asset_cfg else 60) * 1000
            if bar_close_ts - self._last_close_ts.get(symbol, 0) < cooldown_ms:
                rid = self._rid(symbol=symbol, side=signal.side, ts_ms=bar_close_ts, intent_kind="DEFER")
                self._register_defer(symbol, rid, ["anti_churn_cooldown"], now_ms)
                return

            if self._cfg and self._cfg.concentration_guard.enabled:
                entries_this_bar = self._entries_at_ts.get(bar_close_ts, 0)
                if entries_this_bar >= self._cfg.concentration_guard.max_simultaneous_entries_per_bar:
                    rid = self._rid(symbol=symbol, side=signal.side, ts_ms=bar_close_ts, intent_kind="DEFER")
                    self._register_defer(symbol, rid, ["concentration_guard"], now_ms)
                    return
                self._entries_at_ts[bar_close_ts] = entries_this_bar + 1

        if signal.intent_kind in ("FULL_CLOSE", "PARTIAL_CLOSE"):
            self._pending_close[symbol] = True

        trace = dict(signal.trace)
        trace.setdefault("qty_base", abs(float(pos_qty)) if abs(pos_qty) > Decimal("1e-9") else 1.0)
        trace.setdefault("qty_new", trace.get("qty_base", 1.0))
        trace.setdefault("conf_ratio", float(signal.conf_ratio))

        rid = self._rid(symbol=symbol, side=signal.side, ts_ms=bar_close_ts, intent_kind=signal.intent_kind)
        payload = {
            "schema_version": 1,
            "strategy_id": "md_amr",
            "symbol": symbol,
            "tf_sec": int(self.timeframe_sec),
            "side": str(signal.side).upper(),
            "intent_kind": str(signal.intent_kind),
            "exit_reason_code": str(signal.reason_code) if signal.intent_kind != "ENTRY" else None,
            "scaleout_fraction": float(signal.scaleout_fraction) if signal.scaleout_fraction is not None else None,
            "readiness": {"warmup_ok": True},
            "score": float(abs(signal.signal_score)),
            "why": str(signal.reason_code),
            "why_chain": [str(signal.reason_code)],
            "ts_ms": int(bar_close_ts),
            "rid": rid,
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
        }

        self.fsm.emit(
            "EVT:STRATEGY_SIGNAL_PRODUCED",
            payload=payload,
            why=f"strategy_signal:md_amr:{signal.intent_kind}",
            data_ref=[f"md_amr_{rid}"],
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
