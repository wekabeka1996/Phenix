"""
Unified Data Recorder - Captures Bars, Features, and Regimes for Backtesting.

Architecture:
- Listens to EVT:FEATURES_CALCULATED (Bar + Features)
- Listens to EVT:REGIME_DETECTED (Regime)
- Joins streams by (symbol, ts) with a short buffer window
- Writes unified CSV rows to data/recorder/
"""

import os
import time  # T2B-04: Keep for sync sleep in _flush_loop
import json
import csv
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Any, Optional, Literal
from datetime import datetime

# T2B-04: Time abstraction for deterministic testing
from apps.reference.core.time import get_clock

from vfoundation.core.protocol import Message
from apps.reference.config_loader import AuroraConfig
from apps.reference.shared.data_primitives.market_bar_contract import (
    RECORDER_STABLE_COLUMNS,
    build_stable_recorder_row,
)
from apps.reference.shared.data_primitives.ohlc_validator import validate_ohlc


RecorderWriteStatus = Literal[
    "written",
    "rejected_invalid_ohlc",
    "rejected_header_mismatch",
    "rejected_io_error",
]


@dataclass(frozen=True)
class RecorderWriteOutcome:
    status: RecorderWriteStatus
    reason_code: str
    symbol: str
    tf_sec: int
    path: str
    ts_ms: int
    header_expected_cols: int = 0
    header_actual_cols: int = 0
    dropped_fields_count: int = 0


class CsvRecorder:
    """
    Records unified market data snapshots to CSV files.
    """

    @staticmethod
    def _orphan_key(symbol: str, ts_ms: int) -> tuple[str, int]:
        return (str(symbol), int(ts_ms))

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _join_list(value: Any) -> str:
        if not isinstance(value, list):
            return ""
        return "|".join(str(item) for item in value if item not in (None, ""))

    def __init__(self, fsm, config: AuroraConfig):
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Buffer: (symbol, ts_ms) -> { "features": msg, "regime": msg, "timestamp": receive_time }
        self._buffer: Dict[tuple, Dict[str, Any]] = defaultdict(dict)
        self._orphan_regimes: Dict[tuple[str, int], Dict[str, Any]] = {}
        self._buffer_lock = threading.Lock()

        # Config
        self._root_dir = os.path.join(os.getcwd(), "data", "recorder")
        os.makedirs(self._root_dir, exist_ok=True)
        self._ohlc_rejected_log = os.path.join(
            os.getcwd(), "logs", "ohlc_rejected.jsonl")
        os.makedirs(os.path.dirname(self._ohlc_rejected_log), exist_ok=True)

        # Constants
        self._flush_interval = 1.0  # Flush every second
        self._retention_sec = 2.0   # Wait up to 2s for regime sync
        self._running = False

        # Metrics
        self._rows_written = 0
        self._unknown_field_warning_keys: set[tuple[str, str]] = set()
        self._last_flush_outcomes: list[RecorderWriteOutcome] = []

    def _attach_regime(self, entry: Dict[str, Any], regime_pld: Dict[str, Any], *, join_mode: str) -> None:
        entry["regime"] = regime_pld
        entry["regime_join_status"] = "MATCHED"
        entry["regime_join_mode"] = str(join_mode)

    def start(self):
        """Start the recorder service."""
        if self._running:
            return

        self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features)
        self.fsm.listen("EVT:REGIME_DETECTED", self.on_regime)

        self._running = True
        self._thread = threading.Thread(
            target=self._flush_loop, name="RecorderFlush", daemon=True)
        self._thread.start()

        self.logger.info(f"CsvRecorder started. Output dir: {self._root_dir}")

    def stop(self):
        """Stop the recorder service."""
        self._running = False
        if hasattr(self, '_thread'):
            self._thread.join(timeout=2.0)

    def on_features(self, event: Message):
        """Handle incoming features event."""
        try:
            pld = event.pld
            if not pld:
                return

            symbol = pld.get("symbol")
            ts = int(pld.get("ts", 0))
            tf_sec = int(pld.get("tf_sec", 0))

            if not symbol or not ts:
                return

            key = (symbol, ts, tf_sec)
            orphan_key = self._orphan_key(symbol, ts)

            with self._buffer_lock:
                entry = self._buffer[key]
                if "features" not in entry:
                    # Initialize
                    entry["features"] = pld
                    entry["recv_time"] = get_clock().now_sec()
                orphan = self._orphan_regimes.pop(orphan_key, None)
                if orphan is not None and "regime" not in entry:
                    self._attach_regime(
                        entry,
                        orphan["regime"],
                        join_mode="orphan_exact_ts",
                    )
        except Exception as e:
            self.logger.error(f"Error handling features: {e}")

    def on_regime(self, event: Message):
        """Handle incoming regime event."""
        try:
            pld = event.pld
            if not pld:
                return

            symbol = pld.get("symbol")
            ts = int(pld.get("ts", 0))
            # Regime doesn't always have tf_sec in payload top-level, but usually matches basis.
            # We match primarily by symbol/ts.
            # HOWEVER, buffer key includes tf_sec.
            # We need to find the matching entry.

            if not symbol or not ts:
                return

            with self._buffer_lock:
                # Find matching entry for symbol/ts (ignoring tf_sec for lookup if needed,
                # but better to iterate linearly or maintain secondary index?
                # For simplicity/speed, we'll iterate keys since buffer is small (short retention).

                matched = False
                for key in list(self._buffer.keys()):
                    s, t, tf = key
                    if s == symbol and t == ts:
                        self._attach_regime(
                            self._buffer[key],
                            pld,
                            join_mode="buffer_exact_ts",
                        )
                        matched = True
                        break

                if not matched:
                    self._orphan_regimes[self._orphan_key(symbol, ts)] = {
                        "regime": dict(pld),
                        "recv_time": get_clock().now_sec(),
                    }

        except Exception as e:
            self.logger.error(f"Error handling regime: {e}")

    def _flush_loop(self):
        """Periodic flush loop."""
        while self._running:
            time.sleep(self._flush_interval)
            try:
                self._flush()
            except Exception as e:
                self.logger.error(f"Flush error: {e}")

    def _build_output_path(self, symbol: str, tf_sec: int, *, ensure_dir: bool) -> str:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        dir_path = os.path.join(self._root_dir, date_str)
        if ensure_dir:
            os.makedirs(dir_path, exist_ok=True)
        filename = f"{symbol}_{tf_sec}.csv"
        return os.path.join(dir_path, filename)

    def _flush(self) -> list[RecorderWriteOutcome]:
        now = get_clock().now_sec()
        to_write = []
        keys_to_remove = []

        with self._buffer_lock:
            for key, entry in self._buffer.items():
                recv_time = entry.get("recv_time", 0)
                age = now - recv_time

                # Ready condition: Has features + (Has regime OR Timeout)
                has_features = "features" in entry
                has_regime = "regime" in entry
                is_timeout = age > self._retention_sec

                if has_features and (has_regime or is_timeout):
                    to_write.append((key, entry))
                    keys_to_remove.append(key)
                elif is_timeout and not has_features:
                    # Garbage (orphaned entries)
                    keys_to_remove.append(key)

            orphan_keys_to_remove = []
            for orphan_key, orphan in self._orphan_regimes.items():
                recv_time = orphan.get("recv_time", 0)
                age = now - recv_time
                if age > self._retention_sec:
                    orphan_keys_to_remove.append(orphan_key)

            for k in keys_to_remove:
                del self._buffer[k]
            for orphan_key in orphan_keys_to_remove:
                del self._orphan_regimes[orphan_key]

        # Write batch
        outcomes: list[RecorderWriteOutcome] = []
        for key, entry in to_write:
            outcome = self._write_row(key, entry)
            if outcome is not None:
                outcomes.append(outcome)
        self._last_flush_outcomes = outcomes
        return outcomes

    def _record_ohlc_rejection(
        self,
        *,
        symbol: str,
        ts: int,
        tf_sec: int,
        bar: Dict[str, Any],
        reason: str,
        surface: str,
    ) -> None:
        payload = {
            "ts": int(ts),
            "symbol": str(symbol),
            "tf_sec": int(tf_sec),
            "surface": str(surface),
            "reason": str(reason),
            "bar": {
                "open": bar.get("open") if isinstance(bar, dict) else None,
                "high": bar.get("high") if isinstance(bar, dict) else None,
                "low": bar.get("low") if isinstance(bar, dict) else None,
                "close": bar.get("close") if isinstance(bar, dict) else None,
                "volume": bar.get("volume") if isinstance(bar, dict) else None,
            },
        }
        try:
            with open(self._ohlc_rejected_log, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as exc:
            self.logger.error("Failed to append rejected OHLC log: %s", exc)

        if hasattr(self.fsm, "emit"):
            try:
                self.fsm.emit("EVT:OHLC_INVALID", payload=payload, why="recorder_invalid_ohlc")
            except Exception:
                # Best-effort telemetry only; recorder must not crash on missing registry/schema.
                pass

    def _write_row(self, key, entry) -> Optional[RecorderWriteOutcome]:
        symbol, ts, tf_sec = key
        features_pld = entry.get("features", {})
        regime_pld = entry.get("regime", {})

        bar = features_pld.get("bar", {})
        if not bar:
            # Maybe implicit in features? No, we rely on our enrichment.
            # If missing (e.g. tick update), skip?
            # Backtesting usually needs OHLCV.
            return None

        # Prepare Row
        # 1. Standard Columns
        dt_str = datetime.fromtimestamp(ts / 1000.0).isoformat()

        row_dict = {
            "timestamp": ts,
            "datetime": dt_str,
            "symbol": symbol,
            "tf_sec": tf_sec,
            "open": bar.get("open"),
            "high": bar.get("high"),
            "low": bar.get("low"),
            "close": bar.get("close"),
            "volume": bar.get("volume"),
            "trade_count": bar.get("trade_count"),
            "source_mode": features_pld.get("source_mode", ""),
            "close_boundary_ts_ms": features_pld.get("close_boundary_ts_ms", ""),
            "gap_state": features_pld.get("gap_state", ""),
            "gap_policy_action": features_pld.get("gap_policy_action", ""),
            "gap_bars_skipped": features_pld.get("gap_bars_skipped", ""),
            "is_gap_bar": features_pld.get("is_gap_bar", ""),
        }

        valid_ohlc, invalid_reason = validate_ohlc(
            row_dict["open"],
            row_dict["high"],
            row_dict["low"],
            row_dict["close"],
        )
        if not valid_ohlc:
            self._record_ohlc_rejection(
                symbol=symbol,
                ts=ts,
                tf_sec=tf_sec,
                bar=bar,
                reason=str(invalid_reason),
                surface="data_recorder",
            )
            self.logger.warning(
                "Recorder rejected malformed OHLC row for %s tf=%s ts=%s reason=%s",
                symbol,
                tf_sec,
                ts,
                invalid_reason,
            )
            return RecorderWriteOutcome(
                status="rejected_invalid_ohlc",
                reason_code=str(invalid_reason or "INVALID_OHLC"),
                symbol=str(symbol),
                tf_sec=int(tf_sec),
                path=self._build_output_path(str(symbol), int(tf_sec), ensure_dir=False),
                ts_ms=int(ts),
                dropped_fields_count=0,
            )

        # 2. Flatten Features
        feats = features_pld.get("features", {})
        for k, v in feats.items():
            if isinstance(v, (int, float, str, bool)):
                row_dict[f"feat_{k}"] = v
            # Skip nested dicts for now unless specific

        # 3. Price Motion
        pm = features_pld.get("price_motion", {})
        if pm:
            row_dict["pm_norm"] = pm.get("pm_norm")
            row_dict["pm_raw"] = pm.get("pm_raw")
            row_dict["pm_norm_10s"] = pm.get("pm_norm_10s")
            row_dict["pm_norm_60s"] = pm.get("pm_norm_60s")
            row_dict["pm_norm_300s"] = pm.get("pm_norm_300s")
            row_dict["pm_norm_900s"] = pm.get("pm_norm_900s")

        # 4. Regime
        if regime_pld:
            regime_ts_ms = self._optional_int(
                regime_pld.get("ts_ms") if isinstance(
                    regime_pld, dict) else None
            )
            if regime_ts_ms is None:
                regime_ts_ms = self._optional_int(
                    regime_pld.get("ts") if isinstance(
                        regime_pld, dict) else None
                )
            regime_last_update_ts_ms = self._optional_int(
                regime_pld.get("last_update_ts_ms") if isinstance(
                    regime_pld, dict) else None
            )
            regime_warmup = regime_pld.get(
                "warmup", {}) if isinstance(regime_pld, dict) else {}
            regime_quality = regime_pld.get(
                "data_quality", {}) if isinstance(regime_pld, dict) else {}
            row_dict["regime"] = regime_pld.get("regime")
            row_dict["regime_conf"] = regime_pld.get("confidence")
            row_dict["regime_join_status"] = entry.get(
                "regime_join_status", "MATCHED")
            row_dict["regime_join_mode"] = entry.get(
                "regime_join_mode", "buffer_exact_ts")
            row_dict["regime_event_ts_ms"] = regime_ts_ms if regime_ts_ms is not None else ""
            row_dict["regime_last_update_ts_ms"] = regime_last_update_ts_ms if regime_last_update_ts_ms is not None else ""
            row_dict["regime_age_ms"] = (
                ts - regime_ts_ms) if regime_ts_ms is not None else ""
            row_dict["regime_layer"] = regime_pld.get("regime_layer")
            row_dict["regime_scope"] = regime_pld.get("regime_scope")
            row_dict["regime_owner"] = regime_pld.get("regime_owner")
            row_dict["regime_source_model"] = regime_pld.get("source_model")
            row_dict["regime_structural_regime_ref"] = regime_pld.get(
                "structural_regime_ref")
            row_dict["regime_warmup_full_ready"] = regime_warmup.get(
                "full_ready") if isinstance(regime_warmup, dict) else None
            row_dict["regime_warmup_reasons"] = self._join_list(
                regime_warmup.get("reasons") if isinstance(
                    regime_warmup, dict) else None
            )
            row_dict["regime_data_drops"] = self._join_list(
                regime_quality.get("drops") if isinstance(
                    regime_quality, dict) else None
            )
            row_dict["regime_data_notes"] = self._join_list(
                regime_quality.get("notes") if isinstance(
                    regime_quality, dict) else None
            )
        else:
            row_dict["regime"] = "PENDING"  # or UNKNOWN
            row_dict["regime_conf"] = 0.0
            row_dict["regime_join_status"] = "MISSING"
            row_dict["regime_join_mode"] = "missing_timeout"
            row_dict["regime_event_ts_ms"] = ""
            row_dict["regime_last_update_ts_ms"] = ""
            row_dict["regime_age_ms"] = ""
            row_dict["regime_layer"] = ""
            row_dict["regime_scope"] = ""
            row_dict["regime_owner"] = ""
            row_dict["regime_source_model"] = ""
            row_dict["regime_structural_regime_ref"] = ""
            row_dict["regime_warmup_full_ready"] = ""
            row_dict["regime_warmup_reasons"] = ""
            row_dict["regime_data_drops"] = ""
            row_dict["regime_data_notes"] = ""

        # 5. Warmup Reasons (Debug)
        warmup = features_pld.get("warmup", {})
        if warmup:
            row_dict["ready"] = warmup.get("full_ready")
            reasons = warmup.get("reasons", [])
            row_dict["not_ready_reasons"] = "|".join(reasons)

        # Write to file
        stable_row, dropped = build_stable_recorder_row(row_dict)
        for key in dropped:
            dedupe_key = (str(symbol), str(key))
            if dedupe_key in self._unknown_field_warning_keys:
                continue
            self._unknown_field_warning_keys.add(dedupe_key)
            self.logger.warning("RECORDER_UNKNOWN_FIELD_DROPPED symbol=%s field=%s", symbol, key)
        return self._append_to_file(
            symbol,
            tf_sec,
            stable_row,
            ts_ms=int(ts),
            dropped_fields_count=len(dropped),
        )

    def _append_to_file(self, symbol, tf_sec, row_dict, *, ts_ms: int, dropped_fields_count: int) -> RecorderWriteOutcome:
        path = self._build_output_path(str(symbol), int(tf_sec), ensure_dir=True)
        write_header = not os.path.exists(path) or os.path.getsize(path) == 0
        expected_header = list(RECORDER_STABLE_COLUMNS)
        actual_header_len = 0

        try:
            if not write_header:
                with open(path, "r", encoding="utf-8", newline="") as handle:
                    reader = csv.reader(handle)
                    current_header = next(reader, [])
                actual_header_len = len(current_header)
                if list(current_header) != expected_header:
                    self.logger.error(
                        "RECORDER_HEADER_MISMATCH path=%s expected_cols=%s actual_cols=%s",
                        path,
                        len(expected_header),
                        len(current_header),
                    )
                    return RecorderWriteOutcome(
                        status="rejected_header_mismatch",
                        reason_code="RECORDER_HEADER_MISMATCH",
                        symbol=str(symbol),
                        tf_sec=int(tf_sec),
                        path=str(path),
                        ts_ms=int(ts_ms),
                        header_expected_cols=len(expected_header),
                        header_actual_cols=len(current_header),
                        dropped_fields_count=int(dropped_fields_count),
                    )

            with open(path, "a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=expected_header,
                    extrasaction="ignore",
                )
                if write_header:
                    writer.writeheader()
                writer.writerow({column: row_dict.get(column, "") for column in expected_header})

            self._rows_written += 1
            if self._rows_written % 100 == 0:
                self.logger.info(
                    f"Recorder: {self._rows_written} rows written.")
            return RecorderWriteOutcome(
                status="written",
                reason_code="OK",
                symbol=str(symbol),
                tf_sec=int(tf_sec),
                path=str(path),
                ts_ms=int(ts_ms),
                header_expected_cols=len(expected_header),
                header_actual_cols=actual_header_len or len(expected_header),
                dropped_fields_count=int(dropped_fields_count),
            )

        except Exception as e:
            self.logger.error(f"Write error: {e}")
            return RecorderWriteOutcome(
                status="rejected_io_error",
                reason_code="RECORDER_WRITE_ERROR",
                symbol=str(symbol),
                tf_sec=int(tf_sec),
                path=str(path),
                ts_ms=int(ts_ms),
                header_expected_cols=len(expected_header),
                header_actual_cols=int(actual_header_len),
                dropped_fields_count=int(dropped_fields_count),
            )
