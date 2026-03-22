import asyncio
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    attach_shadow_journal,
)
from apps.reference.domains.execution_position.truth_hardening import (
    attach_execution_truth_hardening,
)
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message


class _Bus:
    def __init__(self) -> None:
        self.listeners = {}

    def listen(self, topic, handler):
        self.listeners.setdefault(topic, []).append(handler)

    def emit(self, topic, payload=None, why="", data_ref=None, rid=None):
        return None


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
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _make_execpos_config(path: Path):
    cfg = MagicMock()
    cfg.trading.execution.watchdog.ack_ttl_ms = 5000
    cfg.trading.execution.watchdog.fill_ttl_ms = 5000
    cfg.trading.execution.anti_race_close_ms = 800
    cfg.trading.execution.cooldown_after_close_ms = 10_000
    cfg.domains.execution_position.fsm_open.idempotency_window_sec = 60

    event_dedup = MagicMock()
    event_dedup.max_size = 100000
    event_dedup.ttl_ms = 86400000
    warm_state = MagicMock()
    warm_state.enabled = True
    warm_state.storage_path = str(path.with_name("warm_state.json"))
    warm_state.max_entries = 2000
    event_dedup.warm_state = warm_state
    cfg.domains.execution_position.event_dedup = event_dedup

    idempotent_cancel = MagicMock()
    idempotent_cancel.max_retries = 2
    cfg.domains.execution_position.idempotent_cancel = idempotent_cancel

    emergency = MagicMock()
    emergency.enabled = False
    emergency.wait_mode_bars = 2
    emergency.emergency_sl_bps = 100
    cfg.trading.execution.manage.emergency = emergency

    trailing = MagicMock()
    trailing.activation_pct = 0.003
    trailing.trail_pct = 0.006
    trailing.min_update_interval_sec = 5
    cfg.trailing = trailing

    cfg.trading.execution.manage.auto = True
    cfg.trading.execution.manage.brackets.enable = True
    cfg.trading.execution.manage.brackets.oco_emulation = True
    cfg.trading.execution.manage.brackets.sl.fixed_bps = 40
    cfg.trading.execution.manage.brackets.tp.fixed_bps = 80
    cfg.trading.execution.manage.brackets.offset_bps = 5

    btc_spec = MagicMock()
    btc_spec.tick_size = Decimal("0.01")
    btc_spec.step_size = Decimal("0.001")
    btc_spec.min_qty = Decimal("0.001")
    btc_spec.min_notional = Decimal("5.0")
    btc_spec.execution = MagicMock()
    btc_spec.execution.target_leverage = 20
    cfg.instruments = {"BTCUSDT": btc_spec}

    btc_asset_config = MagicMock()
    btc_asset_config.exit = MagicMock()
    btc_asset_config.exit.sl_pct = 0.02
    btc_asset_config.exit.max_hold_sec = 600
    btc_asset_config.take_profit = MagicMock()
    btc_asset_config.take_profit.tp_low_ratio = 0.5
    btc_asset_config.take_profit.tp_high_ratio = 1.0
    btc_asset_config.take_profit.partial_exit_pct = 0.5
    btc_asset_config.trailing_stop = MagicMock()
    btc_asset_config.trailing_stop.enabled = False
    cfg.strategies.aurora.assets = {"BTCUSDT": btc_asset_config}
    cfg.strategies.aurora.decision.bar_gating = None

    eg = cfg.domains.execution_position.exposure_guard
    eg.max_equity_utilization_pct = "95.0"
    eg.max_portfolio_fraction = "1.0"
    eg.max_long_utilization_pct = "100.0"
    eg.max_short_utilization_pct = "100.0"
    eg.max_directional_ratio = "5.0"
    eg.max_concentration_pct = "20.0"
    eg.pending_ttl_sec = 5
    eg.post_fill_ttl_sec = 5
    eg.stale_ttl_sec = 10

    fb = cfg.domains.execution_position.fallback
    fb.policy = "fail_closed"
    fb.risk_reduction_pct = "0.5"
    fb.backoff_ms = [200, 500, 1000]

    cfg.trading.execution.exposure.leverage_defaults = {"__default__": 20, "BTCUSDT": 20}
    cfg.trading.execution.exposure.count_pending_orders = True
    cfg.trading.execution.exposure.exclude_reduce_only = True
    cfg.trading.risk = {
        "soft_limits": {
            "mode": "clip",
            "clip_min_notional_usdt": "10.0",
            "directional_ratio_max": "3.0",
            "side_exposure_usdt": "600.0",
            "margin_exposure_usdt": "1100.0",
        }
    }
    cfg.ops.storage.order_history_db = ":memory:"
    cfg.binance_api.testnet.api_key = ""
    cfg.binance_api.testnet.api_secret = ""
    cfg.binance_api.testnet.rest_url = ""
    cfg.binance_api.live.api_key = ""
    cfg.binance_api.live.api_secret = ""
    cfg.binance_api.live.rest_url = ""
    cfg.get_domain_mode.return_value = "testnet"
    cfg.trading.mode = "testnet"
    cfg.observability = _shadow_cfg(path).observability
    return cfg


def test_trade_executed_order_only_identity_is_observable_as_degraded(tmp_path):
    path = tmp_path / "journal.jsonl"
    config = ConfigLoader().load_config()
    config.observability.shadow_journal.enabled = True
    config.observability.shadow_journal.path = str(path)
    config.observability.shadow_journal.critical_events = list(DEFAULT_CRITICAL_EVENTS)
    config.domains.execution_position.event_dedup.warm_state.storage_path = str(
        tmp_path / "warm_state.json"
    )

    fsm = FSMCore()
    attach_shadow_journal(fsm, config)
    attach_execution_truth_hardening(fsm, config)

    seen = []
    fsm.listen("EVT:TRADE_EXECUTED", lambda msg: seen.append(msg.pld["orderId"]))

    payload = {"symbol": "BTCUSDT", "orderId": "4444"}
    fsm.emit("EVT:TRADE_EXECUTED", payload=payload, why="polling_fill", rid="rid-weak")

    assert seen == ["4444"]
    records = _read_jsonl(path)
    degraded = [r for r in records if r["event_name"] == "HARDENING:TRADE_EXECUTED_IDENTITY_DEGRADED"]
    assert len(degraded) == 1
    assert "order_only_identity_degraded" in degraded[0]["notes"]
    assert "missing_client_order_id" in degraded[0]["notes"]


def test_restart_reset_is_explicit_and_previous_fill_dedupe_state_is_not_reused(tmp_path):
    path = tmp_path / "journal.jsonl"
    config = ConfigLoader().load_config()
    config.observability.shadow_journal.enabled = True
    config.observability.shadow_journal.path = str(path)
    config.observability.shadow_journal.critical_events = list(DEFAULT_CRITICAL_EVENTS)
    config.domains.execution_position.event_dedup.warm_state.storage_path = str(
        tmp_path / "warm_state.json"
    )
    config.domains.execution_position.event_dedup.warm_state.enabled = False

    payload = {
        "symbol": "BTCUSDT",
        "orderId": "5555",
        "clientOrderId": "ENTRY-BTCUSDT-RST",
        "client_order_id": "ENTRY-BTCUSDT-RST",
    }

    fsm_a = FSMCore()
    attach_shadow_journal(fsm_a, config)
    attach_execution_truth_hardening(fsm_a, config)
    seen_a = []
    fsm_a.listen("EVT:TRADE_EXECUTED", lambda msg: seen_a.append(msg.pld["orderId"]))
    fsm_a.emit("EVT:TRADE_EXECUTED", payload=payload, why="WS_ORDER_UPDATE_FILLED", rid="rid-rst")
    fsm_a.emit("EVT:TRADE_EXECUTED", payload=payload, why="polling_fill", rid="rid-rst")

    fsm_b = FSMCore()
    attach_shadow_journal(fsm_b, config)
    attach_execution_truth_hardening(fsm_b, config)
    seen_b = []
    fsm_b.listen("EVT:TRADE_EXECUTED", lambda msg: seen_b.append(msg.pld["orderId"]))
    fsm_b.emit("EVT:TRADE_EXECUTED", payload=payload, why="WS_ORDER_UPDATE_FILLED", rid="rid-rst")

    assert seen_a == ["5555"]
    assert seen_b == ["5555"]

    records = _read_jsonl(path)
    resets = [r for r in records if r["event_name"] == "RESTORE:EXECUTION_TRUTH_HARDENING_RESET"]
    suppressed = [r for r in records if r["event_name"] == "HARDENING:TRADE_EXECUTED_SUPPRESSED"]
    assert len(resets) == 2
    assert len(suppressed) == 1
    assert resets[0]["restore_marker"] is True
    assert "process_local_only_state" in resets[0]["notes"]


def test_watchdog_fill_payload_preserves_shared_identity_fields():
    async def _run():
        emitted = []

        async def emit_fn(event_name, payload):
            emitted.append((event_name, payload))

        watchdog = OrderTimeoutWatchdog(
            config={"ack_ttl_ms": 1000, "fill_ttl_ms": 5000, "check_interval_ms": 1000}
        )
        watchdog.set_hooks(
            get_order_fn=AsyncMock(
                return_value={
                    "status": "FILLED",
                    "executedQty": 1.0,
                    "avgPrice": 50000,
                    "clientOrderId": "ENTRY-BTCUSDT-WD",
                }
            ),
            emit_fn=emit_fn,
        )
        watchdog.track_order_placed(
            "ord-1",
            "ENTRY-BTCUSDT-WD",
            "BTCUSDT",
            rid="rid-wd-1",
        )
        watchdog.on_order_ack("ord-1")
        await watchdog._poll_order_statuses()
        return emitted

    emitted = asyncio.run(_run())
    assert len(emitted) == 1
    event_name, payload = emitted[0]
    assert event_name == "EVT:TRADE_EXECUTED"
    assert payload["orderId"] == "ord-1"
    assert payload["clientOrderId"] == "ENTRY-BTCUSDT-WD"
    assert payload["client_order_id"] == "ENTRY-BTCUSDT-WD"
    assert payload["rid"] == "rid-wd-1"
    assert payload["ts_ms"] is not None


def test_non_cmd_dec_close_guard_suppresses_repeated_execution_and_allows_after_state_change(tmp_path):
    path = tmp_path / "journal.jsonl"
    config = _make_execpos_config(path)

    async def _run():
        with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as guardian_cls, patch(
            "apps.reference.domains.execution_position.fsm.ExecPosFSM._schedule_guardian_start"
        ), patch(
            "apps.reference.domains.execution_position.fsm.ExecPosFSM._schedule_fsm_cleanup_loop"
        ), patch(
            "apps.reference.domains.execution_position.watchdog.OrderTimeoutWatchdog.start"
        ):
            guardian_cls.return_value.start = AsyncMock()
            bus = _Bus()
            fsm = ExecPosFSM(config=config, fsm=bus, shadow_mode=True)
            fsm.adapter = SimpleNamespace(base_url="https://testnet.binance.local")
            fsm._close_exec.execute_close = AsyncMock()
            fsm._latest_portfolio_state = {
                "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.010"}]
            }

            decision = Message(
                op="DEC",
                verb="CLOSE",
                src="execution_position",
                dst="execution_position",
                rid="rid-max-hold-1",
                pld={
                    "symbol": "BTCUSDT",
                    "qty": "0.01",
                    "reduce_only": True,
                    "reason": "MAX_HOLD_TIME_EXCEEDED",
                    "elapsed_sec": 61,
                    "max_hold_sec": 60,
                },
                why="max_hold_timeout_61s_reduce_only",
            )

            await fsm._execute_decision(decision)
            await fsm._execute_decision(decision)
            fsm._latest_portfolio_state = {
                "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.005"}]
            }
            await fsm._execute_decision(decision)
            return fsm

    fsm = asyncio.run(_run())
    assert fsm._close_exec.execute_close.await_count == 2

    records = _read_jsonl(path)
    suppressed = [r for r in records if r["event_name"] == "HARDENING:NON_CMD_DEC_CLOSE_SUPPRESSED"]
    assert len(suppressed) == 1
    assert "duplicate_non_cmd_dec_close_same_effective_state" in suppressed[0]["notes"]
