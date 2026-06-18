from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_AURORA_LOG_TIMEZONE = "Europe/Minsk"


def parse_log_wallclock_ms(value: str) -> int | None:
    """Parse a naive Aurora log prefix using an explicit, stable timezone."""
    timezone_name = str(
        os.getenv("AURORA_LOG_TIMEZONE", DEFAULT_AURORA_LOG_TIMEZONE)
    ).strip()
    try:
        timezone = ZoneInfo(timezone_name)
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S,%f")
    except (ValueError, ZoneInfoNotFoundError):
        return None
    return int(round(parsed.replace(tzinfo=timezone).timestamp() * 1000.0))
