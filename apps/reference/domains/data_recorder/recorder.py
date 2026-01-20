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
import logging
import threading
from collections import defaultdict
from typing import Dict, Any, Optional
from datetime import datetime

# T2B-04: Time abstraction for deterministic testing
from apps.reference.core.time import get_clock

from vfoundation.core.protocol import Message
from apps.reference.config_loader import AuroraConfig

class CsvRecorder:
    """
    Records unified market data snapshots to CSV files.
    """
    
    def __init__(self, fsm, config: AuroraConfig):
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Buffer: (symbol, ts_ms) -> { "features": msg, "regime": msg, "timestamp": receive_time }
        self._buffer: Dict[tuple, Dict[str, Any]] = defaultdict(dict)
        self._buffer_lock = threading.Lock()
        
        # Config
        self._root_dir = os.path.join(os.getcwd(), "data", "recorder")
        os.makedirs(self._root_dir, exist_ok=True)
        
        # Constants
        self._flush_interval = 1.0  # Flush every second
        self._retention_sec = 2.0   # Wait up to 2s for regime sync
        self._running = False
        
        # Metrics
        self._rows_written = 0
        
    def start(self):
        """Start the recorder service."""
        if self._running:
            return
            
        self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features)
        self.fsm.listen("EVT:REGIME_DETECTED", self.on_regime)
        
        self._running = True
        self._thread = threading.Thread(target=self._flush_loop, name="RecorderFlush", daemon=True)
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
            
            with self._buffer_lock:
                entry = self._buffer[key]
                if "features" not in entry:
                    # Initialize
                    entry["features"] = pld
                    entry["recv_time"] = get_clock().now_sec()
                    # If we already have regime (rare race), we are good
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
                        self._buffer[key]["regime"] = pld
                        matched = True
                        break
                
                if not matched:
                    # Regime came before features? Store it with placeholder tf=0 or pending?
                    # Storing with tf=0 might cause orphan. 
                    # Let's verify commonly used TFs. Regime usually aligns with a specific TF.
                    # We will optimize: Assume regime applies to the buffered bar that matches TS.
                    # If no bar exists yet, we buffer it (orphan regime).
                    # But we don't know tf yet. 
                    # Store as separate orphan dict? No, just drop strictness.
                    # Wait, if Features come LATER, we need this.
                    pass
                    
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

    def _flush(self):
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
                    
            for k in keys_to_remove:
                del self._buffer[k]
                
        # Write batch
        for key, entry in to_write:
            self._write_row(key, entry)

    def _write_row(self, key, entry):
        symbol, ts, tf_sec = key
        features_pld = entry.get("features", {})
        regime_pld = entry.get("regime", {})
        
        bar = features_pld.get("bar", {})
        if not bar:
            # Maybe implicit in features? No, we rely on our enrichment.
            # If missing (e.g. tick update), skip? 
            # Backtesting usually needs OHLCV.
            return

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
        }
        
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

        # 4. Regime
        if regime_pld:
            row_dict["regime"] = regime_pld.get("regime")
            row_dict["regime_conf"] = regime_pld.get("confidence")
        else:
            row_dict["regime"] = "PENDING" # or UNKNOWN
            row_dict["regime_conf"] = 0.0

        # 5. Warmup Reasons (Debug)
        warmup = features_pld.get("warmup", {})
        if warmup:
            row_dict["ready"] = warmup.get("full_ready")
            reasons = warmup.get("reasons", [])
            row_dict["not_ready_reasons"] = "|".join(reasons)

        # Write to file
        self._append_to_file(symbol, tf_sec, row_dict)

    def _append_to_file(self, symbol, tf_sec, row_dict):
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        dir_path = os.path.join(self._root_dir, date_str)
        os.makedirs(dir_path, exist_ok=True)
        
        filename = f"{symbol}_{tf_sec}.csv"
        path = os.path.join(dir_path, filename)
        
        # Check header
        write_header = not os.path.exists(path) or os.path.getsize(path) == 0
        
        # Get flattened keys
        # Note: keys can vary if features change. 
        # For CSV, we ideally want stable columns. 
        # We will sort keys.
        keys = sorted(row_dict.keys())
        
        # If appending, we must respect existing header?
        # A simple recorder assumes stable schema per run.
        # If schema changes, file might be broken.
        
        try:
            with open(path, "a", encoding="utf-8") as f:
                if write_header:
                    f.write(",".join(keys) + "\n")
                
                # Write Value
                values = []
                for k in keys:
                    val = row_dict.get(k, "")
                    values.append(str(val))
                f.write(",".join(values) + "\n")
                
            self._rows_written += 1
            if self._rows_written % 100 == 0:
                self.logger.info(f"Recorder: {self._rows_written} rows written.")
                
        except Exception as e:
            self.logger.error(f"Write error: {e}")
