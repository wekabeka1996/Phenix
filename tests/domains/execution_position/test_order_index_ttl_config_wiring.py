"""
T2 Timer Governance: OrderIndex TTL config wiring test.

Verifies that `_init_order_index` (the composition root in main.py) passes
`domains.execution_position.order_index.ttl_sec` from the typed Pydantic config
directly to the `OrderIndex(ttl_sec=...)` constructor, rather than relying on
the constructor's hardcoded default of 3600.

SSOT: config/aurora/domains.yaml -> domains.execution_position.order_index.ttl_sec
Pydantic: apps/reference/config/domains/execution_position.py -> OrderIndexConfig.ttl_sec
Wiring:  apps/reference/main.py -> _init_order_index() -> fsm.order_index.ttl

Design choice: test targets _init_order_index directly (narrowest seam) to avoid
spinning up ExecPosFSM or the full main.py runtime. A plain MagicMock is sufficient
for fsm; config is a MagicMock with the relevant attribute path set to a sentinel value.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from apps.reference.domains.execution_position.state.order_index import OrderIndex


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(ttl_sec: int) -> MagicMock:
    """Return a minimal config mock with order_index.ttl_sec wired to ttl_sec."""
    config = MagicMock()
    config.domains.execution_position.order_index.ttl_sec = ttl_sec
    return config


# ---------------------------------------------------------------------------
# Primary wiring test — this must pass after the fix is in place
# ---------------------------------------------------------------------------

class TestOrderIndexTTLWiring:
    """T2 wiring: _init_order_index must propagate configured ttl_sec, not the
    constructor default (3600)."""

    def test_order_index_uses_configured_ttl_sec(self):
        """
        SSOT enforcement: when config has order_index.ttl_sec = 123, the wired
        OrderIndex must carry ttl = 123, NOT the hardcoded constructor default 3600.

        Narrows the seam to _init_order_index directly — no full FSM spin-up needed.
        """
        from apps.reference.main import _init_order_index

        config = _make_config(ttl_sec=123)
        fsm = MagicMock()

        _init_order_index(fsm, config)

        # _init_order_index sets fsm.order_index = OrderIndex(ttl_sec=<configured>)
        # OrderIndex stores the value as self.ttl (not self.ttl_sec)
        assert isinstance(fsm.order_index, OrderIndex), (
            "fsm.order_index must be an OrderIndex instance after wiring"
        )
        assert fsm.order_index.ttl == 123, (
            f"Expected ttl=123 (from config), got ttl={fsm.order_index.ttl}. "
            "This means the config TTL is not being forwarded to OrderIndex — "
            "YAML+Pydantic SSOT violation."
        )

    def test_order_index_not_defaulting_to_hardcoded_3600(self):
        """
        Regression guard: a non-3600 configured TTL must NOT be silently replaced
        by the constructor default.  This catches any future regression where the
        wiring is removed or bypassed.
        """
        from apps.reference.main import _init_order_index

        config = _make_config(ttl_sec=7200)
        fsm = MagicMock()

        _init_order_index(fsm, config)

        assert fsm.order_index.ttl == 7200, (
            f"Expected ttl=7200 (from config), got ttl={fsm.order_index.ttl}. "
            "Wiring regression: OrderIndex is NOT receiving the configured TTL."
        )

    def test_order_index_configured_ttl_propagated_not_truncated(self):
        """
        Boundary: smallest valid non-default TTL (1 second) is passed through
        correctly, confirming that int() coercion in the wiring path does not
        truncate or alter the value.
        """
        from apps.reference.main import _init_order_index

        config = _make_config(ttl_sec=1)
        fsm = MagicMock()

        _init_order_index(fsm, config)

        assert fsm.order_index.ttl == 1


# ---------------------------------------------------------------------------
# Fail-closed tests — missing / invalid config must raise, not default to 3600
# ---------------------------------------------------------------------------

class TestOrderIndexTTLWiringFailClosed:
    """_init_order_index must refuse to start when config is absent or invalid."""

    def test_missing_config_raises_value_error_not_default(self):
        """
        Fail-closed: if config provides no readable ttl_sec (not a dict, attribute
        raises), _init_order_index must raise ValueError rather than silently using
        the OrderIndex constructor default of 3600.
        """
        from apps.reference.main import _init_order_index

        class _BrokenConfig:
            @property
            def domains(self):
                raise AttributeError("domains attribute missing")

        fsm = MagicMock()

        with pytest.raises(ValueError, match="fail-closed"):
            _init_order_index(fsm, _BrokenConfig())

    def test_zero_ttl_raises_value_error(self):
        """
        Fail-closed: a zero TTL is invalid and must raise immediately.
        Ensures the guard `if ttl_sec <= 0` is exercised.
        """
        from apps.reference.main import _init_order_index

        config = _make_config(ttl_sec=0)
        fsm = MagicMock()

        with pytest.raises(ValueError, match="fail-closed"):
            _init_order_index(fsm, config)

    def test_negative_ttl_raises_value_error(self):
        """
        Fail-closed: a negative TTL is invalid and must raise immediately.
        """
        from apps.reference.main import _init_order_index

        config = _make_config(ttl_sec=-1)
        fsm = MagicMock()

        with pytest.raises(ValueError, match="fail-closed"):
            _init_order_index(fsm, config)


# ---------------------------------------------------------------------------
# Pydantic model contract test — OrderIndexConfig.ttl_sec must be required (no default)
# ---------------------------------------------------------------------------

class TestOrderIndexConfigPydanticContract:
    """
    The Pydantic model must NOT have a default for ttl_sec.  If it did, a missing
    YAML value would silently produce 3600 instead of a validation error.
    """

    def test_order_index_config_ttl_sec_is_required(self):
        """
        OrderIndexConfig must be defined with `ttl_sec: int = Field(...)` (required).
        Instantiating it with no arguments must raise a Pydantic ValidationError.
        """
        from apps.reference.config.domains.execution_position import OrderIndexConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OrderIndexConfig()  # type: ignore[call-arg]

    def test_order_index_config_accepts_valid_ttl(self):
        """
        OrderIndexConfig must accept a valid integer ttl_sec without error.
        """
        from apps.reference.config.domains.execution_position import OrderIndexConfig

        cfg = OrderIndexConfig(ttl_sec=3600)
        assert cfg.ttl_sec == 3600

    def test_order_index_config_ttl_123_roundtrip(self):
        """
        OrderIndexConfig must preserve ttl_sec=123 through Pydantic validation.
        """
        from apps.reference.config.domains.execution_position import OrderIndexConfig

        cfg = OrderIndexConfig(ttl_sec=123)
        assert cfg.ttl_sec == 123
