"""Tests for seed_startup_bars() on Aurora and md_amr handlers — STARTUP-BASIS-HYDRATION."""
from __future__ import annotations

import logging
from collections import defaultdict

from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler
from apps.reference.domains.strategies.runtimes.md_amr.handler import MDAMRHandler


def _make_aurora_handler() -> AuroraHandler:
    """Build a minimal AuroraHandler via object.__new__ (no FSM required)."""
    handler = object.__new__(AuroraHandler)
    handler.logger = logging.getLogger("tests.aurora.seed")
    handler._bars_seen_since_restart = defaultdict(int)
    return handler


def _make_md_amr_handler() -> MDAMRHandler:
    """Build a minimal MDAMRHandler via object.__new__ (no FSM required)."""
    handler = object.__new__(MDAMRHandler)
    handler.mlog = logging.getLogger("tests.md_amr.seed")
    handler._bars_seen_since_restart = {}
    return handler


class TestAuroraSeedStartupBars:
    def test_sets_counter_from_zero(self):
        """seed_startup_bars sets _bars_seen_since_restart when counter starts at 0."""
        handler = _make_aurora_handler()

        handler.seed_startup_bars("BTCUSDT", 301)

        assert handler._bars_seen_since_restart["BTCUSDT"] == 301

    def test_does_not_overwrite_higher_live_count(self):
        """seed_startup_bars uses max() — does not overwrite if live count is already higher."""
        handler = _make_aurora_handler()
        # already 400 live bars
        handler._bars_seen_since_restart["BTCUSDT"] = 400

        handler.seed_startup_bars("BTCUSDT", 301)

        # max(400, 301) = 400 — live count preserved
        assert handler._bars_seen_since_restart["BTCUSDT"] == 400

    def test_zero_count_is_noop(self):
        """seed_startup_bars with count=0 does not change the counter."""
        handler = _make_aurora_handler()
        handler._bars_seen_since_restart["BTCUSDT"] = 5

        handler.seed_startup_bars("BTCUSDT", 0)

        assert handler._bars_seen_since_restart["BTCUSDT"] == 5

    def test_seeds_per_symbol_independently(self):
        """seed_startup_bars operates per-symbol without cross-contamination."""
        handler = _make_aurora_handler()

        handler.seed_startup_bars("BTCUSDT", 301)
        handler.seed_startup_bars("SOLUSDT", 250)

        assert handler._bars_seen_since_restart["BTCUSDT"] == 301
        assert handler._bars_seen_since_restart["SOLUSDT"] == 250


class TestMDAMRSeedStartupBars:
    def test_sets_counter_from_zero(self):
        """seed_startup_bars sets _bars_seen_since_restart when counter starts at 0."""
        handler = _make_md_amr_handler()

        handler.seed_startup_bars("BTCUSDT", 96)

        assert handler._bars_seen_since_restart["BTCUSDT"] == 96

    def test_does_not_overwrite_higher_live_count(self):
        """seed_startup_bars uses max() — preserves higher live count."""
        handler = _make_md_amr_handler()
        handler._bars_seen_since_restart["BTCUSDT"] = 120

        handler.seed_startup_bars("BTCUSDT", 96)

        assert handler._bars_seen_since_restart["BTCUSDT"] == 120

    def test_zero_count_is_noop(self):
        """seed_startup_bars with count=0 does not modify the counter."""
        handler = _make_md_amr_handler()
        handler._bars_seen_since_restart["BTCUSDT"] = 10

        handler.seed_startup_bars("BTCUSDT", 0)

        assert handler._bars_seen_since_restart["BTCUSDT"] == 10

    def test_seeds_per_symbol_independently(self):
        """seed_startup_bars operates per-symbol without cross-contamination."""
        handler = _make_md_amr_handler()

        handler.seed_startup_bars("BTCUSDT", 96)
        handler.seed_startup_bars("ETHUSDT", 80)

        assert handler._bars_seen_since_restart["BTCUSDT"] == 96
        assert handler._bars_seen_since_restart["ETHUSDT"] == 80
