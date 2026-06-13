from __future__ import annotations

from pathlib import Path


def test_aurora_duration_hot_paths_do_not_use_wall_clock_time() -> None:
    hot_paths = [
        Path("apps/reference/domains/strategies/runtimes/aurora/holding_period.py"),
        Path("apps/reference/domains/strategies/runtimes/aurora/handler.py"),
    ]
    offenders = [
        str(path)
        for path in hot_paths
        if "time.time(" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
