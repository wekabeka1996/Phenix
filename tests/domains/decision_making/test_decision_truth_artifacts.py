from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
from apps.reference.domains.decision_making.decision_truth_artifacts import (
    write_strategy_decision_blocked,
)
from apps.reference.domains.decision_making.intent_emitter import IntentEmitter
from apps.reference.telemetry.shadow_journal import ShadowCriticalEventJournal


class _Clock:
    def __init__(self, now_ms: int = 1_700_000_000_000) -> None:
        self._now_ms = int(now_ms)

    def now_ms(self) -> int:
        return self._now_ms

    def now_sec(self) -> float:
        return self._now_ms / 1000.0


def test_write_strategy_decision_blocked_uses_blocked_wal_verb(monkeypatch) -> None:
    rows: list[dict] = []
    monkeypatch.setattr(
        "apps.reference.domains.decision_making.decision_truth_artifacts.wal.append",
        lambda row: rows.append(dict(row)),
    )

    payload = write_strategy_decision_blocked(
        strategy_id="aurora",
        symbol="BTCUSDT",
        reason_code="READINESS_BLOCKED",
        reason="READINESS",
        context="aurora_handler:bars_required_gate",
        src="test",
        ts_ms=1_700_000_000_000,
        rid="rid-1",
        why="Cold-start bars missing",
        why_chain=["READINESS", "BARS_REQUIRED"],
        tf_sec=300,
        bar_close_ts=1_700_000_000_000,
    )

    assert payload["stage"] == "STRATEGY"
    assert rows, "Expected WAL append for blocked truth"
    assert rows[0]["verb"] == "STRATEGY_DECISION_BLOCKED"
    assert rows[0]["pld"]["reason_code"] == "READINESS_BLOCKED"
    assert rows[0]["pld"]["why"] == "Cold-start bars missing"


def test_intent_emitter_writes_intent_deferred_truth(monkeypatch) -> None:
    rows: list[dict] = []
    monkeypatch.setattr(
        "apps.reference.domains.decision_making.decision_truth_artifacts.wal.append",
        lambda row: rows.append(dict(row)),
    )
    fsm = MagicMock()
    emitter = IntentEmitter(
        fsm=fsm,
        clock=_Clock(),
        config=SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    decision=SimpleNamespace(retry_ttl_ms=5_000, retry_max_count=3)
                )
            ),
            domains=SimpleNamespace(decision_making=SimpleNamespace(risk_gate=SimpleNamespace(min_intents_for_check=10, threshold_pct_testnet=20.0, threshold_pct_production=20.0))),
            trading=SimpleNamespace(mode="testnet"),
        ),
        alert_manager=None,
        get_portfolio=lambda: None,
        propose_trade_intent=lambda **_kw: None,
        logger=MagicMock(),
    )

    emitter.emit_intent_deferred_v1(
        symbol="BTCUSDT",
        reason="NRR-025",
        retry_key="rk-1",
        next_allowed_ts=1_700_000_001_000,
        original_event_name="EVT:STRATEGY_SIGNAL_PRODUCED",
        original_payload_min={"symbol": "BTCUSDT", "side": "BUY", "rid": "rid-1"},
        why_chain=["risk_skew"],
        context="strategy_signal_gateway:risk_skew",
    )

    fsm.emit.assert_called_once()
    emitted_payload = fsm.emit.call_args.args[1]
    assert emitted_payload["reason"] == "NRR-DATA-NOT-READY"
    assert emitted_payload["reason_code"] == "NRR-DATA-NOT-READY"
    assert emitted_payload["raw_reason"] == "NRR-025"
    assert rows, "Expected WAL append for deferred truth"
    assert rows[0]["verb"] == "INTENT_DEFERRED"
    assert rows[0]["pld"]["reason_code"] == "NRR-DATA-NOT-READY"


def test_aurora_handler_blocked_helper_emits_blocked_truth(monkeypatch) -> None:
    rows: list[dict] = []
    monkeypatch.setattr(
        "apps.reference.domains.decision_making.decision_truth_artifacts.wal.append",
        lambda row: rows.append(dict(row)),
    )
    emit_fn = MagicMock()
    handler = AuroraHandler(
        config=SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=60,
                        side_bias_target_ratio=0.5,
                        side_bias_penalty_factor=0.5,
                        side_bias_min_intents=5,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=None,
                    ),
                    assets={},
                )
            )
        ),
        emit_fn=emit_fn,
    )

    handler._emit_strategy_blocked(
        symbol="BTCUSDT",
        reason_code="BARS_REQUIRED_COLD_START",
        reason="READINESS",
        context="aurora_handler:bars_required_gate",
        rid="rid-2",
        why="Cold-start: 1/10 bars seen",
        why_chain=["READINESS", "BARS_REQUIRED"],
        tf_sec=300,
        bar_close_ts=1_700_000_000_000,
    )

    emit_fn.assert_called_once()
    event_name, payload = emit_fn.call_args.args
    assert event_name == "EVT:STRATEGY_DECISION_BLOCKED"
    assert payload["stage"] == "STRATEGY"
    assert payload["rid"] == "rid-2"
    assert rows[0]["verb"] == "STRATEGY_DECISION_BLOCKED"


def test_shadow_journal_defaults_capture_blocked_and_deferred(tmp_path) -> None:
    journal = ShadowCriticalEventJournal(path=str(tmp_path / "shadow.jsonl"))
    assert journal.should_capture("EVT:INTENT_DEFERRED") is True
    assert journal.should_capture("EVT:DECISION_BLOCKED") is True
    assert journal.should_capture("EVT:STRATEGY_DECISION_BLOCKED") is True
