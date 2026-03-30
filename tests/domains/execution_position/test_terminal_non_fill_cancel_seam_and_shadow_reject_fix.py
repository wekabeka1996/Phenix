import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.domains.execution_position.entry_manager import EntryManager
from apps.reference.domains.execution_position.open_executor import OpenExecutor
from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    attach_shadow_journal,
)
from vfoundation.core.fsm_core import FSMCore


def _shadow_cfg(path: Path):
    return SimpleNamespace(
        observability=SimpleNamespace(
            shadow_journal=SimpleNamespace(
                enabled=True,
                path=str(path),
                schema_version="1.0.0",
                instrumentation_version="1.0.0",
                critical_events=list(DEFAULT_CRITICAL_EVENTS),
            )
        )
    )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class _Deadline:
    def __init__(self, *, symbol: str, order_id: str, rid: str, client_order_id: str) -> None:
        self.symbol = symbol
        self.order_id = order_id
        self.rid = rid
        self.client_order_id = client_order_id
        self.corr_id = "corr-1"
        self.timeout_type = SimpleNamespace(value="fill_timeout")


class _MakerOnlyReject(Exception):
    def __init__(self, code: int) -> None:
        super().__init__("maker only reject")
        self.code = code


@pytest.mark.asyncio
async def test_timeout_cancel_emits_canonical_order_state_changed_and_hits_shadow(tmp_path):
    journal_path = tmp_path / "shadow_timeout_cancel.jsonl"
    bus = FSMCore()
    attach_shadow_journal(bus, _shadow_cfg(journal_path))

    wal_records: list[dict] = []
    fsm = SimpleNamespace(
        fsm=bus,
        adapter=AsyncMock(),
        shadow_mode=False,
        watchdog=MagicMock(
            cancel_attempt_count=0,
            cancel_success_count=0,
            on_order_cancel=MagicMock(),
        ),
        metrics_collector=MagicMock(),
        alert_manager=None,
        _is_cancel_success_response=MagicMock(return_value=True),
        _is_unknown_order_error=MagicMock(return_value=False),
    )
    fsm._cancel_order = AsyncMock(return_value={"status": "CANCELED"})

    deadline = _Deadline(
        symbol="SOLUSDT",
        order_id="1811569723",
        rid="aurora_SOLUSDT_1774142702617",
        client_order_id="ENTRY-4dc9a0dc9de7",
    )

    with patch("vfoundation.dr.wal.append", side_effect=wal_records.append), patch(
        "apps.reference.domains.execution_position.entry_manager.order_logger.write"
    ):
        await EntryManager(fsm).handle_order_timeout(deadline)

    fsm.watchdog.on_order_cancel.assert_called_once_with("1811569723")

    state_changed = [r for r in wal_records if r.get("verb") == "ORDER_STATE_CHANGED"]
    assert len(state_changed) == 1
    payload = state_changed[0]["pld"]
    assert payload["symbol"] == "SOLUSDT"
    assert payload["status"] == "CANCELED"
    assert payload["terminal_non_fill"] is True
    assert payload["terminal_state_kind"] == "CANCELED"
    assert payload["canonical_identity_key"] == (
        "evt:order_state_changed:symbol=SOLUSDT:order_id=1811569723:"
        "client_order_id=ENTRY-4dc9a0dc9de7:terminal_state=CANCELED"
    )

    records = _read_jsonl(journal_path)
    shadow_events = [r for r in records if r["event_name"] == "EVT:ORDER_STATE_CHANGED"]
    assert len(shadow_events) == 1
    fragment = shadow_events[0]["payload_fragment"]
    assert fragment["terminal_non_fill"] is True
    assert fragment["terminal_state_kind"] == "CANCELED"
    assert fragment["canonical_identity_key"] == payload["canonical_identity_key"]


@pytest.mark.asyncio
async def test_live_reject_path_reaches_wal_and_local_shadow_without_emit_compat_fallback(tmp_path):
    journal_path = tmp_path / "shadow_reject.jsonl"
    bus = FSMCore()
    attach_shadow_journal(bus, _shadow_cfg(journal_path))

    wal_records: list[dict] = []
    adapter = SimpleNamespace(
        place_limit_entry=AsyncMock(side_effect=_MakerOnlyReject(-5022)),
    )
    fsm = SimpleNamespace(fsm=bus, adapter=adapter)
    executor = OpenExecutor(fsm)
    decision = SimpleNamespace(rid="mdamr-shadow-gap-fix")

    with patch("vfoundation.dr.wal.append", side_effect=wal_records.append), patch(
        "apps.reference.domains.execution_position.open_executor.order_logger.write"
    ), patch(
        "apps.reference.domains.execution_position.terminal_order_contracts.emit_compat",
        new_callable=AsyncMock,
    ) as mock_emit_compat:
        result = await executor._place_limit_entry(
            decision=decision,
            symbol="XRPUSDT",
            side="BUY",
            price="1.4004",
            qty="6246.7",
            tif="GTX",
            entry_id="ENTRY-XRP-1",
            wal=MagicMock(),
        )

    assert result is None
    mock_emit_compat.assert_not_awaited()

    rejected = [r for r in wal_records if r.get("verb") == "ORDER_REJECTED"]
    assert len(rejected) == 1
    payload = rejected[0]["pld"]
    assert payload["symbol"] == "XRPUSDT"
    assert payload["reject_reason_normalized"] == "MAKER_ONLY_REJECT"
    assert payload["terminal_non_fill"] is True
    assert payload["terminal_state_kind"] == "REJECTED"
    assert payload["canonical_identity_key"] == (
        "evt:order_rejected:symbol=XRPUSDT:rid=mdamr-shadow-gap-fix:"
        "terminal_state=REJECTED:reject_reason=MAKER_ONLY_REJECT"
    )

    records = _read_jsonl(journal_path)
    shadow_events = [r for r in records if r["event_name"] == "EVT:ORDER_REJECTED"]
    assert len(shadow_events) == 1
    fragment = shadow_events[0]["payload_fragment"]
    assert fragment["terminal_state_kind"] == "REJECTED"
    assert fragment["reject_reason_normalized"] == "MAKER_ONLY_REJECT"
    assert fragment["canonical_identity_key"] == payload["canonical_identity_key"]
