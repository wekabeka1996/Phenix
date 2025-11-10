"""
AccountConnector for account_balance domain (FSMP-P1-T04).

Connects to Binance REST API via the centralized BinanceAdapter, retrieves
account balance and positions, and emits FSM events.
"""

import asyncio
import decimal
import logging
import threading
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from apps.reference.adapters.binance_adapter import BinanceAdapter

if TYPE_CHECKING:
    from vfoundation.core import FSMCore

LOG = logging.getLogger(__name__)


class AccountConnector:
    """
    Connects to Binance REST API via BinanceAdapter to retrieve account data.
    """

    def __init__(self, fsm: "FSMCore", config: Dict[str, Any]) -> None:
        """
        Initialize connector.

        Args:
            fsm: FSM core instance for event emission.
            config: Configuration dictionary with API credentials.
        """
        self.fsm = fsm
        self.config = config
        self.thread: Optional[threading.Thread] = None
        self.running = False

        # Extract account_observer config for polling interval
        # Handle both dict and Pydantic object access patterns
        account_observer_config = (
            self.config.get("account_observer", {})
            if isinstance(self.config, dict)
            else self.config.account_observer
        )
        poll_interval = (
            account_observer_config.get("poll_interval", 30)
            if isinstance(account_observer_config, dict)
            else account_observer_config.poll_interval
        )
        self.update_interval = poll_interval

        # Initialize the BinanceAdapter based on the trading_mode
        mode = (
            self.config.get("trading_mode", "testnet")
            if isinstance(self.config, dict)
            else self.config.trading_mode
        )
        api_config = (
            self.config.get("binance_api", {})
            if isinstance(self.config, dict)
            else self.config.binance_api
        )

        env_config = {}
        if mode == "live":
            if isinstance(api_config, dict):
                env_config = api_config.get("live", {})
            else:
                env_config = api_config.live
            LOG.info(
                "AccountConnector is configured for LIVE execution environment.")
        else:  # 'testnet' or 'hybrid_live_data_testnet_exec'
            if isinstance(api_config, dict):
                env_config = api_config.get("testnet", {})
            else:
                env_config = api_config.testnet
            LOG.info(
                f"AccountConnector is configured for TESTNET execution environment (mode: {mode})."
            )

        # Extract API credentials from env_config
        if isinstance(env_config, dict):
            api_key = env_config.get("api_key", "")
            api_secret = env_config.get("api_secret", "")
            rest_url = env_config.get("rest_url", "")
        else:
            api_key = env_config.api_key
            api_secret = env_config.api_secret
            rest_url = env_config.rest_url

        if not all([api_key, api_secret, rest_url]):
            raise ValueError(
                f"API configuration for account connection in '{mode}' mode is incomplete."
            )

        self.adapter = BinanceAdapter(
            api_key=api_key,
            api_secret=api_secret,
            rest_url=rest_url,
        )

        # Store latest balance data from /fapi/v2/balance endpoint
        self._latest_balance_data: Optional[List[Dict[str, Any]]] = None

    def start(self) -> None:
        """Start account monitoring in a background thread."""
        if self.running:
            LOG.warning("AccountConnector already running.")
            return

        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        LOG.info("AccountConnector started.")

    def stop(self) -> None:
        """Stop account monitoring."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()
        asyncio.run(self.adapter.close_session())
        LOG.info("AccountConnector stopped.")

    def _monitor_loop(self) -> None:
        """Main monitoring loop that runs in the background thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while self.running:
                loop.run_until_complete(self._fetch_and_emit_account_data())
                time.sleep(self.update_interval)
        finally:
            loop.close()
            LOG.info("Account monitoring loop ended.")

    async def _fetch_and_emit_account_data(self) -> None:
        """Fetch account data from Binance API and emit FSM events."""
        try:
            balance_data = await self.adapter.get_account_balance()
            if balance_data:
                if isinstance(balance_data, list):
                    self._latest_balance_data = (
                        balance_data  # Store for use in positions update
                    )
                    LOG.info(
                        f"✅ Stored balance data: {len(balance_data)} assets")
                    # Log USDT balance specifically
                    usdt_asset = next(
                        (item for item in balance_data if item.get("asset") == "USDT"),
                        None,
                    )
                    if usdt_asset:
                        LOG.info(
                            f"   💰 USDT balance: {usdt_asset.get('balance', 'N/A')}")
                        LOG.info(
                            f"   📊 USDT crossWalletBalance: {usdt_asset.get('crossWalletBalance', 'N/A')}")
                        LOG.info(
                            f"   📈 USDT crossUnPnl: {usdt_asset.get('crossUnPnl', 'N/A')}")
                    else:
                        LOG.warning(
                            "   ⚠️  No USDT asset found in balance data")
                    self._emit_balance_update(balance_data)
                else:
                    LOG.error(
                        f"Error processing balance data: expected a list, got {type(balance_data)}"
                    )
        except Exception as e:
            LOG.error(f"Error fetching account balance: {e}", exc_info=True)

        try:
            positions_data = await self.adapter.get_open_positions()
            api_position_count = len(positions_data) if isinstance(
                positions_data, list) else 0
            LOG.info(
                f"🔍 get_open_positions returned: {api_position_count} positions from API")
            if positions_data is not None:
                if isinstance(positions_data, list):
                    # Convert objects to dict if needed
                    positions_list = [
                        p.to_dict() if hasattr(p, 'to_dict') else (
                            p.__dict__ if not isinstance(p, dict) else p)
                        for p in positions_data
                    ]
                    # Count non-zero positions (using position_amount field from ExchangePosition)
                    non_zero = sum(1 for p in positions_list if abs(
                        float(p.get("position_amount", p.get("positionAmt", 0)))) > 0.0001)
                    LOG.info(
                        f"✅ Fetched positions: {non_zero} non-zero out of {len(positions_list)} total")
                    # Log each non-zero position
                    for pos in positions_list:
                        amt = float(pos.get("position_amount",
                                    pos.get("positionAmt", 0)))
                        if abs(amt) > 0.0001:
                            LOG.info(
                                f"   📊 {pos.get('symbol')}: {amt} @ "
                                f"{pos.get('entry_price', pos.get('entryPrice', 'N/A'))}")

                    # 🔴 DIAGNOSTIC: Check for divergence (API empty but internal has data)
                    if api_position_count == 0:
                        LOG.warning(
                            "🚨 CRITICAL: API returned EMPTY positions! Will trigger FALLBACK in margin calculation")
                        LOG.warning(
                            "   → This means system will use internal self._positions (if any)")
                        LOG.warning(
                            "   → Check: Are orders filled on Binance? Is API key valid?")

                    # Always emit positions update, even if empty
                    self._emit_positions_update(positions_list)
                else:
                    LOG.error(
                        f"Error processing positions data: expected a list, got {type(positions_data)}"
                    )
            else:
                LOG.warning("⚠️ get_open_positions returned None")
        except Exception as e:
            LOG.error(f"Error fetching open positions: {e}", exc_info=True)

    def _emit_balance_update(self, balance_data: List[Dict[str, Any]]) -> None:
        """Emit balance update event with asset balances."""
        assets = [
            {
                "asset": asset["asset"],
                "balance": str(decimal.Decimal(asset.get("balance", "0"))),
                "crossUnPnl": str(decimal.Decimal(asset.get("crossUnPnl", "0"))),
                "crossWalletBalance": str(
                    decimal.Decimal(asset.get("crossWalletBalance", "0"))
                ),
                "updateTime": asset.get("updateTime", 0),
            }
            for asset in balance_data
            if decimal.Decimal(asset.get("balance", "0")) > 0
        ]

        if not assets:
            return

        payload = {
            "assets": assets,
            "updateTime": max(
                (asset.get("updateTime", 0) for asset in assets), default=0
            ),
        }
        self.fsm.emit(
            event_name="EVT:BALANCE_UPDATE_RECEIVED",
            payload=payload,
            why="Balance data updated from Binance API.",
        )
        LOG.info(
            f"Emitted balance update: {len(assets)} assets with balance > 0.")

    def _emit_positions_update(self, positions_data: List[Dict[str, Any]]) -> None:
        """Emit account update event with open positions."""
        LOG.info(
            f"📊 Processing positions data: {len(positions_data)} raw positions")

        open_positions = [
            {
                "symbol": pos["symbol"],
                "positionAmt": str(decimal.Decimal(pos.get("position_amount", pos.get("positionAmt", "0")))),
                "entryPrice": str(decimal.Decimal(pos.get("entry_price", pos.get("entryPrice", "0")))),
                "unRealizedProfit": str(
                    decimal.Decimal(
                        pos.get("unrealized_pnl", pos.get("unRealizedProfit", "0")))),
                "leverage": int(pos.get("leverage", 1)),
                "marginType": pos.get("marginType", "cross"),
                "markPrice": str(decimal.Decimal(pos.get("mark_price", pos.get("markPrice", "0")))),
                "liquidationPrice": str(
                    decimal.Decimal(pos.get("liquidation_price",
                                    pos.get("liquidationPrice", "0")))
                ),
            }
            for pos in positions_data
            if decimal.Decimal(pos.get("position_amount", pos.get("positionAmt", "0"))) != 0
        ]

        LOG.info(f"📊 Filtered to {len(open_positions)} non-zero positions")

        # Use stored balance data from /fapi/v2/balance endpoint
        # that contains walletBalance, unrealizedProfit, etc.
        wallet_balance = "0"
        unrealized_profit = "0"
        cross_wallet_balance = "0"

        LOG.debug(
            f"_emit_positions_update: _latest_balance_data is "
            f"{type(self._latest_balance_data)} with value: "
            f"{self._latest_balance_data is not None}"
        )

        if self._latest_balance_data:
            LOG.info(
                f"✅ Using stored balance data: {len(self._latest_balance_data)} assets available"
            )
            # Find USDT balance (or any base currency that has the account summary)
            # In Binance Futures API /fapi/v2/balance, each asset has balance, crossWalletBalance, etc.
            usdt_asset = next(
                (
                    item
                    for item in self._latest_balance_data
                    if item.get("asset") == "USDT"
                ),
                None,
            )
            if usdt_asset:
                # Use 'balance' field instead of 'walletBalance' (which doesn't exist in /fapi/v2/balance response)
                wallet_balance = str(decimal.Decimal(
                    usdt_asset.get("balance", "0")))
                unrealized_profit = str(
                    decimal.Decimal(usdt_asset.get("crossUnPnl", "0"))
                )
                # crossWalletBalance = balance - unrealizedProfit (approximately)
                cross_wallet_balance = str(
                    decimal.Decimal(usdt_asset.get("crossWalletBalance", "0"))
                )

                LOG.info(
                    f"   ✅ Found USDT: balance={wallet_balance}, "
                    f"unrealizedProfit={unrealized_profit}, "
                    f"crossWalletBalance={cross_wallet_balance}"
                )
            else:
                LOG.warning("   ⚠️  No USDT asset found in balance data")
        else:
            LOG.warning(
                "⚠️  No balance data available yet; positions update will have zero wallet balance"
            )

        payload = {
            "totalWalletBalance": wallet_balance,
            "totalUnrealizedProfit": unrealized_profit,
            "totalCrossWalletBalance": cross_wallet_balance,
            "positions": open_positions,
            "updateTime": int(time.time() * 1000),
        }

        self.fsm.emit(
            event_name="EVT:ACCOUNT_UPDATE_RECEIVED",
            payload=payload,
            why="Open positions data updated from Binance API.",
        )
        LOG.info(
            f"Emitted positions update: {len(open_positions)} open positions, "
            f"totalWalletBalance={wallet_balance}, "
            f"totalUnrealizedProfit={unrealized_profit}"
        )
