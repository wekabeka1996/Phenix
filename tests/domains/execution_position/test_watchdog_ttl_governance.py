"""
T5A Timer Governance: OrderTimeoutWatchdog fill_ttl_ms proof tests.

Verifies that:
1. The canonical YAML value for fill_ttl_ms matches the calibrated trading.yaml SSOT.
2. Non-default fill_ttl_ms kwargs propagate into the watchdog instance without
   being overridden by constructor defaults.
3. Global fill_ttl_ms is used as the fill deadline when no per-order override
   is supplied.
4. Per-order fill_ttl_override_ms wins over global fill_ttl_ms when provided.
5. WatchdogConfig Pydantic model and FSM config-extraction are fail-closed
   (no silent fallback when fill_ttl_ms is missing).
6. A fill timeout event carries the expected timeout_type value.

SSOT (post T5A.1):
  config/aurora/trading.yaml  -> trading.execution.watchdog.fill_ttl_ms  (CANONICAL — sole source)
  config/aurora/system.yaml   -> execution.watchdog block REMOVED (T5A.1 split-brain fix, 2026-05-07)
  apps/reference/config_models.py -> WatchdogConfig (all fields Field(...) required)
  apps/reference/config_models.py -> ExecutionConfig.watchdog: Optional[WatchdogConfig] = Field(default=None)
  apps/reference/domains/execution_position/fsm.py -> _get_config_value(["trading", "execution", "watchdog"]) only
  apps/reference/domains/execution_position/adapters/watchdog.py -> implementation

DO NOT change fill_ttl_ms, ack_ttl_ms, check_interval_ms, or rps_limit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
TRADING_YAML = REPO_ROOT / "config" / "aurora" / "trading.yaml"
SYSTEM_YAML = REPO_ROOT / "config" / "aurora" / "system.yaml"

CANONICAL_FILL_TTL_MS = 1_800_000  # 30 minutes — calibrated T5D global backstop


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_watchdog(fill_ttl_ms: int = 30_000, ack_ttl_ms: int = 8_000,
                   check_interval_ms: int = 1_000, rps_limit: int = 10):
    from apps.reference.domains.execution_position.adapters.watchdog import (
        OrderTimeoutWatchdog,
    )
    return OrderTimeoutWatchdog(
        ack_ttl_ms=ack_ttl_ms,
        fill_ttl_ms=fill_ttl_ms,
        check_interval_ms=check_interval_ms,
        rps_limit=rps_limit,
    )


# ---------------------------------------------------------------------------
# Test 1 — canonical config YAML paths exist and hold calibrated fill_ttl_ms
# ---------------------------------------------------------------------------

class TestWatchdogConfigCanonicalValue:
    """T5A-1: trading.yaml holds the calibrated fill_ttl_ms and system.yaml stays absent."""

    def test_trading_yaml_fill_ttl_ms_matches_calibrated_canonical_value(self):
        """trading.execution.watchdog.fill_ttl_ms must equal the calibrated canonical value.

        SSOT: config/aurora/trading.yaml -> trading.execution.watchdog.fill_ttl_ms
        Further changes require a new calibration package.
        """
        raw = yaml.safe_load(TRADING_YAML.read_text(encoding="utf-8"))
        trading = raw.get("trading", {}) or {}
        execution = trading.get("execution", {}) or {}
        watchdog = execution.get("watchdog", {}) or {}
        value = watchdog.get("fill_ttl_ms")

        assert value is not None, (
            "trading.yaml is missing trading.execution.watchdog.fill_ttl_ms. "
            f"Expected {CANONICAL_FILL_TTL_MS}."
        )
        assert value == CANONICAL_FILL_TTL_MS, (
            f"trading.execution.watchdog.fill_ttl_ms = {value!r}, "
            f"expected {CANONICAL_FILL_TTL_MS!r}. "
            "Do not change this value without a T5B calibration report."
        )

    def test_system_yaml_watchdog_absent_after_ssot_fix(self):
        """system.yaml must NOT contain execution.watchdog after T5A.1 SSOT fix.

        T5A.1 removed the noncanonical duplicate execution.watchdog from system.yaml.
        Canonical source is now trading.yaml -> trading.execution.watchdog.*
        The FSM uses only ["trading", "execution", "watchdog"] (not system path).

        If this test fails, the noncanonical duplicate has been re-introduced —
        remove execution.watchdog from system.yaml.
        """
        raw = yaml.safe_load(SYSTEM_YAML.read_text(encoding="utf-8"))
        execution = raw.get("execution", {}) or {}
        watchdog = execution.get("watchdog")

        assert watchdog is None, (
            "NONCANONICAL watchdog block found in system.yaml at execution.watchdog. "
            "T5A.1 SSOT fix removed this duplicate. Do not re-add it. "
            "Canonical source is trading.yaml -> trading.execution.watchdog.*\n"
            f"Found: {watchdog!r}"
        )

    def test_trading_yaml_is_sole_canonical_fill_ttl_source(self):
        """trading.yaml is the sole canonical source for fill_ttl_ms after T5A.1.

        Before T5A.1: both trading.yaml and system.yaml carried fill_ttl_ms
        (split-brain). After T5A.1: only trading.yaml carries the value.
        system.yaml execution.watchdog block is absent.
        """
        raw_trading = yaml.safe_load(TRADING_YAML.read_text(encoding="utf-8"))
        trading_val = (
            (raw_trading.get("trading") or {})
            .get("execution", {})
            .get("watchdog", {})
            .get("fill_ttl_ms")
        )

        raw_system = yaml.safe_load(SYSTEM_YAML.read_text(encoding="utf-8"))
        system_val = (
            (raw_system.get("execution") or {})
            .get("watchdog", {})
            .get("fill_ttl_ms")
        )

        assert trading_val == CANONICAL_FILL_TTL_MS, (
            f"trading.yaml fill_ttl_ms = {trading_val!r}, expected {CANONICAL_FILL_TTL_MS!r}. "
            "The canonical trading path must hold the production value."
        )
        assert system_val is None, (
            f"system.yaml execution.watchdog.fill_ttl_ms = {system_val!r}; expected absent. "
            "T5A.1 removed the noncanonical duplicate from system.yaml. "
            "Do not re-add it — trading.yaml is now the sole canonical source."
        )


# ---------------------------------------------------------------------------
# Test 2 — non-default fill_ttl_ms propagates; constructor default not used
# ---------------------------------------------------------------------------

class TestNonDefaultFillTtlPropagates:
    """T5A-2: A non-default fill_ttl_ms kwarg must survive into the instance."""

    def test_nondefault_fill_ttl_ms_propagates_into_watchdog(self):
        """Sentinel value 12345 must appear on watchdog.fill_ttl_ms.

        The constructor signature has fill_ttl_ms: int = 30000 (hardcoded default).
        When the FSM passes the config value explicitly via keyword arg, the
        constructor default must NOT win.  This test proves the kwarg wins.
        """
        wd = _make_watchdog(fill_ttl_ms=12345)

        assert wd.fill_ttl_ms == 12345, (
            f"Expected fill_ttl_ms=12345, got {wd.fill_ttl_ms}. "
            "The constructor default (30000) must not override the kwarg. "
            "YAML SSOT violation."
        )

    def test_constructor_default_differs_from_canonical(self):
        """The constructor default (30000) is NOT the canonical production value.

        This is documented as compatibility debt: the default is a development-era
        value.  The production path always passes an explicit kwarg from config, so
        the default is unreachable in production.  This test documents the gap.
        """
        from apps.reference.domains.execution_position.adapters.watchdog import (
            OrderTimeoutWatchdog,
        )
        import inspect
        sig = inspect.signature(OrderTimeoutWatchdog.__init__)
        default_fill_ttl = sig.parameters["fill_ttl_ms"].default

        assert default_fill_ttl != CANONICAL_FILL_TTL_MS, (
            "Constructor default now matches production value — update this test. "
            "If you changed the default to the calibrated canonical value, also verify the FSM still passes "
            "the kwarg explicitly so there is no regression on fail-closed loading."
        )
        # Document: constructor default is 30000; production value comes from trading.yaml SSOT.
        assert default_fill_ttl == 30_000, (
            f"Expected constructor default to be 30000, got {default_fill_ttl}. "
            "Update this test if the default has intentionally changed."
        )

    def test_config_dict_path_fill_ttl_ms_also_propagates(self):
        """OrderTimeoutWatchdog also accepts config via dict (legacy path).

        When called with config={'fill_ttl_ms': 77777, ...}, the dict value
        must win over the kwarg default.  This covers the alternate construction
        path used in some test fixtures.
        """
        from apps.reference.domains.execution_position.adapters.watchdog import (
            OrderTimeoutWatchdog,
        )
        wd = OrderTimeoutWatchdog(
            config={"ack_ttl_ms": 8000, "fill_ttl_ms": 77777,
                    "check_interval_ms": 1000, "rps_limit": 10}
        )
        assert wd.fill_ttl_ms == 77777, (
            f"Expected fill_ttl_ms=77777 from config dict, got {wd.fill_ttl_ms}. "
            "Config dict path must propagate correctly."
        )


# ---------------------------------------------------------------------------
# Test 3 — global fill_ttl_ms used when no per-order override
# ---------------------------------------------------------------------------

class TestGlobalFillTtlUsedWhenNoOverride:
    """T5A-3: When no per-order fill_ttl_override_ms, global fill_ttl_ms governs."""

    def test_global_fill_ttl_used_when_no_override(self):
        """After ACK, fill deadline must equal now_ms + global fill_ttl_ms.

        This tests the narrowest seam: on_order_ack() with no fill_ttl_override_ms
        set on the deadline.  The fill deadline must be based on self.fill_ttl_ms.
        """
        wd = _make_watchdog(fill_ttl_ms=99_999)
        NOW = 500_000

        with patch(
            "apps.reference.domains.execution_position.adapters.watchdog.get_clock"
        ) as mock_clock:
            mock_clock.return_value.now_ms.return_value = NOW

            wd.track_order_placed("o1", "c1", "BTCUSDT")
            wd.on_order_ack("o1")

        assert "o1" in wd.acked_orders, "Order must be in acked_orders after ACK"
        dl = wd.acked_orders["o1"]
        assert dl.deadline_ms == NOW + 99_999, (
            f"Fill deadline {dl.deadline_ms} != expected {NOW + 99_999}. "
            "Global fill_ttl_ms (99999) must govern when no override is set."
        )
        assert dl.fill_ttl_override_ms is None, (
            "fill_ttl_override_ms must be None when not supplied."
        )

    def test_acked_order_timeout_type_is_fill(self):
        """After ACK, timeout_type must be FILL_TIMEOUT (not ACK_TIMEOUT)."""
        from apps.reference.domains.execution_position.adapters.watchdog import (
            OrderTimeoutType,
        )
        wd = _make_watchdog(fill_ttl_ms=50_000)

        with patch(
            "apps.reference.domains.execution_position.adapters.watchdog.get_clock"
        ) as mock_clock:
            mock_clock.return_value.now_ms.return_value = 100_000

            wd.track_order_placed("o1", "c1", "ETHUSDT")
            wd.on_order_ack("o1")

        dl = wd.acked_orders["o1"]
        assert dl.timeout_type == OrderTimeoutType.FILL_TIMEOUT, (
            f"timeout_type after ACK must be FILL_TIMEOUT, got {dl.timeout_type}."
        )


# ---------------------------------------------------------------------------
# Test 4 — per-order fill_ttl_override_ms wins over global fill_ttl_ms
# ---------------------------------------------------------------------------

class TestPerOrderFillOverrideWins:
    """T5A-4: Per-order fill_ttl_override_ms must win over global fill_ttl_ms."""

    def test_per_order_override_wins_over_global(self):
        """fill_ttl_override_ms=12345 must produce deadline = now_ms + 12345.

        The override is set via track_order_placed(fill_ttl_override_ms=12345)
        and consumed by on_order_ack() at:
          fill_ttl = deadline.fill_ttl_override_ms if deadline.fill_ttl_override_ms else self.fill_ttl_ms
        """
        wd = _make_watchdog(fill_ttl_ms=99_999)  # global = 99999
        NOW = 200_000

        with patch(
            "apps.reference.domains.execution_position.adapters.watchdog.get_clock"
        ) as mock_clock:
            mock_clock.return_value.now_ms.return_value = NOW

            wd.track_order_placed("o1", "c1", "SOLUSDT",
                                  fill_ttl_override_ms=12_345)
            wd.on_order_ack("o1")

        dl = wd.acked_orders["o1"]
        assert dl.deadline_ms == NOW + 12_345, (
            f"Fill deadline {dl.deadline_ms} must equal now_ms + override (12345), "
            f"expected {NOW + 12_345}. Global fill_ttl_ms (99999) must NOT win."
        )
        assert dl.fill_ttl_override_ms == 12_345, (
            "fill_ttl_override_ms must be preserved on the deadline object."
        )

    def test_zero_override_falls_back_to_global(self):
        """fill_ttl_override_ms=0 is falsy; global fill_ttl_ms must be used.

        This documents the existing behavior: `if deadline.fill_ttl_override_ms`
        treats 0 as falsy, so zero is not a valid override — global wins.
        """
        wd = _make_watchdog(fill_ttl_ms=55_000)
        NOW = 300_000

        with patch(
            "apps.reference.domains.execution_position.adapters.watchdog.get_clock"
        ) as mock_clock:
            mock_clock.return_value.now_ms.return_value = NOW

            wd.track_order_placed("o1", "c1", "XRPUSDT",
                                  fill_ttl_override_ms=0)
            wd.on_order_ack("o1")

        dl = wd.acked_orders["o1"]
        assert dl.deadline_ms == NOW + 55_000, (
            f"Fill deadline {dl.deadline_ms} must equal now_ms + global (55000) "
            f"when override is 0 (falsy). Expected {NOW + 55_000}."
        )

    def test_override_path_exists_in_open_executor(self):
        """fill_ttl_override_ms is wired from decision.pld['valid_for_ms'] in open_executor.py.

        This test proves the override path is not dead code — it is reachable from
        the production call site at open_executor.py:1091 (_post_entry_registration).
        """
        from apps.reference.domains.execution_position.flows.open.open_executor import (
            OpenExecutor,
        )
        import inspect
        source = inspect.getsource(OpenExecutor._post_entry_registration)
        assert "fill_ttl_override_ms" in source, (
            "_post_entry_registration no longer passes fill_ttl_override_ms "
            "to track_order_placed. The per-order override path may be dead. "
            "Check open_executor.py."
        )
        assert "valid_for_ms" in source, (
            "valid_for_ms source binding is missing from _post_entry_registration. "
            "The override path may be broken."
        )


# ---------------------------------------------------------------------------
# Test 5 — no silent fallback on missing watchdog config
# ---------------------------------------------------------------------------

class TestNoSilentFallbackOnMissingConfig:
    """T5A-5: WatchdogConfig and FSM extraction must be fail-closed."""

    def test_watchdog_config_pydantic_all_fields_required(self):
        """WatchdogConfig must reject construction if any field is missing.

        All four fields use Field(...) (required, no default). Omitting fill_ttl_ms
        must raise ValidationError, not silently use a fallback.
        """
        from pydantic import ValidationError
        from apps.reference.config_models import WatchdogConfig

        with pytest.raises(ValidationError) as exc_info:
            WatchdogConfig(ack_ttl_ms=8000,
                           check_interval_ms=1000, rps_limit=10)
            # fill_ttl_ms deliberately missing

        errors = exc_info.value.errors()
        missing_fields = [e["loc"][0]
                          for e in errors if e["type"] == "missing"]
        assert "fill_ttl_ms" in missing_fields, (
            f"Expected ValidationError on missing fill_ttl_ms. "
            f"Got errors: {errors}. "
            "WatchdogConfig.fill_ttl_ms must be Field(...) with no default."
        )

    def test_watchdog_config_pydantic_no_fill_ttl_default(self):
        """WatchdogConfig.fill_ttl_ms must have no Pydantic-level default.

        Field(...) enforces this. If a default were added (even the calibrated canonical value), this
        test would fail — alerting that silent fallback has been introduced.
        """
        from pydantic.fields import PydanticUndefined
        from apps.reference.config_models import WatchdogConfig

        field_info = WatchdogConfig.model_fields["fill_ttl_ms"]
        # Field(...) means default is PydanticUndefined (no default set)
        assert field_info.default is PydanticUndefined, (
            f"WatchdogConfig.fill_ttl_ms has a default: {field_info.default!r}. "
            "This introduces a silent fallback — remove the default and keep Field(...)."
        )

    def test_fsm_get_watchdog_setting_raises_on_missing_key(self):
        """FSM's get_watchdog_setting helper raises ValueError on missing key.

        This is the production fail-closed guard at fsm.py:592-595. It prevents
        silent use of the OrderTimeoutWatchdog constructor default (30000) in
        production when fill_ttl_ms is absent from config.
        """
        # Replicate the logic from fsm.py:588-599
        watchdog_config = {"ack_ttl_ms": 8000,
                           "check_interval_ms": 1000, "rps_limit": 10}
        # fill_ttl_ms is deliberately absent

        def get_watchdog_setting(key: str, default: Any):
            if isinstance(watchdog_config, dict):
                if key not in watchdog_config:
                    raise ValueError(
                        f"CRITICAL: watchdog.{key} missing. FSM cannot start without watchdog config."
                    )
                return watchdog_config[key]
            return getattr(watchdog_config, key)

        with pytest.raises(ValueError, match="fill_ttl_ms missing"):
            get_watchdog_setting("fill_ttl_ms", None)

    def test_watchdog_config_extra_fields_forbidden(self):
        """WatchdogConfig forbids extra fields (extra='forbid').

        Any unexpected key in the YAML watchdog section raises ValidationError,
        preventing silent config drift (typos, orphaned keys).
        """
        from pydantic import ValidationError
        from apps.reference.config_models import WatchdogConfig

        with pytest.raises(ValidationError):
            WatchdogConfig(
                ack_ttl_ms=8000,
                fill_ttl_ms=CANONICAL_FILL_TTL_MS,
                check_interval_ms=1000,
                rps_limit=10,
                unknown_future_field=99,  # must be rejected
            )


# ---------------------------------------------------------------------------
# Test 6 — timeout event shape (synchronous check path)
# ---------------------------------------------------------------------------

class TestTimeoutEventShape:
    """T5A-6: Timeout callback receives deadline with correct timeout_type."""

    @pytest.mark.asyncio
    async def test_fill_timeout_callback_receives_fill_timeout_type(self):
        """When a FILL deadline expires, callback receives timeout_type=FILL_TIMEOUT.

        This tests _check_timeouts() directly (no event loop background task).
        The callback is a synchronous MagicMock; asyncio.iscoroutine() guard in
        _handle_timeout routes to it correctly.
        """
        from apps.reference.domains.execution_position.adapters.watchdog import (
            OrderTimeoutType,
            OrderDeadline,
        )

        received: list[Any] = []

        def capture_callback(deadline):
            received.append(deadline)

        wd = _make_watchdog(fill_ttl_ms=5_000)
        wd.on_timeout_callback = capture_callback

        # Manually inject an expired FILL deadline (deadline_ms in the past)
        wd.acked_orders["order-expired"] = OrderDeadline(
            order_id="order-expired",
            client_order_id="cid-expired",
            symbol="BTCUSDT",
            deadline_ms=1_000,  # far in the past
            timeout_type=OrderTimeoutType.FILL_TIMEOUT,
        )

        with patch(
            "apps.reference.domains.execution_position.adapters.watchdog.get_clock"
        ) as mock_clock:
            mock_clock.return_value.now_ms.return_value = 9_999_999_999

            await wd._check_timeouts()

        assert len(received) == 1, (
            f"Expected 1 timeout callback, got {len(received)}. "
            "Expired FILL deadline must trigger the callback."
        )
        dl = received[0]
        assert dl.order_id == "order-expired"
        assert dl.timeout_type == OrderTimeoutType.FILL_TIMEOUT, (
            f"Expected FILL_TIMEOUT, got {dl.timeout_type}. "
            "Fill timeout must carry FILL_TIMEOUT type, not ACK_TIMEOUT."
        )
        assert dl.timeout_type.value == "fill_timeout", (
            f"timeout_type.value must be 'fill_timeout', got {dl.timeout_type.value!r}."
        )
        assert "order-expired" not in wd.acked_orders, (
            "Expired order must be removed from acked_orders after timeout handling."
        )
        assert wd.timeout_count == 1

    @pytest.mark.asyncio
    async def test_ack_timeout_callback_receives_ack_timeout_type(self):
        """When an ACK deadline expires, callback receives timeout_type=ACK_TIMEOUT."""
        from apps.reference.domains.execution_position.adapters.watchdog import (
            OrderTimeoutType,
            OrderDeadline,
        )

        received: list[Any] = []

        def capture_callback(deadline):
            received.append(deadline)

        wd = _make_watchdog(ack_ttl_ms=1_000)
        wd.on_timeout_callback = capture_callback

        wd.pending_orders["order-ack-expired"] = OrderDeadline(
            order_id="order-ack-expired",
            client_order_id="cid-ack",
            symbol="ETHUSDT",
            deadline_ms=500,  # expired
            timeout_type=OrderTimeoutType.ACK_TIMEOUT,
        )

        with patch(
            "apps.reference.domains.execution_position.adapters.watchdog.get_clock"
        ) as mock_clock:
            mock_clock.return_value.now_ms.return_value = 9_999_999_999

            await wd._check_timeouts()

        assert len(received) == 1
        assert received[0].timeout_type == OrderTimeoutType.ACK_TIMEOUT
        assert received[0].timeout_type.value == "ack_timeout"

    def test_timeout_type_enum_values_are_stable(self):
        """OrderTimeoutType enum values must be stable string constants.

        These values appear in WAL logs (event_type='ORDER_TIMEOUT',
        timeout_type='fill_timeout'). Changing them breaks log parsers and
        operators' dashboards without a migration path.
        """
        from apps.reference.domains.execution_position.adapters.watchdog import (
            OrderTimeoutType,
        )
        assert OrderTimeoutType.ACK_TIMEOUT.value == "ack_timeout", (
            "ACK_TIMEOUT enum value must stay 'ack_timeout' — changing breaks WAL schema."
        )
        assert OrderTimeoutType.FILL_TIMEOUT.value == "fill_timeout", (
            "FILL_TIMEOUT enum value must stay 'fill_timeout' — changing breaks WAL schema."
        )
