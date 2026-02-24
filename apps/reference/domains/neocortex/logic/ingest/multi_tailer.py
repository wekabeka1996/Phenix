"""
Multi-Source Tailer

Unified tailer that reads from multiple Aurora log sources simultaneously:
1. Feature Logs (logs/features/*.log) - Market state (S)
2. Order Logs (logs/order_log_v1.jsonl) - Actions (A)
3. Core Logs (logs/aurora_core.log) - Rewards/Outcomes (R)

This enables proper RL training with (State, Action, Reward) tuples.

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                       MultiTailer                               │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
    │  │FeatureStream │  │ OrderStream  │  │  CoreStream  │          │
    │  │logs/features/│  │order_log.json│  │aurora_core.lo│          │
    │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
    │         │                 │                 │                  │
    │         └────────────┬────┴─────────────────┘                  │
    │                      ▼                                         │
    │              ┌──────────────┐                                  │
    │              │EpisodeBuilder│                                  │
    │              │ (correlate)  │                                  │
    │              └──────┬───────┘                                  │
    │                     ▼                                          │
    │              Handler (Adapter)                                  │
    └─────────────────────────────────────────────────────────────────┘
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from glob import glob
from contextlib import asynccontextmanager
from typing import Callable, Awaitable, Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import defaultdict

try:
    import aiofiles  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    aiofiles = None

from .parsers import (
    FeatureLogEntry, parse_feature_log_line,
    OrderLogEntry, OrderEventType, parse_order_log_line,
    CoreLogEntry, CoreEventType, parse_core_log_line,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _aio_open(path: Path, mode: str):
    """
    Async file open. Prefers aiofiles; falls back to asyncio.to_thread(open).
    """
    open_kwargs: Dict[str, Any] = {}
    if "b" not in mode:
        # Windows default codepage may fail on mixed-encoding logs.
        open_kwargs = {"encoding": "utf-8", "errors": "replace"}

    if aiofiles is not None:
        # type: ignore[attr-defined]
        async with aiofiles.open(path, mode, **open_kwargs) as f:
            yield f
        return

    f = await asyncio.to_thread(open, path, mode, **open_kwargs)

    class _AsyncFile:
        def __init__(self, file_obj):
            self._f = file_obj

        async def seek(self, *args):
            return await asyncio.to_thread(self._f.seek, *args)

        async def tell(self):
            return await asyncio.to_thread(self._f.tell)

        async def read(self):
            return await asyncio.to_thread(self._f.read)

        async def write(self, data):
            return await asyncio.to_thread(self._f.write, data)

        async def readline(self):
            return await asyncio.to_thread(self._f.readline)

    try:
        yield _AsyncFile(f)
    finally:
        await asyncio.to_thread(f.close)


@dataclass
class Episode:
    """
    A complete (State, Action, Reward) episode for RL training.
    """
    symbol: str
    timestamp: float

    # State: Market features at decision time
    features: Dict[str, float] = field(default_factory=dict)

    # Action: Order intent
    side: Optional[str] = None  # BUY or SELL
    quantity: Optional[float] = None
    order_type: str = "UNKNOWN"
    rejected: bool = False
    reject_reason: Optional[str] = None

    # Reward: Outcome
    reward: Optional[float] = 0.0
    pnl: Optional[float] = None
    position_closed: bool = False


@dataclass
class MultiSourceConfig:
    """Configuration for multi-source tailing."""
    enabled: bool = True

    # Log paths
    features_dir: Path = Path("logs/features")
    orders_file: Path = Path("logs/order_log_v1.jsonl")
    core_log: Path = Path("logs/aurora_core.log")

    # Processing
    batch_size: int = 100
    poll_interval: float = 0.1
    max_feature_lines_total_per_cycle: int = 1000
    max_feature_lines_per_symbol_per_cycle: int = 200
    max_order_lines_per_cycle: int = 500
    max_core_lines_per_cycle: int = 500

    # Symbol mapping
    symbols: List[str] = field(default_factory=lambda: [
                               "BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"])


class MultiTailer:
    """
    Multi-source log tailer for synchronized ingestion.

    Reads features, orders, and core events, correlating them
    into complete episodes for RL training.

    Reward policy in R2: Structured only (no equity-delta fallback).
    """

    REWARD_SCALE = 10.0

    def __init__(
        self,
        config: MultiSourceConfig,
        feature_handler: Callable[[Dict[str, Any]], Awaitable[None]],
        episode_handler: Optional[Callable[[Episode], Awaitable[None]]] = None,
        state_path: Optional[Path] = None,
        run_mode: str = "live"
    ):
        """
        Args:
            config: MultiSourceConfig with log paths
            feature_handler: Handler for feature events (passed to adapter)
            episode_handler: Optional handler for complete episodes
            state_path: Path to persist tailer state
            run_mode: "live" or "backtest" (modifies path resolution)
        """
        self.config = config
        self.run_mode = run_mode
        self._resolve_paths()

        self.feature_handler = feature_handler
        self.episode_handler = episode_handler
        self.state_path = state_path or Path("data/multi_tailer_state.json")

        # State
        self._running = False
        self._offsets: Dict[str, int] = {}  # file -> byte offset

        # Market state per symbol
        self._market_state: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._last_feature_ts: Dict[str, float] = defaultdict(float)

        # Pending episodes (waiting for reward/close)
        # symbol -> latest episode
        self._pending_episodes: Dict[str, Episode] = {}

        # Equity timeline retained for diagnostics (not used for reward fallback in R2).
        self._equity_history: List[tuple] = []  # [(ts, equity), ...]
        # symbol -> equity at order placement
        self._equity_at_entry: Dict[str, float] = {}
        self._last_equity: float = 0.0

        # Stats
        self._features_processed = 0
        self._orders_processed = 0
        self._episodes_completed = 0

    def _resolve_paths(self):
        """Resolve log paths based on run_mode."""
        if self.run_mode != "backtest":
            return

        logger.info(
            "Running in BACKTEST mode - Routing paths to logs/backtests/...")

        # 1. Features (still use base logs/ for now - backtest doesn't generate separate features)
        # self.config.features_dir = Path("logs/backtests/features")

        # 2. Core Log (backtest uses main log)
        # self.config.core_log = Path("logs/backtests/aurora_core.log")

        # 3. Order Log (dynamic resolution)
        # Find latest order_log_*.jsonl in logs/backtests/ (with 's'!)
        try:
            order_logs = sorted(glob("logs/backtests/order_log_*.jsonl"))
            if order_logs:
                latest_log = Path(order_logs[-1])
                self.config.orders_file = latest_log
                logger.info(
                    f"Resolved latest backtest order log: {latest_log}")
            else:
                logger.warning(
                    "No backtest order logs found in logs/backtests/")
        except Exception as e:
            logger.error(f"Failed to resolve backtest order logs: {e}")

    async def load_state(self) -> bool:
        """Load persisted offsets."""
        try:
            if self.state_path.exists():
                async with _aio_open(self.state_path, "r") as f:
                    data = json.loads(await f.read())
                self._offsets = data.get("offsets", {})
                logger.info(
                    f"Loaded multi-tailer state: {len(self._offsets)} offsets")
                return True
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
        return False

    async def save_state(self) -> bool:
        """Persist offsets."""
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            async with _aio_open(self.state_path, "w") as f:
                await f.write(json.dumps({"offsets": self._offsets}, indent=2))
            return True
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return False

    async def run(self):
        """Main async loop."""
        if not self.config.enabled:
            logger.info("MultiTailer disabled")
            return

        self._running = True
        await self.load_state()

        logger.info("Starting MultiTailer...")
        logger.info(f"  Features: {self.config.features_dir}")
        logger.info(f"  Orders: {self.config.orders_file}")
        logger.info(f"  Core: {self.config.core_log}")

        # DEBUG: Show if files exist
        logger.info(
            f"  DEBUG: Features dir exists = {self.config.features_dir.exists()}")
        logger.info(
            f"  DEBUG: Orders file exists = {self.config.orders_file.exists()}")
        logger.info(
            f"  DEBUG: Core log exists = {self.config.core_log.exists()}")
        if self.config.features_dir.exists():
            feature_files = list(self.config.features_dir.glob("*.log"))
            logger.info(
                f"  DEBUG: Feature files found = {[f.name for f in feature_files]}")

        # Initial stats logging
        last_log_time = 0

        try:
            while self._running:
                # Process all streams with fairness quotas per cycle.
                await self._process_features()
                await asyncio.sleep(0)
                await self._process_orders()
                await asyncio.sleep(0)
                await self._process_core()
                await asyncio.sleep(0)

                # Periodic progress log (every 5 seconds)
                now = time.time()
                if now - last_log_time > 5:
                    feature_backlog_bytes = self._calculate_features_backlog_bytes()
                    orders_backlog_bytes = self._calculate_file_backlog_bytes(
                        self.config.orders_file)
                    core_backlog_bytes = self._calculate_file_backlog_bytes(
                        self.config.core_log)
                    logger.info(
                        f"Progress: Features={self._features_processed} "
                        f"Orders={self._orders_processed} "
                        f"Episodes={self._episodes_completed} "
                        f"PendingEpisodes={len(self._pending_episodes)} "
                        f"MarketState={len(self._market_state)} symbols "
                        f"BacklogBytes(F={feature_backlog_bytes},O={orders_backlog_bytes},C={core_backlog_bytes})"
                    )
                    last_log_time = now

                    # TASK (Optimization): Cleanup stale episodes
                    self._cleanup_stale_episodes(now)

                # Yield to event loop
                await asyncio.sleep(self.config.poll_interval)

        except asyncio.CancelledError:
            logger.info("MultiTailer cancelled")
        finally:
            await self.save_state()
            self._running = False
            logger.info(
                f"MultiTailer stopped: features={self._features_processed}, "
                f"orders={self._orders_processed}, episodes={self._episodes_completed}"
            )

    async def _process_features(self):
        """Process feature log files."""
        features_dir = self.config.features_dir

        if not features_dir.exists():
            return

        total_quota = max(
            1, int(self.config.max_feature_lines_total_per_cycle))
        per_symbol_quota = max(
            1, int(self.config.max_feature_lines_per_symbol_per_cycle))

        active_symbols: List[str] = []
        for symbol in self.config.symbols:
            log_file = features_dir / f"{symbol}.log"
            if not log_file.exists():
                continue
            offset = self._offsets.get(str(log_file), 0)
            file_size = log_file.stat().st_size
            if offset < file_size:
                active_symbols.append(symbol)

        if not active_symbols:
            return

        remaining = total_quota
        made_progress = True
        while remaining > 0 and made_progress:
            made_progress = False
            for symbol in active_symbols:
                if remaining <= 0:
                    break

                log_file = features_dir / f"{symbol}.log"
                if not log_file.exists():
                    continue
                offset = self._offsets.get(str(log_file), 0)
                file_size = log_file.stat().st_size
                if offset >= file_size:
                    continue

                lines_budget = min(per_symbol_quota, remaining)
                lines_read = await self._tail_feature_file(
                    log_file,
                    symbol,
                    max_lines=lines_budget,
                )
                if lines_read > 0:
                    made_progress = True
                    remaining -= lines_read
                    await asyncio.sleep(0)

    async def _tail_feature_file(
        self,
        file_path: Path,
        symbol: str,
        max_lines: Optional[int] = None,
    ) -> int:
        """Tail a single feature log file."""
        offset = self._offsets.get(str(file_path), 0)
        batch_count = 0
        lines_processed = 0

        try:
            async with _aio_open(file_path, "r") as f:
                await f.seek(offset)

                while max_lines is None or lines_processed < max_lines:
                    line = await f.readline()
                    if not line:
                        break
                    lines_processed += 1

                    # Pass symbol for pure JSON format
                    entry = parse_feature_log_line(line, symbol=symbol)

                    if entry:
                        # Update market state
                        self._market_state[symbol] = entry.features
                        self._last_feature_ts[symbol] = entry.timestamp

                        # Send to handler (adapter)
                        await self.feature_handler({
                            "timestamp": entry.timestamp,
                            "symbol": symbol,
                            "features": entry.features
                        })

                        self._features_processed += 1
                        batch_count += 1

                        # Log first feature per symbol
                        if self._features_processed == 1 or self._features_processed % 1000 == 0:
                            logger.info(
                                f"Feature #{self._features_processed}: {symbol} ts={entry.timestamp:.0f}")

                        if batch_count >= self.config.batch_size:
                            await asyncio.sleep(0.001)
                            batch_count = 0

                    self._offsets[str(file_path)] = await f.tell()

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
        return lines_processed

    async def _process_orders(self):
        """Process order log file."""
        orders_file = self.config.orders_file

        if not orders_file.exists():
            return

        offset = self._offsets.get(str(orders_file), 0)
        file_size = orders_file.stat().st_size

        if offset >= file_size:
            return

        try:
            async with _aio_open(orders_file, "r") as f:
                await f.seek(offset)
                max_lines = max(1, int(self.config.max_order_lines_per_cycle))
                lines_processed = 0

                while lines_processed < max_lines:
                    line = await f.readline()
                    if not line:
                        break
                    lines_processed += 1

                    entry = parse_order_log_line(line)

                    if entry:
                        await self._handle_order_event(entry)
                        self._orders_processed += 1

                    self._offsets[str(orders_file)] = await f.tell()

        except Exception as e:
            logger.error(f"Error processing orders: {e}")

    async def _handle_order_event(self, order: OrderLogEntry):
        """Handle an order event, creating/updating episodes."""
        symbol = order.symbol

        if order.event_type == OrderEventType.PLACED:
            # Snapshot equity at entry time for diagnostics.
            self._equity_at_entry[symbol] = self._last_equity

            # Create new episode with current market state
            episode = Episode(
                symbol=symbol,
                timestamp=order.timestamp,
                features=dict(self._market_state.get(symbol, {})),
                side=order.side,
                quantity=order.quantity,
                order_type="ENTRY" if order.is_entry else "EXIT",
                rejected=False
            )
            self._pending_episodes[symbol] = episode
            logger.info(
                f"ORDER_PLACED: {symbol} {order.side} qty={order.quantity}")

        elif order.event_type == OrderEventType.REJECTED:
            # Create rejected episode
            episode = Episode(
                symbol=symbol,
                timestamp=order.timestamp,
                features=dict(self._market_state.get(symbol, {})),
                side=order.side,
                rejected=True,
                reject_reason=order.nrr_code,
                reward=-0.001  # Small penalty for rejection
            )

            if self.episode_handler:
                await self.episode_handler(episode)
            self._episodes_completed += 1
            logger.info(
                f"ORDER_REJECTED: {symbol} {order.side} reason={order.nrr_code}")

        elif order.event_type == OrderEventType.CANCELLED:
            # Handle cancelled orders (e.g., regime change cancellations in backtest).
            # A cancellation means the agent committed to an action but it was never
            # executed — no state transition occurred.  Training on this as a full
            # episode with reward=0.0 is dangerous because:
            #   1. It contributes zero-variance advantages that can trigger NaN in PPO
            #      (adv.std() == 0 → division by zero in normalization).
            #   2. It's pure noise: the market gave no feedback, so there's nothing to
            #      learn from this specific (S, A) pair.
            #
            # Policy decision: apply a small negative penalty to discourage
            # indecisive behaviour, but SKIP episode delivery when no market features
            # were captured (no state to learn from).
            if symbol in self._pending_episodes:
                episode = self._pending_episodes.pop(symbol)
                reason = order.raw.get("reason", "UNKNOWN")

                has_features = bool(episode.features)
                if has_features:
                    # Small penalty to discourage timeout/cancelled orders.
                    episode.reward = -0.001
                    episode.position_closed = True

                    if self.episode_handler:
                        await self.episode_handler(episode)
                    self._episodes_completed += 1
                    logger.info(
                        "ORDER_CANCELLED: %s reason=%s (episode with penalty=-0.001)",
                        symbol, reason,
                    )
                else:
                    # No features attached → no useful (S,A,R) tuple.  Drop silently.
                    logger.info(
                        "ORDER_CANCELLED: %s reason=%s (dropped — no features/state captured)",
                        symbol, reason,
                    )

    async def _process_core(self):
        """Process core log for position closes and equity updates."""
        core_log = self.config.core_log

        if not core_log.exists():
            return

        offset = self._offsets.get(str(core_log), 0)
        file_size = core_log.stat().st_size

        if offset > file_size:
            logger.warning(
                f"Core log appears truncated/rotated; resetting offset from {offset} to 0 "
                f"(file_size={file_size}, path={core_log})"
            )
            offset = 0
            self._offsets[str(core_log)] = 0

        if offset >= file_size:
            return

        try:
            async with _aio_open(core_log, "r") as f:
                await f.seek(offset)
                max_lines = max(1, int(self.config.max_core_lines_per_cycle))
                lines_processed = 0

                while lines_processed < max_lines:
                    line = await f.readline()
                    if not line:
                        break
                    lines_processed += 1

                    entry = parse_core_log_line(line)

                    if entry:
                        if entry.event_type == CoreEventType.POSITION_CLOSED:
                            await self._handle_position_close(entry)
                        elif entry.event_type == CoreEventType.EQUITY_UPDATE:
                            # TASK-R1: Track equity for PnL estimation
                            if entry.equity is not None:
                                self._last_equity = entry.equity
                                self._equity_history.append(
                                    (entry.timestamp, entry.equity))
                                # Keep only last 100 snapshots
                                if len(self._equity_history) > 100:
                                    self._equity_history = self._equity_history[-100:]

                    self._offsets[str(core_log)] = await f.tell()

        except Exception as e:
            logger.error(f"Error processing core log: {e}")

    async def _handle_position_close(self, core_entry: CoreLogEntry):
        """Handle position close, completing pending episode with structured reward only."""
        symbol = core_entry.symbol

        if symbol in self._pending_episodes:
            episode = self._pending_episodes.pop(symbol)
            episode.position_closed = True
            self._equity_at_entry.pop(symbol, None)

            structured_pnl = core_entry.realized_pnl_net
            if structured_pnl is None:
                episode.reward = None
                episode.pnl = None
                logger.warning(
                    "WARN:NO_STRUCTURED_REWARD_RECEIVED symbol=%s trade_id=%s close_ts_ms=%s",
                    symbol,
                    core_entry.trade_id,
                    core_entry.close_ts_ms,
                )
            else:
                import numpy as np

                normalized_reward = float(
                    np.tanh(float(structured_pnl) / self.REWARD_SCALE))
                episode.pnl = float(structured_pnl)
                episode.reward = normalized_reward
                logger.debug(
                    "Structured reward applied: symbol=%s pnl=%s reward=%s trade_id=%s",
                    symbol,
                    structured_pnl,
                    normalized_reward,
                    core_entry.trade_id,
                )

            if self.episode_handler:
                await self.episode_handler(episode)
            self._episodes_completed += 1

            logger.info(
                "EPISODE COMPLETE: %s side=%s trade_id=%s close_ts_ms=%s pnl=%s reward=%s",
                symbol,
                episode.side,
                core_entry.trade_id,
                core_entry.close_ts_ms,
                episode.pnl,
                episode.reward,
            )

    async def handle_position_closed_event(self, payload: Dict[str, Any]) -> None:
        """
        Handle EVT:POSITION_CLOSED payload directly (event-bus contract path).

        This is a contract-level ingestion path that bypasses core log parsing but
        reuses the same close/reward logic as _handle_position_close().
        """
        symbol_raw = payload.get("symbol")
        symbol = str(symbol_raw).strip() if symbol_raw is not None else ""
        if not symbol:
            logger.warning(
                "Ignoring EVT:POSITION_CLOSED without symbol: %s", payload)
            return

        close_ts_ms_raw = payload.get("close_ts_ms")
        close_ts_ms: Optional[int]
        try:
            close_ts_ms = int(
                close_ts_ms_raw) if close_ts_ms_raw is not None else None
        except (TypeError, ValueError):
            close_ts_ms = None

        realized_pnl_net_raw = payload.get("realized_pnl_net")
        try:
            realized_pnl_net = (
                float(realized_pnl_net_raw)
                if realized_pnl_net_raw is not None
                else None
            )
        except (TypeError, ValueError):
            realized_pnl_net = None

        fees_raw = payload.get("fees")
        try:
            fees = float(fees_raw) if fees_raw is not None else None
        except (TypeError, ValueError):
            fees = None

        event_ts = (
            (float(close_ts_ms) / 1000.0)
            if close_ts_ms is not None
            else float(payload.get("timestamp", 0.0) or 0.0)
        )
        if event_ts <= 0.0:
            event_ts = time.time()

        entry = CoreLogEntry(
            timestamp=event_ts,
            timestamp_str="",
            event_type=CoreEventType.POSITION_CLOSED,
            symbol=symbol,
            realized_pnl_net=realized_pnl_net,
            trade_id=str(payload.get("trade_id")) if payload.get(
                "trade_id") is not None else None,
            close_ts_ms=close_ts_ms,
            fees=fees,
            raw_line="EVT:POSITION_CLOSED",
        )
        await self._handle_position_close(entry)

    def stop(self):
        """Stop tailing."""
        self._running = False
        # State is persisted in the async run() finalizer.

    @property
    def stats(self) -> Dict[str, Any]:
        """Get tailer statistics."""
        return {
            "features_processed": self._features_processed,
            "orders_processed": self._orders_processed,
            "episodes_completed": self._episodes_completed,
            "pending_episodes": len(self._pending_episodes),
            "running": self._running,
            "offsets": dict(self._offsets)
        }

    @property
    def market_state(self) -> Dict[str, Dict[str, float]]:
        """Current market state per symbol."""
        return dict(self._market_state)

    def _cleanup_stale_episodes(self, current_time: float, ttl: float = 3600.0):
        """
        Cleanup pending episodes that exceeded TTL (e.g. orphan orders never closed).
        Prevent indefinite memory growth.
        """
        expired = []
        for symbol, episode in self._pending_episodes.items():
            if current_time - episode.timestamp > ttl:
                expired.append(symbol)

        for symbol in expired:
            del self._pending_episodes[symbol]
            logger.warning(
                f"Cleaned up stale episode for {symbol} (Age > {ttl}s)")

    def _calculate_file_backlog_bytes(self, file_path: Path) -> int:
        if not file_path.exists():
            return 0
        try:
            size = file_path.stat().st_size
            offset = self._offsets.get(str(file_path), 0)
            return max(0, int(size - offset))
        except Exception:
            return 0

    def _calculate_features_backlog_bytes(self) -> int:
        if not self.config.features_dir.exists():
            return 0
        backlog = 0
        for symbol in self.config.symbols:
            log_file = self.config.features_dir / f"{symbol}.log"
            backlog += self._calculate_file_backlog_bytes(log_file)
        return backlog
