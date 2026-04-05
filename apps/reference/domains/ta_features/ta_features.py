"""
TA Features Domain — FSM Handler (TAFeaturesEngine).

Isolated bar-based technical indicator computation and logging.

Lifecycle:
    1. Subscribes to EVT:BAR_CLOSED (emitted by BarAggregator from live WebSocket bars).
    2. Maintains a rolling BarBuffer per (symbol, tf_sec).
    3. Computes 8 TA features on every configured bar close.
    4. Emits EVT:TA_FEATURES_CALCULATED with explicit warmup state.
    5. Writes a JSONL record to logs/ta_features/{SYMBOL}.jsonl for observability.

Config is canonical: config.domains.ta_features in config/aurora/domains.yaml.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Tuple

from apps.reference.config_models import TAFeaturesDomainConfig
from apps.reference.domains.ta_features.bar_buffer import BarBuffer
from apps.reference.domains.ta_features.calculators import (
    compute_price_momentum,
    compute_price_sma_deviation,
    compute_stochastic,
    compute_ta_bb,
    compute_ta_rsi,
    compute_volume_sma_ratio,
)
from apps.reference.domains.ta_features.contracts import TA_FEATURE_EVENT

_LOG = logging.getLogger("apps.reference.domains.ta_features")

# ---------------------------------------------------------------------------
# Windows-safe rotating file handler (mirrors logging_setup.WinSafeRotatingFileHandler)
# ---------------------------------------------------------------------------


class _WinSafeRotHandler(RotatingFileHandler):
    def rotate(self, source: str, dest: str) -> None:
        try:
            super().rotate(source, dest)
        except PermissionError:
            pass


# Path for per-symbol JSONL logs relative to project root
_LOGS_SUBDIR = "logs/ta_features"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class TAFeaturesEngine:
    """
    Isolated TA feature computation engine.

    Listens to EVT:BAR_CLOSED, computes 8 bar-based features, emits
    EVT:TA_FEATURES_CALCULATED and writes per-symbol JSONL logs.

    Subscription (future consumers):
        fsm.listen("EVT:TA_FEATURES_CALCULATED", handler)
    """

    def __init__(self, *, fsm: Any, config: TAFeaturesDomainConfig) -> None:
        self._fsm = fsm
        self._config = config
        self._enabled = bool(config.enabled)
        self._timeframes: set[int] = set(
            int(tf_sec) for tf_sec in config.timeframes_sec)
        self._min_bars = int(config.warm_up_bars)
        self._buffer_max_bars = int(config.buffer_max_bars)
        self._log_calcs = bool(config.log_calculations)

        # Rolling OHLCV buffers keyed by (symbol, tf_sec)
        self._buffers: Dict[Tuple[str, int], BarBuffer] = {}

        # Per-symbol JSONL file loggers keyed by symbol
        self._sym_loggers: Dict[str, logging.Logger] = {}

        if self._enabled:
            fsm.listen("EVT:BAR_CLOSED", self.on_bar_closed)
            _LOG.info(
                "TAFeaturesEngine started",
                extra={
                    "why": "ta_features_started",
                    "timeframes": sorted(self._timeframes),
                    "warm_up_bars": self._min_bars,
                    "buffer_max_bars": self._buffer_max_bars,
                    "log_calculations": self._log_calcs,
                },
            )
        else:
            _LOG.info("TAFeaturesEngine disabled via config (enabled=false)")

    # ------------------------------------------------------------------
    # FSM handler
    # ------------------------------------------------------------------

    def on_bar_closed(self, msg: Any) -> None:
        """Handle EVT:BAR_CLOSED — update buffer and compute features."""
        try:
            pld = msg.pld if hasattr(msg, "pld") else msg
            symbol: str = pld["symbol"]
            tf_sec: int = int(pld["tf_sec"])

            if tf_sec not in self._timeframes:
                return

            bar = pld["bar"]
            self._push_bar(symbol, tf_sec, bar)

            buf = self._buffers[(symbol, tf_sec)]
            bar_close_ts = int(pld.get("bar_close_ts", buf.last_ts_ms))
            features = self._compute_features(
                symbol, tf_sec, buf, bar_close_ts)

            self._fsm.emit(TA_FEATURE_EVENT, features)

            if self._log_calcs:
                self._write_symbol_log(symbol, features)

        except Exception as exc:
            _LOG.error(
                "TAFeaturesEngine: on_bar_closed error — %s",
                exc,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Buffer management
    # ------------------------------------------------------------------

    def _push_bar(self, symbol: str, tf_sec: int, bar: Dict[str, Any]) -> None:
        key = (symbol, tf_sec)
        if key not in self._buffers:
            self._buffers[key] = BarBuffer(maxlen=self._buffer_max_bars)
        buf = self._buffers[key]

        def _d(v: Any) -> Decimal:
            return Decimal(str(v))

        buf.push(
            open_=_d(bar["open"]),
            high=_d(bar["high"]),
            low=_d(bar["low"]),
            close=_d(bar["close"]),
            volume=_d(bar["volume"]),
            ts_ms=int(bar.get("end_ts_ms", bar.get("ts_ms", 0))),
        )

    # ------------------------------------------------------------------
    # Feature computation
    # ------------------------------------------------------------------

    def _compute_features(
        self,
        symbol: str,
        tf_sec: int,
        buf: BarBuffer,
        bar_close_ts: int,
    ) -> Dict[str, Any]:
        closes = buf.closes
        highs = buf.highs
        lows = buf.lows
        volumes = buf.volumes

        bb_position, bb_width = compute_ta_bb(closes)
        rsi_14 = compute_ta_rsi(closes)
        stoch_k, stoch_d = compute_stochastic(highs, lows, closes)
        price_sma_dev = compute_price_sma_deviation(closes)
        volume_ratio = compute_volume_sma_ratio(volumes)

        # Adaptive momentum lookback: represent ~5 minutes regardless of timeframe
        momentum_lookback = max(1, 300 // tf_sec)
        momentum = compute_price_momentum(closes, lookback=momentum_lookback)
        warm_up_bars = len(buf)
        is_warm = warm_up_bars >= self._min_bars

        return {
            "ts": bar_close_ts,
            "symbol": symbol,
            "tf_sec": tf_sec,
            "bar_close_ts": bar_close_ts,
            "close": float(closes[-1]),
            "bb_position": bb_position,
            "bb_width": bb_width,
            "rsi_14": rsi_14,
            "price_sma_20_deviation": price_sma_dev,
            "volume_sma_ratio": volume_ratio,
            "stoch_k": stoch_k,
            "stoch_d": stoch_d,
            "price_momentum_5m": momentum,
            "warm_up_bars": warm_up_bars,
            "required_warm_up_bars": self._min_bars,
            "is_warm": is_warm,
            "source": "ta_features",
        }

    # ------------------------------------------------------------------
    # Per-symbol JSONL logging
    # ------------------------------------------------------------------

    def _get_symbol_logger(self, symbol: str) -> logging.Logger:
        if symbol not in self._sym_loggers:
            self._sym_loggers[symbol] = self._build_symbol_logger(symbol)
        return self._sym_loggers[symbol]

    def _build_symbol_logger(self, symbol: str) -> logging.Logger:
        logs_dir = Path(__file__).resolve().parents[4] / _LOGS_SUBDIR
        logs_dir.mkdir(parents=True, exist_ok=True)

        log_path = logs_dir / f"{symbol}.jsonl"
        logger_name = f"apps.reference.domains.ta_features.{symbol}"

        sym_logger = logging.getLogger(logger_name)
        sym_logger.setLevel(logging.DEBUG)
        sym_logger.propagate = False  # Don't bubble up to root logger

        # Only add handler if not already configured (re-import protection)
        if not sym_logger.handlers:
            handler = _WinSafeRotHandler(
                log_path,
                maxBytes=int(self._config.log_max_bytes),
                backupCount=int(self._config.log_backup_count),
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            sym_logger.addHandler(handler)

        return sym_logger

    def _write_symbol_log(self, symbol: str, features: Dict[str, Any]) -> None:
        try:
            record = {
                "ts": datetime.utcnow().isoformat() + "Z",
                **features,
            }
            self._get_symbol_logger(symbol).info(json.dumps(record))
        except Exception as exc:
            _LOG.warning(
                "ta_features: symbol log write failed for %s — %s", symbol, exc)
