from __future__ import annotations

import asyncio

from tools.data_repair import repair_recorder_days as mod


class _FakeAdapter:
    calls: list[tuple[str, str, int, int | None, int | None]]

    def __init__(self, *_, **__) -> None:
        self.calls = []

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[list[object]]:
        self.calls.append((symbol, interval, limit, start_ms, end_ms))
        step_ms = 1_000 if interval == "1s" else 60_000
        if len(self.calls) == 1:
            return [
                [
                    start_ms + idx * step_ms,
                    "1",
                    "2",
                    "0.5",
                    "1.5",
                    "10",
                    start_ms + idx * step_ms + (step_ms - 1),
                    "",
                    1,
                ]
                for idx in range(limit)
            ]
        return [
            [start_ms, "1", "2", "0.5", "1.5", "10", start_ms + (step_ms - 1), "", 1],
        ]

    async def aclose(self) -> None:
        return None


def test_validate_kline_continuity_rejects_gap() -> None:
    ok, summary = mod._validate_kline_continuity(
        [
            [0, "", "", "", "", "", 59_999],
            [120_000, "", "", "", "", "", 179_999],
        ],
        tf_sec=60,
        start_ms=0,
    )
    assert ok is False
    assert summary["reason"] == "NON_CONTIGUOUS_KLINES"
    assert summary["gaps"] == 1


def test_fetch_klines_for_day_uses_interval_step_pagination(monkeypatch) -> None:
    fake = _FakeAdapter()
    monkeypatch.setattr(mod, "BinanceAdapter", lambda *args, **kwargs: fake)
    monkeypatch.setitem(mod.TF_INTERVAL_MAP, 1, "1s")

    rows = asyncio.run(
        mod._fetch_klines_for_day(
            symbol="BTCUSDT",
            tf_sec=1,
            date_str="2026-01-01",
            base_url="https://example.invalid",
        )
    )

    assert len(rows) == 1501
    assert len(fake.calls) == 2
    first = fake.calls[0]
    second = fake.calls[1]
    assert second[3] == first[3] + 1500 * 1_000
