"""
BinanceExecutionAdapter for executing trades on Binance Futures.
"""

import httpx
import time
import hmac
import hashlib
from typing import Dict, Any
from vfoundation.core.protocol import Message
from .execution_adapter import AbstractExecutionAdapter


class BinanceExecutionAdapter(AbstractExecutionAdapter):
    def __init__(self, fsm, config, shadow_mode=False):
        super().__init__(fsm, config)
        self.shadow_mode = shadow_mode
        self.base_url = (
            "https://testnet.binancefuture.com"
            if self.config.get("trading_env") == "test"
            else "https://fapi.binance.com"
        )
        self.api_key = self.config.get("binance_ro_api_key")
        self.api_secret = self.config.get("binance_ro_api_secret")
        self.headers = {"X-MBX-APIKEY": self.api_key}

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        query_string = "&".join(
            [f"{key}={params[key]}" for key in sorted(params.keys())]
        )
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _build_order_params(self, pld: dict) -> dict:
        order_type = (
            self.config.get("trading", {})
            .get("execution", {})
            .get("open_order_type", "MARKET")
            .upper()
        )
        params = {
            "symbol": pld["symbol"],
            "side": pld["side"].upper(),
            "type": order_type,
            "newOrderRespType": "RESULT",
        }
        if order_type == "MARKET":
            params["quantity"] = pld["qty"]
        elif order_type == "LIMIT":
            params["quantity"] = pld["qty"]
            params["price"] = pld["price"]
            params["timeInForce"] = (
                self.config.get("trading", {})
                .get("execution", {})
                .get("order_params", {})
                .get("LIMIT", {})
                .get("timeInForce", "GTC")
            )
        # Add other order types here based on TASK.md
        return params

    async def place_order(self, msg: Message) -> dict:
        if self.shadow_mode:
            return {
                "status": "ok",
                "order_id": "shadow-order-123",
                "lifecycle": "filled",
            }

        pld = msg.pld
        params = self._build_order_params(pld)
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = self._generate_signature(params)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/fapi/v1/order",
                    params=params,
                    headers=self.headers,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                return {"status": "error", "message": str(e.response.text)}

    async def cancel_order(self, msg: Message) -> dict:
        # Implementation for cancel_order
        pass

    def get_status(self) -> str:
        if self.shadow_mode:
            return "shadow"
        return "connected"

    async def get_positions_notional_usd_shadow(self) -> float:
        """
        EXP-FIX: Get shadow notional from Binance API for safety auditing.

        Fetches current positions from /fapi/v2/positionRisk and calculates
        total notional value. Used for safety comparison with portfolio data.

        Returns:
            Total notional value in USD, or 0.0 on error
        """
        if self.shadow_mode:
            return 0.0

        try:
            params = {"timestamp": int(time.time() * 1000)}
            params["signature"] = self._generate_signature(params)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/fapi/v2/positionRisk",
                    params=params,
                    headers=self.headers,
                )
                response.raise_for_status()
                positions = response.json()

                total_notional = 0.0
                for pos in positions:
                    try:
                        position_amt = abs(float(pos.get("positionAmt", 0)))
                        mark_price = float(pos.get("markPrice", 0))
                        if position_amt > 0 and mark_price > 0:
                            total_notional += position_amt * mark_price
                    except (ValueError, TypeError):
                        continue

                return round(total_notional, 2)

        except Exception as e:
            self.logger.error(f"SHADOW_NOTIONAL_ERROR: {e}")
            return 0.0
