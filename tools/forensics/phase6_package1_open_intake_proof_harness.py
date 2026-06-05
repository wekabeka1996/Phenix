from __future__ import annotations
from vfoundation.core.schema_registry import get_global_registry, init_global_registry
from vfoundation.core.fsm_core import FSMCore
from apps.reference.domains.execution_position.fsm import ExecPosFSM

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _git_head() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def build_execpos_shadow_config() -> MagicMock:
    cfg = MagicMock()
    cfg.trading.execution.watchdog.ack_ttl_ms = 5000
    cfg.trading.execution.watchdog.fill_ttl_ms = 5000
    cfg.trading.execution.watchdog.check_interval_ms = 1000
    cfg.trading.execution.watchdog.rps_limit = 10
    cfg.trading.execution.anti_race_close_ms = 800
    cfg.trading.execution.cooldown_after_close_ms = 10_000
    cfg.domains.execution_position.fsm_open.idempotency_window_sec = 60

    event_dedup = MagicMock()
    event_dedup.max_size = 100000
    event_dedup.ttl_ms = 86400000
    warm_state = MagicMock()
    warm_state.enabled = True
    warm_state.storage_path = "logs/test_execution_terminal_identity_cache.json"
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

    class InstrumentsDict(dict):
        pass

    cfg.instruments = InstrumentsDict({"BTCUSDT": btc_spec})

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

    cfg.trading.execution.exposure.leverage_defaults = {
        "__default__": 20, "BTCUSDT": 20}
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

    storage_mock = MagicMock()
    storage_mock.order_history_db = ":memory:"
    cfg.ops.storage = storage_mock

    cfg.binance_api.testnet.api_key = ""
    cfg.binance_api.testnet.api_secret = ""
    cfg.binance_api.testnet.rest_url = ""
    cfg.binance_api.live.api_key = ""
    cfg.binance_api.live.api_secret = ""
    cfg.binance_api.live.rest_url = ""
    cfg.get_domain_mode.return_value = "testnet"
    cfg.trading.mode = "testnet"

    return cfg


def build_valid_trade_intent_payload() -> Dict[str, Any]:
    return {
        "rid": "RID-PHASE6-HARNESS-SUCCESS-1",
        "instrument": "BTCUSDT",
        "side": "BUY",
        "strategy": "aurora",
        "order": {
            "qty": "0.01",
            "price": "50000",
            "price_ref": "50000",
            "reduce_only": False,
            "order_type": "LIMIT",
            "tif": "GTC",
        },
        "valid_for_ms": 15000,
        "idempotent_key": "KEY-PHASE6-HARNESS-SUCCESS-1",
        "stop_price": "49000",
        "target_price": "51000",
        "regime": "TREND_UP",
        "regime_confidence": 0.81,
        "regime_provenance": {
            "source_kind": "detector_cache",
            "detector_event": None,
            "cache_snapshot": {
                "cache_write_ts_ms": 1700000000456,
                "regime": "TREND_UP",
                "confidence": 0.81,
            },
        },
        "tca_budget": {
            "max_slippage_bps": "10",
            "max_latency_ms": 100,
            "maker_preference": "False",
        },
        "p": "0.75",
        "payoff_ratio_r": "2.0",
        "risk_budget": {
            "trade_cvar95_max_bps": "50",
            "session_cvar95_max_bps": "100",
        },
        "size": {
            "notional_cap_usd": "500",
            "kelly_fraction": "0.1",
        },
        "risk_context": {"risk_score": 0.55},
        "why": ["phase6_package1_harness_success"],
        "dto_version": "1.0.0",
        "schema_ref": "trade_intent_v1.json",
    }


def build_schema_compatible_reject_payload() -> Dict[str, Any]:
    payload = dict(build_valid_trade_intent_payload())
    payload["rid"] = "RID-PHASE6-HARNESS-REJECT-1"
    payload["idempotent_key"] = "KEY-PHASE6-HARNESS-REJECT-1"
    payload["regime_confidence"] = 1.5
    payload["why"] = ["phase6_package1_harness_reject"]
    return payload


def generate_phase6_package1_open_intake_harness_proof(output_dir: Path) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    init_global_registry(project_root=str(PROJECT_ROOT))
    bus = FSMCore()
    cfg = build_execpos_shadow_config()
    success_cmd_open: dict[str, Any] | None = None
    success_dec_open: list[dict[str, Any]] = []
    reject_events: list[dict[str, Any]] = []

    bus.listen("DEC:OPEN", lambda msg: success_dec_open.append(
        dict(msg.pld or {})))
    bus.listen("EVT:TRADE_INTENT_REJECTED",
               lambda msg: reject_events.append(dict(msg.pld or {})))

    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_guardian_cls, patch(
        "apps.reference.domains.execution_position.fsm.ALERT_MANAGER_AVAILABLE",
        new=False,
    ):
        fsm = ExecPosFSM(config=cfg, fsm=bus, shadow_mode=True)
        fsm.order_guardian = mock_guardian_cls.return_value

    original_handle = fsm.handle

    def _capture_handle(msg):
        nonlocal success_cmd_open
        if msg.op == "CMD" and msg.verb == "OPEN" and success_cmd_open is None:
            success_cmd_open = msg.model_dump()
        return original_handle(msg)

    fsm.handle = _capture_handle

    fsm._latest_portfolio_state = {
        "equity_free_usdt": "10000",
        "positions": [],
        "positions_last_ts_ms": 9_999_999_999_999,
    }
    fsm.exposure_guard.on_portfolio(dict(fsm._latest_portfolio_state))

    valid_payload = build_valid_trade_intent_payload()
    reject_payload = build_schema_compatible_reject_payload()

    bus.emit(
        "EVT:TRADE_INTENT_PROPOSED",
        payload=valid_payload,
        why="phase6_package1_harness_success",
    )
    bus.emit(
        "EVT:TRADE_INTENT_PROPOSED",
        payload=reject_payload,
        why="phase6_package1_harness_reject",
    )

    if success_cmd_open is None:
        raise RuntimeError(
            "Expected one captured CMD:OPEN envelope from the success path")
    if not success_dec_open:
        raise RuntimeError("Expected one DEC:OPEN event from the success path")
    if not reject_events:
        raise RuntimeError(
            "Expected one EVT:TRADE_INTENT_REJECTED event from the reject path")

    generated_at = datetime.now(timezone.utc).isoformat()
    provenance = {
        "generated_at_utc": generated_at,
        "generator": "tools/forensics/phase6_package1_open_intake_proof_harness.py",
        "project_root": str(PROJECT_ROOT),
        "git_head": _git_head(),
        "python": sys.version,
        "schema_validation_active": get_global_registry() is not None,
        "execution_mode": "shadow_mode",
        "evidence_grade": "harness-grade",
        "harness_notes": [
            "Uses real FSMCore listener dispatch with schema registry active.",
            "Uses real ExecPosFSM, IntentRouter, TradeIntentOpenIntake, and OpenFlowFSM code paths.",
            "Patches OrderGuardian and disables AlertManager bootstrap to avoid unrelated external dependencies.",
            "Success CMD:OPEN envelope is captured by an instrumentation wrapper around ExecPosFSM.handle before delegating to the real handler.",
            "Reject proof uses schema-compatible regime_confidence=1.5 so failure occurs at typed intake rather than upstream schema validation.",
            "This harness is reproducible proof, not live runtime proof.",
        ],
        "success_case": {
            "input_contract": "schema-compatible",
            "expected_path": "EVT:TRADE_INTENT_PROPOSED -> IntentRouter -> parse_trade_intent_open_intake -> CMD:OPEN -> OpenFlowFSM",
        },
        "reject_case": {
            "input_contract": "schema-compatible",
            "typed_reject_trigger": "regime_confidence > 1.0 violates typed intake bound while upstream schema only requires numeric type",
            "expected_path": "EVT:TRADE_INTENT_PROPOSED -> IntentRouter -> parse_trade_intent_open_intake -> EVT:TRADE_INTENT_REJECTED",
        },
        "command_example": f"{sys.executable} tools/forensics/phase6_package1_open_intake_proof_harness.py --output-dir {output_dir}",
    }
    summary = {
        "evidence_grade": "harness-grade",
        "success_cmd_open_count": 1,
        "success_dec_open_count": len(success_dec_open),
        "reject_event_count": len(reject_events),
        "schema_validation_active": provenance["schema_validation_active"],
        "success_contract": success_cmd_open.get("pld", {}).get("metadata", {}).get("execution_intake_contract"),
        "success_path": success_cmd_open.get("pld", {}).get("metadata", {}).get("execution_intake_path"),
        "reject_reason_code": reject_events[0].get("reason_code"),
        "reject_stage": reject_events[0].get("details", {}).get("execution_intake_stage"),
    }
    inputs = {
        "success_payload": valid_payload,
        "reject_payload": reject_payload,
    }

    _write_json(output_dir / "provenance.json", provenance)
    _write_json(output_dir / "summary.json", summary)
    _write_json(output_dir / "input_payloads.json", inputs)
    _write_json(output_dir / "success_cmd_open.json", success_cmd_open)
    _write_json(output_dir / "success_dec_open.json", success_dec_open[0])
    _write_json(output_dir / "reject_event.json", reject_events[0])

    return {
        "output_dir": str(output_dir),
        "summary": summary,
        "provenance": provenance,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate reproducible harness-grade proof artifacts for Phase 6 Package 1 typed open intake."
    )
    default_output_dir = PROJECT_ROOT / "reports" / (
        f"runtime_phase6_package1_open_intake_harness_proof_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help="Directory where the harness proof artifacts will be written.",
    )
    args = parser.parse_args(argv)

    result = generate_phase6_package1_open_intake_harness_proof(
        args.output_dir)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
