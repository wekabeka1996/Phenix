"""Observability tests for ExecPosFSM aggregated OCO state dump."""

from __future__ import annotations

import time
import types
from decimal import Decimal
from typing import Any, Dict, List

import pytest

import apps.reference.domains.execution_position.fsm as execpos_mod
from apps.reference.domains.execution_position.fsm import PositionSnapshot
from apps.reference.services.order_guardian import BracketSetMeta


class _StubGuardian:
    """Minimal guardian stub that returns pre-seeded bracket meta."""

    def __init__(self, metas: List[BracketSetMeta]) -> None:
        self._metas = list(metas)

    def list_bracket_sets(self) -> List[BracketSetMeta]:
        return list(self._metas)


def _aggregated_only_manage_config() -> Dict[str, Any]:
    """Return a trimmed aggregated-only manage config for the test harness."""

    return {
        "trading": {
            "execution": {
                "manage": {
                    "mode": "aggregated_only",
                    "auto": True,
                    "brackets": {
                        "enable": True,
                        "aggregated_oco": {
                            "enabled": True,
                            "aggregated_only_mode": True,
                            "recalc_on_scale_in": True,
                            "recalc_on_partial_close": True,
                            "ttl_protect_new_bracket_ms": 0,
                            "allow_unprotected_position": False,
                            "watchdog": {
                                "enabled": False,
                                "interval_sec": 5,
                                "auto_heal_orphans": True,
                            },
                        },
                    },
                    "guardian": {
                        "unified": True,
                        "emit_tidy_event": True,
                        "poll_interval_ms": 500,
                        "cleanup_ttl_ms": 700,
                        "symbol_cooldown_ms": 800,
                    },
                    "watchdog": {
                        "ack_ttl_ms": 8000,
                        "fill_ttl_ms": 30000,
                        "check_interval_ms": 1000,
                        "source": "test",
                    },
                    "orphan_monitor": {
                        "enabled": False,
                        "run_on_startup": False,
                        "periodic_interval_sec": 300,
                        "min_order_age_sec": 0,
                        "batch_cancel_limit": 50,
                        "rate_limit_per_min": 120,
                    },
                    "positions": {
                        "ws_snapshot": {
                            "enabled": True,
                            "max_age_ms": 1500,
                            "rest_fallback_enabled": True,
                        }
                    },
                }
            }
        }
    }


def test_agg_oco_state_snapshot_contains_position_brackets_and_watchdog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify rows combine WS cache, manage flow state, guardian, and watchdog."""

    monkeypatch.setattr(
        execpos_mod.ExecPosFSM, "_schedule_guardian_start", lambda self: None
    )
    monkeypatch.setattr(
        execpos_mod.ExecPosFSM, "_schedule_agg_oco_watchdog", lambda self: None
    )

    fsm = execpos_mod.ExecPosFSM(
        config=_aggregated_only_manage_config(),
        fsm=None,
        shadow_mode=True,
    )

    symbol = "SOLUSDT"
    agg_side = "LONG"
    snapshot = PositionSnapshot(
        symbol=symbol,
        side=agg_side,
        position_amt=1.25,
        avg_price=25.5,
        updated_ts=time.time(),
    )
    fsm._ws_position_cache[(symbol, agg_side)] = snapshot

    bracket_meta = BracketSetMeta(
        bracket_set_id="agg-sol-long",
        symbol=symbol,
        side=agg_side,
        sl_order_id="sl-123",
        tp_order_id="tp-456",
        created_ts=time.time(),
        version=1,
    )
    fsm.order_guardian = _StubGuardian([bracket_meta])

    manage_stub = types.SimpleNamespace(
        _agg_side=agg_side,
        position_qty=Decimal("1.25"),
        position_entry_price=Decimal("25.5"),
        sl_price=Decimal("24"),
        tp_price=Decimal("28"),
        _current_bracket_meta=bracket_meta,
    )
    fsm.manage_flows[symbol] = manage_stub

    fsm._agg_watchdog_status[(symbol, agg_side)] = {
        "status": "OK",
        "updated_ts": 1700000000.0,
        "details": {"source": "unit-test"},
    }

    rows = fsm.get_agg_oco_state_snapshot()
    assert rows, "expected aggregated snapshot rows"

    by_key = {(row["symbol"], row["side"]): row for row in rows}
    target = by_key[(symbol, agg_side)]

    assert target["position_qty"] == "1.25"
    assert target["position_source"] == "ws_snapshot"
    assert target["avg_entry_price"] == "25.5"
    assert target["sl_price"] == "24"
    assert target["tp_price"] == "28"
    assert target["bracket_set_id"] == bracket_meta.bracket_set_id
    assert target["bracket_sl_order_id"] == bracket_meta.sl_order_id
    assert target["watchdog_status"] == "OK"
    assert target["watchdog_details"] == {"source": "unit-test"}
