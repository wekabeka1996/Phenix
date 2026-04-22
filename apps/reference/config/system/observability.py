from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from apps.reference.telemetry.shadow_journal import DEFAULT_CRITICAL_EVENTS


class LogRotationConfig(BaseModel):
    """Log file rotation settings."""
    model_config = ConfigDict(extra='forbid')

    max_bytes: int = Field(default=10485760, ge=1024,
                           description='Max bytes before rotation (default 10MB)')
    backup_count: int = Field(default=5, ge=1, le=100,
                              description='Number of backup files to keep')


class ConsoleLogConfig(BaseModel):
    """Console (stdout) logging configuration."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(default=True, description='Enable console logging')
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description='Console log level')
    format: Literal["text", "json"] = Field(
        default="text", description='Console log format')
    colorize: bool = Field(
        default=False, description='Enable ANSI color output (future)')


class CoreLogSinkConfig(BaseModel):
    """Core file sink configuration (aurora_core.log)."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(default=True, description='Enable core file logging')
    path: str = Field(default="logs/aurora_core.log",
                      description='Log file path')
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="DEBUG", description='File log level')
    format: Literal["text", "json"] = Field(
        default="text", description='File log format')
    max_bytes: Optional[int] = Field(
        default=None, description='Override rotation.max_bytes')
    backup_count: Optional[int] = Field(
        default=None, description='Override rotation.backup_count')


class DomainLogConfig(BaseModel):
    """Per-domain logging configuration."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True, description='Enable domain-specific log file')
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="DEBUG", description='Domain log level')
    max_bytes: int = Field(default=5242880, ge=1024,
                           description='Max bytes before rotation (default 5MB)')
    backup_count: int = Field(default=3, ge=1, le=100,
                              description='Number of backup files')


class EventChainLogConfig(BaseModel):
    """Structured event chain log configuration (JSON format)."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True, description='Enable event chain logging')
    path: str = Field(default="logs/event_chain.log",
                      description='Event chain log file path')
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description='Event chain log level')
    format: Literal["text", "json"] = Field(
        default="json", description='Event chain format (should be json)')
    max_bytes: int = Field(
        default=10485760, description='Max bytes before rotation')
    backup_count: int = Field(default=5, description='Number of backup files')


class ObservabilityLoggingConfig(BaseModel):
    """Complete logging configuration (SSOT for all log handlers)."""
    model_config = ConfigDict(extra='forbid')

    default_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description='Global default log level')
    default_format: Literal["text", "json"] = Field(
        default="text", description='Global default log format')
    rotation: LogRotationConfig = Field(
        default_factory=LogRotationConfig, description='Default rotation settings')
    console: ConsoleLogConfig = Field(
        default_factory=ConsoleLogConfig, description='Console sink config')
    core: CoreLogSinkConfig = Field(
        default_factory=CoreLogSinkConfig, description='Core file sink config')
    domains: Dict[str, DomainLogConfig] = Field(
        default_factory=dict, description='Per-domain log configs')
    event_chain: EventChainLogConfig = Field(
        default_factory=EventChainLogConfig, description='Event chain config')


class AlertsConfig(BaseModel):
    """Typed alerting configuration (SSOT)."""
    model_config = ConfigDict(extra='forbid')

    slack_webhook_url: Optional[str] = Field(
        default=None, description='Slack incoming webhook URL')
    deduplication_window_sec: int = Field(
        default=300, ge=0, description='Deduplication window for same alert key')
    max_alerts_per_hour: int = Field(
        default=10, ge=1, description='Rate limit for raised alerts per hour')
    risk_gate_threshold_pct: int = Field(
        default=80, ge=0, le=100, description='Risk gate alert threshold in percent')
    wal_size_threshold_mb: int = Field(
        default=500, ge=1, description='WAL size threshold for warning alert')
    cb_active_threshold_sec: int = Field(
        default=60, ge=0, description='Circuit breaker active duration threshold')
    recent_alerts_max_keys: int = Field(
        default=5000, ge=100, description='Hard cap for dedup cache keys')
    entropy_volume_threshold: int = Field(
        default=3000, ge=10,
        description=(
            'EntropyMonitor: max FSM events per 60s window before CRITICAL alert. '
            'Baseline: N_symbols × 60 ticks/min × ~5 events/tick. '
            'Default 3000 covers 7 symbols at normal tick rate with 2x headroom.'
        ),
    )
    entropy_error_rate_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description='EntropyMonitor: max ERR-op fraction (0.0–1.0) before CRITICAL alert.',
    )


class ShadowCriticalEventJournalConfig(BaseModel):
    """Shadow-only critical event journal configuration."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True,
        description="Enable append-only shadow journal for critical decision/execution events.",
    )
    path: str = Field(
        default="logs/shadow_critical_event_journal_v1.jsonl",
        description="Append-only JSONL sink for the shadow critical event journal.",
    )
    schema_version: str = Field(
        default="1.0.0",
        description="Schema version written into each journal record.",
    )
    instrumentation_version: str = Field(
        default="1.0.0",
        description="Instrumentation package version written into each journal record.",
    )
    critical_events: List[str] = Field(
        default_factory=lambda: list(DEFAULT_CRITICAL_EVENTS),
        description="Critical events/transitions captured by the shadow journal.",
    )


class ObservabilityConfig(BaseModel):
    """Root observability configuration (logging, metrics, tracing)."""
    model_config = ConfigDict(extra='forbid')

    config_version: str = Field(
        default="1.0.0", description='Observability config version')
    logging: ObservabilityLoggingConfig = Field(
        default_factory=ObservabilityLoggingConfig, description='Logging configuration')
    alerts: AlertsConfig = Field(
        default_factory=AlertsConfig, description='Alert manager configuration')
    shadow_journal: ShadowCriticalEventJournalConfig = Field(
        default_factory=ShadowCriticalEventJournalConfig,
        description='Shadow-only critical event journal configuration')
    # Future: metrics, tracing
