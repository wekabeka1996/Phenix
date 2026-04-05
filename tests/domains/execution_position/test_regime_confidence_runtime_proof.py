from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.config_loader import get_config
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.decision_making.safety_gates import apply_safety_gates as _apply_safety_gates
from apps.reference.telemetry.order_logger import order_logger
from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    attach_shadow_journal,
)
from apps.reference.telemetry.trade_lifecycle_logger import trade_lifecycle
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message
from vfoundation.core.schema_registry import init_global_registry
from vfoundation.dr import wal


def _shadow_cfg(path: Path) -> SimpleNamespace:
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
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_controlled_runtime_proof_persists_regime_provenance_through_order_placed(tmp_path: Path) -> None:
    init_global_registry(project_root=".")

    rid = "RID-RUNTIME-PROOF-ORDER-PLACED-1"
    symbol = "BTCUSDT"
    shadow_path = tmp_path / "shadow_critical_event_journal_v1.jsonl"
    wal_dir = tmp_path / "wal"
    order_log_path = tmp_path / "order_log_v1.jsonl"
    lifecycle_path = tmp_path / "trade_lifecycle.jsonl"
    cache_snapshot_path = tmp_path / "regime_cache_snapshot.json"
    safety_gate_path = tmp_path / "safety_gate_result.json"
    summary_path = tmp_path / "runtime_proof_summary.json"

    bus = FSMCore()
    attach_shadow_journal(bus, _shadow_cfg(shadow_path))

    original_wal_dir = wal.WAL_DIR
    original_order_log_path = order_logger.log_file
    original_lifecycle_log_path = trade_lifecycle._log_file
    original_lifecycle_trades = trade_lifecycle._trades
    original_lifecycle_recent = trade_lifecycle._recent_terminal

    try:
        wal.set_wal_dir(wal_dir)
        order_logger.log_file = order_log_path
        trade_lifecycle._log_file = lifecycle_path
        trade_lifecycle._trades = OrderedDict()
        trade_lifecycle._recent_terminal = OrderedDict()

        cfg = get_config()
        cfg.strategies.aurora.safety_gates.enabled = True
        cfg.domains.decision_making.directional_sanity.enabled = False
        cfg.domains.decision_making.price_motion_sanity.enabled = False

        observed_intents = []
        observed_open = []
        observed_order_placed = []
        bus.listen("EVT:TRADE_INTENT_PROPOSED",
                   lambda msg: observed_intents.append(msg))
        bus.listen("DEC:OPEN", lambda msg: observed_open.append(msg))
        bus.listen("EVT:ORDER_PLACED",
                   lambda msg: observed_order_placed.append(msg))

        with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_guardian_cls, patch(
            "apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"
        ), patch("apps.reference.domains.execution_position.fsm.MetricsCollector"), patch(
            "apps.reference.domains.execution_position.fsm.read_pending_brackets_from_wal",
            return_value={},
        ):
            from apps.reference.domains.execution_position.fsm import ExecPosFSM

            mock_guardian_cls.return_value.start = AsyncMock()
            mock_guardian_cls.return_value.link_existing_from_rest = AsyncMock()
            mock_guardian_cls.return_value.cleanup_orphans = AsyncMock()
            ep = ExecPosFSM(config=cfg, fsm=bus, shadow_mode=True)

        ep.log_adapter = MagicMock()
        ep._evt_handlers.entry_tidy_gate_allow = MagicMock(return_value=True)
        ep.watchdog.pending_orders = {}
        ep.watchdog.acked_orders = {}
        ep.watchdog.ensure_started = MagicMock()
        ep.watchdog.track_order_placed = MagicMock()
        ep.watchdog.on_order_ack = MagicMock()
        ep._bracket_mgr.preflight_position_check = AsyncMock(
            return_value=False)
        ep.adapter = SimpleNamespace(
            base_url="https://testnet.binance.vision",
            get_mark_price=AsyncMock(return_value="50000"),
            place_market_entry=AsyncMock(
                return_value={
                    "orderId": "900001",
                    "symbol": symbol,
                    "status": "NEW",
                }
            ),
            track_order=MagicMock(),
        )

        portfolio_state = {
            "positions_last_ts_ms": 9_999_999_999_999,
            "equity_free_usdt": "10000",
            "open_positions_margin_usd": "0",
            "positions": [],
        }
        ep._latest_portfolio_state = dict(portfolio_state)
        ep.exposure_guard.on_portfolio(dict(portfolio_state))

        dm = DecisionMaking(fsm=bus, config=cfg)
        dm._builder._warmup_gate = lambda **_kw: False
        dm._builder._tca_prefs = {
            "max_slippage_bps": 10,
            "max_latency_ms": 100,
            "maker_preference": False,
        }
        dm._builder._risk_budgets = {
            "trade_cvar95_max_bps": 50,
            "session_cvar95_max_bps": 100,
        }
        dm._builder._resolve_order_policy = MagicMock(
            return_value=("MARKET", None, None))
        dm._builder._check_strategy_arbitration = MagicMock(
            return_value={"allowed": True})

        regime_payload = {
            "ts": 1_700_000_000_000,
            "ts_ms": 1_700_000_000_000,
            "symbol": symbol,
            "regime": "TREND_UP",
            "confidence": "0.87",
            "source_model": "controlled_runtime_proof",
            "regime_layer": "structural",
            "regime_scope": "per_symbol",
            "regime_clock": "bar",
            "regime_owner": "regime_detector",
            "structural_regime_ref": "structural:BTCUSDT:1700000000000",
            "warmup": {
                "full_ready": True,
                "ticks_seen": 256,
                "ready": {"structural": True},
                "reasons": [],
            },
            "data_quality": {
                "drops": [],
                "notes": ["controlled_runtime_proof"],
            },
            "changed": False,
            "last_update_ts_ms": 1_700_000_000_123,
            "basis_tf_sec": 300,
            "bar_close_ts_ms": 1_700_000_000_000,
            "raw_regime": "TREND_UP",
            "raw_confidence": "0.87",
            "stable_confidence": "0.87",
            "pre_cutoff_source_model": "controlled_runtime_proof",
            "confidence_min": "0.15",
            "confidence_max": "0.85",
            "pre_cutoff_regime": "TREND_UP",
            "pre_cutoff_confidence": "0.87",
            "pre_cutoff_clamped_to_min": False,
            "pre_cutoff_clamped_to_max": True,
            "pre_cutoff_boundary_reason": "trend_ceiling_clamp",
            "uncertain_cutoff": "0.22",
            "demoted_to_uncertain": False,
            "raw_boundary_reason": "trend_ceiling_clamp",
            "hysteresis_bars": 3,
            "hysteresis_confirm_count": 3,
            "carried_previous_stable": False,
            "emitted_confidence_kind": "stable_heartbeat",
            "reason_summary": "pre_cutoff_source=controlled_runtime_proof; trend_ceiling_clamp; hysteresis_confirm=3/3",
        }
        bus.emit("EVT:REGIME_DETECTED", regime_payload,
                 "controlled_runtime_proof", rid="rid-detector-runtime-proof-1")

        cached_regime = dict(dm._per_symbol_regimes[symbol])
        _write_json(cache_snapshot_path, cached_regime)

        captured_safety_gate: dict[str, object] = {}

        def _capture_apply_safety_gates(**kwargs):
            result = _apply_safety_gates(**kwargs)
            captured_safety_gate["result"] = result
            return result

        strategy_trace = {
            "objective": {"score": 0.93, "winner": "aurora"},
            "model": "aurora",
        }

        with patch(
            "apps.reference.domains.decision_making.decision_making.apply_safety_gates",
            side_effect=_capture_apply_safety_gates,
        ):
            dm._propose_trade_intent(
                symbol=symbol,
                side="BUY",
                qty=Decimal("0.01"),
                price=Decimal("50000"),
                stop_price=Decimal("49000"),
                target_price=Decimal("51000"),
                why_chain=["controlled_runtime_proof", "signal_score=0.93"],
                rid=rid,
                reduce_only=False,
                strategy_id="aurora",
                decision_ts_ms=1_700_000_000_000,
                strategy_trace=strategy_trace,
            )

        assert observed_intents, "Expected EVT:TRADE_INTENT_PROPOSED emission"
        assert observed_open, "Expected DEC:OPEN emission"
        assert captured_safety_gate.get(
            "result") is not None, "Expected apply_safety_gates capture"

        safety_gate_result = asdict(captured_safety_gate["result"])
        _write_json(safety_gate_path, safety_gate_result)

        assert cached_regime["regime_provenance"]["source_kind"] == "detector_event"
        assert cached_regime["regime_provenance"]["detector_event"]["rid"] == "rid-detector-runtime-proof-1"
        assert cached_regime["regime_provenance"]["detector_event"]["bar_close_ts_ms"] == 1_700_000_000_000
        assert cached_regime["regime_provenance"]["detector_event"]["stable_confidence"] == "0.87"
        assert safety_gate_result["outcome"] == "ALLOW"
        assert safety_gate_result["regime"] == "TREND_UP"
        assert safety_gate_result["regime_confidence"] == 0.87
        assert safety_gate_result["regime_provenance"]["source_kind"] == "detector_cache"

        intent_payload = observed_intents[0].pld
        dec_open_payload = observed_open[0].pld
        assert intent_payload["regime_provenance"]["source_kind"] == "detector_cache"
        assert dec_open_payload["regime_provenance"]["source_kind"] == intent_payload["regime_provenance"]["source_kind"]
        assert dec_open_payload["regime_provenance"]["detector_event"]["rid"] == intent_payload["regime_provenance"]["detector_event"]["rid"]
        assert dec_open_payload["regime_provenance"]["detector_event"]["bar_close_ts_ms"] == intent_payload["regime_provenance"]["detector_event"]["bar_close_ts_ms"]
        assert dec_open_payload["regime_provenance"]["detector_event"]["stable_confidence"] == intent_payload["regime_provenance"]["detector_event"]["stable_confidence"]
        assert dec_open_payload["regime_provenance"]["detector_event"]["bar_close_ts_ms"] == 1_700_000_000_000
        assert dec_open_payload["regime_provenance"]["detector_event"]["emitted_confidence_kind"] == "stable_heartbeat"
        assert "trend_ceiling_clamp" in dec_open_payload["regime_provenance"]["detector_event"]["reason_summary"]

        pre_execution_wal_events, _, _ = wal.read_by_rid(rid)
        dec_open_record = next(
            record
            for record in pre_execution_wal_events
            if record.get("op") == "DEC" and record.get("verb") == "OPEN"
        )
        decision_to_execute = Message(**dec_open_record)
        assert decision_to_execute.corr_id is not None

        await ep._execute_decision(decision_to_execute)

        assert observed_order_placed, "Expected EVT:ORDER_PLACED emission"
        order_placed_payload = observed_order_placed[0].pld
        assert order_placed_payload["regime"] == "TREND_UP"
        assert order_placed_payload["regime_confidence"] == 0.87
        assert order_placed_payload["regime_provenance"]["detector_event"]["rid"] == dec_open_payload["regime_provenance"]["detector_event"]["rid"]
        assert order_placed_payload["regime_provenance"]["detector_event"]["bar_close_ts_ms"] == dec_open_payload["regime_provenance"]["detector_event"]["bar_close_ts_ms"]
        assert order_placed_payload["regime_provenance"]["detector_event"]["stable_confidence"] == "0.87"

        # The lifecycle logger only flushes terminal/open-trade snapshots on close/reject/cancel.
        # In this controlled proof we flush the open aggregate after ORDER_PLACED to persist evidence.
        trade_lifecycle.flush_all()

        wal_events, why_chain, integrity_ok = wal.read_by_rid(rid)
        shadow_records = _read_jsonl(shadow_path)
        order_log_records = _read_jsonl(order_log_path)
        lifecycle_records = _read_jsonl(lifecycle_path)

        assert integrity_ok is True
        assert any(record.get("verb") ==
                   "TRADE_INTENT_PROPOSED" for record in wal_events)
        assert any(record.get("verb") == "OPEN" and record.get(
            "op") == "DEC" for record in wal_events)
        assert any(record.get("verb") ==
                   "ORDER_PLACED" for record in wal_events)

        shadow_regime = [
            record
            for record in shadow_records
            if record.get("event_name") == "EVT:REGIME_DETECTED"
            and record.get("symbol") == symbol
        ]
        shadow_cmd_open = [
            record
            for record in shadow_records
            if record.get("event_name") == "CMD:OPEN" and record.get("rid") == rid
        ]
        shadow_dec_open = [
            record
            for record in shadow_records
            if record.get("event_name") == "DEC:OPEN" and record.get("rid") == rid
        ]
        shadow_order_placed = [
            record
            for record in shadow_records
            if record.get("event_name") == "EVT:ORDER_PLACED" and record.get("rid") == rid
        ]
        assert shadow_regime, "Expected shadow journal detector evidence"
        assert shadow_cmd_open, "Expected shadow journal CMD:OPEN evidence"
        assert shadow_dec_open, "Expected shadow journal DEC:OPEN evidence"
        assert shadow_order_placed, "Expected shadow journal ORDER_PLACED evidence"

        order_placed_rows = [
            record
            for record in order_log_records
            if record.get("rid") == rid and record.get("event_type") == "ORDER_PLACED"
        ]
        lifecycle_rows = [
            record for record in lifecycle_records if record.get("rid") == rid]
        assert order_placed_rows, "Expected order_log ORDER_PLACED evidence"
        assert lifecycle_rows, "Expected trade_lifecycle evidence"
        assert lifecycle_rows[0]["execution_regime"] == "TREND_UP"
        assert lifecycle_rows[0]["execution_regime_confidence"] == 0.87
        assert lifecycle_rows[0]["execution_regime_provenance"] == dec_open_payload["regime_provenance"]

        wal_file = next(wal_dir.glob("*.jsonl"), None)
        assert wal_file is not None, "Expected persisted WAL file"

        summary = {
            "rid": rid,
            "symbol": symbol,
            "paths": {
                "shadow_journal": str(shadow_path),
                "wal_file": str(wal_file),
                "order_log": str(order_log_path),
                "trade_lifecycle": str(lifecycle_path),
                "regime_cache_snapshot": str(cache_snapshot_path),
                "safety_gate_result": str(safety_gate_path),
            },
            "regime_event": regime_payload,
            "cache_snapshot": cached_regime,
            "safety_gate_result": safety_gate_result,
            "why_chain": why_chain,
            "wal_events": wal_events,
            "shadow_records": {
                "regime_detected": shadow_regime,
                "cmd_open": shadow_cmd_open,
                "dec_open": shadow_dec_open,
                "order_placed": shadow_order_placed,
            },
            "order_log_records": order_placed_rows,
            "trade_lifecycle_records": lifecycle_rows,
        }
        _write_json(summary_path, summary)
    finally:
        order_logger.log_file = original_order_log_path
        trade_lifecycle._log_file = original_lifecycle_log_path
        trade_lifecycle._trades = original_lifecycle_trades
        trade_lifecycle._recent_terminal = original_lifecycle_recent
        wal.set_wal_dir(original_wal_dir)
