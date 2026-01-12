import json
from decimal import Decimal

import pytest

from vfoundation.dr import wal


@pytest.fixture(autouse=True)
def _isolate_wal_dir(tmp_path):
    wal_dir = tmp_path / "wal"
    wal.set_wal_dir(wal_dir)
    wal.reset()
    yield


def _read_wal_jsonl(wal_path):
    entries = []
    with open(wal_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def test_two_bars_produce_two_bar_closed_wal_records(tmp_path):
    from apps.reference.domains.market_data.bar_aggregator import BarAggregator

    agg = BarAggregator(timeframes_sec=[2], emit_fn=None)

    # Bar 1 spans [0..1999], closes when tick arrives at >=2000
    agg.on_tick("BTCUSDT", Decimal("100"), Decimal("1"), ts_ms=1000)
    agg.on_tick("BTCUSDT", Decimal("101"), Decimal("1"), ts_ms=1999)
    agg.on_tick("BTCUSDT", Decimal("102"), Decimal("1"), ts_ms=2000)  # closes bar1

    # Bar 2 spans [2000..3999], closes when tick arrives at >=4000
    agg.on_tick("BTCUSDT", Decimal("103"), Decimal("1"), ts_ms=3999)
    agg.on_tick("BTCUSDT", Decimal("104"), Decimal("1"), ts_ms=4000)  # closes bar2

    wal_path = wal._get_wal_file_path()  # exposed for tests
    entries = _read_wal_jsonl(wal_path)

    bar_closed = [e for e in entries if e.get("op") == "EVT" and e.get("verb") == "BAR_CLOSED"]
    assert len(bar_closed) == 2

    for e in bar_closed:
        pld = e.get("pld") or {}
        assert pld.get("symbol") == "BTCUSDT"
        assert int(pld.get("tf_sec")) == 2
        assert isinstance(pld.get("ts_ms"), int)
        assert isinstance(pld.get("bar_close_ts"), int)
        assert isinstance(pld.get("bar"), dict)

        bar = pld["bar"]
        for k in ("open", "high", "low", "close", "volume"):
            assert k in bar

