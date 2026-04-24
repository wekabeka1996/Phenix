
"""Append-only mean-reversion bar logs for operator inspection and forensics.

This logger is called from MeanReversionHandler after a bar has already been
evaluated. It must never influence the trading decision path; write failures are
logged and swallowed so signal generation can continue.
"""

import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict

from apps.reference.shared.types import Bar


LOG = logging.getLogger(__name__)


class MeanReversionBarLogger:
    """
    Persist completed mean-reversion bars in TSV and JSONL sidecars.

    The TSV file is a compact operator-facing summary with a fixed set of
    columns. The JSONL file keeps the richer per-bar payload needed for later
    forensic inspection.
    """

    def __init__(self, timeframe_sec: int):
        self.timeframe_sec = timeframe_sec
        self.log_dir = os.path.join("logs", "mean_reversion")
        os.makedirs(self.log_dir, exist_ok=True)

        # File paths
        base_name = f"bars_{timeframe_sec}s"
        self.tsv_path = os.path.join(self.log_dir, f"{base_name}.tsv")
        self.jsonl_path = os.path.join(self.log_dir, f"{base_name}.jsonl")

        # Initialize TSV header if file is empty/new
        self._init_tsv_header()

    def _init_tsv_header(self):
        """Create the TSV header once per file, preserving append-only writes."""
        if not os.path.exists(self.tsv_path) or os.path.getsize(self.tsv_path) == 0:
            with open(self.tsv_path, "a", encoding="utf-8") as f:
                # Time | Symbol | O | H | L | C | V | BB_U | BB_L | RSI | Signal | Reason | Regime
                header = (
                    "Time\tSymbol\tOpen\tHigh\tLow\tClose\tVolume\t"
                    "BB_Upper\tBB_Lower\tRSI\tSignal\tReason\tRegime\n"
                )
                f.write(header)

    def log_bar(
        self,
        symbol: str,
        bar: Bar,
        context: Dict[str, Any]
    ) -> None:
        """
        Log one completed bar plus the already-computed strategy context.

        Expected context keys come from MeanReversionHandler._log_bar(). Only a
        compact subset is written to TSV: ``bb.upper``, ``bb.lower``, ``rsi``,
        signal type, reason, and regime. The JSONL record keeps the broader
        indicator payload and optional mean-reversion parameters.
        """
        try:
            ts_str = time.strftime("%Y-%m-%d %H:%M:%S",
                                   time.gmtime(bar.end_ts_ms / 1000.0))

            # Extract basic data
            o = f"{bar.open:.4f}"  # Assume Decimal
            h = f"{bar.high:.4f}"
            l = f"{bar.low:.4f}"
            c = f"{bar.close:.4f}"
            v = f"{bar.volume:.4f}"

            # Extract context
            bb = context.get("bb") or {}
            bb_u_val = bb.get("upper")
            bb_u = f"{Decimal(str(bb_u_val)):.4f}" if bb_u_val is not None else ""
            bb_l_val = bb.get("lower")
            bb_l = f"{Decimal(str(bb_l_val)):.4f}" if bb_l_val is not None else ""

            rsi_val = context.get("rsi")
            rsi = f"{float(rsi_val):.1f}" if rsi_val is not None else ""

            signal = context.get("signal_type", "NEUTRAL")
            reason = context.get("reason", "")
            regime = context.get("regime", "")

            # 1. Write TSV
            row = (
                f"{ts_str}\t{symbol}\t{o}\t{h}\t{l}\t{c}\t{v}\t"
                f"{bb_u}\t{bb_l}\t{rsi}\t{signal}\t{reason}\t{regime}\n"
            )
            with open(self.tsv_path, "a", encoding="utf-8") as f:
                f.write(row)

            # 2. Write JSONL
            json_record = {
                "ts_ms": bar.end_ts_ms,
                "ts_human": ts_str,
                "symbol": symbol,
                "ohlcv": {
                    "o": str(bar.open),
                    "h": str(bar.high),
                    "l": str(bar.low),
                    "c": str(bar.close),
                    "v": str(bar.volume),
                },
                "indicators": {
                    "bb": bb,
                    "rsi": str(rsi_val) if rsi_val is not None else None,
                    "atr": str(context.get("atr")) if context.get("atr") is not None else None,
                },
                "signal": {
                    "type": signal,
                    "reason": reason,
                    "regime": regime,
                },
                "params": context.get("mr_params"),
            }
            with open(self.jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(json_record) + "\n")

        except Exception as exc:
            # Fallback to standard logging if something explodes
            # (Don't want logging to crash the strategy)
            LOG.error("Failed to log bar for %s: %s", symbol, exc)
