import pytest

from vfoundation.core.fsm_core import FSMCore


def test_order_index_wiring_failclosed_missing_ttl_sec() -> None:
    from apps.reference.main import _init_order_index

    fsm = FSMCore()
    bad_config = {
        "domains": {
            "execution_position": {
                "order_index": {
                    # ttl_sec intentionally missing
                }
            }
        }
    }

    with pytest.raises(ValueError, match=r"OrderIndex wiring fail-closed: missing required config path"):
        _init_order_index(fsm, bad_config)


def test_order_index_wiring_failclosed_invalid_ttl_sec() -> None:
    from apps.reference.main import _init_order_index

    fsm = FSMCore()
    bad_config = {
        "domains": {
            "execution_position": {
                "order_index": {
                    "ttl_sec": 0
                }
            }
        }
    }

    with pytest.raises(ValueError, match=r"OrderIndex wiring fail-closed: invalid"):
        _init_order_index(fsm, bad_config)
