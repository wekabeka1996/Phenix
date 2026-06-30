from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from apps.reference.domains.agent_bridge.reducer import (
    AgentFeedReducer,
    bounded_tail_jsonl,
)


NOW_MS = 1_800_000_000_000


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_bounded_tail_reads_only_capped_end_and_tolerates_partial_line(tmp_path: Path) -> None:
    path = tmp_path / "huge.jsonl"
    path.write_bytes((b"x" * 20_000) + b"\n" + json.dumps({"ts_ms": NOW_MS, "ok": True}).encode() + b"\n")

    rows, diagnostics = bounded_tail_jsonl(path, max_bytes=256, max_lines=5)

    assert rows == [{"ts_ms": NOW_MS, "ok": True}]
    assert "leading_partial_line_discarded" in diagnostics
    source = inspect.getsource(bounded_tail_jsonl)
    assert ".seek(start)" in source
    assert ".read(max(1, int(max_bytes)))" in source
    assert "for line in handle" not in source


def test_packet_marks_missing_sources_and_reports_budget(tmp_path: Path) -> None:
    reducer = AgentFeedReducer(project_root=tmp_path, now_ms=NOW_MS)

    packet = reducer.build_packet(symbols=["BTCUSDT"], max_tokens=4_400)

    assert packet.read_only is True
    assert packet.symbol_markets[0].meta.freshness == "missing"
    assert "close_price" in packet.symbol_markets[0].meta.missing_fields
    assert packet.business_warnings.policy == "advisory_only"
    assert any(item.code == "READINESS_DATA_MISSING" for item in packet.business_warnings.warnings)
    assert packet.budget.payload_bytes > 0
    assert packet.budget.estimated_tokens <= packet.budget.max_tokens_requested
    assert packet.freshness_summary.missing > 0


def test_packet_uses_bounded_latest_truth_without_execution_calls(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_critical_event_journal_v1.jsonl",
        [{
            "ts_ms": NOW_MS - 1_000,
            "payload_fragment": {"portfolio_state": {
                "ts_ms": NOW_MS - 1_000,
                "equity": "1000",
                "available_balance": "900",
                "positions": [],
            }},
        }],
    )
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [{
            "decision_id": "d1",
            "rid": "r1",
            "symbol": "BTCUSDT",
            "response_ts_ms": NOW_MS - 2_000,
            "regime": "TREND_UP",
            "regime_confidence": 0.8,
            "decision_score": 0.2,
            "side": "BUY",
        }],
    )
    _write_jsonl(tmp_path / "logs" / "order_log_v1.jsonl", [])

    class ReadOnlyRuntime:
        manage_flows = {}
        _symbol_brackets = {}

        def submit_order(self, *_args, **_kwargs):  # pragma: no cover - must never run
            raise AssertionError("execution was called")

    packet = AgentFeedReducer(
        project_root=tmp_path,
        execution_position=ReadOnlyRuntime(),
        now_ms=NOW_MS,
    ).build_packet(symbols=["BTCUSDT"])

    assert packet.global_market.equity_usd == 1000.0
    assert packet.symbol_markets[0].regime == "TREND_UP"
    assert packet.execution_body.execution_available is True
    assert packet.execution_body.trace_ref is not None


def test_routes_are_get_only(tmp_path: Path) -> None:
    fastapi = pytest.importorskip("fastapi")
    from apps.reference.domains.agent_bridge.routes import register_agent_feed_routes

    app = fastapi.FastAPI()
    register_agent_feed_routes(app, project_root=tmp_path)
    bridge_routes = [route for route in app.routes if str(getattr(route, "path", "")).startswith("/agent-feed/v0")]

    assert {route.path for route in bridge_routes} == {
        "/agent-feed/v0/health",
        "/agent-feed/v0/sources",
        "/agent-feed/v0/execution-readiness",
        "/agent-feed/v0/packet",
    }
    assert all(set(route.methods or ()) == {"GET"} for route in bridge_routes)
