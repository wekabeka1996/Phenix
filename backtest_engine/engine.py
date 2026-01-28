"""
Backtest Engine Core
====================

The "Time Machine" that simulates market history and orchestrates:
1. Data Replay (Polars)
2. MockBroker Execution (Limit/Market orders)
3. Event Emission (EventBus)
4. Strategy Synchronization
"""
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
    from apps.reference.orchestrator.utils_event_bus import LocalBus
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
        clock_advance_fn: Any = None  # Callback to advance global clock: fn(ts_ms: int) -> None
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.symbol_list = symbol_list
        self.timeframe = timeframe
        self.data_dir = Path(data_dir)
        self.event_bus = event_bus if event_bus else LocalBus()
        self.clock_advance_fn = clock_advance_fn  # For backtest timebase synchronization
        
        # Initialize Mock Broker
        self.broker = MockBroker(initial_balance_usdt=initial_balance)
        
        # DET-BT-15: Direct reference to ExecPosFSM for tick-barrier sync
        self.execpos_fsm = None
        
        # Data storage
        self.feed: Optional[pl.DataFrame] = None

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
                
                start_ts = datetime.combine(self.start_date, datetime.min.time()) if isinstance(self.start_date, date) and not isinstance(self.start_date, datetime) else self.start_date
                end_ts = datetime.combine(self.end_date, datetime.max.time()) if isinstance(self.end_date, date) and not isinstance(self.end_date, datetime) else self.end_date
                
                q = q.filter(
                    (pl.col("open_time") >= start_ts) & 
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
                
                frames.append(q.collect(streaming=True))  # Materialize per symbol
            except Exception as e:
                LOG.error(f"Error loading {symbol}: {e}")
                
        if not frames:
            raise ValueError("No data loaded!")
            
        # Merge and sort
        full_df = pl.concat(frames)
        full_df = full_df.sort("ts")
        
        self.feed = full_df
        LOG.info(f"Data ready: {len(self.feed)} rows.")

    def run(self, *, max_ticks: int | None = None) -> BacktestResult:
        """
        Execute the Simulation Loop.
        """
        if self.feed is None:
            self.load_data()
            
        LOG.info("Starting Backtest Simulation...")
        start_time = time.time()
        
        # Iterating strictly over Polars rows is slow in pure Python loop. 
        # But required for row-by-row simulation.
        # Use iter_rows(named=True)
        
        row_iterator = self.feed.iter_rows(named=True)
        count = 0
        initial_portfolio_emitted = False
        
        for row in row_iterator:
            count += 1
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
                    initial_portfolio_emitted = True
                else:
                    # Emit portfolio heartbeat on EVERY bar to keep staleness guards satisfied.
                    # ExposureGuard checks staleness: stale_sec = now_sec() - (positions_last_ts_ms / 1000)
                    self._emit_portfolio_heartbeat()

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

            # --- DEBUG SNIFFER START ---
            if not hasattr(self, "_sniff_count"):
                self._sniff_count = 0

            if self._sniff_count < 5:
                LOG.warning(f"🔍 [SNIFFER] TICK {self._sniff_count} RAW ROW: {row}")
                LOG.warning(f"🔍 [SNIFFER] TICK {self._sniff_count} PAYLOAD OrderBook: {payload.get('order_book')}")
                LOG.warning(
                    f"🔍 [SNIFFER] TICK {self._sniff_count} PAYLOAD Vol: {payload.get('buy_volume')} / {payload.get('sell_volume')}"
                )
                self._sniff_count += 1
            # --- DEBUG SNIFFER END ---
            
            # Emit to Bus
            # We use a standard topic. "market_data" usually emits EVT:MARKET_TICK_RECEIVED
            # But the FSM Manage we saw listens to UPD:MARKET_DATA or similar? 
            # The doc says "EVT:MARKET_TICK_RECEIVED".
            # Let's emit that.
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
            
            # Also emit "UPD:MARKET_DATA" if needed by some legacy components?
            # Safe to emit both if cheap.
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
                },
                "bar_meta": {
                    "source": "backtest",
                    "close_reason": "kline_replay",
                },
                "why": "backtest_replay_bar",
            }
            
            self.event_bus.emit(
                event_name="EVT:BAR_CLOSED",
                payload=bar_payload,
                why="backtest_replay_bar"
            )

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
        LOG.info(f"Simulation ended. Processed {count} ticks in {duration:.2f}s ({count/duration:.0f} ticks/s)")
        
        return self._calculate_results()

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
             
        total_balance = current_balance + unrealized
        pnl = total_balance - self.broker.initial_balance
        roi = (pnl / self.broker.initial_balance) * 100
        
        # Win Rate: calculated from broker's trade PnL history
        trade_pnl_history = getattr(self.broker, '_trade_pnl_history', [])
        winning_trades = sum(1 for p in trade_pnl_history if p > 0)
        total_closed_trades = len(trade_pnl_history)
        win_rate = winning_trades / total_closed_trades if total_closed_trades > 0 else 0.0
        
        # Max Drawdown: calculated from broker's equity history
        equity_history = getattr(self.broker, '_equity_history', [self.broker.initial_balance])
        max_drawdown = 0.0
        peak = equity_history[0] if equity_history else self.broker.initial_balance
        for equity in equity_history:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak if peak > 0 else 0.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # Total trades = all filled orders
        trades = [o for o in self.broker._orders.values() if o.status == "FILLED"]
        
        return BacktestResult(
            total_pnl=pnl,
            max_drawdown=max_drawdown,
            total_trades=len(trades),
            win_rate=win_rate,
            start_balance=self.broker.initial_balance,
            end_balance=total_balance,
            roi_pct=roi
        )

    def _emit_portfolio_update(self):
        """Emit EVT:PORTFOLIO_STATE_UPDATED based on MockBroker state."""
        # transformation to match PositionTracking payload
        
        # Balances
        balances = [{
            "asset": "USDT",
            "balance": str(self.broker.balance_usdt),
            "crossWalletBalance": str(self.broker.balance_usdt),
            "availableBalance": str(self.broker.balance_usdt)
        }]
        
        # Positions
        positions = []
        for pos in self.broker._positions.values():
            positions.append({
                "symbol": pos.symbol,
                "positionAmt": pos.position_amount,
                # ExposureGuard SSOT keys
                "net_position": pos.position_amount,
                "entryPrice": pos.entry_price,
                "avg_entry_price": pos.entry_price,
                "markPrice": pos.mark_price,
                "unrealizedProfit": pos.unrealized_profit,
                "leverage": str(pos.leverage),
                "marginType": pos.margin_type,
                "isolatedMargin": str(pos.isolated_margin),
                "positionSide": pos.position_side
            })
        # Calculate equity (balance + unrealized PnL from positions)
        unrealized_pnl = sum(float(pos.unrealized_profit) for pos in self.broker._positions.values())
        total_equity = self.broker.balance_usdt + unrealized_pnl
        positions_last_ts_ms = get_clock().now_ms()  # Use simulated clock, not wall-clock
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
            
        payload = {
            "balances": balances,
            "positions": positions,
            "event_time_ms": get_clock().now_ms(),  # Use simulated clock
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
