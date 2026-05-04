from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.reference.config_loader import get_config
from vfoundation.core.fsm_core import FSMCore, InvalidMessagePayloadError
from vfoundation.core.protocol import Message
from vfoundation.core.schema_registry import get_global_registry, init_global_registry


@pytest.fixture(autouse=True)
def _reset_global_registry():
    import vfoundation.core.schema_registry as mod

    original = mod._global_registry
    mod._global_registry = None
    yield
    mod._global_registry = original


def _build_execpos_with_real_bus():
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    cfg = get_config()
    bus = FSMCore()

    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"), \
         patch("apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"), \
         patch("apps.reference.domains.execution_position.fsm.MetricsCollector"), \
         patch("apps.reference.domains.execution_position.fsm.read_pending_brackets_from_wal", return_value={}):
        fsm = ExecPosFSM(config=cfg, fsm=bus, shadow_mode=True)

    fsm.log_adapter = MagicMock()
    portfolio_state = {
        "positions_last_ts_ms": 9_999_999_999_999,
        "equity_free_usdt": "10000",
        "open_positions_margin_usd": "0",
        "positions": [],
    }
    fsm._latest_portfolio_state = dict(portfolio_state)
    fsm.exposure_guard.on_portfolio(dict(portfolio_state))
    return fsm, bus


def _cmd_open_message(rid: str = "RID-DEC-OPEN-AUDIT") -> Message:
    return Message(
        op="CMD",
        verb="OPEN",
        src="execution_position",
        dst="execution_position",
        rid=rid,
        pld={
            "rid": rid,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.1",
            "order_type": "MARKET",
            "price": "1000",
            "price_ref": "1000",
            "idempotent_key": f"KEY-{rid}",
        },
        why="dec_open_contract_audit",
    )


def _cmd_open_limit_message(rid: str = "RID-DEC-OPEN-LIMIT-AUDIT") -> Message:
    return Message(
        op="CMD",
        verb="OPEN",
        src="execution_position",
        dst="execution_position",
        rid=rid,
        pld={
            "rid": rid,
            "symbol": "BTCUSDT",
            "side": "SELL",
            "qty": "0.1",
            "order_type": "LIMIT",
            "price": "1000.005",
            "tif": "GTX",
            "valid_for_ms": 60_000,
            "idempotent_key": f"KEY-{rid}",
        },
        why="dec_open_limit_contract_audit",
    )


def test_real_dec_open_producer_payload_matches_registered_schema() -> None:
    """Real OpenFlow producer payload must validate before any bus re-emit enrichment."""
    init_global_registry(project_root=".")
    fsm, bus = _build_execpos_with_real_bus()

    with patch("apps.reference.domains.execution_position.fsm.wal.append", return_value="wal-ok"):
        result = fsm.handle(_cmd_open_message())

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "OPEN"
    assert "rid" not in (result.pld or {})

    registry = get_global_registry()
    assert registry is not None
    validator = registry.get_validator("DEC", "OPEN")
    assert validator is not None
    validator.validate(result.pld)


def test_real_limit_dec_open_payload_matches_registered_schema_without_trace_drift() -> None:
    """LIMIT DEC:OPEN must stay schema-valid while trace-only rounding metadata lives outside payload."""
    init_global_registry(project_root=".")
    fsm, _ = _build_execpos_with_real_bus()

    with patch("apps.reference.domains.execution_position.fsm.wal.append", return_value="wal-ok"):
        result = fsm.handle(_cmd_open_limit_message())

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "OPEN"
    assert result.pld["order_type"] == "LIMIT"
    assert result.pld["price"] == "1000.1"
    assert "price_before_rounding" not in (result.pld or {})
    assert "price_after_rounding" not in (result.pld or {})
    assert "tick_size" not in (result.pld or {})
    assert "rounding_mode" not in (result.pld or {})
    assert any(
        isinstance(ref, str) and ref.startswith("obs://execution_position/limit_rounding?")
        for ref in (result.data_ref or [])
    )

    registry = get_global_registry()
    assert registry is not None
    validator = registry.get_validator("DEC", "OPEN")
    assert validator is not None
    validator.validate(result.pld)

def test_dec_open_reemit_preserves_envelope_rid_without_payload_rid() -> None:
    """Aligned re-emit must keep rid in envelope metadata while preserving strict payload schema."""
    init_global_registry(project_root=".")
    fsm, bus = _build_execpos_with_real_bus()
    observed: list[Message] = []
    bus.listen("DEC:OPEN", lambda msg: observed.append(msg))

    with patch("apps.reference.domains.execution_position.fsm.wal.append", return_value="wal-ok"):
        result = fsm.handle(_cmd_open_message(rid="RID-DEC-OPEN-REEMIT"))

    assert result is not None
    bus.emit(
        "DEC:OPEN",
        payload=dict(result.pld or {}),
        why=result.why,
        data_ref=result.data_ref,
        rid=result.rid,
    )

    assert observed
    assert observed[0].rid == "RID-DEC-OPEN-REEMIT"
    assert "rid" not in (observed[0].pld or {})
    assert observed[0].pld["symbol"] == "BTCUSDT"
    assert observed[0].pld["order_type"] == "MARKET"


def test_dec_open_reemit_with_payload_rid_fails_before_listener_dispatch() -> None:
    """Static mismatch class: IntentRouter-style rid enrichment breaks DEC:OPEN strict schema."""
    init_global_registry(project_root=".")
    fsm, bus = _build_execpos_with_real_bus()
    observed: list[dict] = []
    bus.listen("DEC:OPEN", lambda msg: observed.append(msg.pld))

    with patch("apps.reference.domains.execution_position.fsm.wal.append", return_value="wal-ok"):
        result = fsm.handle(_cmd_open_message(rid="RID-DEC-OPEN-RID-DRIFT"))

    assert result is not None
    invalid_payload = dict(result.pld or {})
    invalid_payload["rid"] = result.rid

    with pytest.raises(InvalidMessagePayloadError, match="rid"):
        bus.emit(
            "DEC:OPEN",
            payload=invalid_payload,
            why=result.why,
            data_ref=result.data_ref,
        )

    assert observed == []
