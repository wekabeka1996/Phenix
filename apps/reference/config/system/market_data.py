from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class MacroSyncConfig(BaseModel):
    """Macro sync configuration for market data."""
    model_config = ConfigDict(extra='forbid')
    enabled: bool = Field(
        description='Enable macro sync (anchor subscription and events)')
    anchors: List[str] = Field(
        description='Anchor symbols for macro alignment')
    window: int = Field(description='Window in seconds')
    emit_abs: bool = Field(
        description='DEPRECATED: Not implemented. Planned removal: v2.0')

    # D4 Phase 1: Alignment mode for correlation calculation
    align_mode: str = Field(
        description="Alignment mode: 'strict_len' (exact match) or 'tail_min_len' (use min overlap tail)")
    min_buffer_size: int = Field(
        description='Min samples in buffer for correlation')
    time_diff_threshold_ms: int = Field(
        description='Max time diff (ms) between ticks for return calculation')
    anchor_update_from_ticks: bool = Field(
        description='Update anchor buffers from symbol ticks (false = EVT:ANCHOR_UPDATED only)')


class BarAggregatorConfig(BaseModel):
    """Bar aggregator SSOT configuration.

    BAR-SSOT-002: Configuration for BarAggregator wiring.
    If enabled=True, timeframes_sec is mandatory.
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        description='Enable bar aggregator (EVT:BAR_CLOSED emission)')
    timeframes_sec: List[int] = Field(
        description='Bar timeframes in seconds (e.g., [180, 300] for 3m and 5m)')


class MarketDataConfig(BaseModel):
    """Market data configuration.

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields known).
    """
    model_config = ConfigDict(extra='forbid')

    poll_interval_sec: float = Field()
    use_multiprocessing: bool = Field(description='Enable multiprocessing')
    websocket_streams: List[str] = Field()
    # PURGE-DIRTY-DOZEN: Removed api_call_limits (dead stub, REST replaced by WebSocket) - 2026-01-25
    macro_sync: Optional[MacroSyncConfig] = Field()
    bar_aggregator: Optional[BarAggregatorConfig] = Field(
        default=None, description='Bar aggregator config (optional, disabled if missing)')


class SystemMarketDataConfig(BaseModel):
    """System-level Market Data configuration."""
    model_config = ConfigDict(extra='forbid')

    queue_maxsize: int = Field(...,
                               description="Max size of IPC queue (worker → proxy)")
    # DEPRECATED: Not used in runtime (CFG-OBS-001)
    local_queue_maxsize: int = Field(
        default=10000, description="[DEPRECATED] Max size of local queue (proxy internal)")
    emit_workers: int = Field(
        default=4, description="[DEPRECATED] Thread pool size for non-blocking FSM.emit()")
    tick_ttl_ms: int = Field(
        ..., description="Max age of tick data in ms — older ticks are DROPPED")
    bar_ttl_ms: Optional[int] = Field(
        default=10000, description="Max age of bar data in ms (BAR-TTL-REFORM-01)")
    bar_event_age_mode: Literal["received", "close_ts"] = Field(
        default="received",
        description="How to calculate bar age: 'received' (arrival time) or 'close_ts' (event time)"
    )
    ws_heartbeat_sec: float = Field(
        ..., description="aiohttp WS heartbeat interval (sec) to keep connection alive")
    ws_receive_timeout_sec: float = Field(
        ..., description="Max time without WS messages (sec) before reconnect")
    proxy_batch_size: int = Field(...,
                                  description="Proxy consumer: max items processed per batch")
    proxy_queue_get_timeout_sec: float = Field(
        ..., description="Proxy consumer: blocking get() timeout (sec)")
    proxy_idle_sleep_sec: float = Field(
        ..., description="Proxy consumer: sleep when queue is empty (sec)")
