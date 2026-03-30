"""
Adapter initialization — Phase 14.2 extraction from fsm.py.

Encapsulates BinanceAdapter bootstrap logic used by ExecPosFSM.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.reference.adapters.binance_adapter import BinanceAdapter

LOG = logging.getLogger(__name__)


class AdapterInitMixin:
    """
    Mixin providing adapter initialization for ExecPosFSM.

    Expects:
        self.config: AuroraConfig
        self.shadow_mode: bool
        self.adapter: Optional[BinanceAdapter]
        self._orphan_metrics: dict
        self.fsm: FSMCore
    """

    def _initialize_adapter(self) -> None:
        """Initializes the BinanceAdapter based on the domain-level trading_mode."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter

        # Check if config_loader has get_domain_mode method (new approach)
        mode = "testnet"  # Default fallback

        # Try to get domain-specific mode first
        if hasattr(self.config, "get_domain_mode"):
            try:
                mode = self.config.get_domain_mode("execution_position")
                LOG.info(f"ExecPosFSM using domain-specific mode: {mode}")
            except Exception as e:
                LOG.warning(f"Could not get domain mode, using fallback: {e}")
                try:
                    if self.config.trading:
                        mode = self.config.trading.mode
                except AttributeError:
                    mode = "testnet"
        else:
            # Fallback to global mode
            try:
                if self.config.trading:
                    mode = self.config.trading.mode
            except AttributeError:
                mode = "testnet"
            LOG.info(f"ExecPosFSM using global trading_mode: {mode}")

        LOG.info(f"EXECUTION POSITION FSM MODE: {mode.upper()}")

        api_config = self.config.binance_api

        # Safe extraction of env config
        if mode == "live":
            env_config = api_config.live
            LOG.info("ExecPosFSM adapter is configured for LIVE execution.")
        else:  # 'testnet' or 'hybrid_live_data_testnet_exec'
            env_config = api_config.testnet
            LOG.info(
                f"ExecPosFSM adapter is configured for TESTNET execution (mode: {mode})."
            )

        # Extract API credentials (fail-closed: no default fallbacks on critical fields)
        try:
            api_key = env_config.api_key
            api_secret = env_config.api_secret
            rest_url = env_config.rest_url
        except Exception:  # pragma: no cover - defensive
            api_key = None
            api_secret = None
            rest_url = None

        if not all([api_key, api_secret, rest_url]):
            LOG.error(
                f"API configuration for execution in '{mode}' mode is incomplete. "
                "Execution will be simulated."
            )
            LOG.debug(f"  - API Key present: {bool(api_key)}")
            LOG.debug(f"  - API Secret present: {bool(api_secret)}")
            LOG.debug(f"  - REST URL: {rest_url}")
            self.shadow_mode = True  # Fallback to shadow mode if config is missing
            return

        self.adapter = BinanceAdapter(
            api_key=api_key,
            api_secret=api_secret,
            rest_url=rest_url,
        )
        # PHASE B1: Pass metrics reference to adapter for -4116 tracking
        self.adapter._orphan_metrics_ref = self._orphan_metrics
        LOG.info(
            f"BinanceAdapter initialized for ExecPosFSM with base URL: {self.adapter.base_url}"
        )

        # POLLING FIX: Connect adapter to THIS ExecPosFSM instance
        # Adapter needs direct access to ExecPosFSM.handle() to deliver TRADE_EXECUTED events
        self.adapter.exec_fsm = self  # Direct reference to ExecPosFSM for handle() calls
        # Keep for backwards compatibility (event bus)
        self.adapter.fsm_core = self.fsm

        # ── FILL-PIPELINE-FIX: Start WebSocket User Data Stream ─────
        # Primary fill detection path; REST polling in watchdog is fallback.
        # FILL-PIPELINE-FIX-AUDIT: Stop existing WS client before creating new (F-4)
        if hasattr(self, 'ws_client') and self.ws_client is not None:
            try:
                self.ws_client.stop()
                LOG.info("Stopped previous BinanceWebSocketClient before re-init")
            except Exception:
                pass
        self.ws_client = None
        try:
            from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient

            use_testnet = mode != "live"
            # Capture the running event loop for thread-safe event delivery
            try:
                main_loop = asyncio.get_running_loop()
            except RuntimeError:
                main_loop = None

            self.ws_client = BinanceWebSocketClient(
                api_key=api_key,
                base_url=rest_url,
                use_testnet=use_testnet,
                fsm_core=self.fsm,
                main_loop=main_loop,
            )
            self.ws_client.start()
            LOG.info("BinanceWebSocketClient started for USER_DATA_STREAM fill detection")
        except Exception as e:
            LOG.warning(
                f"Failed to start BinanceWebSocketClient (REST polling fallback active): {e}"
            )
            self.ws_client = None
