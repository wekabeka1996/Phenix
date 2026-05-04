"""
Phase 10.3: Tests for vfoundation.obs.order_logger (compat shim).
Tests that the shim exports a working order_logger object with a write() method.
"""
from __future__ import annotations

import pytest

from vfoundation.obs.order_logger import order_logger


class TestOrderLoggerShim:
    """Tests for the order_logger compat shim."""

    def test_order_logger_importable(self) -> None:
        """order_logger should be importable without raising."""
        assert order_logger is not None

    def test_order_logger_has_write(self) -> None:
        """order_logger must expose a write() method."""
        assert hasattr(order_logger, "write"), (
            "expected order_logger to have write() method (either real or shim)"
        )

    def test_write_does_not_raise(self) -> None:
        """Calling order_logger.write() with typical args should not raise."""
        # This tests the shim fallback path; real implementation also must not raise
        order_logger.write({"rid": "test-rid", "verb": "EVAL", "why": "test-why"})
