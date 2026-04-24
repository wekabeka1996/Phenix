"""Tests for apps.reference.shared.types — Phase 4.1."""
from __future__ import annotations

from decimal import Decimal


class TestSharedBar:
    def test_import_bar(self) -> None:
        from apps.reference.shared.types import Bar
        b = Bar(
            symbol="BTCUSDT", timeframe_sec=60,
            open=Decimal("42000"), high=Decimal("42100"),
            low=Decimal("41900"), close=Decimal("42050"),
            volume=Decimal("1.5"), trade_count=100,
            start_ts_ms=1700000000000, end_ts_ms=1700000060000,
        )
        assert b.symbol == "BTCUSDT"
        assert b.is_bullish

    def test_bar_identity(self) -> None:
        """Shared Bar is the same class as feature_engineering's Bar."""
        from apps.reference.shared.types import Bar as SharedBar
        from apps.reference.domains.feature_engineering.bar_resampler import Bar as OrigBar
        assert SharedBar is OrigBar


class TestSharedNRR:
    def test_import_nrr(self) -> None:
        from apps.reference.shared.types import NormalizedRejectReasons as NRR
        assert hasattr(NRR, "INSUFFICIENT_BALANCE")
        assert NRR.INSUFFICIENT_BALANCE == "NRR-001"

    def test_nrr_identity(self) -> None:
        from apps.reference.shared.types import NormalizedRejectReasons as SharedNRR
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons as OrigNRR
        assert SharedNRR is OrigNRR
