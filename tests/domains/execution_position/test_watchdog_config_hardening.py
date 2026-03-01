from unittest.mock import MagicMock

import pytest

from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog


def test_watchdog_rejects_magicmock_config():
    with pytest.raises(RuntimeError, match="config must be mapping"):
        OrderTimeoutWatchdog(config=MagicMock())


def test_watchdog_rps_limit_must_be_int():
    with pytest.raises(RuntimeError, match="rps_limit must be int"):
        OrderTimeoutWatchdog(config={"rps_limit": "10"})


def test_watchdog_accepts_none_config_defaults():
    watchdog = OrderTimeoutWatchdog(config=None)
    assert watchdog._rps_limit == 10
