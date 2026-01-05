# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""Central logging setup with timed rotation.

Usage:
    from .logging_setup import configure_logging
    configure_logging(cfg.io)

Idempotent: safe to call multiple times.
"""
from __future__ import annotations
import logging, os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from .config import IOConfig

_INITIALIZED = False

def configure_logging(io_cfg: IOConfig) -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    log_dir = Path(io_cfg.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / 'agent.log'
    handler = TimedRotatingFileHandler(
        filename=str(logfile),
        when=io_cfg.rotate_when,
        interval=io_cfg.rotate_interval,
        backupCount=io_cfg.rotate_backup_count,
        encoding='utf-8',
        utc=True,
    )
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # Also keep console handler if none
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(logging.StreamHandler())
    _INITIALIZED = True
