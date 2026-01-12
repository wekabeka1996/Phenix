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
from pathlib import Path
from glob import glob
from typing import Callable, Awaitable, Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import defaultdict

from .parsers import (
    FeatureLogEntry, parse_feature_log_line,
    OrderLogEntry, OrderEventType, parse_order_log_line,
    CoreLogEntry, CoreEventType, parse_core_log_line,
)

logger = logging.getLogger(__name__)


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
    reward: float = 0.0
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
    
    # Symbol mapping
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"])


class MultiTailer:
    """
    Multi-source log tailer for synchronized ingestion.
    
    Reads features, orders, and core events, correlating them
    into complete episodes for RL training.
    
    TASK-R1: Added equity-based PnL estimation.
    """
    
    def __init__(
        self,
        config: MultiSourceConfig,
        feature_handler: Callable[[Dict[str, Any]], Awaitable[None]],
        episode_handler: Optional[Callable[[Episode], Awaitable[None]]] = None,
        state_path: Optional[Path] = None
    ):
        """
        Args:
            config: MultiSourceConfig with log paths
            feature_handler: Handler for feature events (passed to adapter)
            episode_handler: Optional handler for complete episodes
            state_path: Path to persist tailer state
        """
        self.config = config
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
        self._pending_episodes: Dict[str, Episode] = {}  # symbol -> latest episode
        
        # TASK-R1: Equity tracking for PnL estimation
        self._equity_history: List[tuple] = []  # [(ts, equity), ...]
        self._equity_at_entry: Dict[str, float] = {}  # symbol -> equity at order placement
        self._last_equity: float = 0.0
        
        # Stats
        self._features_processed = 0
        self._orders_processed = 0
        self._episodes_completed = 0
        
    def load_state(self) -> bool:
        """Load persisted offsets."""
        try:
            if self.state_path.exists():
                with open(self.state_path) as f:
                    data = json.load(f)
                    self._offsets = data.get("offsets", {})
                logger.info(f"Loaded multi-tailer state: {len(self._offsets)} offsets")
                return True
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
        return False
    
    def save_state(self) -> bool:
        """Persist offsets."""
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_path, 'w') as f:
                json.dump({"offsets": self._offsets}, f, indent=2)
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
        self.load_state()
        
        logger.info("Starting MultiTailer...")
        logger.info(f"  Features: {self.config.features_dir}")
        logger.info(f"  Orders: {self.config.orders_file}")
        logger.info(f"  Core: {self.config.core_log}")
        
        # Initial stats logging
        last_log_time = 0
        
        try:
            while self._running:
                # Process all streams
                await self._process_features()
                await self._process_orders()
                await self._process_core()
                
                # Periodic progress log (every 5 seconds)
                import time
                now = time.time()
                if now - last_log_time > 5:
                    logger.info(
                        f"Progress: Features={self._features_processed} "
                        f"Orders={self._orders_processed} "
                        f"Episodes={self._episodes_completed} "
                        f"MarketState={len(self._market_state)} symbols"
                    )
                    last_log_time = now
                
                # Yield to event loop
                await asyncio.sleep(self.config.poll_interval)
                
        except asyncio.CancelledError:
            logger.info("MultiTailer cancelled")
        finally:
            self.save_state()
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
            
        for symbol in self.config.symbols:
            log_file = features_dir / f"{symbol}.log"
            if not log_file.exists():
                continue
                
            offset = self._offsets.get(str(log_file), 0)
            file_size = log_file.stat().st_size
            
            if offset >= file_size:
                continue
                
            await self._tail_feature_file(log_file, symbol)
    
    async def _tail_feature_file(self, file_path: Path, symbol: str):
        """Tail a single feature log file."""
        offset = self._offsets.get(str(file_path), 0)
        batch_count = 0
        
        try:
            with open(file_path, 'r') as f:
                f.seek(offset)
                
                while True:
                    line = f.readline()
                    if not line:
                        break
                        
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
                            logger.info(f"Feature #{self._features_processed}: {symbol} ts={entry.timestamp:.0f}")
                        
                        if batch_count >= self.config.batch_size:
                            await asyncio.sleep(0.001)
                            batch_count = 0
                    
                    self._offsets[str(file_path)] = f.tell()
                    
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
    
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
            with open(orders_file, 'r') as f:
                f.seek(offset)
                
                while True:
                    line = f.readline()
                    if not line:
                        break
                        
                    entry = parse_order_log_line(line)
                    
                    if entry:
                        await self._handle_order_event(entry)
                        self._orders_processed += 1
                    
                    self._offsets[str(orders_file)] = f.tell()
                    
        except Exception as e:
            logger.error(f"Error processing orders: {e}")
    
    async def _handle_order_event(self, order: OrderLogEntry):
        """Handle an order event, creating/updating episodes."""
        symbol = order.symbol
        
        if order.event_type == OrderEventType.PLACED:
            # TASK-R1: Snapshot equity at entry time
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
            logger.info(f"ORDER_PLACED: {symbol} {order.side} qty={order.quantity}")
            
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
            logger.info(f"ORDER_REJECTED: {symbol} {order.side} reason={order.nrr_code}")
    
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
            with open(core_log, 'r') as f:
                f.seek(offset)
                
                while True:
                    line = f.readline()
                    if not line:
                        break
                        
                    entry = parse_core_log_line(line)
                    
                    if entry:
                        if entry.event_type == CoreEventType.POSITION_CLOSED:
                            await self._handle_position_close(entry)
                        elif entry.event_type == CoreEventType.EQUITY_UPDATE:
                            # TASK-R1: Track equity for PnL estimation
                            if entry.equity is not None:
                                self._last_equity = entry.equity
                                self._equity_history.append((entry.timestamp, entry.equity))
                                # Keep only last 100 snapshots
                                if len(self._equity_history) > 100:
                                    self._equity_history = self._equity_history[-100:]
                    
                    self._offsets[str(core_log)] = f.tell()
                    
        except Exception as e:
            logger.error(f"Error processing core log: {e}")
    
    async def _handle_position_close(self, core_entry: CoreLogEntry):
        """Handle position close, completing pending episode with PnL estimation."""
        symbol = core_entry.symbol
        
        if symbol in self._pending_episodes:
            episode = self._pending_episodes.pop(symbol)
            episode.position_closed = True
            
            # TASK-R1: Estimate PnL from equity delta
            entry_equity = self._equity_at_entry.pop(symbol, self._last_equity)
            current_equity = self._last_equity
            
            # Raw PnL estimate (might include other symbols, but best we have)
            raw_pnl = current_equity - entry_equity
            
            # Normalize reward using tanh for PPO stability
            # Scale factor: $10 delta -> reward ~0.76
            import numpy as np
            normalized_reward = float(np.tanh(raw_pnl / 10.0))
            
            episode.pnl = raw_pnl
            episode.reward = normalized_reward
            
            logger.info(f"DEBUG: Closing Episode {id(episode)} with Reward={episode.reward}")

            if self.episode_handler:
                await self.episode_handler(episode)
            self._episodes_completed += 1
            
            logger.info(
                f"EPISODE COMPLETE: {symbol} side={episode.side} "
                f"pnl={raw_pnl:.4f} reward={normalized_reward:.4f}"
            )
    
    def stop(self):
        """Stop tailing."""
        self._running = False
        self.save_state()
    
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
