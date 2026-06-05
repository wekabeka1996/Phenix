"""T5D fill_ttl_ms calibration tests.

Scope:
1. Canonical watchdog fill_ttl_ms is calibrated to 1_800_000 in trading.yaml.
2. system.yaml still does not contain execution.watchdog.
3. Canonical trading.execution.watchdog.fill_ttl_ms propagates into OrderTimeoutWatchdog.
4. Per-order fill_ttl_override_ms remains stronger than the global watchdog backstop.
5. Missing canonical fill_ttl_ms still fails closed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
TRADING_YAML = REPO_ROOT / "config" / "aurora" / "trading.yaml"
SYSTEM_YAML = REPO_ROOT / "config" / "aurora" / "system.yaml"

CANONICAL_FILL_TTL_MS = 1_800_000
PER_ORDER_OVERRIDE_MS = 1_200_000


class _FakeBus:
    def emit(self, topic, payload=None, why=None, data_ref=None, **kwargs):
        return None

    def listen(self, topic, handler) -> None:
        return None


def _build_cfg(*, fill_ttl_ms: int = CANONICAL_FILL_TTL_MS):
    from tests.domains.execution_position.conftest import fsm_config

    cfg = fsm_config.__wrapped__() if hasattr(
        fsm_config, "__wrapped__") else fsm_config()
    watchdog_mock = cfg.trading.execution.watchdog
    watchdog_mock.ack_ttl_ms = 8_000
    watchdog_mock.fill_ttl_ms = fill_ttl_ms
    watchdog_mock.check_interval_ms = 1_000
    watchdog_mock.rps_limit = 10
    return cfg


def _make_fsm(cfg):
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    bus = _FakeBus()
    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_guardian_cls:
        mock_guardian = mock_guardian_cls.return_value
        mock_guardian.is_duplicate.return_value = False
        return ExecPosFSM(config=cfg, fsm=bus, shadow_mode=True)


def _make_watchdog(fill_ttl_ms: int = CANONICAL_FILL_TTL_MS):
    from apps.reference.domains.execution_position.adapters.watchdog import OrderTimeoutWatchdog

    return OrderTimeoutWatchdog(
        ack_ttl_ms=8_000,
        fill_ttl_ms=fill_ttl_ms,
        check_interval_ms=1_000,
        rps_limit=10,
    )


def test_trading_yaml_fill_ttl_ms_is_1800000():
    raw = yaml.safe_load(TRADING_YAML.read_text(encoding="utf-8"))
    value = (
        (raw.get("trading") or {})
        .get("execution", {})
        .get("watchdog", {})
        .get("fill_ttl_ms")
    )

    assert value == CANONICAL_FILL_TTL_MS, (
        f"trading.execution.watchdog.fill_ttl_ms = {value!r}, "
        f"expected {CANONICAL_FILL_TTL_MS!r} for T5D calibration."
    )


def test_system_yaml_has_no_execution_watchdog_block():
    raw = yaml.safe_load(SYSTEM_YAML.read_text(encoding="utf-8"))
    watchdog = (raw.get("execution") or {}).get("watchdog")

    assert watchdog is None, (
        "system.yaml must not define execution.watchdog after T5A.1 SSOT fix. "
        f"Found: {watchdog!r}"
    )


def test_runtime_uses_canonical_trading_fill_ttl_ms():
    cfg = _build_cfg(fill_ttl_ms=CANONICAL_FILL_TTL_MS)
    fsm = _make_fsm(cfg)

    assert fsm.watchdog.fill_ttl_ms == CANONICAL_FILL_TTL_MS, (
        f"Expected live watchdog.fill_ttl_ms={CANONICAL_FILL_TTL_MS}, "
        f"got {fsm.watchdog.fill_ttl_ms}."
    )


def test_per_order_override_beats_global_backstop():
    wd = _make_watchdog(fill_ttl_ms=CANONICAL_FILL_TTL_MS)
    now_ms = 100_000

    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = now_ms
        wd.track_order_placed(
            "order-1",
            "client-1",
            "BTCUSDT",
            fill_ttl_override_ms=PER_ORDER_OVERRIDE_MS,
        )
        wd.on_order_ack("order-1")

    deadline = wd.acked_orders["order-1"]
    assert deadline.deadline_ms == now_ms + PER_ORDER_OVERRIDE_MS, (
        f"Expected per-order override deadline {now_ms + PER_ORDER_OVERRIDE_MS}, "
        f"got {deadline.deadline_ms}."
    )
    assert deadline.fill_ttl_override_ms == PER_ORDER_OVERRIDE_MS


def test_missing_canonical_fill_ttl_ms_fails_closed():
    from pydantic import ValidationError
    from apps.reference.config_models import WatchdogConfig

    with pytest.raises(ValidationError) as exc_info:
        WatchdogConfig(ack_ttl_ms=8_000, check_interval_ms=1_000, rps_limit=10)

    missing_fields = [e["loc"][0]
                      for e in exc_info.value.errors() if e["type"] == "missing"]
    assert "fill_ttl_ms" in missing_fields, (
        f"Expected missing fill_ttl_ms ValidationError, got {exc_info.value.errors()}."
    )
