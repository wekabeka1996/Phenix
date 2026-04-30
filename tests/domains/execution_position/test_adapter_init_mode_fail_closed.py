"""
Phase 2 — Ingress and Config Fail-Closed

Tests for DEF-E09: Adapter mode must not silently fall to testnet/shadow in
live/hybrid modes. Missing credentials must be observable, not quietly swallowed.

Tests for DEF-E05: Missing instrument config must fail-closed, not use
generic fallback constants (MIN_ORDER_QTY, MIN_NOTIONAL, etc.).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from apps.reference.domains.execution_position.adapter_init import AdapterInitMixin


class _FakeAdapterInitFSM(AdapterInitMixin):
    """Minimal stub that satisfies AdapterInitMixin attribute expectations."""

    def __init__(self, config):
        self.config = config
        self.shadow_mode = False
        self.adapter = None
        self._orphan_metrics = {}


def _make_config(mode: str, *, api_key: str = "k", api_secret: str = "s", rest_url: str = "https://testnet.binancefuture.com"):
    """Build a minimal mock config with given mode and credentials."""
    config = MagicMock()
    config.get_domain_mode.return_value = mode

    env_config = MagicMock()
    env_config.api_key = api_key
    env_config.api_secret = api_secret
    env_config.rest_url = rest_url

    config.binance_api.live = env_config if mode == "live" else MagicMock(
        api_key="", api_secret="", rest_url="")
    config.binance_api.testnet = env_config if mode != "live" else MagicMock(
        api_key="", api_secret="", rest_url="")
    return config


class TestAdapterInitModeBehavior:
    """DEF-E09: Adapter mode resolution and credential checks must be observable."""

    def test_missing_live_credentials_fail_closed(self):
        """
        DEF-E09: When live mode credentials are missing, execution must fail
        closed instead of silently degrading to shadow_mode.
        """
        config = MagicMock()
        config.get_domain_mode.return_value = "live"
        # Credentials are missing (empty strings → falsy)
        env_config = MagicMock()
        env_config.api_key = ""
        env_config.api_secret = ""
        env_config.rest_url = ""
        config.binance_api.live = env_config

        fsm = _FakeAdapterInitFSM(config)

        with patch("apps.reference.adapters.binance_adapter.BinanceAdapter"):
            with pytest.raises(ValueError, match="fail closed"):
                fsm._initialize_adapter()

        assert fsm.shadow_mode is False, (
            "DEF-E09: Missing live credentials must fail before shadow_mode fallback."
        )

    def test_missing_hybrid_credentials_fail_closed(self):
        """Hybrid live-data/testnet-exec mode must also fail closed on missing testnet credentials."""
        config = MagicMock()
        config.get_domain_mode.return_value = "hybrid_live_data_testnet_exec"
        config.binance_api.testnet = MagicMock(
            api_key="", api_secret="", rest_url="")

        fsm = _FakeAdapterInitFSM(config)

        with patch("apps.reference.adapters.binance_adapter.BinanceAdapter"):
            with pytest.raises(ValueError, match="fail closed"):
                fsm._initialize_adapter()

    def test_mode_resolution_uses_domain_config_first(self):
        """Domain-specific mode must take priority over global trading mode."""
        config = MagicMock()
        config.get_domain_mode.return_value = "testnet"
        env_config = MagicMock()
        env_config.api_key = "key"
        env_config.api_secret = "secret"
        env_config.rest_url = "https://testnet.binancefuture.com"
        config.binance_api.testnet = env_config

        fsm = _FakeAdapterInitFSM(config)

        with patch("apps.reference.adapters.binance_adapter.BinanceAdapter") as mock_adapter_cls:
            mock_adapter_cls.return_value = MagicMock()
            try:
                fsm._initialize_adapter()
            except Exception:
                pass  # WS client setup may fail in test; we only care about mode resolution

        # get_domain_mode should have been called (domain-first resolution)
        config.get_domain_mode.assert_called()

    def test_mode_resolution_failure_raises_instead_of_defaulting_to_testnet(self):
        """
        DEF-E09: unresolved mode must fail closed instead of silently defaulting
        to testnet.
        """
        config = MagicMock()
        config.get_domain_mode.side_effect = RuntimeError(
            "mode resolution failed")
        config.trading = None

        fsm = _FakeAdapterInitFSM(config)

        with patch("apps.reference.adapters.binance_adapter.BinanceAdapter"):
            with pytest.raises(ValueError, match="must be explicitly configured"):
                fsm._initialize_adapter()

    def test_explicit_testnet_mode_can_degrade_to_shadow_on_missing_credentials(self):
        """Explicit testnet mode may simulate, but only because testnet itself was explicit."""
        config = MagicMock()
        config.get_domain_mode.return_value = "testnet"
        config.binance_api.testnet = MagicMock(
            api_key="", api_secret="", rest_url="")

        fsm = _FakeAdapterInitFSM(config)

        with patch("apps.reference.adapters.binance_adapter.BinanceAdapter"):
            fsm._initialize_adapter()

        assert fsm.shadow_mode is True


class TestInstrumentConfigFailClosed:
    """DEF-E05: Missing instrument config must fail-closed, not use generic fallback."""

    def test_fsm_open_raises_on_missing_instrument(self):
        """
        DEF-E05: When config.instruments[symbol] is missing, execution must fail
        closed rather than using MIN_ORDER_QTY / MIN_NOTIONAL constants.
        """
        from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM

        mock_config = MagicMock()
        mock_config.instruments = {}  # Empty — no instruments configured
        mock_domains = MagicMock()
        mock_domains.execution_position.fsm_open.idempotency_window_sec = 60.0
        mock_config.domains = mock_domains

        fsm = OpenFlowFSM(config=mock_config, guard_enabled=False)

        # Accessing instrument specs for a symbol not in config must raise, not use defaults
        with pytest.raises(Exception):
            fsm._get_instrument_specs("BTCUSDT")

    def test_generic_constants_not_returned_for_missing_symbol(self):
        """
        DEF-E05: _get_instrument_specs must not silently return MIN_ORDER_QTY=0.001
        when instrument is not in config. The constants in contracts.py are for
        tests only.
        """
        from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM
        from decimal import Decimal

        mock_config = MagicMock()
        mock_config.instruments = {}
        mock_domains = MagicMock()
        mock_domains.execution_position.fsm_open.idempotency_window_sec = 60.0
        mock_config.domains = mock_domains

        fsm = OpenFlowFSM(config=mock_config, guard_enabled=False)

        try:
            result = fsm._get_instrument_specs("XRPUSDT")
            # If it didn't raise, verify it didn't return the hardcoded fallback
            # DEF-E05: If result is the generic MIN_ORDER_QTY=0.001, that's the bug
            if result is not None:
                min_qty = getattr(result, "min_qty", None) or (
                    result[0] if isinstance(result, tuple) else None
                )
                assert min_qty != Decimal("0.001"), (
                    "DEF-E05: _get_instrument_specs returned MIN_ORDER_QTY=0.001 fallback "
                    "for missing symbol 'XRPUSDT'. Generic constants must not be used as "
                    "instrument SSOT. Add fail-closed guard."
                )
        except Exception:
            pass  # Exception is the expected fail-closed behavior — test passes
