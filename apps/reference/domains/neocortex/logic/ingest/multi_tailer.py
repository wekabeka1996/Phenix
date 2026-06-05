# QUARANTINED: legacy_runtime
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
__quarantined__ = True

import asyncio
import json
import logging
import time
from pathlib import Path
from glob import glob
from contextlib import asynccontextmanager
from typing import Callable, Awaitable, Dict, Any, Optional, List, Literal
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
class EpisodeReward:
    """Canonical structured reward contract for one resolved episode close."""
    episode_id: str
    trade_id: str
    symbol: str
    side: str
    entry_ts_ms: int
    close_ts_ms: int
    duration_ms: int
    entry_price: Optional[float]
    close_price: Optional[float]
    quantity: Optional[float]
    realized_pnl: Optional[float]
    fees: Optional[float]
    net_pnl: Optional[float]
    entry_event: str
    close_event: str
    reward_complete: bool


@dataclass
class Episode:
    """
    A complete (State, Action, Reward) episode for RL training.
    """
    symbol: str
    timestamp: float
    event_ts_ms: Optional[int] = None
    episode_id: Optional[str] = None

    # Canonical lifecycle identity (P2)
    lifecycle_id: Optional[str] = None
    trade_id: Optional[str] = None
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    lifecycle_state: str = "NEW"
    entry_anchor_event: Optional[str] = None
    executed_entry: bool = False
    placed_event_ts_ms: Optional[int] = None
    close_event_ts_ms: Optional[int] = None
    fill_count: int = 0
    filled_quantity: float = 0.0
    priced_fill_quantity: float = 0.0
    entry_price: Optional[float] = None
    unresolved_reason: Optional[str] = None

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
    reward_complete: bool = False
    episode_reward: Optional[EpisodeReward] = None

    def __post_init__(self):
        if self.event_ts_ms is None and self.timestamp > 0.0:
            self.event_ts_ms = int(round(self.timestamp * 1000.0))
        if self.placed_event_ts_ms is None and self.lifecycle_state == "PLACED":
            self.placed_event_ts_ms = self.event_ts_ms


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
    feature_missing_timestamp_policy: Literal[
        "fail_closed", "legacy_non_causal_file_offset"
    ] = "fail_closed"
    legacy_feature_base_ts_ms: Optional[int] = None

    # Symbol mapping
    symbols: List[str] = field(default_factory=lambda: [
                               "BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"])

    def __post_init__(self):
        allowed = {"fail_closed", "legacy_non_causal_file_offset"}
        if self.feature_missing_timestamp_policy not in allowed:
            raise ValueError(
                f"Unsupported feature_missing_timestamp_policy={self.feature_missing_timestamp_policy!r}"
            )
        if (
            self.feature_missing_timestamp_policy == "legacy_non_causal_file_offset"
            and self.legacy_feature_base_ts_ms is None
        ):
            raise ValueError(
                "legacy_feature_base_ts_ms is required when "
                "feature_missing_timestamp_policy='legacy_non_causal_file_offset'"
            )


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
        self._latest_event_ts_ms: Optional[int] = None

        # Lifecycle-safe episode storage (P2)
        # staged: placed/cancelled/rejected path before execution
        # pending: executed/open episodes waiting for structured close
        self._staged_episodes: Dict[str, Episode] = {}
        self._pending_episodes: Dict[str, Episode] = {}
        self._episode_keys_by_lifecycle_id: Dict[str, str] = {}
        self._episode_keys_by_trade_id: Dict[str, str] = {}
        self._episode_keys_by_order_id: Dict[str, str] = {}
        self._episode_keys_by_client_order_id: Dict[str, str] = {}
        self._unresolved_lifecycle_events = 0

        # Equity timeline retained for diagnostics (not used for reward fallback in R2).
        self._equity_history: List[tuple] = []  # [(ts, equity), ...]
        # episode_key -> equity snapshot at executed entry
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
                        f"StagedEpisodes={len(self._staged_episodes)} "
                        f"PendingEpisodes={len(self._pending_episodes)} "
                        f"MarketState={len(self._market_state)} symbols "
                        f"BacklogBytes(F={feature_backlog_bytes},O={orders_backlog_bytes},C={core_backlog_bytes})"
                    )
                    last_log_time = now

                    # TASK (Optimization): Cleanup stale episodes
                    if self._latest_event_ts_ms is not None:
                        self._cleanup_stale_episodes(
                            current_event_ts_ms=self._latest_event_ts_ms
                        )

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
                    line_start_offset = await f.tell()
                    line = await f.readline()
                    if not line:
                        break
                    lines_processed += 1

                    # Pass symbol for pure JSON format
                    synthetic_event_ts_ms = None
                    if (
                        self.config.feature_missing_timestamp_policy
                        == "legacy_non_causal_file_offset"
                    ):
                        synthetic_event_ts_ms = (
                            int(self.config.legacy_feature_base_ts_ms or 0)
                            + int(line_start_offset)
                        )

                    entry = parse_feature_log_line(
                        line,
                        symbol=symbol,
                        missing_timestamp_policy=self.config.feature_missing_timestamp_policy,
                        synthetic_event_ts_ms=synthetic_event_ts_ms,
                    )

                    if entry:
                        # Update market state
                        self._market_state[symbol] = entry.features
                        self._last_feature_ts[symbol] = entry.timestamp
                        self._observe_event_ts_ms(entry.event_ts_ms)

                        # Send to handler (adapter)
                        await self.feature_handler({
                            "timestamp": entry.timestamp,
                            "event_ts_ms": entry.event_ts_ms,
                            "symbol": symbol,
                            "features": entry.features,
                            "event_id": f"feature:{symbol}:{entry.event_ts_ms}:{line_start_offset}",
                            "source_stream": "feature_log",
                            "source_offset": line_start_offset,
                            "event_time_source": entry.time_source,
                            "event_time_is_causal": entry.time_is_causal,
                            "event_time_provenance": entry.time_provenance.value,
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

    def _mark_unresolved(self, reason: str, details: Optional[Dict[str, Any]] = None) -> None:
        self._unresolved_lifecycle_events += 1
        logger.warning(
            "Lifecycle event unresolved: reason=%s details=%s",
            reason,
            details or {},
        )

    def _primary_episode_key(
        self,
        *,
        lifecycle_id: Optional[str] = None,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        trade_id: Optional[str] = None,
    ) -> Optional[str]:
        if lifecycle_id:
            return f"lifecycle:{lifecycle_id}"
        if order_id:
            return f"order:{order_id}"
        if client_order_id:
            return f"client:{client_order_id}"
        if trade_id:
            return f"trade:{trade_id}"
        return None

    def _lookup_candidate_keys(
        self,
        *,
        lifecycle_id: Optional[str] = None,
        trade_id: Optional[str] = None,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        legacy_rid: Optional[str] = None,
    ) -> List[str]:
        keys: List[str] = []
        for mapping, value in (
            (self._episode_keys_by_lifecycle_id, lifecycle_id),
            (self._episode_keys_by_trade_id, trade_id),
            (self._episode_keys_by_order_id, order_id),
            (self._episode_keys_by_client_order_id, client_order_id),
            # Transitional bridge for current ORDER_FILLED producer shape:
            # execution_position writes rid = clientOrderId or orderId.
            (self._episode_keys_by_order_id, legacy_rid),
            (self._episode_keys_by_client_order_id, legacy_rid),
        ):
            if value is None:
                continue
            key = mapping.get(value)
            if key is not None and key not in keys:
                keys.append(key)
        return keys

    def _resolve_existing_episode_key(self, order: OrderLogEntry) -> Optional[str]:
        candidates = self._lookup_candidate_keys(
            lifecycle_id=order.lifecycle_id,
            trade_id=order.trade_id,
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            legacy_rid=order.legacy_rid,
        )
        if not candidates:
            return None
        if len(candidates) > 1:
            self._mark_unresolved(
                "ambiguous_identity_mapping",
                {
                    "symbol": order.symbol,
                    "event_type": order.event_type.value,
                    "candidates": candidates,
                    "lifecycle_id": order.lifecycle_id,
                    "trade_id": order.trade_id,
                    "order_id": order.order_id,
                    "client_order_id": order.client_order_id,
                    "legacy_rid": order.legacy_rid,
                },
            )
            return None
        return candidates[0]

    def _bind_identity(
        self,
        mapping: Dict[str, str],
        value: Optional[str],
        episode_key: str,
        field_name: str,
    ) -> bool:
        if not value:
            return True
        existing_key = mapping.get(value)
        if existing_key is None or existing_key == episode_key:
            mapping[value] = episode_key
            return True
        self._mark_unresolved(
            "identity_conflict",
            {
                "field": field_name,
                "value": value,
                "existing_episode_key": existing_key,
                "incoming_episode_key": episode_key,
            },
        )
        return False

    def _register_episode_identities(self, episode_key: str, episode: Episode) -> bool:
        return all(
            [
                self._bind_identity(
                    self._episode_keys_by_lifecycle_id,
                    episode.lifecycle_id,
                    episode_key,
                    "lifecycle_id",
                ),
                self._bind_identity(
                    self._episode_keys_by_trade_id,
                    episode.trade_id,
                    episode_key,
                    "trade_id",
                ),
                self._bind_identity(
                    self._episode_keys_by_order_id,
                    episode.order_id,
                    episode_key,
                    "order_id",
                ),
                self._bind_identity(
                    self._episode_keys_by_client_order_id,
                    episode.client_order_id,
                    episode_key,
                    "client_order_id",
                ),
            ]
        )

    def _unregister_episode_identities(self, episode_key: str, episode: Episode) -> None:
        for mapping, value in (
            (self._episode_keys_by_lifecycle_id, episode.lifecycle_id),
            (self._episode_keys_by_trade_id, episode.trade_id),
            (self._episode_keys_by_order_id, episode.order_id),
            (self._episode_keys_by_client_order_id, episode.client_order_id),
        ):
            if value and mapping.get(value) == episode_key:
                del mapping[value]

    def _get_episode(self, episode_key: str) -> Optional[Episode]:
        return self._staged_episodes.get(episode_key) or self._pending_episodes.get(episode_key)

    def _store_staged_episode(self, episode_key: str, episode: Episode) -> bool:
        episode.episode_id = episode_key
        if not self._register_episode_identities(episode_key, episode):
            return False
        self._pending_episodes.pop(episode_key, None)
        self._staged_episodes[episode_key] = episode
        return True

    def _store_pending_episode(self, episode_key: str, episode: Episode) -> bool:
        episode.episode_id = episode_key
        if not self._register_episode_identities(episode_key, episode):
            return False
        self._staged_episodes.pop(episode_key, None)
        self._pending_episodes[episode_key] = episode
        return True

    def _pop_staged_episode(self, episode_key: str) -> Optional[Episode]:
        episode = self._staged_episodes.pop(episode_key, None)
        if episode is not None:
            self._unregister_episode_identities(episode_key, episode)
        return episode

    def _pop_pending_episode(self, episode_key: str) -> Optional[Episode]:
        episode = self._pending_episodes.pop(episode_key, None)
        if episode is not None:
            self._unregister_episode_identities(episode_key, episode)
        return episode

    def _coerce_qty(self, value: Optional[float]) -> float:
        try:
            return max(0.0, float(value or 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _coerce_positive_float(self, value: Optional[float]) -> Optional[float]:
        try:
            numeric = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if numeric <= 0.0:
            return None
        return numeric

    def _coerce_finite_float(self, value: Optional[float]) -> Optional[float]:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _new_staged_episode(self, order: OrderLogEntry) -> Episode:
        return Episode(
            symbol=order.symbol,
            timestamp=order.timestamp,
            event_ts_ms=order.event_ts_ms,
            lifecycle_id=order.lifecycle_id,
            trade_id=order.trade_id,
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            lifecycle_state="PLACED",
            placed_event_ts_ms=order.event_ts_ms,
            features=dict(self._market_state.get(order.symbol, {})),
            side=order.side,
            quantity=order.quantity,
            order_type="ENTRY" if order.is_entry else "EXIT",
            rejected=False,
            filled_quantity=0.0,
        )

    def _apply_fill_to_episode(self, episode: Episode, order: OrderLogEntry) -> None:
        if episode.trade_id and order.trade_id and episode.trade_id != order.trade_id:
            raise ValueError(
                f"trade_id conflict for episode {episode.symbol}: "
                f"{episode.trade_id!r} != {order.trade_id!r}"
            )

        episode.lifecycle_id = episode.lifecycle_id or order.lifecycle_id
        episode.trade_id = episode.trade_id or order.trade_id
        episode.order_id = episode.order_id or order.order_id
        episode.client_order_id = episode.client_order_id or order.client_order_id
        episode.side = order.side or episode.side
        if episode.quantity is None and order.quantity is not None:
            episode.quantity = order.quantity

        if not episode.executed_entry:
            episode.executed_entry = True
            episode.entry_anchor_event = "ORDER_FILLED"
            episode.timestamp = order.timestamp
            episode.event_ts_ms = order.event_ts_ms
            episode.features = dict(self._market_state.get(order.symbol, {}))

        fill_qty = self._coerce_qty(order.quantity)
        fill_price = self._coerce_positive_float(order.price)
        episode.filled_quantity += fill_qty
        episode.fill_count += 1
        if fill_qty > 0.0 and fill_price is not None:
            total_priced_qty = episode.priced_fill_quantity + fill_qty
            if total_priced_qty > 0.0:
                weighted_entry = (episode.entry_price or 0.0) * \
                    episode.priced_fill_quantity
                weighted_entry += fill_price * fill_qty
                episode.entry_price = weighted_entry / total_priced_qty
                episode.priced_fill_quantity = total_priced_qty

        requested_qty = self._coerce_qty(episode.quantity)
        if requested_qty > 0.0 and episode.filled_quantity + 1e-12 < requested_qty:
            episode.lifecycle_state = "PARTIALLY_FILLED"
        else:
            episode.lifecycle_state = "ENTERED"

    def _build_episode_reward(
        self,
        *,
        episode_key: str,
        episode: Episode,
        core_entry: CoreLogEntry,
    ) -> EpisodeReward:
        entry_ts_ms = episode.event_ts_ms
        close_ts_ms = core_entry.close_ts_ms or core_entry.event_ts_ms
        quantity = episode.filled_quantity if episode.filled_quantity > 0.0 else self._coerce_positive_float(
            episode.quantity)
        if quantity is None:
            quantity = self._coerce_positive_float(core_entry.quantity)
        entry_price = self._coerce_positive_float(episode.entry_price)
        close_price = self._coerce_positive_float(core_entry.close_price)
        fees = self._coerce_finite_float(core_entry.fees)

        realized_pnl = None
        if core_entry.realized_pnl is not None:
            realized_pnl = float(core_entry.realized_pnl)

        net_pnl = None
        if core_entry.realized_pnl_net is not None:
            net_pnl = float(core_entry.realized_pnl_net)

        if realized_pnl is None and net_pnl is not None and fees is not None:
            realized_pnl = net_pnl + fees
        if net_pnl is None and realized_pnl is not None and fees is not None:
            net_pnl = realized_pnl - fees

        duration_ms = 0
        if entry_ts_ms is not None and close_ts_ms is not None:
            duration_ms = close_ts_ms - entry_ts_ms

        effective_priced_quantity = episode.priced_fill_quantity
        if effective_priced_quantity <= 0.0 and entry_price is not None and quantity is not None:
            effective_priced_quantity = quantity

        reward_complete = all(
            value is not None
            for value in (
                entry_ts_ms,
                close_ts_ms,
                entry_price,
                close_price,
                quantity,
                realized_pnl,
                fees,
                net_pnl,
            )
        )
        if reward_complete and quantity is not None:
            reward_complete = quantity > 0.0 and duration_ms >= 0
        if reward_complete and quantity is not None:
            reward_complete = effective_priced_quantity + 1e-12 >= quantity

        return EpisodeReward(
            episode_id=episode_key,
            trade_id=episode.trade_id or core_entry.trade_id or "",
            symbol=episode.symbol,
            side=episode.side or "UNKNOWN",
            entry_ts_ms=entry_ts_ms or 0,
            close_ts_ms=close_ts_ms or 0,
            duration_ms=duration_ms,
            entry_price=entry_price,
            close_price=close_price,
            quantity=quantity,
            realized_pnl=realized_pnl,
            fees=fees,
            net_pnl=net_pnl,
            entry_event=episode.entry_anchor_event or "UNKNOWN",
            close_event=core_entry.event_type.name,
            reward_complete=reward_complete,
        )

    async def _handle_order_event(self, order: OrderLogEntry):
        """Handle an order event using lifecycle-safe identity resolution."""
        self._observe_event_ts_ms(order.event_ts_ms)
        symbol = order.symbol

        if order.event_type == OrderEventType.PLACED:
            episode_key = (
                self._resolve_existing_episode_key(order)
                or self._primary_episode_key(
                    lifecycle_id=order.lifecycle_id,
                    order_id=order.order_id,
                    client_order_id=order.client_order_id,
                )
            )
            if episode_key is None:
                self._mark_unresolved(
                    "placed_missing_identity",
                    {"symbol": symbol, "event_type": order.event_type.value},
                )
                return

            episode = self._get_episode(episode_key)
            if episode is None:
                episode = self._new_staged_episode(order)
            else:
                episode.lifecycle_id = episode.lifecycle_id or order.lifecycle_id
                episode.order_id = episode.order_id or order.order_id
                episode.client_order_id = episode.client_order_id or order.client_order_id
                episode.side = order.side or episode.side
                if episode.quantity is None and order.quantity is not None:
                    episode.quantity = order.quantity
                episode.lifecycle_state = "PLACED"
                episode.placed_event_ts_ms = episode.placed_event_ts_ms or order.event_ts_ms
                if not episode.features:
                    episode.features = dict(self._market_state.get(symbol, {}))

            if not self._store_staged_episode(episode_key, episode):
                return

            logger.info(
                "ORDER_PLACED staged: %s key=%s side=%s qty=%s",
                symbol,
                episode_key,
                order.side,
                order.quantity,
            )
            return

        if order.event_type == OrderEventType.FILLED:
            episode_key = self._resolve_existing_episode_key(order)
            if episode_key is None:
                episode_key = self._primary_episode_key(
                    lifecycle_id=order.lifecycle_id,
                    order_id=order.order_id,
                    client_order_id=order.client_order_id,
                    trade_id=order.trade_id,
                )
            if episode_key is None:
                self._mark_unresolved(
                    "filled_missing_identity",
                    {
                        "symbol": symbol,
                        "event_type": order.event_type.value,
                        "legacy_rid": order.legacy_rid,
                    },
                )
                return

            episode = self._get_episode(episode_key)
            if episode is None:
                episode = self._new_staged_episode(order)

            try:
                self._apply_fill_to_episode(episode, order)
            except ValueError as exc:
                self._mark_unresolved(
                    "filled_identity_conflict",
                    {"symbol": symbol, "error": str(
                        exc), "episode_key": episode_key},
                )
                return

            if not self._store_pending_episode(episode_key, episode):
                return
            self._equity_at_entry[episode_key] = self._last_equity

            logger.info(
                "ORDER_FILLED entered: %s key=%s trade_id=%s fills=%s filled_qty=%s state=%s",
                symbol,
                episode_key,
                episode.trade_id,
                episode.fill_count,
                episode.filled_quantity,
                episode.lifecycle_state,
            )
            return

        if order.event_type == OrderEventType.REJECTED:
            episode_key = self._resolve_existing_episode_key(order)
            episode = self._pop_staged_episode(
                episode_key) if episode_key else None
            if episode is None:
                episode = Episode(
                    symbol=symbol,
                    timestamp=order.timestamp,
                    event_ts_ms=order.event_ts_ms,
                    lifecycle_id=order.lifecycle_id,
                    trade_id=order.trade_id,
                    order_id=order.order_id,
                    client_order_id=order.client_order_id,
                    lifecycle_state="REJECTED",
                    features=dict(self._market_state.get(symbol, {})),
                    side=order.side,
                    quantity=order.quantity,
                    rejected=True,
                    reject_reason=order.nrr_code,
                    reward=-0.001,
                )
            else:
                episode.lifecycle_state = "REJECTED"
                episode.rejected = True
                episode.reject_reason = order.nrr_code
                episode.reward = -0.001
                episode.executed_entry = False
                episode.entry_anchor_event = None

            if self.episode_handler:
                await self.episode_handler(episode)
            self._episodes_completed += 1
            logger.info(
                "ORDER_REJECTED terminal: %s side=%s reason=%s key=%s",
                symbol,
                order.side,
                order.nrr_code,
                episode_key,
            )
            return

        if order.event_type in (OrderEventType.CANCELLED, OrderEventType.TIMEOUT):
            episode_key = self._resolve_existing_episode_key(order)
            if episode_key is None:
                self._mark_unresolved(
                    "terminal_without_identity",
                    {
                        "symbol": symbol,
                        "event_type": order.event_type.value,
                        "order_id": order.order_id,
                        "client_order_id": order.client_order_id,
                    },
                )
                return

            episode = self._pop_staged_episode(episode_key)
            if episode is None:
                self._mark_unresolved(
                    "terminal_without_staged_episode",
                    {
                        "symbol": symbol,
                        "event_type": order.event_type.value,
                        "episode_key": episode_key,
                    },
                )
                return

            reason = order.raw.get("reason") or order.why or "UNKNOWN"
            episode.lifecycle_state = (
                "TIMEOUT" if order.event_type == OrderEventType.TIMEOUT else "CANCELLED"
            )
            episode.executed_entry = False
            episode.entry_anchor_event = None
            episode.position_closed = True
            episode.reward = -0.001

            if episode.features:
                if self.episode_handler:
                    await self.episode_handler(episode)
                self._episodes_completed += 1
                logger.info(
                    "%s terminal: %s key=%s reason=%s reward=-0.001",
                    order.event_type.value,
                    symbol,
                    episode_key,
                    reason,
                )
            else:
                logger.info(
                    "%s dropped: %s key=%s reason=%s (no state/features)",
                    order.event_type.value,
                    symbol,
                    episode_key,
                    reason,
                )
            return

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
                        if entry.event_type in (CoreEventType.POSITION_CLOSED, CoreEventType.TRADE_CLOSED):
                            await self._handle_position_close(entry)
                        elif entry.event_type == CoreEventType.EQUITY_UPDATE:
                            # TASK-R1: Track equity for PnL estimation
                            if entry.equity is not None:
                                self._last_equity = entry.equity
                                self._observe_event_ts_ms(entry.event_ts_ms)
                                self._equity_history.append(
                                    (entry.event_ts_ms, entry.equity))
                                # Keep only last 100 snapshots
                                if len(self._equity_history) > 100:
                                    self._equity_history = self._equity_history[-100:]

                    self._offsets[str(core_log)] = await f.tell()

        except Exception as e:
            logger.error(f"Error processing core log: {e}")

    async def _handle_position_close(self, core_entry: CoreLogEntry):
        """Handle position close, completing pending episode with structured reward only."""
        symbol = core_entry.symbol
        self._observe_event_ts_ms(core_entry.event_ts_ms)
        trade_id = core_entry.trade_id
        if not trade_id:
            self._mark_unresolved(
                "close_missing_trade_id",
                {"symbol": symbol, "close_ts_ms": core_entry.close_ts_ms},
            )
            return

        episode_key = self._episode_keys_by_trade_id.get(trade_id)
        if episode_key is None:
            self._mark_unresolved(
                "close_unmatched_trade_id",
                {"symbol": symbol, "trade_id": trade_id,
                    "close_ts_ms": core_entry.close_ts_ms},
            )
            return

        episode = self._pop_pending_episode(episode_key)
        if episode is None:
            self._mark_unresolved(
                "close_missing_pending_episode",
                {"symbol": symbol, "trade_id": trade_id, "episode_key": episode_key},
            )
            return

        if symbol and episode.symbol != symbol:
            self._mark_unresolved(
                "close_symbol_mismatch",
                {
                    "symbol": symbol,
                    "trade_id": trade_id,
                    "episode_symbol": episode.symbol,
                    "episode_key": episode_key,
                },
            )
            self._pending_episodes[episode_key] = episode
            self._register_episode_identities(episode_key, episode)
            return

        episode.position_closed = True
        episode.lifecycle_state = "CLOSED"
        episode.trade_id = trade_id
        episode.close_event_ts_ms = core_entry.close_ts_ms or core_entry.event_ts_ms
        self._equity_at_entry.pop(episode_key, None)
        reward_contract = self._build_episode_reward(
            episode_key=episode_key,
            episode=episode,
            core_entry=core_entry,
        )
        episode.episode_reward = reward_contract
        episode.reward_complete = reward_contract.reward_complete
        episode.pnl = reward_contract.net_pnl

        if reward_contract.net_pnl is None:
            episode.reward = None
            logger.warning(
                "WARN:NO_STRUCTURED_REWARD_RECEIVED symbol=%s trade_id=%s close_ts_ms=%s",
                symbol,
                trade_id,
                core_entry.close_ts_ms,
            )
        else:
            import numpy as np

            episode.reward = float(
                np.tanh(float(reward_contract.net_pnl) / self.REWARD_SCALE))
            logger.debug(
                "Structured reward applied: symbol=%s net_pnl=%s reward=%s trade_id=%s complete=%s",
                symbol,
                reward_contract.net_pnl,
                episode.reward,
                trade_id,
                reward_contract.reward_complete,
            )

        if self.episode_handler:
            await self.episode_handler(episode)
        self._episodes_completed += 1

        logger.info(
            "EPISODE COMPLETE: %s side=%s trade_id=%s close_ts_ms=%s pnl=%s reward=%s",
            symbol,
            episode.side,
            trade_id,
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
        close_ts_ms = _normalize_epoch_to_ms(close_ts_ms_raw)

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
        close_price_raw = payload.get("close_price")
        try:
            close_price = float(
                close_price_raw) if close_price_raw is not None else None
        except (TypeError, ValueError):
            close_price = None
        realized_pnl_raw = payload.get("realized_pnl")
        try:
            realized_pnl = float(
                realized_pnl_raw) if realized_pnl_raw is not None else None
        except (TypeError, ValueError):
            realized_pnl = None

        event_ts_ms = close_ts_ms
        if event_ts_ms is None:
            event_ts_ms = _normalize_epoch_to_ms(payload.get("event_ts_ms"))
        if event_ts_ms is None:
            event_ts_ms = _normalize_epoch_to_ms(payload.get("timestamp"))
        if event_ts_ms is None:
            logger.warning(
                "Ignoring EVT:POSITION_CLOSED without canonical causal timestamp: %s",
                payload,
            )
            return

        entry = CoreLogEntry(
            timestamp=event_ts_ms / 1000.0,
            event_ts_ms=event_ts_ms,
            timestamp_str="",
            event_type=(
                CoreEventType.TRADE_CLOSED
                if str(payload.get("event_type", "POSITION_CLOSED")).strip().upper() == "TRADE_CLOSED"
                else CoreEventType.POSITION_CLOSED
            ),
            symbol=symbol,
            realized_pnl=realized_pnl,
            realized_pnl_net=realized_pnl_net,
            trade_id=str(payload.get("trade_id")) if payload.get(
                "trade_id") is not None else None,
            close_ts_ms=close_ts_ms,
            close_price=close_price,
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
            "staged_episodes": len(self._staged_episodes),
            "pending_episodes": len(self._pending_episodes),
            "unresolved_lifecycle_events": self._unresolved_lifecycle_events,
            "running": self._running,
            "offsets": dict(self._offsets)
        }

    @property
    def market_state(self) -> Dict[str, Dict[str, float]]:
        """Current market state per symbol."""
        return dict(self._market_state)

    def _observe_event_ts_ms(self, event_ts_ms: Optional[int]) -> None:
        if event_ts_ms is None or event_ts_ms <= 0:
            return
        if self._latest_event_ts_ms is None or event_ts_ms > self._latest_event_ts_ms:
            self._latest_event_ts_ms = event_ts_ms

    def _cleanup_stale_episodes(
        self,
        current_event_ts_ms: int,
        ttl_ms: int = 3_600_000,
    ):
        """
        Cleanup pending episodes that exceeded TTL (e.g. orphan orders never closed).
        Prevent indefinite memory growth.
        """
        expired: List[tuple[str, str]] = []
        for state_name, store in (
            ("staged", self._staged_episodes),
            ("pending", self._pending_episodes),
        ):
            for episode_key, episode in store.items():
                if episode.event_ts_ms is None:
                    logger.warning(
                        "Dropping %s episode without canonical event_ts_ms: %s",
                        state_name,
                        episode_key,
                    )
                    expired.append((state_name, episode_key))
                    continue
                if current_event_ts_ms - episode.event_ts_ms > ttl_ms:
                    expired.append((state_name, episode_key))

        for state_name, episode_key in expired:
            if state_name == "staged":
                self._pop_staged_episode(episode_key)
            else:
                self._pop_pending_episode(episode_key)
            logger.warning(
                "Cleaned up stale %s episode for %s (Age > %sms)",
                state_name,
                episode_key,
                ttl_ms,
            )

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


def _normalize_epoch_to_ms(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None

    if numeric <= 0.0:
        return None
    if numeric >= 1e11:
        return int(round(numeric))
    if numeric >= 1e9:
        return int(round(numeric * 1000.0))
    return None
