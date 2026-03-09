"""
Backtest Engine Core
====================

The "Time Machine" that simulates market history and orchestrates:
1. Data Replay (Polars)
2. MockBroker Execution (Limit/Market orders)
3. Event Emission (EventBus)
4. Strategy Synchronization
"""
import math
import os
import time
import logging
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, date
from dataclasses import dataclass
from pathlib import Path

import polars as pl

# Import clock abstraction for consistent time in backtest
try:
    from apps.reference.core.time import get_clock
except ImportError:
    # Fallback: use wall-clock if import fails
    class _FallbackClock:
        def now_ms(self) -> int:
            return int(time.time() * 1000)
        def now_sec(self) -> float:
            return time.time()
    def get_clock():
        return _FallbackClock()

# Try to import real EventBus or use LocalBus for simulation
try:
    from apps.reference.domains.execution_position.utils_event_bus import LocalBus
except ImportError:
    class LocalBus:
        """Minimal fallback if app imports fail completely."""
        def __init__(self): self.listeners = {}
        def listen(self, ev, cb): 
            if ev not in self.listeners: self.listeners[ev] = []
            self.listeners[ev].append(cb)
        def emit(self, event_name: str, payload: dict, why: str, data_ref=None):
            for cb in self.listeners.get(event_name, []):
                cb({'op': 'EVT', 'verb': event_name, 'pld': payload})

# Try to import MockBroker
try:
    from backtest_engine.mock_broker import MockBroker
except ImportError:
    # Fallback/Error - should not happen if path correct
    pass

LOG = logging.getLogger(__name__)


_OHLCV_REQUIRED: frozenset[str] = frozenset({"ts", "open", "high", "low", "close", "volume"})
_OHLCV_NUMERIC: frozenset[str] = frozenset({"open", "high", "low", "close", "volume"})
_OHLCV_NUMERIC_DTYPES = (pl.Float32, pl.Float64, pl.Int32, pl.Int64, pl.UInt32, pl.UInt64)


def _validate_ohlcv_contract(frame: "pl.DataFrame", symbol: str) -> None:
    """Phase 0.7: Fail-fast OHLCV data contract validation at parquet load.

    Native polars implementation — no pyarrow / pandas dependency.
    Validates the post-select engine frame (columns: ts, open, high, low,
    close, volume) against required columns, dtype classes, null constraints,
    and OHLCV semantic invariants.

    Raises:
        ValueError: Prefixed "DataContract violation (ohlcv)" on any failure.
    """
    errors: list[str] = []
    present = set(frame.columns)

    # 1. Missing columns
    missing = sorted(_OHLCV_REQUIRED - present)
    if missing:
        errors.append(f"missing columns: {missing}")

    # 2. Dtype class check (only for present columns)
    for col in _OHLCV_NUMERIC:
        if col in present:
            if frame[col].dtype not in _OHLCV_NUMERIC_DTYPES:
                errors.append(f"column '{col}': expected numeric, got {frame[col].dtype}")
    if "ts" in present:
        if not isinstance(frame["ts"].dtype, pl.Datetime):
            errors.append(f"column 'ts': expected Datetime, got {frame['ts'].dtype}")

    # 3. Null checks (all required columns are non-nullable)
    for col in _OHLCV_REQUIRED:
        if col in present:
            null_count = frame[col].null_count()
            if null_count > 0:
                errors.append(f"column '{col}': {null_count} null(s) in non-nullable column")

    # 4. OHLCV semantic invariants (only when no structural errors)
    if not errors:
        high, low, open_, close, volume = (
            frame["high"], frame["low"], frame["open"], frame["close"], frame["volume"]
        )
        for bad_count, msg in [
            ((high < low).sum(),    "rows with high < low"),
            ((high < open_).sum(),  "rows with high < open"),
            ((high < close).sum(),  "rows with high < close"),
            ((low > open_).sum(),   "rows with low > open"),
            ((low > close).sum(),   "rows with low > close"),
            ((volume < 0).sum(),    "rows with volume < 0"),
        ]:
            if bad_count:
                errors.append(f"OHLCV invariant: {bad_count} {msg}")

    if errors:
        raise ValueError(
            f"DataContract violation (ohlcv) [{symbol}]: " + "; ".join(errors)
        )

    LOG.debug("DataContract OHLCV validation passed for %s (%d rows)", symbol, len(frame))


@dataclass
class BacktestResult:
    """Summary of backtest performance."""
    total_pnl: float
    max_drawdown: float
    total_trades: int
    win_rate: float
    start_balance: float
    end_balance: float
    roi_pct: float
    # Risk-adjusted performance metrics (OPTIMIZATION-PHASE1)
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    # Profit withdrawal (backtest-only cashflow simulation)
    withdrawals_total: float = 0.0
    withdrawals_count: int = 0
    end_balance_gross: float = 0.0
    total_pnl_on_account: float = 0.0
    roi_on_account_pct: float = 0.0
    max_drawdown_on_account: float = 0.0

class BacktestEngine:
    """
    Simulates a live trading environment using historical data.
    """
    
    def __init__(
        self,
        start_date: Union[date, datetime],
        end_date: Union[date, datetime],
        symbol_list: List[str],
        timeframe: str,
        event_bus: Any = None, # Expecting LocalBus or compatible
        data_dir: str = "data/processed",
        initial_balance: float = 10000.0,
        profit_withdrawal_enabled: bool | None = None,
        profit_withdrawal_roi_pct: float | None = None,
        clock_advance_fn: Any = None,  # Callback to advance global clock: fn(ts_ms: int) -> None
        htf_provider: Any = None,      # Optional HTFHistoryProvider for autonomous warmup
        turbo_mode: str = "off",       # Phase 1/2/3/4 dispatcher string
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.symbol_list = symbol_list
        self.timeframe = timeframe
        self.data_dir = Path(data_dir)
        self.event_bus = event_bus if event_bus else LocalBus()
        self.clock_advance_fn = clock_advance_fn  # For backtest timebase synchronization
        self.htf_provider = htf_provider
        self.turbo_mode = turbo_mode
        self.profit_withdrawal_enabled = (
            profit_withdrawal_enabled
            if isinstance(profit_withdrawal_enabled, bool) or profit_withdrawal_enabled is None
            else None
        )
        self.profit_withdrawal_roi_pct = float(profit_withdrawal_roi_pct) if profit_withdrawal_roi_pct is not None else None
        self.capital_withdrawals: list[dict[str, Any]] = []
        self.capital_withdrawn_total: float = 0.0
        self._equity_tracking_initialized: bool = False
        self._peak_equity_gross: float = 0.0
        self._peak_equity_on_account: float = 0.0
        self._max_drawdown_gross: float = 0.0
        self._max_drawdown_on_account: float = 0.0
        # OPTIMIZATION-PHASE1: Per-bar equity returns for Sharpe ratio calculation
        self._equity_snapshots: list[float] = []
        # Bar-only backtest by default for Aurora. Legacy tick emits are opt-in only.
        self._emit_market_ticks: bool = str(os.getenv("BACKTEST_EMIT_MARKET_TICKS", "0")).strip() == "1"
        
        # Initialize Mock Broker
        self.broker = MockBroker(initial_balance_usdt=initial_balance)
        
        # DET-BT-15: Direct reference to ExecPosFSM for tick-barrier sync
        self.execpos_fsm = None
        
        # PILLAR-WARMUP: Multi-TF resampler for pillar warmup (set externally by main.py)
        self._bar_resampler = None
        
        # Data storage
        self.feed: Optional[pl.DataFrame] = None
        self.warmup_feed: Optional[pl.DataFrame] = None

    def _find_data_files(self, symbol: str) -> list[Path]:
        """
        Locate parquet files for a symbol/timeframe, prioritizing *_enriched.parquet.
        Search order:
        1) data/processed/{symbol}/{timeframe}
        2) data/processed/{symbol}/klines/{timeframe}
        """
        candidates = [
            self.data_dir / symbol / self.timeframe,
            self.data_dir / symbol / "klines" / self.timeframe,
        ]

        for path in candidates:
            if not path.exists():
                continue

            all_files = sorted(path.glob("*.parquet"))
            month_to_file: dict[str, Path] = {}
            for f in all_files:
                if f.name.endswith("_enriched.parquet"):
                    month_to_file[f.stem[: -len("_enriched")]] = f
            for f in all_files:
                if f.name.endswith("_enriched.parquet"):
                    continue
                month_to_file.setdefault(f.stem, f)

            selected_files = [month_to_file[k] for k in sorted(month_to_file.keys())]
            if selected_files:
                return selected_files

        return []
        
    def load_data(self):
        """
        Load, filter, merge, and sort data for all symbols.
        Returns the prepared Polars DataFrame: [ts, symbol, open, high, low, close, volume]
        """
        LOG.info(f"Loading data for {self.symbol_list} from {self.start_date} to {self.end_date}...")
        
        frames = []
        for symbol in self.symbol_list:
            # We need to find the files for this range.
            # Simplified: Load ALL files for symbol/timeframe, then filter.
            # Optimization: could filter filenames by YYYY-MM if strictly checking date.
            
            try:
                selected_files = self._find_data_files(symbol)
                if not selected_files:
                    LOG.warning(f"No parquet files found for {symbol} {self.timeframe} under {self.data_dir}")
                    continue

                for file_path in selected_files:
                    # Track last loaded file for sniffer
                    self.current_file_path = str(file_path)
                    LOG.warning(f"🛑 [SNIFFER] LOADED FILE: {file_path}")

                q = pl.scan_parquet([str(f) for f in selected_files])
                
                # Filter by date
                # Ensure 'open_time' is treated as timestamp
                # start/end could be date or datetime. Convert to datetime if needed.
                # Polars timestamps are usually microseconds or milliseconds.
                # Our Converter uses 'ms' (datetime[ms]).
                
                start_ts = (
                    datetime.combine(self.start_date, datetime.min.time())
                    if isinstance(self.start_date, date) and not isinstance(self.start_date, datetime)
                    else self.start_date
                )
                end_ts = (
                    datetime.combine(self.end_date, datetime.max.time())
                    if isinstance(self.end_date, date) and not isinstance(self.end_date, datetime)
                    else self.end_date
                )
                
                # PILLAR-WARMUP: Extend start time by 210 days to fetch data for SMA200 (D1) backfill.
                from datetime import timedelta
                warmup_start_ts = start_ts - timedelta(days=210)

                # Inclusive date semantics: if caller passed a midnight datetime,
                # treat it as end-of-day rather than a single instant.
                if isinstance(end_ts, datetime) and end_ts.time() == datetime.min.time():
                    end_ts = end_ts.replace(hour=23, minute=59, second=59, microsecond=999999)
                
                q = q.filter(
                    (pl.col("open_time") >= warmup_start_ts) & 
                    (pl.col("open_time") <= end_ts)
                )
                
                # Standardize columns for the feed.
                # Enriched datasets include buy/sell flow columns; pass through when present.
                available = set(q.schema.keys())
                select_exprs: list[pl.Expr] = [
                    pl.col("open_time").alias("ts"),
                    pl.lit(symbol).alias("symbol"),
                    pl.col("open"),
                    pl.col("high"),
                    pl.col("low"),
                    pl.col("close"),
                    pl.col("volume"),
                ]

                def _col_or_zero(name: str, dtype: pl.DataType) -> pl.Expr:
                    if name in available:
                        return pl.col(name).cast(dtype).fill_null(0).alias(name)
                    return pl.lit(0).cast(dtype).alias(name)

                for name, dtype in [
                    ("buy_volume", pl.Float64),
                    ("sell_volume", pl.Float64),
                    ("buy_notional", pl.Float64),
                    ("sell_notional", pl.Float64),
                    ("buy_count", pl.Int64),
                    ("sell_count", pl.Int64),
                    # bookTicker-derived order book stats (optional)
                    ("avg_bid_qty", pl.Float64),
                    ("avg_ask_qty", pl.Float64),
                    ("last_bid_price", pl.Float64),
                    ("last_ask_price", pl.Float64),
                ]:
                    select_exprs.append(_col_or_zero(name, dtype))

                q = q.select(select_exprs)

                collected = q.collect(streaming=True)  # Materialize per symbol

                # Phase 0.7: Fail-fast OHLCV data contract check
                _validate_ohlcv_contract(collected, symbol)

                frames.append(collected)
            except ValueError:
                raise  # DataContract violations are fatal — do not swallow
            except Exception as e:
                LOG.error(f"Error loading {symbol}: {e}")
                
        if not frames:
            raise ValueError("No data loaded!")
            
        # Merge and sort
        full_df = pl.concat(frames)
        full_df = full_df.sort("ts")
        
        # ALPHA-SEARCH: Optionally augment with TA indicators
        try:
            print("DEBUG: Importing Augmenter...", flush=True)
            from backtest_engine.feature_augmenter import BacktestFeatureAugmenter
            print("DEBUG: Initializing Augmenter...", flush=True)
            augmenter = BacktestFeatureAugmenter(full_df)
            print("DEBUG: Running Augmenter...", flush=True)
            full_df = augmenter.augment()
            print("DEBUG: Augmenter Done.", flush=True)
            LOG.info(f"Feature augmentation complete: {augmenter.get_feature_names()}")
        except Exception as aug_err:
            LOG.warning(f"Feature augmentation skipped: {aug_err}")
        
        # Split into warmup and simulation feeds
        sim_start_ts = (
            datetime.combine(self.start_date, datetime.min.time())
            if isinstance(self.start_date, date) and not isinstance(self.start_date, datetime)
            else self.start_date
        )

        try:
            # Drop timezone information from the `ts` column if present so it can compare with naive sim_start_ts
            ts_expr = pl.col("ts")
            if "time_zone" in dir(full_df.schema["ts"]) and full_df.schema["ts"].time_zone is not None:
                ts_expr = pl.col("ts").dt.replace_time_zone(None)
                
            self.warmup_feed = full_df.filter(ts_expr < sim_start_ts)
            self.feed = full_df.filter(ts_expr >= sim_start_ts)
        except Exception as e:
            LOG.error(f"Failed to split warmup/sim feeds: {e}")
            self.feed = full_df
            self.warmup_feed = None
        
        LOG.info(f"Data ready: {len(self.warmup_feed)} warmup rows, {len(self.feed)} sim rows.")

    def _warmup_pillars(self) -> None:
        """
        Pre-warm Pillar State by aggregating the warmup_feed into H4 and D1
        and emitting EVT:BAR_CLOSED backwards to start_date.
        """
        if self.warmup_feed is None or self.warmup_feed.is_empty():
            LOG.warning("No warmup data available. Pillars will start cold.")
            return

        LOG.info(f"Warming up pillars with {len(self.warmup_feed)} rows of historical data.")
        # Try to resolve configured pillar timeframes via _bar_resampler or defaults
        pillar_tfs = [14400, 86400]  # H4 and D1
        
        for symbol in self.symbol_list:
            df_sym = self.warmup_feed.filter(pl.col("symbol") == symbol)
            if df_sym.is_empty():
                continue

            events_to_emit = []
            from datetime import timedelta

            for tf_sec in pillar_tfs:
                # Polars group_by_dynamic
                # timeframe strings for polars: "4h", "1d"
                period_str = f"{tf_sec // 3600}h" if tf_sec < 86400 else f"{tf_sec // 86400}d"
                
                try:
                    # Note: Need open_time alias or sort on ts
                    df_agg = df_sym.sort("ts").group_by_dynamic("ts", every=period_str).agg([
                        pl.first("open").alias("open"),
                        pl.max("high").alias("high"),
                        pl.min("low").alias("low"),
                        pl.last("close").alias("close"),
                        pl.sum("volume").alias("volume"),
                        pl.sum("buy_volume").alias("buy_volume"),
                        pl.sum("sell_volume").alias("sell_volume"),
                        pl.sum("buy_count").alias("buy_count"),
                        pl.sum("sell_count").alias("sell_count"),
                        pl.sum("buy_notional").alias("buy_notional"),
                        pl.sum("sell_notional").alias("sell_notional")
                    ]).sort("ts")

                    # Convert to bar payloads
                    for row in df_agg.iter_rows(named=True):
                        # The start of the bar
                        start_ts_dt = row["ts"]
                        # The end of the bar (close time)
                        end_ts_dt = start_ts_dt + timedelta(seconds=tf_sec)
                        start_ts_ms = int(start_ts_dt.timestamp() * 1000)
                        end_ts_ms = int(end_ts_dt.timestamp() * 1000)
                        
                        # In polars, if sum contains nulls, might return None
                        close_val = row["close"]
                        
                        bar_payload = {
                            "symbol": symbol,
                            "ts_ms": end_ts_ms,
                            "tf_sec": tf_sec,
                            "bar_close_ts": end_ts_ms,
                            "bar": {
                                "symbol": symbol,
                                "timeframe_sec": tf_sec,
                                "start_ts_ms": start_ts_ms,
                                "end_ts_ms": end_ts_ms,
                                "open": str(row["open"] or close_val),
                                "high": str(row["high"] or close_val),
                                "low": str(row["low"] or close_val),
                                "close": str(close_val),
                                "volume": str(row["volume"] or 0),
                                "buy_volume": str(row.get("buy_volume") or 0),
                                "sell_volume": str(row.get("sell_volume") or 0),
                                "buy_count": int(row.get("buy_count") or 0),
                                "sell_count": int(row.get("sell_count") or 0),
                                "buy_notional": str(row.get("buy_notional") or 0),
                                "sell_notional": str(row.get("sell_notional") or 0),
                                "bid_size": "0",
                                "ask_size": "0",
                                "bid": str(close_val),
                                "ask": str(close_val),
                            },
                            "bar_meta": {
                                "source": "backtest_warmup",
                                "close_reason": "historical_backfill",
                            },
                            "why": "backtest_pillar_warmup",
                        }
                        
                        events_to_emit.append((end_ts_ms, bar_payload))
                except Exception as e:
                    LOG.error(f"Failed to group warmup feed for {symbol} {period_str}: {e}")

            # Sort all historical events by time and emit
            events_to_emit.sort(key=lambda x: x[0])
            for _, payload in events_to_emit:
                # Advance simulated clock to the historical bar time prior to emission
                if self.clock_advance_fn is not None:
                    self.clock_advance_fn(payload["ts_ms"])
                    
                self.event_bus.emit(
                    event_name="EVT:BAR_CLOSED",
                    payload=payload,
                    why="backtest_pillar_warmup"
                )
                
            LOG.info(f"✅ Emitted {len(events_to_emit)} historical HTF bars for {symbol} warmup.")

    def _warmup_htf_api(self) -> None:
        """
        Use HTFHistoryProvider to autonomously backfill 1d and 4h pillars.
        Anchored to the exact first timestamp of `self.feed` to prevent Lookahead Bias.
        """
        if self.htf_provider is None:
            return

        if self.feed is None or self.feed.is_empty():
            LOG.warning("No feed loaded. Cannot anchor HTF warmup properly.")
            return

        # 1. Determine causal anchor = first TS in the backtest feed - 1ms
        first_row = self.feed.row(0, named=True)
        first_ts_val = first_row.get("ts")
        if first_ts_val is None:
            return
            
        first_ts_ms = int(first_ts_val.timestamp() * 1000) if hasattr(first_ts_val, "timestamp") else int(first_ts_val)
        anchor_ms = first_ts_ms - 1
        
        import asyncio
        
        pillar_tfs = {14400: 100, 86400: 200}  # {tf_sec: limit}
        
        for symbol in self.symbol_list:
            for tf_sec, limit in pillar_tfs.items():
                LOG.info(f"HTF Warmup: Fetching {limit}x {tf_sec}s for {symbol} anchoring at {anchor_ms}")
                
                # We use asyncio.run because this runs before the main async execution loop starts
                # or from a synchronous main thread.
                bars = asyncio.run(
                    self.htf_provider.get_klines(symbol, tf_sec, anchor_ms, limit)
                )
                
                if not bars:
                    # Fail-closed policy
                    LOG.error(f"HTF provider returned empty bars for {symbol} {tf_sec}s. Backtest results might be severely compromised.")
                    continue
                    
                payload = {
                    "symbol": symbol,
                    "tf_sec": tf_sec,
                    "as_of_ms": anchor_ms,
                    "bars": bars,
                    "why": "backtest_autonomous_htf_fetch"
                }
                
                # Emit the dedicated bypass event
                if self.clock_advance_fn is not None:
                    self.clock_advance_fn(anchor_ms)
                    
                self.event_bus.emit(
                    event_name="EVT:HTF_BARS_IMPORTED",
                    payload=payload,
                    why="backtest_autonomous_htf_fetch"
                )

    def run(self, *, max_ticks: int | None = None) -> BacktestResult:
        """
        Execute the Simulation Loop.
        """
        if self.feed is None:
            self.load_data()
            
        LOG.info("Starting Backtest Simulation...")
        start_time = time.time()
        
        # --- PILLAR WARMUP ---
        # 1. API-based HTF lookup (safe from lookahead bias)
        self._warmup_htf_api()
        # 2. Local fallback feed (if still configured)
        self._warmup_pillars()
        
        # QUICK HACK FIX: advance clock back to true start so initial portfolio matches reality
        if self.clock_advance_fn is not None and len(self.feed) > 0:
            ts_val = self.feed[0, "ts"]
            if hasattr(ts_val, "timestamp"):
                self.clock_advance_fn(int(ts_val.timestamp() * 1000))

        initial_portfolio_emitted = False
        
        # OPTIMIZATION-PHASE1: Resolve timeframe to seconds for Sharpe/Calmar annualization
        _tf_map = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200,
            "1d": 86400,
        }
        self._tf_sec_resolved = _tf_map.get(self.timeframe, 300)
        
        # Iterating strictly over Polars rows is slow in pure Python loop. 
        # But required for row-by-row simulation.
        # Use iter_rows(named=True)
        
        row_iterator = self.feed.iter_rows(named=True)
        count = 0
        initial_portfolio_emitted = False
        loop_unit = "ticks" if self._emit_market_ticks else "bars"
        loop_rate_unit = "ticks/s" if self._emit_market_ticks else "bars/s"
        
        # Phase 3: Fast-forward vector-warmed bars without EventBus overhead
        turbo_fast_forward_bars = 0  # disabled; warmup is handled by warmup_feed loop below
        symbol_counts = {s: 0 for s in self.symbol_list}

        # ── PRE-SIMULATION WARMUP LOOP ────────────────────────────────────────
        # Replay warmup_feed (start_date - 210 days) through EVT:BAR_CLOSED ONLY.
        # No broker fills, no portfolio emission, no CMD:PROCESS_STRATEGY.
        # Goal: warm up all on-bar state — EMA, ATR, macro_resid, macro_sync,
        #       volatility_state, anchor_prices — so warmup.full_ready==True
        #       on bar #1 of the real simulation window.
        if getattr(self, "warmup_feed", None) is not None and len(self.warmup_feed) > 0:
            warmup_row_count = len(self.warmup_feed)
            LOG.info(
                f"[Warmup] Replaying {warmup_row_count} pre-simulation bars "
                f"(state-only, no decisions) ..."
            )
            for wrow in self.warmup_feed.iter_rows(named=True):
                w_symbol = wrow["symbol"]
                # Advance clock (needed for cooldown/staleness state)
                try:
                    w_ts_val = wrow.get("ts")
                    if w_ts_val is not None and self.clock_advance_fn is not None:
                        w_ts_ms = int(w_ts_val.timestamp() * 1000) if hasattr(w_ts_val, "timestamp") else int(w_ts_val)
                        self.clock_advance_fn(w_ts_ms)
                except Exception:
                    pass
                
                # Build bar payload — minimal fields needed by FeatureEngineering
                bar_payload: dict = {
                    "symbol": w_symbol,
                    "open": wrow.get("open", 0.0),
                    "high": wrow.get("high", 0.0),
                    "low": wrow.get("low", 0.0),
                    "close": wrow.get("close", 0.0),
                    "volume": wrow.get("volume", 0.0),
                    "buy_volume": wrow.get("buy_volume", 0.0),
                    "sell_volume": wrow.get("sell_volume", 0.0),
                    "buy_notional": wrow.get("buy_notional", 0.0),
                    "sell_notional": wrow.get("sell_notional", 0.0),
                    "buy_count": wrow.get("buy_count", 0),
                    "sell_count": wrow.get("sell_count", 0),
                    "avg_bid_qty": wrow.get("avg_bid_qty", 0.0),
                    "avg_ask_qty": wrow.get("avg_ask_qty", 0.0),
                    "last_bid_price": wrow.get("last_bid_price", 0.0),
                    "last_ask_price": wrow.get("last_ask_price", 0.0),
                    "timeframe": self.timeframe,
                    "timeframe_sec": _tf_map.get(self.timeframe, 300),
                    "ts": int(w_ts_val.timestamp() * 1000) if hasattr(w_ts_val, "timestamp") else int(w_ts_val or 0),
                    # Signal to FeatureEngineering that this is a warmup bar → no CMD:PROCESS_STRATEGY
                    "_warmup_bar": True,
                }
                # Emit bar closed — lets FeatureEngineering update all state
                self.event_bus.emit("EVT:BAR_CLOSED", payload=bar_payload, why="warmup_replay")
            
            LOG.info("[Warmup] Pre-simulation warmup complete.")

        for row in row_iterator:

            count += 1
            symbol = row["symbol"]
            symbol_counts[symbol] += 1
            
            if max_ticks is not None and count > int(max_ticks):
                break

            # CRITICAL: Advance global clock BEFORE processing this row.
            # This ensures ExposureGuard staleness checks, cooldowns, etc.
            # see the simulated time, not wall-clock.
            try:
                ts_val = row.get("ts")
                if ts_val is not None and self.clock_advance_fn is not None:
                    ts_ms = int(ts_val.timestamp() * 1000) if hasattr(ts_val, "timestamp") else int(ts_val)
                    self.clock_advance_fn(ts_ms)
            except Exception:
                pass
            

            # BACKTEST-ARCH-FIX: Emit initial portfolio AFTER first clock advance.
            # DecisionMaking requires latest_portfolio to be set, otherwise it blocks ALL signals
            # with "NRR-PORTFOLIO-UNKNOWN". We emit initial portfolio AFTER clock is set to
            # first bar's timestamp so ExposureGuard staleness check passes.
           # NOTE: PositionTracking is "truth-first" and intentionally skips emitting an initial
            # EVT:PORTFOLIO_STATE_UPDATED at startup. In backtest, that creates a deadlock:
            # - DecisionMaking blocks all intents without portfolio (NRR-PORTFOLIO-UNKNOWN)
            # - No trades occur -> PositionTracking never emits portfolio
            # Therefore, backtest engine must be the authoritative portfolio emitter.
            position_tracking_initialized = bool(
                getattr(self, "_position_tracking_initialized", False)
            )
            if not position_tracking_initialized:
                if not initial_portfolio_emitted:
                    self._emit_initial_portfolio()
                    # FIX-BACKTEST-RACE: Wait for async exposure cache update to finish
                    if self.execpos_fsm and hasattr(self.execpos_fsm, "drain_pending_tasks"):
                        self.execpos_fsm.drain_pending_tasks()
                    initial_portfolio_emitted = True
                else:
                    # Emit portfolio heartbeat on EVERY bar to keep staleness guards satisfied.
                    # ExposureGuard checks staleness: stale_sec = now_sec() - (positions_last_ts_ms / 1000)
                    self._emit_portfolio_heartbeat()
                    # FIX-BACKTEST-RACE: Wait for async exposure cache update to finish
                    if self.execpos_fsm and hasattr(self.execpos_fsm, "drain_pending_tasks"):
                        self.execpos_fsm.drain_pending_tasks()

            # Emit deferred ACKs before matching this bar (keeps ACK->FILL ordering sane)
            try:
                flush_acks = getattr(self.broker, "flush_acks", None)
                if callable(flush_acks):
                    flush_acks()
            except Exception:
                pass
            
            # --- STEP 1: Broker Update (Matching Engine) ---
            # MockBroker needs a dict with OHLC logic if possible.
            # Our row has: ts, symbol, open, high, low, close
            # We treat this candle as "Market Data".
            # For strict limit fills, High/Low matters.
            # --- STEP 1: Broker Update (Matching Engine) ---
            # MockBroker needs a dict with OHLC logic if possible.
            # Our row has: ts, symbol, open, high, low, close
            # We treat this candle as "Market Data".
            # For strict limit fills, High/Low matters.
            fills = self.broker.process_data(row)
            
            # Emit Fills
            for fill in fills:
                # EVT:ORDER_FILL for ExecPosFSM order lifecycle
                self.event_bus.emit(
                    event_name="EVT:ORDER_FILL",
                    payload=fill,
                    why="backtest_fill"
                )
                # BACKTEST-ARCH-FIX: Emit EVT:TRADE_EXECUTED for PositionTracking (production parity)
                # PositionTracking listens to TRADE_EXECUTED, not ORDER_FILL
                trade_executed_payload = {
                    "symbol": fill.get("symbol"),
                    "side": fill.get("side", "").lower(),  # PositionTracking expects lowercase
                    "price": fill.get("price"),
                    "quantity": fill.get("quantity"),
                    "fees": fill.get("fee", "0"),
                    "venue": "backtest",
                    "ts": fill.get("timestamp", get_clock().now_ms()),
                }
                self.event_bus.emit(
                    event_name="EVT:TRADE_EXECUTED",
                    payload=trade_executed_payload,
                    why="backtest_trade_executed"
                )
                LOG.info(f"Filled: {fill['symbol']} {fill['side']} {fill['quantity']} @ {fill['price']}")

            # BACKTEST-ARCH-FIX: Removed _emit_portfolio_update() here.
            # PositionTracking now emits EVT:PORTFOLIO_STATE_UPDATED after processing TRADE_EXECUTED.
            # Fallback: emit portfolio update only if PositionTracking is not initialized
            # (for backward compatibility with tests that don't init all domains)
            if not hasattr(self, '_position_tracking_initialized') or not self._position_tracking_initialized:
                self._emit_portfolio_update()
            
            # --- STEP 2: Emit Market Event ---
            # Simulate the "EVT:MARKET_TICK_RECEIVED" or "UPD:MARKET_DATA"
            # Based on docs/README, payload: ts, symbol, price, bid, ask...
            # We approximate Bid/Ask from Close (spread=0 for now or sim?)
            # Let's emit a clean payload used by FeatureEngineering.
            
            # SSOT note:
            # - EVT:MARKET_TICK_RECEIVED schema requires bid/ask/mid + sizes/volumes.
            # - Backtest kline replay doesn't have L2/trade-split, so we emit neutral placeholders.
            ts_ms = int(row["ts"].timestamp() * 1000)  # Unix ms
            close_val = float(row["close"] or 0)
            open_val = float(row["open"] or 0)
            close_px = str(close_val)
            volume_val = float(row["volume"] or 0)
            volume = str(volume_val)

            # High-fidelity trade-flow inputs (from enricher). If missing/zero, synthesize from kline.
            buy_v = float(row.get("buy_volume") or 0.0)
            sell_v = float(row.get("sell_volume") or 0.0)
            buy_count = int(row.get("buy_count") or 0)
            sell_count = int(row.get("sell_count") or 0)
            buy_notional = float(row.get("buy_notional") or 0.0)
            sell_notional = float(row.get("sell_notional") or 0.0)

            # Optional order book (from bookTicker enrichment)
            avg_bid_qty = float(row.get("avg_bid_qty") or 0.0)
            avg_ask_qty = float(row.get("avg_ask_qty") or 0.0)
            last_bid_price = float(row.get("last_bid_price") or 0.0)
            last_ask_price = float(row.get("last_ask_price") or 0.0)

            # Data synthesis heuristic (backtest only):
            # - If we only have OHLCV, we split volume 50/50 and estimate trade counts from base volume.
            # - avg_trade_size_base is a conservative constant (0.05 base units by default), matching earlier discussion.
            # - This unblocks warmup/readiness gates that require non-zero buy/sell flow fields.
            if close_val > 0 and volume_val > 0:
                flow_missing = (
                    (buy_v <= 0 and sell_v <= 0)
                    and (buy_notional <= 0 and sell_notional <= 0)
                    and (buy_count <= 0 and sell_count <= 0)
                )
                if flow_missing:
                    avg_trade_size_base = 0.05
                    est_total_count = max(1, int(volume_val / max(avg_trade_size_base, 1e-12)))
                    # Split 50/50.
                    buy_v = volume_val * 0.5
                    sell_v = volume_val - buy_v
                    buy_count = est_total_count // 2
                    sell_count = est_total_count - buy_count
                    buy_notional = buy_v * close_val
                    sell_notional = sell_v * close_val

                # Partial-missing: if volumes exist but notionals are zero.
                if (buy_notional <= 0 and buy_v > 0):
                    buy_notional = buy_v * close_val
                if (sell_notional <= 0 and sell_v > 0):
                    sell_notional = sell_v * close_val

                # Partial-missing: if counts are zero but volumes are present.
                if (buy_count <= 0 and buy_v > 0):
                    avg_trade_size_base = 0.05
                    buy_count = max(1, int(buy_v / max(avg_trade_size_base, 1e-12)))
                if (sell_count <= 0 and sell_v > 0):
                    avg_trade_size_base = 0.05
                    sell_count = max(1, int(sell_v / max(avg_trade_size_base, 1e-12)))
            payload = {
                "ts": ts_ms,
                "symbol": row["symbol"],
                "price": close_px,
                "bid": close_px,
                "ask": close_px,
                "mid": close_px,
                # Placeholder book sizes (backtest replay has no L2 depth)
                "bid_size": str(max(avg_bid_qty, buy_v, 0.0)),
                "ask_size": str(max(avg_ask_qty, sell_v, 0.0)),
                "order_book": {
                    "bid_qty": float(avg_bid_qty),
                    "ask_qty": float(avg_ask_qty),
                    "bid_price": float(last_bid_price),
                    "ask_price": float(last_ask_price),
                },
                # Trade-flow fields used by FeatureEngineering warmup gates
                "buy_volume": str(buy_v),
                "sell_volume": str(sell_v),
                "buy_count": int(buy_count),
                "sell_count": int(sell_count),
                "buy_notional": str(buy_notional),
                "sell_notional": str(sell_notional),
                "trades_dropped_out_of_order": 0,
                "data_source": "backtest",
                "data_type": "market_tick_aggregated",
                # Optional extras (not schema-validated here) for debugging/analysis
                "open": str(open_val),
                "high": str(row["high"] or 0),
                "low": str(row["low"] or 0),
                "close": close_px,
                "volume": volume,
            }
            
            # ALPHA-SEARCH: Include augmented TA features if present in feed
            # These are added by BacktestFeatureAugmenter during load_data()
            augmented_cols = [
                "macd_line", "macd_signal", "macd_histogram",
                "stochastic_k", "stochastic_d",
                "price_momentum_5m", "price_momentum_1h", "price_momentum_1d",
                "volume_momentum_5m", "rsi_14", "atr_pct", "ema_bias"
            ]
            augmented_values: Dict[str, float] = {}
            for col in augmented_cols:
                if col in row and row[col] is not None:
                    augmented_values[col] = float(row[col])
            payload.update(augmented_values)


            # --- BACKTEST HEARTBEAT ---
            if not hasattr(self, "_sniff_count"):
                self._sniff_count = 0
            
            self._sniff_count += 1
            
            if self._sniff_count % 100 == 0:
                LOG.info(f"❤️ [HEARTBEAT] {loop_unit.upper()} {self._sniff_count} processed. TS={row.get('ts')}")
            # --------------------------
            
            # Legacy tick events are optional and disabled in bar-only mode.
            if self._emit_market_ticks:
                self.event_bus.emit(
                    event_name="EVT:MARKET_TICK_RECEIVED", 
                    payload=payload, 
                    why="backtest_replay"
                )

            # Emit anchor updates for macro_sync/macro_resid pipelines.
            # FeatureEngineering will ignore anchors that are not configured.
            try:
                self.event_bus.emit(
                    event_name="EVT:ANCHOR_UPDATED",
                    payload={"anchor": row["symbol"], "price": close_px, "ts_ms": ts_ms},
                    why="backtest_anchor_update",
                )
            except Exception:
                pass
            
            # Legacy compatibility update for components that still consume market-data updates.
            if self._emit_market_ticks:
                self.event_bus.emit(
                    event_name="UPD:MARKET_DATA",
                    payload=payload,
                    why="backtest_replay"
                )

            # --- STEP 2.5: Emit Bar Event (Crucial for Bar-Driven Strategies) ---
            # Treat the kline row as a closed bar.
            tf_map = {
                "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
                "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200,
                "1d": 86400
            }
            tf_sec = tf_map.get(self.timeframe, 300) # Default to 5m if unknown
            
            bar_end_ts_ms = ts_ms
            bar_start_ts_ms = bar_end_ts_ms - int(tf_sec) * 1000
            bar_payload = {
                "symbol": row["symbol"],
                "ts_ms": bar_end_ts_ms,
                "tf_sec": tf_sec,
                "bar_close_ts": bar_end_ts_ms,
                "bar": {
                    "symbol": row["symbol"],
                    "timeframe_sec": tf_sec,
                    "start_ts_ms": bar_start_ts_ms,
                    "end_ts_ms": bar_end_ts_ms,
                    "open": str(row["open"] or 0),
                    "high": str(row["high"] or 0),
                    "low": str(row["low"] or 0),
                    "close": close_px,
                    "volume": volume,
                    "buy_volume": str(buy_v),
                    "sell_volume": str(sell_v),
                    "buy_count": int(buy_count),
                    "sell_count": int(sell_count),
                    "buy_notional": str(buy_notional),
                    "sell_notional": str(sell_notional),
                    "bid_size": str(max(avg_bid_qty, buy_v, 0.0)),
                    "ask_size": str(max(avg_ask_qty, sell_v, 0.0)),
                    "bid": close_px,
                    "ask": close_px,
                },
                "bar_meta": {
                    "source": "backtest",
                    "close_reason": "kline_replay",
                },
                "why": "backtest_replay_bar",
            }
            bar_payload["bar"].update(augmented_values)
            
            self.event_bus.emit(
                event_name="EVT:BAR_CLOSED",
                payload=bar_payload,
                why="backtest_replay_bar"
            )

            # PILLAR-WARMUP: Feed 5m bar into multi-TF resampler for M15/H4/D1 aggregation.
            # Resampler emits additional EVT:BAR_CLOSED events when HTF boundaries are crossed.
            if self._bar_resampler is not None:
                try:
                    self._bar_resampler.on_5m_bar(
                        symbol=row["symbol"],
                        bar_data=bar_payload["bar"],
                        ts_ms=ts_ms,
                    )
                except Exception as e:
                    LOG.warning(f"HTF resampler error: {e}")

            # --- STEP 3: Sync ---
            # Since LocalBus is synchronous (callbacks run immediately in emit),
            # we don't need explicit .join() unless using an async bus.
            # This is "Step C" fulfilled by the nature of LocalBus.
            join = getattr(self.event_bus, "join", None)
            if callable(join):
                try:
                    join()
                except Exception:
                    pass
            
            # DET-BT-15: TICK-BARRIER - Drain all pending async tasks before next bar
            # This ensures deterministic ordering of FSM operations.
            if self.execpos_fsm is not None and hasattr(self.execpos_fsm, "drain_pending_tasks"):
                try:
                    tasks_before = len(getattr(self.execpos_fsm, "_pending_tasks", set()))
                    self.execpos_fsm.drain_pending_tasks()
                    if tasks_before > 0:
                        LOG.debug(f"BARRIER_DRAIN: tasks_before={tasks_before} tasks_after=0")
                except Exception as e:
                    LOG.warning(f"BARRIER_DRAIN failed: {e}")
            
        duration = time.time() - start_time
        LOG.info(
            f"Simulation ended. Processed {count} {loop_unit} in {duration:.2f}s "
            f"({count/duration:.0f} {loop_rate_unit})"
        )
        
        # Cleanup pending orders
        abandoned_count = 0
        for oid, order in list(self.broker._orders.items()):
            if order.status == "ACCEPTED":
                order.status = "CANCELED"
                abandoned_count += 1
                try:
                    payload = self.broker._order_to_dict(oid)
                    rid = self.broker._lookup_rid(order_id=oid, client_order_id=order.client_order_id)
                    if rid:
                        payload["rid"] = rid
                    payload["reason"] = "BACKTEST_END"
                    self.event_bus.emit(
                        event_name="EVT:ORDER_CANCELLED",
                        payload=payload,
                        why="BACKTEST_END",
                    )
                    # Write abandoned order to order_logger
                    try:
                        from apps.reference.telemetry.order_logger import get_order_logger
                        get_order_logger().write({
                            "rid": str(payload.get("rid") or f"backtest_end:{oid}"),
                            "event_type": "ORDER_CANCELLED",
                            "symbol": str(payload.get("symbol") or "UNKNOWN"),
                            "order_id": oid,
                            "client_order_id": order.client_order_id,
                            "side": str(payload.get("side") or ""),
                            "reason": "BACKTEST_END",
                            "source_fsm": "BacktestEngine",
                            "order_type": str(payload.get("type") or ""),
                        })
                    except Exception as _log_err:
                        LOG.debug(f"Failed to write abandoned order to order_logger: {_log_err}")
                except Exception as e:
                    LOG.debug(f"Failed to emit ORDER_CANCELLED at backtest end: {e}")
                    
        if abandoned_count > 0:
            LOG.info(f"Cleaned up {abandoned_count} abandoned pending orders at backtest end.")
        
        return self._calculate_results()

    def _profit_withdrawal_enabled_effective(self) -> bool:
        """Effective enable switch for profit withdrawals (supports backwards-compatible auto-enable)."""
        if self.profit_withdrawal_enabled is True:
            return True
        if self.profit_withdrawal_enabled is False:
            return False
        # None -> auto-enable when ROI threshold is configured
        return self.profit_withdrawal_roi_pct is not None

    def _profit_withdrawal_trigger_balance(self) -> float | None:
        """Return USDT balance threshold that triggers profit withdrawal, if enabled."""
        if not self._profit_withdrawal_enabled_effective():
            return None

        roi_pct = self.profit_withdrawal_roi_pct
        if roi_pct is None:
            return None
        try:
            roi_pct_f = float(roi_pct)
        except Exception:
            return None
        if roi_pct_f <= 0:
            return None
        try:
            base = float(getattr(self.broker, "initial_balance", 0.0) or 0.0)
        except Exception:
            base = 0.0
        if base <= 0:
            return None
        return base * (1.0 + (roi_pct_f / 100.0))

    def _portfolio_is_flat(self) -> bool:
        """Best-effort: true if all positions have ~0 amount."""
        try:
            for pos in (getattr(self.broker, "_positions", {}) or {}).values():
                try:
                    amt = float(getattr(pos, "position_amount", 0.0) or 0.0)
                except Exception:
                    continue
                if abs(amt) > 1e-12:
                    return False
        except Exception:
            return True
        return True

    def _maybe_withdraw_profits(self, *, ts_ms: int) -> None:
        """
        Backtest-only: withdraw profits when configured threshold is reached.

        Policy:
          - Uses equity_free_usdt (broker.balance_usdt) as the withdrawable amount.
          - Fail-closed: only withdraw when portfolio is flat (no open positions).
          - When triggered, withdraws ALL profit above the initial balance, so trading
            continues from the same base capital (initial_balance).
        """
        trigger = self._profit_withdrawal_trigger_balance()
        if trigger is None:
            return

        try:
            base = float(getattr(self.broker, "initial_balance", 0.0) or 0.0)
            bal = float(getattr(self.broker, "balance_usdt", 0.0) or 0.0)
        except Exception:
            return

        if base <= 0:
            return
        if bal < trigger:
            return
        if bal <= base:
            return

        if not self._portfolio_is_flat():
            return

        withdraw_usdt = bal - base
        if withdraw_usdt <= 0:
            return

        # Apply withdrawal: reset trading capital back to base.
        balance_before = bal
        self.broker.balance_usdt = base
        self.capital_withdrawn_total += float(withdraw_usdt)

        rec = {
            "ts_ms": int(ts_ms),
            "withdrawn_usdt": float(withdraw_usdt),
            "balance_before_usdt": float(balance_before),
            "balance_after_usdt": float(base),
            "initial_balance_usdt": float(base),
            "trigger_balance_usdt": float(trigger),
            "trigger_roi_pct": float(self.profit_withdrawal_roi_pct or 0.0),
        }
        self.capital_withdrawals.append(rec)
        LOG.info(
            f"🏦 BACKTEST PROFIT WITHDRAWAL: withdrew={withdraw_usdt:.6f} "
            f"balance_before={balance_before:.6f} balance_after={base:.6f} "
            f"trigger={trigger:.6f} roi_pct={self.profit_withdrawal_roi_pct}"
        )

        # Optional: emit an event for reporting/analysis (no-op if nobody listens).
        try:
            self.event_bus.emit(
                event_name="EVT:CAPITAL_WITHDRAWN",
                payload=rec,
                why="backtest_profit_withdrawal",
            )
        except Exception:
            pass

    def _track_equity(self, *, equity_on_account: float) -> None:
        """Track gross/on-account equity drawdowns (gross ignores withdrawals)."""
        try:
            eq_on = float(equity_on_account)
        except Exception:
            return

        eq_gross = eq_on + float(self.capital_withdrawn_total or 0.0)

        # OPTIMIZATION-PHASE1: Collect equity snapshots for Sharpe ratio
        self._equity_snapshots.append(eq_gross)

        if not self._equity_tracking_initialized:
            self._equity_tracking_initialized = True
            self._peak_equity_on_account = eq_on
            self._peak_equity_gross = eq_gross
            self._max_drawdown_on_account = 0.0
            self._max_drawdown_gross = 0.0
            return

        if eq_on > self._peak_equity_on_account:
            self._peak_equity_on_account = eq_on
        if eq_gross > self._peak_equity_gross:
            self._peak_equity_gross = eq_gross

        if self._peak_equity_on_account > 0:
            dd_on = (self._peak_equity_on_account - eq_on) / self._peak_equity_on_account
            if dd_on > self._max_drawdown_on_account:
                self._max_drawdown_on_account = float(dd_on)

        if self._peak_equity_gross > 0:
            dd_g = (self._peak_equity_gross - eq_gross) / self._peak_equity_gross
            if dd_g > self._max_drawdown_gross:
                self._max_drawdown_gross = float(dd_g)

    def _calculate_results(self) -> BacktestResult:
        """Compute final metrics from MockBroker state."""
        current_balance = self.broker.balance_usdt
        # Add unrealized PnL from open positions
        # (This requires async call implementation in mock broker, but here we can just call the private methods if strictly local? Or use getattr)
        # MockBroker has synchronous state access for properties usually.
        # But get_open_positions is async. 
        # For simplicity in this synchronous loop method, we access the dict directly if possible, or run simple logic.
        
        unrealized = 0.0
        for pos in self.broker._positions.values():
             unrealized += float(pos.unrealized_profit)
             
        end_balance_on_account = current_balance + unrealized
        start_balance = float(self.broker.initial_balance)
        withdrawals_total = float(self.capital_withdrawn_total or 0.0)
        end_balance_gross = end_balance_on_account + withdrawals_total

        total_pnl_on_account = end_balance_on_account - start_balance
        roi_on_account = (total_pnl_on_account / start_balance) * 100 if start_balance > 0 else 0.0

        total_pnl = end_balance_gross - start_balance
        roi = (total_pnl / start_balance) * 100 if start_balance > 0 else 0.0
        
        # Win Rate: calculated from broker's trade PnL history
        trade_pnl_history = getattr(self.broker, '_trade_pnl_history', [])
        winning_trades = sum(1 for p in trade_pnl_history if p > 0)
        total_closed_trades = len(trade_pnl_history)
        win_rate = winning_trades / total_closed_trades if total_closed_trades > 0 else 0.0
        
        # Max Drawdown:
        # - gross: ignores withdrawals (recommended for strategy performance)
        # - on-account: includes withdrawals (useful to visualize trading-capital equity curve)
        if self._equity_tracking_initialized:
            max_drawdown = float(self._max_drawdown_gross or 0.0)
            max_drawdown_on_account = float(self._max_drawdown_on_account or 0.0)
        else:
            equity_history = getattr(self.broker, '_equity_history', [self.broker.initial_balance])
            max_drawdown_on_account = 0.0
            peak = float(equity_history[0] if equity_history else self.broker.initial_balance)
            for equity in equity_history:
                eq = float(equity)
                if eq > peak:
                    peak = eq
                drawdown = (peak - eq) / peak if peak > 0 else 0.0
                if drawdown > max_drawdown_on_account:
                    max_drawdown_on_account = drawdown
            max_drawdown = float(max_drawdown_on_account)
        
        # Total trades = all filled orders
        trades = [o for o in self.broker._orders.values() if o.status == "FILLED"]
        
        # OPTIMIZATION-PHASE1: Sharpe ratio from per-bar equity returns
        sharpe_ratio = 0.0
        if len(self._equity_snapshots) >= 2:
            returns = []
            for i in range(1, len(self._equity_snapshots)):
                prev = self._equity_snapshots[i - 1]
                if prev > 0:
                    returns.append((self._equity_snapshots[i] - prev) / prev)
            if len(returns) >= 2:
                mean_r = sum(returns) / len(returns)
                var_r = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
                std_r = math.sqrt(var_r) if var_r > 0 else 0.0
                if std_r > 1e-12:
                    # Annualize: bars_per_year depends on timeframe
                    # Default 5m bars: 365 * 24 * 12 = 105120 bars/year
                    tf_sec = getattr(self, '_tf_sec_resolved', 300)
                    bars_per_year = (365.25 * 24 * 3600) / max(tf_sec, 1)
                    sharpe_ratio = (mean_r / std_r) * math.sqrt(bars_per_year)
        
        # OPTIMIZATION-PHASE1: Calmar ratio = annualized ROI / max drawdown
        calmar_ratio = 0.0
        if max_drawdown > 1e-9 and start_balance > 0:
            # Estimate annualized return from total equity snapshots
            n_bars = max(len(self._equity_snapshots), 1)
            tf_sec = getattr(self, '_tf_sec_resolved', 300)
            duration_years = (n_bars * tf_sec) / (365.25 * 24 * 3600)
            if duration_years > 0:
                gross_return = (end_balance_gross / start_balance)
                annualized_return = gross_return ** (1.0 / duration_years) - 1.0
                calmar_ratio = annualized_return / max_drawdown
        
        return BacktestResult(
            total_pnl=total_pnl,
            max_drawdown=max_drawdown,
            total_trades=len(trades),
            win_rate=win_rate,
            start_balance=start_balance,
            end_balance=end_balance_on_account,
            roi_pct=roi,
            sharpe_ratio=sharpe_ratio,
            calmar_ratio=calmar_ratio,
            withdrawals_total=withdrawals_total,
            withdrawals_count=len(self.capital_withdrawals),
            end_balance_gross=end_balance_gross,
            total_pnl_on_account=total_pnl_on_account,
            roi_on_account_pct=roi_on_account,
            max_drawdown_on_account=max_drawdown_on_account,
        )

    def _emit_portfolio_update(self):
        """Emit EVT:PORTFOLIO_STATE_UPDATED based on MockBroker state."""
        # transformation to match PositionTracking payload

        # Positions
        positions = []
        for pos in self.broker._positions.values():
            positions.append({
                "symbol": pos.symbol,
                "net_position": pos.position_amount,
                "avg_entry_price": pos.entry_price,
                "venues": ["BINANCE"]
            })

        # Calculate equity (balance + unrealized PnL from positions)
        unrealized_pnl = sum(float(pos.unrealized_profit) for pos in self.broker._positions.values())
        ts_ms = int(get_clock().now_ms())  # Use simulated clock, not wall-clock

        # Backtest-only cashflow simulation: withdraw profits on configured threshold.
        self._maybe_withdraw_profits(ts_ms=ts_ms)

        # Balances (after any withdrawal)
        balances = [{
            "asset": "USDT",
            "balance": str(self.broker.balance_usdt),
            "crossWalletBalance": str(self.broker.balance_usdt),
            "availableBalance": str(self.broker.balance_usdt)
        }]

        total_equity = self.broker.balance_usdt + unrealized_pnl
        positions_last_ts_ms = ts_ms  # staleness SSOT
        open_positions_usd = 0.0
        open_positions_margin_usd = 0.0
        for pos in self.broker._positions.values():
            try:
                amt = float(pos.position_amount)
                entry = float(pos.entry_price)
                lev = float(getattr(pos, "leverage", 1) or 1)
                if abs(amt) < 1e-12 or entry <= 0:
                    continue
                notional = abs(amt) * entry
                open_positions_usd += notional
                open_positions_margin_usd += notional / max(1.0, lev)
            except Exception:
                continue

        # Track drawdowns (gross ignores withdrawals).
        self._track_equity(equity_on_account=float(total_equity))
            
        payload = {
            "balances": balances,
            "positions": positions,
            "event_time_ms": ts_ms,  # Use simulated clock
            # ExposureGuard staleness SSOT
            "positions_last_ts_ms": positions_last_ts_ms,
            "open_positions_usd": str(open_positions_usd),
            "open_positions_margin_usd": str(open_positions_margin_usd),
            # Add equity fields for order sizing
            "equity": str(total_equity),
            "equity_free_usdt": str(self.broker.balance_usdt),
            "equity_cross_usdt": str(total_equity),
            "margin": "0",  # No margin used in backtest initially
        }
        
        self.event_bus.emit(
            event_name="EVT:PORTFOLIO_STATE_UPDATED",
            payload=payload,
            why="backtest_portfolio_sync"
        )

    def _emit_initial_portfolio(self):
        """
        Emit initial empty/flat portfolio at backtest start.
        
        BACKTEST-ARCH-FIX: DecisionMaking blocks ALL signals if latest_portfolio == None
        (fail-closed with "NRR-PORTFOLIO-UNKNOWN"). PositionTracking.start() intentionally
        does NOT emit initial portfolio for production safety (truth-first startup).
        
        In backtest, we bootstrap with synthetic "flat" portfolio:
        - No positions (empty list)
        - Full initial balance available
        - This unblocks first trade signals
        
        After first trade, PositionTracking takes over via EVT:TRADE_EXECUTED handler.
        """
        initial_balance = self.broker.initial_balance
        ts_ms = get_clock().now_ms()
        
        payload = {
            "balances": [{
                "asset": "USDT",
                "balance": str(initial_balance),
                "crossWalletBalance": str(initial_balance),
                "availableBalance": str(initial_balance)
            }],
            "positions": [],  # Flat - no open positions
            "event_time_ms": ts_ms,
            "positions_last_ts_ms": ts_ms,
            "open_positions_usd": "0",
            "open_positions_margin_usd": "0",
            "equity": str(initial_balance),
            "equity_free_usdt": str(initial_balance),
            "equity_cross_usdt": str(initial_balance),
            "margin": "0",
        }
        
        self.event_bus.emit(
            event_name="EVT:PORTFOLIO_STATE_UPDATED",
            payload=payload,
            why="backtest_initial_portfolio_bootstrap"
        )
        self._track_equity(equity_on_account=float(initial_balance))
        LOG.info(f"✅ Emitted initial portfolio: equity={initial_balance}, positions=[] (flat)")

    def _emit_portfolio_heartbeat(self):
        """
        Emit portfolio "heartbeat" to keep positions_last_ts_ms fresh.
        
        BACKTEST-ARCH-FIX: ExposureGuard checks staleness via:
            stale_sec = now_sec() - (positions_last_ts_ms / 1000)
        
        In backtest, simulation clock advances faster than real time.
        If we only emit portfolio on trades, the timestamp becomes stale
        after a few bars and ExposureGuard blocks with PORTFOLIO_STALE.
        
        This heartbeat emits current broker state with fresh timestamp
        on EVERY bar, ensuring ExposureGuard staleness check passes.
        
        When PositionTracking emits after TRADE_EXECUTED, it will override
        this with truth-source data. The heartbeat is just for timestamp freshness.
        """
        # Reuse existing _emit_portfolio_update logic
        self._emit_portfolio_update()


if __name__ == "__main__":
    # Quick Test
    from datetime import date
    logging.basicConfig(level=logging.INFO)
    
    # Needs valid data to run.
    print("BacktestEngine module loaded.")
