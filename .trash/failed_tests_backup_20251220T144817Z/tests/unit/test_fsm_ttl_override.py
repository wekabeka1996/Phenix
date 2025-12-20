"""
Test that ExecPosFSM honors trading.orders.default_ttl_seconds by overriding
watchdog fill_ttl_ms.
"""

from apps.reference.domains.execution_position.fsm import ExecPosFSM


def test_execposfsm_applies_default_ttl_seconds_override():
    config = {
        "trading": {
            "orders": {
                "default_ttl_seconds": 15,
            },
            "execution": {
                "watchdog": {
                    "ack_ttl_ms": 8000,
                    "fill_ttl_ms": 30000,
                }
            },
        }
    }

    fsm = ExecPosFSM(config=config, fsm=None, shadow_mode=True)
    # Expect fill TTL to be overridden to 15000 ms
    assert getattr(fsm, "watchdog").fill_ttl_ms == 15000

