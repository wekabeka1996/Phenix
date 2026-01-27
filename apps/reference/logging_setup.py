"""
Centralized Logging Setup (CFG-OBS-001)
========================================

This module provides YAML-driven logging configuration, replacing hardcoded values in main.py.
All logging settings are read from config.observability (SSOT: observability.yaml).

Usage:
    from apps.reference.logging_setup import setup_logging
    
    config = load_config()
    setup_logging(config)
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig, ObservabilityLoggingConfig

# Prevent duplicate handler registration across imports
_AURORA_LOGGING_TAG = "_aurora_obs_logging_configured"


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging (event chain, forensics)."""
    
    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime
        
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Include extra fields if present
        if hasattr(record, "rid"):
            log_data["rid"] = record.rid
        if hasattr(record, "symbol"):
            log_data["symbol"] = record.symbol
        if hasattr(record, "event"):
            log_data["event"] = record.event
        
        # Include exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


def _tag_handler(handler: logging.Handler) -> logging.Handler:
    """Mark handler to prevent duplicate registration."""
    setattr(handler, _AURORA_LOGGING_TAG, True)
    return handler


def _is_already_configured(root_logger: logging.Logger) -> bool:
    """Check if logging was already configured by this module."""
    return any(
        getattr(h, _AURORA_LOGGING_TAG, False) for h in root_logger.handlers
    )


def _get_log_level(level_str: str) -> int:
    """Convert level string to logging constant."""
    return getattr(logging, level_str.upper(), logging.INFO)


def _create_text_formatter() -> logging.Formatter:
    """Standard text formatter for file/console output."""
    return logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def _create_console_formatter() -> logging.Formatter:
    """Compact formatter for console output."""
    return logging.Formatter(
        "%(asctime)s - %(name)s - %(message)s"
    )


def setup_logging(
    config: "AuroraConfig",
    *,
    logs_dir: Optional[Path] = None,
    force_reconfigure: bool = False,
) -> None:
    """
    Configure logging from observability config (SSOT).
    
    CFG-OBS-001: All logging settings are read from config.observability.logging.
    
    Args:
        config: AuroraConfig with observability section
        logs_dir: Override logs directory (default: project_root/logs)
        force_reconfigure: If True, reconfigure even if already set up
    """
    root_logger = logging.getLogger()
    
    # Prevent duplicate configuration
    if not force_reconfigure and _is_already_configured(root_logger):
        return
    
    # Get observability config
    obs_logging: "ObservabilityLoggingConfig" = config.observability.logging
    
    # Ensure logs directory exists
    if logs_dir is None:
        # Default: project_root/logs
        logs_dir = Path(__file__).parent.parent.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Set root logger level
    root_logger.setLevel(_get_log_level(obs_logging.default_level))
    
    # =========================================================================
    # Console Handler
    # =========================================================================
    if obs_logging.console.enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(_get_log_level(obs_logging.console.level))
        
        if obs_logging.console.format == "json":
            console_handler.setFormatter(JSONFormatter())
        else:
            console_handler.setFormatter(_create_console_formatter())
        
        try:
            console_handler.stream.reconfigure(encoding="utf-8")  # type: ignore
        except Exception:
            pass  # Not all streams support reconfigure
        
        root_logger.addHandler(_tag_handler(console_handler))
    
    # =========================================================================
    # Core File Handler (aurora_core.log)
    # =========================================================================
    if obs_logging.core.enabled:
        core_path = logs_dir / Path(obs_logging.core.path).name
        
        max_bytes = obs_logging.core.max_bytes or obs_logging.rotation.max_bytes
        backup_count = obs_logging.core.backup_count or obs_logging.rotation.backup_count
        
        core_handler = RotatingFileHandler(
            core_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        core_handler.setLevel(_get_log_level(obs_logging.core.level))
        
        if obs_logging.core.format == "json":
            core_handler.setFormatter(JSONFormatter())
        else:
            core_handler.setFormatter(_create_text_formatter())
        
        root_logger.addHandler(_tag_handler(core_handler))
    
    # =========================================================================
    # Domain-Specific Handlers
    # =========================================================================
    domain_name_mapping = {
        "feature_engineering": "apps.reference.domains.feature_engineering",
        "risk_management": "apps.reference.domains.risk_management",
        "decision_making": "apps.reference.domains.decision_making",
        "execution_position": "apps.reference.domains.execution_position",
        "regime_detector": "apps.reference.domains.regime_detector",
        "mean_reversion": "domain_mean_reversion",  # Special case: uses custom logger name
    }
    
    for domain_name, domain_cfg in obs_logging.domains.items():
        if not domain_cfg.enabled:
            continue
        
        # Determine log file path
        log_filename = f"domain_{domain_name}.log"
        domain_log_path = logs_dir / log_filename
        
        # Create handler
        domain_handler = RotatingFileHandler(
            domain_log_path,
            maxBytes=domain_cfg.max_bytes,
            backupCount=domain_cfg.backup_count,
            encoding="utf-8",
        )
        domain_handler.setLevel(_get_log_level(domain_cfg.level))
        domain_handler.setFormatter(_create_text_formatter())
        
        # Add filter for this domain
        logger_prefix = domain_name_mapping.get(domain_name, f"apps.reference.domains.{domain_name}")
        domain_handler.addFilter(
            lambda record, prefix=logger_prefix: record.name.startswith(prefix)
        )
        
        root_logger.addHandler(_tag_handler(domain_handler))
    
    # =========================================================================
    # Event Chain Handler (JSON structured logs)
    # =========================================================================
    if obs_logging.event_chain.enabled:
        event_chain_path = logs_dir / Path(obs_logging.event_chain.path).name
        
        event_handler = RotatingFileHandler(
            event_chain_path,
            maxBytes=obs_logging.event_chain.max_bytes,
            backupCount=obs_logging.event_chain.backup_count,
            encoding="utf-8",
        )
        event_handler.setLevel(_get_log_level(obs_logging.event_chain.level))
        event_handler.setFormatter(JSONFormatter())
        
        # Filter: only log records with 'rid' attribute or from 'event_chain' logger
        event_handler.addFilter(
            lambda record: hasattr(record, "rid") or record.name == "event_chain"
        )
        
        root_logger.addHandler(_tag_handler(event_handler))
    
    # Log successful setup
    logger = logging.getLogger("AuroraCore")
    logger.info(
        f"✅ Logging configured from observability.yaml "
        f"(default_level={obs_logging.default_level}, "
        f"domains={len(obs_logging.domains)})"
    )


def get_domain_logger(domain_name: str) -> logging.Logger:
    """
    Get a logger for a specific domain.
    
    Args:
        domain_name: Domain name (e.g., 'decision_making', 'risk_management')
        
    Returns:
        Logger instance for the domain
    """
    return logging.getLogger(f"apps.reference.domains.{domain_name}")
