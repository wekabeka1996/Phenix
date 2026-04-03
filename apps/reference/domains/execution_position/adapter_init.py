"""Adapter bootstrap helpers for the execution-position FSM.

The mixin owns only adapter and user-data-stream initialization. Broader FSM
startup, guardian wiring, and shutdown remain in ``fsm.py``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.reference.adapters.binance_adapter import BinanceAdapter

LOG = logging.getLogger(__name__)


class AdapterInitMixin:
    """Mixin providing execution-adapter bootstrap for ``ExecPosFSM``.

    Expects:
        self.config: AuroraConfig
        self.shadow_mode: bool
        self.adapter: Optional[BinanceAdapter]
        self._orphan_metrics: dict
        self.fsm: FSMCore
    """

    def _resolve_ws_main_loop(self) -> asyncio.AbstractEventLoop | None:
        """Resolve the loop used to marshal websocket callbacks back to runtime."""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            get_loop = getattr(self, "_get_async_loop", None)
            if callable(get_loop):
                try:
                    return get_loop()
                except Exception as exc:  # pragma: no cover - defensive
                    LOG.debug("ExecPosFSM async loop lookup failed: %s", exc)
            return None

    def _initialize_adapter(self) -> None:
        """Initialize the runtime adapter and optional user-data WS client.

        Mode resolution prefers the execution_position domain override when the
        config exposes ``get_domain_mode()``; otherwise it falls back to the
        legacy global trading mode. Missing API credentials do not raise here:
        the mixin flips the FSM into ``shadow_mode`` and leaves execution
        simulated rather than half-configured.
        """
        from apps.reference.adapters.binance_adapter import BinanceAdapter

        # Prefer the domain-specific execution mode when available so
        # execution_position can diverge from any legacy global trading mode.
        mode = "testnet"  # Default fallback

        # Fall back to the global trading mode only when the newer domain-level
        # resolver is absent or raises.
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

        # Credential extraction is fail-closed for live execution: the mixin
        # never invents defaults for key/secret/REST URL.
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
            # Keep the FSM alive in simulation mode instead of starting a
            # partially configured live adapter.
            self.shadow_mode = True
            return

        self.adapter = BinanceAdapter(
            api_key=api_key,
            api_secret=api_secret,
            rest_url=rest_url,
        )
        # Share the orphan-order metrics dict so adapter-side recoveries update
        # the same counters the FSM exposes for forensics.
        self.adapter._orphan_metrics_ref = self._orphan_metrics
        LOG.info(
            f"BinanceAdapter initialized for ExecPosFSM with base URL: {self.adapter.base_url}"
        )

        # The adapter still emits into the FSM boundary directly for fill/order
        # events; ``fsm_core`` remains for older event-bus based paths.
        self.adapter.exec_fsm = self
        self.adapter.fsm_core = self.fsm

        # ── FILL-PIPELINE-FIX: Start WebSocket User Data Stream ─────
        # Primary fill detection path; REST watchdog polling remains the
        # fallback if WS startup fails.
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
            # Capture the shared execution loop even when adapter init runs on a
            # synchronous thread; otherwise the WS client falls back to unsafe emit.
            main_loop = self._resolve_ws_main_loop()

            self.ws_client = BinanceWebSocketClient(
                api_key=api_key,
                base_url=rest_url,
                use_testnet=use_testnet,
                fsm_core=self.fsm,
                main_loop=main_loop,
            )
            self.ws_client.start()
            LOG.info(
                "BinanceWebSocketClient started for USER_DATA_STREAM fill detection")
        except Exception as e:
            LOG.warning(
                f"Failed to start BinanceWebSocketClient (REST polling fallback active): {e}"
            )
            self.ws_client = None
