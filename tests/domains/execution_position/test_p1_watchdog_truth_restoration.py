"""
P1_EXECUTION_TIMEOUT_TRUTH_RESTORATION — Focused regression tests.

Proves three things only (per package scope):

1. live watchdog instance receives check_interval_ms from canonical config;
2. live watchdog instance receives rps_limit from canonical config;
3. shadow alias reads (trading.orders.default_ttl_seconds /
   root orders.default_ttl_seconds) no longer affect fill_ttl_ms
   in the execution runtime path.

Boundary: does NOT test valid_for_ms chain, ack_ttl_ms/fill_ttl_ms semantics,
or any out-of-scope timing surface.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class _FakeBus:
    """Minimal bus that captures events without routing them."""

    def __init__(self):
        self.events: list = []

    def emit(self, topic, payload=None, why=None, data_ref=None, **kwargs):
        self.events.append((topic, payload or {}))

    def listen(self, topic, handler) -> None:
        pass


def _build_cfg(*, check_interval_ms: int = 1000, rps_limit: int = 10,
               ack_ttl_ms: int = 5000, fill_ttl_ms: int = 5000):
    """
    Build a MagicMock config with explicit canonical watchdog values.
    Delegates common fields to conftest.fsm_config() then overrides.

    The shared harness keeps cfg.execution=None, so the canonical path for these
    tests is trading.execution.watchdog. The helper should populate the explicit
    watchdog contract there rather than inventing a root execution block.
    """
    from tests.domains.execution_position.conftest import fsm_config
    cfg = fsm_config.__wrapped__() if hasattr(
        fsm_config, "__wrapped__") else fsm_config()
    watchdog_mock = cfg.trading.execution.watchdog
    watchdog_mock.ack_ttl_ms = ack_ttl_ms
    watchdog_mock.fill_ttl_ms = fill_ttl_ms
    watchdog_mock.check_interval_ms = check_interval_ms
    watchdog_mock.rps_limit = rps_limit
    return cfg


def _make_fsm(cfg):
    """Instantiate ExecPosFSM with the given config and a FakeBus."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    bus = _FakeBus()
    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_cls:
        mock_cls.return_value.is_duplicate.return_value = False
        fsm = ExecPosFSM(config=cfg, fsm=bus, shadow_mode=True)
    return fsm


# ---------------------------------------------------------------------------
# PART 1: Watchdog cadence / throttle wiring
# ---------------------------------------------------------------------------

class TestWatchdogCadenceWiring:
    """
    check_interval_ms and rps_limit set in canonical config must reach the live
    OrderTimeoutWatchdog instance (fsm.watchdog).
    """

    def test_check_interval_ms_reaches_watchdog(self):
        """
        check_interval_ms=2500 set via canonical config must be stored on
        fsm.watchdog.check_interval_ms, not the constructor default (1000).
        """
        cfg = _build_cfg(check_interval_ms=2500, rps_limit=10)
        fsm = _make_fsm(cfg)

        assert fsm.watchdog.check_interval_ms == 2500, (
            f"Expected check_interval_ms=2500, got {fsm.watchdog.check_interval_ms}. "
            "P1: watchdog cadence must come from canonical trading.execution.watchdog.check_interval_ms."
        )

    def test_rps_limit_reaches_watchdog(self):
        """
        rps_limit=7 set via canonical config must be stored on
        fsm.watchdog._rps_limit, not the constructor default (10).
        """
        cfg = _build_cfg(check_interval_ms=1000, rps_limit=7)
        fsm = _make_fsm(cfg)

        assert fsm.watchdog._rps_limit == 7, (
            f"Expected _rps_limit=7, got {fsm.watchdog._rps_limit}. "
            "P1: watchdog throttle must come from canonical trading.execution.watchdog.rps_limit."
        )

    def test_both_canonical_knobs_propagate_symmetrically(self):
        """
        Non-default values for BOTH check_interval_ms and rps_limit must
        propagate independently without cross-interference.
        """
        cfg = _build_cfg(check_interval_ms=3000, rps_limit=5)
        fsm = _make_fsm(cfg)

        assert fsm.watchdog.check_interval_ms == 3000
        assert fsm.watchdog._rps_limit == 5


# ---------------------------------------------------------------------------
# PART 2: Shadow alias removal proof
# ---------------------------------------------------------------------------

class TestShadowAliasRemoved:
    """
    trading.orders.default_ttl_seconds and root orders.default_ttl_seconds
    must NOT affect fill_ttl_ms on the live watchdog.
    The shadow alias override block was removed in the P1 slice.
    """

    def test_trading_orders_default_ttl_seconds_ignored(self):
        """
        If trading.orders.default_ttl_seconds is present in config,
        fill_ttl_ms on the live watchdog must remain equal to the canonical
        watchdog fill_ttl_ms value (5000), not candidate_ms (999 * 1000 = 999000).

        In the pre-P1 code, default_ttl_seconds=999 (999000ms > 5000ms) would
        have been applied, raising fill_ttl_ms to 999000ms.  That code is gone.
        """
        cfg = _build_cfg(ack_ttl_ms=5000, fill_ttl_ms=5000,
                         check_interval_ms=1000, rps_limit=10)

        # Inject the shadow alias value that would have overridden fill_ttl_ms before P1.
        # 999 * 1000 = 999000ms  >  fill_ttl_ms=5000ms  →  old code would apply it.
        orders_mock = MagicMock()
        orders_mock.default_ttl_seconds = 999
        cfg.trading.orders = orders_mock

        fsm = _make_fsm(cfg)

        assert fsm.watchdog.fill_ttl_ms == 5000, (
            f"Shadow alias trading.orders.default_ttl_seconds=999 should be IGNORED. "
            f"Got fill_ttl_ms={fsm.watchdog.fill_ttl_ms}. "
            "P1: shadow alias path was removed; watchdog.fill_ttl_ms is sole SSOT."
        )

    def test_root_orders_default_ttl_seconds_ignored(self):
        """
        If root orders.default_ttl_seconds is present in config,
        fill_ttl_ms on the live watchdog must remain at its canonical value (5000).

        In the pre-P1 code, root orders.default_ttl_seconds=999 (999000ms > 5000ms)
        would have been applied.  That code is gone.
        """
        cfg = _build_cfg(ack_ttl_ms=5000, fill_ttl_ms=5000,
                         check_interval_ms=1000, rps_limit=10)

        # Inject root-level alias.
        root_orders_mock = MagicMock()
        root_orders_mock.default_ttl_seconds = 42  # 42000ms
        cfg.orders = root_orders_mock

        fsm = _make_fsm(cfg)

        assert fsm.watchdog.fill_ttl_ms == 5000, (
            f"Shadow root alias orders.default_ttl_seconds=42 should be IGNORED. "
            f"Got fill_ttl_ms={fsm.watchdog.fill_ttl_ms}. "
            "P1: root orders alias path was removed; watchdog.fill_ttl_ms is sole SSOT."
        )

    def test_fill_ttl_ms_equals_watchdog_config_regardless_of_shadow_aliases(self):
        """
        With BOTH shadow aliases injected simultaneously, fill_ttl_ms must
        equal the canonical watchdog config value exactly.
        """
        cfg = _build_cfg(ack_ttl_ms=8000, fill_ttl_ms=3_600_000,
                         check_interval_ms=1000, rps_limit=10)

        # Both alias paths inject smaller values — old code would have chosen whichever
        # was larger; both paths are now dead.
        orders_mock = MagicMock()
        orders_mock.default_ttl_seconds = 15   # 15000ms — far smaller than 3600000
        cfg.trading.orders = orders_mock
        cfg.orders = orders_mock  # root alias too

        fsm = _make_fsm(cfg)

        assert fsm.watchdog.fill_ttl_ms == 3_600_000, (
            f"Expected fill_ttl_ms=3600000 (watchdog SSOT). "
            f"Got {fsm.watchdog.fill_ttl_ms}. P1 shadow alias paths must be inert."
        )
