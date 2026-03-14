from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.domains.decision_making.md_amr_handler import MDAMRHandler


class _Event:
    def __init__(self, payload: dict) -> None:
        self.pld = payload


def test_md_amr_process_strategy_blocks_cold_start_until_basis_bars_seen() -> None:
    handler = object.__new__(MDAMRHandler)
    rejections: list[dict] = []

    handler.logger = logging.getLogger("tests.md_amr.runtime")
    handler.mlog = logging.getLogger("tests.md_amr.runtime")
    handler._enabled = True
    handler._enabled_symbols = {"BTCUSDT"}
    handler._cfg = SimpleNamespace(
        timeframe_sec=900,
        llm_gate=SimpleNamespace(
            enabled=False,
            sentiment_block_threshold=0.0,
            block_ttl_sec=0,
        ),
    )
    handler.config = SimpleNamespace()
    handler._bars_seen_since_restart = {}
    handler._pending_close = {}
    handler._position_qty = {}
    handler._bars_held = {}
    handler._last_ingested_bar_ts_ms = {}
    handler._deferred = {}
    handler._strategies = {
        "BTCUSDT": SimpleNamespace(on_bar=lambda **_kwargs: {"status": "SIGNAL"})
    }
    handler._is_duplicate_live_event = lambda symbol, ts_ms: False
    handler._expire_defer_if_needed = lambda symbol, now_ms: None
    handler._is_mandatory_live_warmup_active = lambda now_ms: False
    handler._emit_trade_intent_rejected_gate = lambda **kwargs: rejections.append(kwargs)
    handler._rid = lambda **_kwargs: "md-amr-bars-required"

    event = _Event(
        {
            "symbol": "BTCUSDT",
            "tf_sec": 900,
            "warmup": {"full_ready": True},
            "bar": {"end_ts_ms": 1_700_000_000_000},
            "features": {},
        }
    )

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=SimpleNamespace(basis_required_bars=5),
    ):
        handler._on_process_strategy(event)

    assert handler._bars_seen_since_restart["BTCUSDT"] == 1
    assert len(rejections) == 1
    assert rejections[0]["reason_code"] == "BARS_REQUIRED_COLD_START"
    assert rejections[0]["details"] == {
        "bars_seen": 1,
        "basis_required_bars": 5,
    }


def test_md_amr_seeded_basis_bars_bypass_cold_start_gate() -> None:
    handler = object.__new__(MDAMRHandler)
    rejections: list[dict] = []
    on_bar_calls: list[dict] = []

    handler.logger = logging.getLogger("tests.md_amr.runtime")
    handler.mlog = logging.getLogger("tests.md_amr.runtime")
    handler._enabled = True
    handler._enabled_symbols = {"BTCUSDT"}
    handler._cfg = SimpleNamespace(
        timeframe_sec=900,
        llm_gate=SimpleNamespace(
            enabled=False,
            sentiment_block_threshold=0.0,
            block_ttl_sec=0,
        ),
    )
    handler.config = SimpleNamespace()
    handler._bars_seen_since_restart = {}
    handler._pending_close = {}
    handler._position_qty = {}
    handler._bars_held = {}
    handler._last_ingested_bar_ts_ms = {}
    handler._deferred = {}
    handler._strategies = {
        "BTCUSDT": SimpleNamespace(
            on_bar=lambda **kwargs: on_bar_calls.append(kwargs) or {"status": "NO_SIGNAL"}
        )
    }
    handler._is_duplicate_live_event = lambda symbol, ts_ms: False
    handler._expire_defer_if_needed = lambda symbol, now_ms: None
    handler._is_mandatory_live_warmup_active = lambda now_ms: False
    handler._emit_trade_intent_rejected_gate = lambda **kwargs: rejections.append(kwargs)
    handler._rid = lambda **_kwargs: "md-amr-bars-seeded"
    handler.seed_startup_bars("BTCUSDT", 5)

    event = _Event(
        {
            "symbol": "BTCUSDT",
            "tf_sec": 900,
            "warmup": {"full_ready": True},
            "bar": {"end_ts_ms": 1_700_000_000_000},
            "features": {},
        }
    )

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=SimpleNamespace(basis_required_bars=5),
    ):
        handler._on_process_strategy(event)

    assert rejections == []
    assert on_bar_calls
