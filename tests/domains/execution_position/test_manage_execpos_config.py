import copy

import pytest

from apps.reference.config_loader import AuroraConfig
from apps.reference.config_models import ConfigV2
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.manage_config import (
    clear_manage_config_cache,
)


class DummyGuardian:
    def __init__(self, adapter, config=None, poll_interval_ms=0, bus=None):
        self.adapter = adapter
        self.config = config
        self.poll_interval_ms = poll_interval_ms
        self.bus = bus
        self._symbols = set()

    def update_known_symbols(self, symbols):
        self._symbols = set(symbols)

    def get_metrics(self):
        return {}

    def register_entry(self, **kwargs):
        self.last_entry = kwargs

    def register_brackets(self, **kwargs):
        self.last_brackets = kwargs

    def on_fill(self, **kwargs):
        self.last_fill = kwargs

    async def should_place_brackets(self, *args, **kwargs):
        return True

    async def get_brackets_for_entry(self, *args, **kwargs):
        return {}

    async def get_our_open_brackets(self, *args, **kwargs):
        return []

    async def cleanup_before_close(self, *args, **kwargs):
        return None

    async def close_entry(self, *args, **kwargs):
        return None

    async def cleanup_orphans(self, *args, **kwargs):
        return 0

    async def reconcile_symbol(self, *args, **kwargs):
        return None

    async def cleanup_other_brackets_for_symbol(self, *args, **kwargs):
        return None

    async def link_existing_from_rest(self, *args, **kwargs):
        return None

    def list_entries(self, *args, **kwargs):
        return []

    async def start(self):
        return None

    async def stop(self):
        return None


@pytest.fixture(autouse=True)
def clear_manage_cache():
    clear_manage_config_cache()
    yield
    clear_manage_config_cache()


@pytest.fixture(autouse=True)
def stub_order_guardian(monkeypatch):
    monkeypatch.setattr(
        "apps.reference.domains.execution_position.fsm.OrderGuardian",
        DummyGuardian,
    )


def _make_execpos(config):
    return ExecPosFSM(config=config, fsm=None, shadow_mode=True)


def test_execpos_uses_manage_resolver_values():
    config = {
        "trading": {
            "execution": {
                "manage": {
                    "auto": True,
                    "orphan_monitor": {
                        "enabled": True,
                        "run_on_startup": False,
                        "periodic_interval_sec": 42,
                        "min_order_age_sec": 3,
                        "batch_cancel_limit": 7,
                        "rate_limit_per_min": 13,
                    },
                    "order_guardian": {
                        "poll_interval_ms": 150,
                    },
                    "watchdog": {
                        "ack_ttl_ms": 1234,
                        "fill_ttl_ms": 5678,
                    },
                    "brackets": {
                        "keep_single_bracket_set": False,
                    },
                }
            },
            "orders": {
                "default_ttl_seconds": 55,
            },
            "instruments": {
                "BTCUSDT": {},
            },
        },
        "guardian": {
            "cleanup_ttl_ms": 9000,
            "symbol_cooldown_ms": 11000,
            "unified": False,
            "emit_tidy_event": False,
        },
    }

    fsm = _make_execpos(copy.deepcopy(config))

    assert fsm._orphan_cfg.periodic_interval_sec == 42
    assert fsm._orphan_cfg.min_order_age_sec == 3
    assert fsm._orphan_cfg.batch_cancel_limit == 7
    assert fsm._orphan_cfg.rate_limit_per_min == 13

    assert fsm._guardian_cfg.poll_interval_ms == 150
    assert fsm._guardian_cfg.cleanup_ttl_ms == 9000
    assert fsm._guardian_unified is False
    assert fsm._guardian_emit_tidy_event is False

    assert fsm.watchdog.ack_ttl_ms == 1234
    assert fsm.watchdog.fill_ttl_ms == 55000  # 55s override -> 55000ms

    first = fsm._manage_cfg()
    second = fsm._manage_cfg()
    assert first is second
    assert first.brackets.keep_single_bracket_set is False
    assert first.watchdog.source == "trading.orders.default_ttl_seconds"


def test_execpos_manage_resolver_legacy_defaults():
    fsm = _make_execpos({})

    assert fsm._orphan_cfg.periodic_interval_sec == 300
    assert fsm._orphan_cfg.batch_cancel_limit == 50
    assert fsm._guardian_cfg.poll_interval_ms == 500
    assert fsm._guardian_cfg.cleanup_ttl_ms == 6000
    assert fsm.watchdog.ack_ttl_ms == 8000
    assert fsm.watchdog.fill_ttl_ms == 30000
    assert fsm._manage_cfg().watchdog.source == "defaults"


def test_execpos_uses_v2_guardian_poll_interval():
    v2_data = {
        "domains": {
            "execution": {
                "manage": {
                    "guardian": {
                        "unified": True,
                        "emit_tidy_event": True,
                        "poll_interval_ms": 150,
                        "cleanup_ttl_ms": 6500,
                        "symbol_cooldown_ms": 3200,
                    },
                    "orphan_monitor": {
                        "enabled": True,
                    },
                }
            }
        }
    }

    config = AuroraConfig.model_construct(
        trading={"instruments": {"BTCUSDT": {"symbol": "BTCUSDT"}}},
        config_v2=ConfigV2(**v2_data),
    )

    fsm = _make_execpos(config)

    assert getattr(fsm, "_manage_cfg_source", None) == "config_v2"
    assert fsm._guardian_cfg.poll_interval_ms == 150
    assert fsm.order_guardian.poll_interval_ms == 150
