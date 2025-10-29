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

from vfoundation.adapters.binance_adapter import BinanceAdapter

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
        account_observer_config = config.get('account_observer', {})
        self.update_interval = account_observer_config.get('poll_interval', 30)

        # Initialize the BinanceAdapter based on the trading_mode
        mode = config.get("trading_mode", "testnet")
        api_config = config.get("binance_api", {})
        
        env_config = {}
        if mode == "live":
            env_config = api_config.get("live", {})
            LOG.info("AccountConnector is configured for LIVE execution environment.")
        else:  # 'testnet' or 'hybrid_live_data_testnet_exec'
            env_config = api_config.get("testnet", {})
            LOG.info(f"AccountConnector is configured for TESTNET execution environment (mode: {mode}).")

        if not all([env_config.get("api_key"), env_config.get("api_secret"), env_config.get("rest_url")]):
            raise ValueError(f"API configuration for account connection in '{mode}' mode is incomplete.")

        self.adapter = BinanceAdapter(
            api_key=env_config["api_key"],
            api_secret=env_config["api_secret"],
            rest_url=env_config["rest_url"]
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
                    self._latest_balance_data = balance_data  # Store for use in positions update
                    LOG.info(f"✅ Stored balance data: {len(balance_data)} assets")
                    # Log USDT balance specifically
                    usdt_asset = next((item for item in balance_data if item.get("asset") == "USDT"), None)
                    if usdt_asset:
                        LOG.info(f"   USDT asset keys: {usdt_asset.keys()}")
                        LOG.info(f"   USDT walletBalance: {usdt_asset.get('walletBalance', 'N/A')}")
                        # Also log all values
                        for key, val in usdt_asset.items():
                            LOG.info(f"      {key}: {val}")
                    else:
                        LOG.warning("   ⚠️  No USDT asset found in balance data")
                    self._emit_balance_update(balance_data)
                else:
                    LOG.error(f"Error processing balance data: expected a list, got {type(balance_data)}")
        except Exception as e:
            LOG.error(f"Error fetching account balance: {e}", exc_info=True)

        try:
            positions_data = await self.adapter.get_open_positions()
            if positions_data:
                if isinstance(positions_data, list):
                    LOG.info(f"✅ Fetched positions data: {len(positions_data)} positions")
                    self._emit_positions_update(positions_data)
                else:
                    LOG.error(f"Error processing positions data: expected a list, got {type(positions_data)}")
        except Exception as e:
            LOG.error(f"Error fetching open positions: {e}", exc_info=True)

    def _emit_balance_update(self, balance_data: List[Dict[str, Any]]) -> None:
        """Emit balance update event with asset balances."""
        assets = [
            {
                'asset': asset['asset'],
                'balance': str(decimal.Decimal(asset.get('balance', '0'))),
                'crossUnPnl': str(decimal.Decimal(asset.get('crossUnPnl', '0'))),
                'crossWalletBalance': str(decimal.Decimal(asset.get('crossWalletBalance', '0'))),
                'updateTime': asset.get('updateTime', 0)
            }
            for asset in balance_data if decimal.Decimal(asset.get('balance', '0')) > 0
        ]

        # Always emit event, even if no assets have positive balance
        # This ensures FSM knows balance was updated, even if all assets are filtered out
        payload = {
            'assets': assets,
            'updateTime': max((asset.get('updateTime', 0) for asset in balance_data), default=0)
        }
        self.fsm.emit(
            event_name="EVT:BALANCE_UPDATE_RECEIVED",
            payload=payload,
            why="Balance data updated from Binance API."
        )
        LOG.info(f"Emitted balance update: {len(assets)} assets with balance > 0.")

    def _emit_positions_update(self, positions_data: List[Dict[str, Any]]) -> None:
        """Emit account update event with open positions."""
        open_positions = [
            {
                'symbol': pos['symbol'],
                'positionAmt': str(decimal.Decimal(pos.get('positionAmt', '0'))),
                'entryPrice': str(decimal.Decimal(pos.get('entryPrice', '0'))),
                'unRealizedProfit': str(decimal.Decimal(pos.get('unRealizedProfit', '0'))),
                'leverage': int(pos.get('leverage', 1)),
                'marginType': pos.get('marginType', 'cross'),
                'markPrice': str(decimal.Decimal(pos.get('markPrice', '0'))),
                'liquidationPrice': str(decimal.Decimal(pos.get('liquidationPrice', '0'))),
            }
            for pos in positions_data if decimal.Decimal(pos.get('positionAmt', '0')) != 0
        ]

        # Use stored balance data from /fapi/v2/balance endpoint
        # that contains walletBalance, unrealizedProfit, etc.
        wallet_balance = '0'
        unrealized_profit = '0'
        cross_wallet_balance = '0'
        
        LOG.debug(f"_emit_positions_update: _latest_balance_data is {type(self._latest_balance_data)} with value: {self._latest_balance_data is not None}")
        
        if self._latest_balance_data:
            LOG.info(f"✅ Using stored balance data: {len(self._latest_balance_data)} assets available")
            # Find USDT balance (or any base currency that has the account summary)
            # In Binance Futures API /fapi/v2/balance, each asset has balance, crossWalletBalance, etc.
            usdt_asset = next(
                (item for item in self._latest_balance_data if item.get("asset") == "USDT"),
                None
            )
            if usdt_asset:
                # Use 'balance' field instead of 'walletBalance' (which doesn't exist in /fapi/v2/balance response)
                wallet_balance = str(decimal.Decimal(usdt_asset.get('balance', '0')))
                unrealized_profit = str(decimal.Decimal(usdt_asset.get('crossUnPnl', '0')))
                # crossWalletBalance = balance - unrealizedProfit (approximately)
                cross_wallet_balance = str(decimal.Decimal(usdt_asset.get('crossWalletBalance', '0')))
                
                LOG.info(f"   ✅ Found USDT: balance={wallet_balance}, unrealizedProfit={unrealized_profit}, crossWalletBalance={cross_wallet_balance}")
            else:
                LOG.warning(f"   ⚠️  No USDT asset found in balance data")
        else:
            LOG.warning("⚠️  No balance data available yet; positions update will have zero wallet balance")
        
        payload = {
            'totalWalletBalance': wallet_balance,
            'totalUnrealizedProfit': unrealized_profit,
            'totalCrossWalletBalance': cross_wallet_balance,
            'positions': open_positions,
            'updateTime': int(time.time() * 1000)
        }

        self.fsm.emit(
            event_name="EVT:ACCOUNT_UPDATE_RECEIVED",
            payload=payload,
            why="Open positions data updated from Binance API."
        )
        LOG.info(f"Emitted positions update: {len(open_positions)} open positions, wallet_balance={wallet_balance}")