from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.domains.strategies.runtimes.md_amr.entry_anchor_artifact import (
    MDAMREntryAnchorArtifactStore,
)
from apps.reference.domains.strategies.runtimes.md_amr.handler import MDAMRHandler
from apps.reference.domains.feature_engineering.md_amr_strategy import MDAMRSignal


class _FSMStub:
    def __init__(self, execution_domain: object | None = None) -> None:
        self.execution_domain = execution_domain
        self.listeners: list[tuple[str, object]] = []
        self.emitted: list[tuple[str, dict, str | None]] = []

    def listen(self, event: str, handler: object) -> None:
        self.listeners.append((event, handler))

    def emit(
        self,
        event_name: str,
        payload: dict | None = None,
        why: str | None = None,
        data_ref: object = None,
    ) -> None:
        self.emitted.append((event_name, payload or {}, why))

    def get_domain(self, name: str):
        if name == "execution_position":
            return self.execution_domain
        return None


class _Event:
    def __init__(self, payload: dict) -> None:
        self.pld = payload


def _artifact_path(tmp_path: Path) -> Path:
    return tmp_path / "md_amr_entry_anchor_state_v1.json"


def _make_handler(
    tmp_path: Path,
    *,
    execution_domain: object | None = None,
    symbol: str = "BNBUSDT",
) -> MDAMRHandler:
    handler = object.__new__(MDAMRHandler)
    handler.fsm = _FSMStub(execution_domain)
    handler.logger = logging.getLogger("tests.md_amr.anchor")
    handler.mlog = logging.getLogger("tests.md_amr.anchor")
    handler._enabled = True
    handler._enabled_symbols = {symbol}
    handler._cfg = SimpleNamespace(
        timeframe_sec=900,
        llm_gate=SimpleNamespace(
            enabled=False,
            sentiment_block_threshold=0.0,
            block_ttl_sec=0,
        ),
        objective=SimpleNamespace(enabled=False),
        execution=SimpleNamespace(
            gtx_retry_max=2,
            emit_market_fallback_marker_on_retry_exhaustion=True,
        ),
        concentration_guard=SimpleNamespace(
            enabled=False,
            max_simultaneous_entries_per_bar=2,
        ),
        assets={
            symbol: SimpleNamespace(
                cooldown_sec=60,
                allowed_regimes=["MEAN_REVERSION", "LOW_VOLATILITY"],
                exit=SimpleNamespace(
                    sl_pct=0.005,
                    tp_rr=1.0,
                    regime_tpsl=None,
                ),
            )
        },
        entry_anchor_persistence=SimpleNamespace(
            storage_path=str(_artifact_path(tmp_path)),
        ),
    )
    handler.config = SimpleNamespace()
    handler._bars_seen_since_restart = {symbol: 1}
    handler._pending_close = {}
    handler._position_qty = {symbol: Decimal("0")}
    handler._bars_held = {}
    handler._deferred = {}
    handler._macro_block_until_ms = {}
    handler._regime = {symbol: "MEAN_REVERSION"}
    handler._regime_ts_ms = {}
    handler._regime_confidence = {symbol: 0.8}
    handler._rest_hydrated = False
    handler._rest_last_bar_ts_ms = {}
    handler._last_ingested_bar_ts_ms = {}
    handler._last_close_ts = {}
    handler._gtx_retries = {}
    handler._entries_at_ts = {}
    handler._objective_blocked_ts_ms = {}
    handler._objective_cancel_replace_ts_ms = {}
    handler._objective_reentry_ts_ms = {}
    handler._analytics_restore_snapshots = {}
    handler._latest_portfolio = None
    handler._latest_exposure_summary = None
    handler._position_queries = None
    handler._entry_anchor = {}
    handler._entry_anchor_records = {}
    handler._entry_anchor_store = None
    handler._entry_anchor_diag_tokens = {}
    handler._last_features = {}
    handler._signal_ready_logged = set()
    handler.mandatory_warmup_until = 0
    handler._strategies = {}
    handler._is_duplicate_live_event = lambda symbol, ts_ms: False
    handler._expire_defer_if_needed = lambda symbol, now_ms: None
    handler._is_mandatory_live_warmup_active = lambda now_ms: False
    handler._emit_trade_intent_rejected_gate = lambda **kwargs: None
    handler._rid = lambda **kwargs: "md-amr-anchor-rid"
    return handler


def _entry_signal() -> MDAMRSignal:
    return MDAMRSignal(
        intent_kind="ENTRY",
        side="BUY",
        reason_code="MD_AMR_ENTRY_LONG",
        signal_score=0.9,
        conf_ratio=0.8,
        scaleout_fraction=None,
        price_ref=Decimal("600"),
        channel_state={"avg_close_12": 610.0},
        atr=1.0,
        dir_score=0.5,
        trace={},
    )


def _process_event(symbol: str = "BNBUSDT") -> _Event:
    return _Event(
        {
            "symbol": symbol,
            "tf_sec": 900,
            "warmup": {"full_ready": True},
            "bar": {
                "end_ts_ms": 1_700_000_000_000,
                "open": "600",
                "high": "601",
                "low": "599",
                "close": "600.5",
            },
            "features": {},
        }
    )


def test_entry_signal_sets_and_persists_anchor(tmp_path: Path) -> None:
    handler = _make_handler(tmp_path)
    handler._strategies["BNBUSDT"] = SimpleNamespace(
        on_bar=lambda **kwargs: {"status": "SIGNAL", "signal": _entry_signal()}
    )

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=SimpleNamespace(basis_required_bars=1),
    ):
        handler._on_process_strategy(_process_event())

    assert handler._entry_anchor["BNBUSDT"] == {
        "entry_price": 600.0,
        "entry_target_price": 610.0,
    }

    store = MDAMREntryAnchorArtifactStore(str(_artifact_path(tmp_path)))
    records = store.load_records()
    assert records["BNBUSDT"].entry_target_price == 610.0
    assert records["BNBUSDT"].entry_price_hint == 600.0


def test_register_restores_anchor_using_persisted_target_and_execution_entry_price(
    tmp_path: Path,
    caplog,
) -> None:
    store = MDAMREntryAnchorArtifactStore(str(_artifact_path(tmp_path)))
    baseline = _make_handler(tmp_path)
    baseline._capture_entry_anchor(
        symbol="BNBUSDT",
        entry_price=600.0,
        entry_target_price=610.0,
        entry_signal_rid="rid-1",
        updated_at_ms=1_700_000_000_000,
    )
    assert store.load_records()["BNBUSDT"].entry_target_price == 610.0

    execution_domain = SimpleNamespace(
        _latest_portfolio_state={
            "positions": [
                {
                    "symbol": "BNBUSDT",
                    "net_position": "1",
                    "entryPrice": "605.5",
                }
            ]
        }
    )
    handler = _make_handler(tmp_path, execution_domain=execution_domain)
    handler._hydrate_state_from_rest = lambda: None

    with caplog.at_level(logging.INFO):
        handler.register()

    assert handler._entry_anchor["BNBUSDT"] == {
        "entry_price": 605.5,
        "entry_target_price": 610.0,
    }
    assert "MD_AMR_C1_ANCHOR_RESTORED" in caplog.text


def test_portfolio_update_restores_anchor_when_execution_truth_arrives_late(
    tmp_path: Path,
) -> None:
    baseline = _make_handler(tmp_path)
    baseline._capture_entry_anchor(
        symbol="BNBUSDT",
        entry_price=600.0,
        entry_target_price=610.0,
        entry_signal_rid="rid-2",
        updated_at_ms=1_700_000_000_000,
    )

    handler = _make_handler(tmp_path)
    handler._load_persisted_entry_anchor_records()

    handler._on_portfolio_state_updated(
        _Event(
            {
                "ts": 1_700_000_005_000,
                "positions_last_ts_ms": 1_700_000_005_000,
                "positions": [
                    {
                        "symbol": "BNBUSDT",
                        "net_position": "1",
                        "entryPrice": "602.25",
                    }
                ],
            }
        )
    )

    assert handler._entry_anchor["BNBUSDT"] == {
        "entry_price": 602.25,
        "entry_target_price": 610.0,
    }


def test_missing_persisted_target_keeps_context_fail_closed_and_logs_unknown(
    tmp_path: Path,
    caplog,
) -> None:
    execution_domain = SimpleNamespace(
        _latest_portfolio_state={
            "positions": [
                {
                    "symbol": "BNBUSDT",
                    "net_position": "1",
                    "entryPrice": "605.5",
                }
            ]
        }
    )
    handler = _make_handler(tmp_path, execution_domain=execution_domain)
    handler._position_qty["BNBUSDT"] = Decimal("1")
    handler._bars_held["BNBUSDT"] = 3
    handler._strategies["BNBUSDT"] = SimpleNamespace(
        on_bar=lambda **kwargs: {"status": "NO_SIGNAL"}
    )

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=SimpleNamespace(basis_required_bars=1),
    ):
        with caplog.at_level(logging.INFO):
            handler._on_process_strategy(_process_event())

    assert "BNBUSDT" not in handler._entry_anchor
    assert "MD_AMR_C1_ANCHOR_UNAVAILABLE" in caplog.text
    assert "MD_AMR_C4_CONTEXT_FALLBACK_UNKNOWN" in caplog.text
