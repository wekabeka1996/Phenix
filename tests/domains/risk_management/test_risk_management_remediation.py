from __future__ import annotations

import json
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from apps.reference.config_loader import get_config
from apps.reference.domains.risk_management.daily_gate import DailyRiskState
from apps.reference.domains.risk_management.risk_management import RiskManagement, _to_dec
from vfoundation.core.protocol import Message


class _CaptureFSM:
    def __init__(self) -> None:
        self.emitted: list[dict] = []

    def listen(self, *_a, **_k) -> None:
        return

    def emit(self, event_name, payload, why, data_ref=None, rid=None) -> None:
        self.emitted.append(
            {
                "event_name": event_name,
                "payload": payload,
                "why": why,
                "rid": rid,
                "data_ref": data_ref,
            }
        )


class _DummyFsm:
    def listen(self, *_a, **_k) -> None:
        return

    def emit(self, *_a, **_k) -> None:
        return


def _cfg_daily_enabled():
    cfg = get_config()
    return cfg.model_copy(
        deep=True,
        update={
            "trading_mode": "live",
            "trading": cfg.trading.model_copy(
                update={
                    "risk": {
                        **cfg.trading.risk,
                        "daily": {
                            **cfg.trading.risk["daily"],
                            "enabled": True,
                        },
                    }
                }
            )
        },
    )


def test_rid_is_forwarded_to_risk_assessment_emit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AURORA_RISK_GATE_STATE_PATH", str(tmp_path / "risk_state.json"))

    fsm = _CaptureFSM()
    rm = RiskManagement(fsm=fsm, config=_cfg_daily_enabled())

    rid = "RID-CHAIN-123"
    msg = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        src="test",
        dst="any",
        rid=rid,
        pld={"symbol": "BTCUSDT", "ts": 1700000000000, "features": {}},
        why="test",
    )

    rm.on_features_calculated(msg)

    emitted = fsm.emitted[-1]
    assert emitted["event_name"] == "EVT:RISK_ASSESSMENT_COMPLETED"
    assert emitted["rid"] == rid


def test_risk_assessment_payload_matches_json_schema(monkeypatch, tmp_path: Path) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    monkeypatch.setenv("AURORA_RISK_GATE_STATE_PATH", str(tmp_path / "risk_state.json"))

    fsm = _CaptureFSM()
    rm = RiskManagement(fsm=fsm, config=_cfg_daily_enabled())

    now = datetime(2026, 2, 24, 12, 0, tzinfo=timezone.utc)
    rm.daily_risk_state.on_portfolio({"equity_cross_usdt": "1000"}, now=now)

    msg = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        src="test",
        dst="any",
        rid="RID-SCHEMA",
        pld={
            "symbol": "BTCUSDT",
            "ts": 1700000000000,
            "features": {
                "price": "100",
                "delta_price": "1.0",
                "obi": "0.1",
                "tfi": "0.1",
                "absorption": "0.5",
            },
        },
        why="test",
    )
    rm.on_features_calculated(msg)
    payload = fsm.emitted[-1]["payload"]

    schema_path = Path("apps/reference/domains/risk_management/schemas/risk_assessment_v1.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)


def test_to_dec_raises_on_invalid_data() -> None:
    with pytest.raises(Exception):
        _to_dec("not-a-decimal")
    with pytest.raises(Exception):
        _to_dec(None)


def test_daily_risk_state_has_thread_lock() -> None:
    gate = DailyRiskState(_cfg_daily_enabled())
    assert hasattr(gate, "_lock")
    assert isinstance(gate._lock, threading.Lock().__class__)


def test_corrupted_state_blocks_intraday_until_next_day(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "risk_state.json"
    monkeypatch.setenv("AURORA_RISK_GATE_STATE_PATH", str(state_path))

    # Freeze wall-clock so _load_state recovery_trading_date matches test's frozen datetime.
    # Without this, _now_utc() returns real date (2026-03-04) while test uses 2026-02-24,
    # causing the recovery block to be immediately cleared on the first on_portfolio call.
    from apps.reference.domains.risk_management import daily_gate as daily_gate_mod
    now = datetime(2026, 2, 24, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(daily_gate_mod, "_now_utc", lambda: now)

    cfg = _cfg_daily_enabled()
    gate = DailyRiskState(cfg)

    gate.on_portfolio({"equity_cross_usdt": "1000"}, now=now)
    gate.on_portfolio({"equity_cross_usdt": "850"}, now=now)
    allowed_before, reason_before = gate.can_open()

    assert allowed_before is False
    assert reason_before.get("detail") == "MAX_DRAWDOWN"

    state_path.write_text("{bad-json", encoding="utf-8")

    restarted = DailyRiskState(cfg)
    restarted.on_portfolio({"equity_cross_usdt": "850"}, now=now)
    allowed_same_day, reason_same_day = restarted.can_open()

    assert allowed_same_day is False
    assert reason_same_day.get("detail") == "NO_EQUITY"

    next_day = now + timedelta(days=1)
    # Advance frozen clock to next day for re-anchor
    monkeypatch.setattr(daily_gate_mod, "_now_utc", lambda: next_day)
    restarted.on_portfolio({"equity_cross_usdt": "850"}, now=next_day)
    allowed_next_day, _ = restarted.can_open()

    assert allowed_next_day is True
