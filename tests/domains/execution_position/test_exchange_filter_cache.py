from __future__ import annotations

from decimal import Decimal

import pytest

from apps.reference.domains.execution_position.exchange_filter_cache import (
    ExchangeFilterCache,
)
from apps.reference.domains.execution_position.guards.qty_normalizer import (
    normalize_qty_with_filter,
)


def _exchange_info(step_size: str = "0.01") -> dict:
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                    {"filterType": "LOT_SIZE", "stepSize": step_size, "minQty": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "5"},
                ],
            }
        ]
    }


def test_live_exchange_filter_overrides_static_and_normalizes_qty(tmp_path) -> None:
    static_path = tmp_path / "instruments.yaml"
    static_path.write_text(
        "instruments:\n  BTCUSDT:\n    tick_size: '1'\n    step_size: '1'\n    min_qty: '1'\n    min_notional: '100'\n",
        encoding="utf-8",
    )
    cache = ExchangeFilterCache(
        fetch_exchange_info=lambda: _exchange_info("0.01"),
        static_config_path=static_path,
        mode="test",
    )

    report = cache.refresh(["BTCUSDT"])
    snapshot = cache.get_filter("BTCUSDT")
    result = normalize_qty_with_filter(
        raw_qty="0.129",
        price="100",
        exchange_filter=snapshot,
    )

    assert report.source == "live"
    assert snapshot.source == "live"
    assert snapshot.step_size == Decimal("0.01")
    assert result.ok is True
    assert result.qty == Decimal("0.12")


def test_stale_live_exchange_filter_fails_closed_in_production() -> None:
    clock = {"now": 100.0}
    cache = ExchangeFilterCache(
        fetch_exchange_info=lambda: _exchange_info(),
        monotonic_fn=lambda: clock["now"],
        mode="production",
    )
    cache.refresh(["BTCUSDT"])
    clock["now"] = 1_000.0

    with pytest.raises(LookupError):
        cache.require_fresh_filter("BTCUSDT", max_age_sec=60.0)
