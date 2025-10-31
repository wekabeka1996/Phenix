"""
Account Observer Domain.

Monitors user trades on Binance Testnet using read-only API keys
and emits EVT:TRADE_EXECUTED events for new trades.
"""

import decimal
import logging
import threading
from typing import Any, Set

try:
    from binance.client import Client
except ImportError:
    Client = None


class AccountObserver:
    """
    Account Observer component that monitors user trades on Binance Testnet.

    Uses read-only API keys to poll for recent trades and emit EVT:TRADE_EXECUTED
    events for any new trades detected.
    """

    def __init__(self, fsm: Any, config: dict[str, Any]) -> None:
        """
        Initialize Account Observer.

        Args:
            fsm: FSM core instance
            config: Configuration dict with 'binance_api' credentials
        """
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")

        if Client is None:
            raise ImportError(
                "python-binance is required. Install with: pip install python-binance")

        # Get trading mode and API config
        mode = config.get("trading_mode", "testnet")
        api_config = config.get("binance_api", {})

        # Get credentials based on mode
        env_config = {}
        if mode == "live":
            env_config = api_config.get("live", {})
        else:  # testnet or hybrid modes
            env_config = api_config.get("testnet", {})

        api_key = env_config.get("api_key")
        api_secret = env_config.get("api_secret")

        if not api_key or not api_secret:
            raise ValueError(
                f"API configuration for account observer in '{mode}' mode is incomplete")

        # Get account observer config
        account_observer_config = config.get('account_observer', {})

        # Determine testnet/mainnet based on trading mode
        # If mode is 'live' or contains 'live' → mainnet, otherwise testnet
        self.testnet = mode != "live"

        # Initialize Binance client for testnet/mainnet
        self.client = Client(api_key, api_secret, testnet=self.testnet)

        # Track processed trade IDs to avoid duplicates
        self.processed_trade_ids: Set[int] = set()

        # Polling thread
        self._polling_thread: threading.Thread | None = None
        self._stop_polling = threading.Event()

        # Polling interval (seconds) - from config
        self.poll_interval = account_observer_config.get('poll_interval', 5)

        # Symbols to monitor - from config
        self.symbols = account_observer_config.get(
            'symbols', ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'])

        # Trade limit per symbol - from config
        self.trade_limit = account_observer_config.get('trade_limit', 50)

        self.logger.info("AccountObserver initialized with testnet client")

    def start(self) -> None:
        """Start the account monitoring process."""
        if self._polling_thread is not None:
            self.logger.warning("AccountObserver already started")
            return

        self._stop_polling.clear()
        self._polling_thread = threading.Thread(
            target=self._poll_loop, daemon=True)
        self._polling_thread.start()
        self.logger.info("AccountObserver started polling for trades")

    def stop(self) -> None:
        """Stop the account monitoring process."""
        if self._polling_thread is None:
            return

        self._stop_polling.set()
        self._polling_thread.join(timeout=10)
        self.logger.info("AccountObserver stopped")

    def _poll_loop(self) -> None:
        """Main polling loop."""
        while not self._stop_polling.is_set():
            try:
                self._poll_trades()
            except Exception as e:
                self.logger.error(f"Error polling trades: {e}")

            self._stop_polling.wait(self.poll_interval)

    def _poll_trades(self) -> None:
        """Poll for recent trades and emit events for new ones."""
        try:
            # First, poll for open orders to update active orders count
            self._poll_open_orders()
            
            # Get recent trades for all configured symbols (limit to recent ones)
            # Note: For Futures API, we need to use futures-specific methods
            for symbol in self.symbols:
                try:
                    self.logger.debug(f"Polling trades for {symbol}...")

                    # Use Futures API methods for Futures trading
                    if hasattr(self.client, 'futures_account_trades'):
                        # Get account trades for the symbol
                        trades = self.client.futures_account_trades(
                            symbol=symbol, limit=self.trade_limit)
                        self.logger.info(
                            f"Retrieved {len(trades)} futures trades for {symbol}")
                        if trades:
                            self.logger.info(
                                f"Latest trade for {symbol}: ID={trades[-1].get('id', 'N/A')}, side={trades[-1].get('side', 'N/A')}, qty={trades[-1].get('qty', 'N/A')}")
                        self._process_futures_trades(trades, 'binance')
                    else:
                        # Fallback to spot API (should not happen in futures mode)
                        trades = self.client.get_my_trades(
                            symbol=symbol, limit=self.trade_limit)
                        self.logger.info(
                            f"Retrieved {len(trades)} spot trades for {symbol}")
                        self._process_trades(trades, 'binance')

                except Exception as e:
                    self.logger.error(
                        f"Error getting trades for {symbol}: {e}")

        except Exception as e:
            self.logger.error(f"Error in _poll_trades: {e}")

    def _poll_open_orders(self) -> None:
        """Poll for open orders and emit events to update active orders count."""
        try:
            # Get all open orders
            if hasattr(self.client, 'futures_get_open_orders'):
                # Futures API
                open_orders = self.client.futures_get_open_orders()
                self.logger.info(f"Retrieved {len(open_orders)} open futures orders")
            else:
                # Spot API fallback
                open_orders = self.client.get_open_orders()
                self.logger.info(f"Retrieved {len(open_orders)} open spot orders")
            
            # Emit event to update active orders count
            self.fsm.emit(
                "EVT:OPEN_ORDERS_UPDATE",
                payload={
                    "open_orders": open_orders,
                    "count": len(open_orders)
                },
                why="Update active orders count from open orders polling"
            )
            
        except Exception as e:
            self.logger.error(f"Error polling open orders: {e}")

    def _process_trades(self, trades: list[dict[str, Any]], venue: str) -> None:
        """Process list of trades and emit events for new ones."""
        import time
        
        # Only process trades from the last 10 minutes to avoid reprocessing old trades on restart
        current_time_ms = int(time.time() * 1000)
        recent_cutoff_ms = current_time_ms - (10 * 60 * 1000)  # 10 minutes ago
        
        self.logger.debug(f"Processing {len(trades)} trades from {venue}, filtering for trades after {recent_cutoff_ms}")
        
        recent_trades = [trade for trade in trades if trade['time'] > recent_cutoff_ms]
        self.logger.debug(f"Found {len(recent_trades)} recent trades to process")
        
        for trade in recent_trades:
            trade_id = trade['id']

            if trade_id in self.processed_trade_ids:
                continue  # Already processed

            # Mark as processed
            self.processed_trade_ids.add(trade_id)
            self.logger.info(
                f"Found NEW trade: ID={trade_id}, symbol={trade.get('symbol', 'N/A')}, side={'BUY' if trade.get('isBuyer') else 'SELL'}, qty={trade.get('qty', 'N/A')}, time={trade.get('time', 'N/A')}")

            # Convert Binance trade to our payload format
            payload = self._trade_to_payload(trade, venue)

            # Emit event
            self.fsm.emit(
                "EVT:TRADE_EXECUTED",
                payload=payload,
                why="Detected new user trade from Binance account."
            )

            self.logger.info(
                f"Emitted TRADE_EXECUTED for trade {trade_id}: {payload}")

    def _trade_to_payload(self, trade: dict[str, Any], venue: str) -> dict[str, Any]:
        """Convert Binance trade dict to EVT:TRADE_EXECUTED payload."""
        # Binance trade fields:
        # 'symbol', 'id', 'orderId', 'price', 'qty', 'quoteQty', 'commission', 'commissionAsset',
        # 'time', 'isBuyer', 'isMaker', 'isBestMatch'

        symbol = trade['symbol']
        side = 'buy' if trade['isBuyer'] else 'sell'
        price = str(trade['price'])  # Preserve precision as string
        # Preserve precision, handle sign
        quantity = str(
            trade['qty']) if trade['isBuyer'] else str(-decimal.Decimal(trade['qty']))
        ts = trade['time']  # Already in milliseconds
        # Preserve precision as string
        fees = str(trade.get('commission', '0.0'))

        return {
            "symbol": symbol,
            "side": side,
            "price": price,
            "quantity": quantity,
            "ts": ts,
            "fees": fees,
            "venue": venue
        }

    def _process_futures_trades(self, trades: list[dict[str, Any]], venue: str) -> None:
        """Process list of futures trades and emit events for new ones."""
        import time
        
        # Only process trades from the last 10 minutes to avoid reprocessing old trades on restart
        current_time_ms = int(time.time() * 1000)
        recent_cutoff_ms = current_time_ms - (10 * 60 * 1000)  # 10 minutes ago
        
        self.logger.debug(
            f"Processing {len(trades)} futures trades from {venue}, filtering for trades after {recent_cutoff_ms}")
        
        recent_trades = [trade for trade in trades if trade['time'] > recent_cutoff_ms]
        self.logger.debug(f"Found {len(recent_trades)} recent trades to process")
        
        for trade in recent_trades:
            trade_id = trade['id']

            if trade_id in self.processed_trade_ids:
                continue  # Already processed

            # Mark as processed
            self.processed_trade_ids.add(trade_id)
            self.logger.info(
                f"Found NEW futures trade: ID={trade_id}, symbol={trade.get('symbol', 'N/A')}, side={trade.get('side', 'N/A')}, qty={trade.get('qty', 'N/A')}, time={trade.get('time', 'N/A')}")

            # Convert Binance futures trade to our payload format
            payload = self._futures_trade_to_payload(trade, venue)

            # Emit event
            self.fsm.emit(
                "EVT:TRADE_EXECUTED",
                payload=payload,
                why="Detected new futures user trade from Binance account."
            )

            self.logger.info(
                f"Emitted EVT:TRADE_EXECUTED for futures trade {trade_id}: {payload}")

    def _futures_trade_to_payload(self, trade: dict[str, Any], venue: str) -> dict[str, Any]:
        """Convert Binance futures trade dict to EVT:TRADE_EXECUTED payload."""
        # Futures trade fields:
        # 'symbol', 'id', 'orderId', 'side', 'price', 'qty', 'realizedPnl', 'marginAsset',
        # 'quoteQty', 'commission', 'commissionAsset', 'time', 'buyer', 'maker'

        symbol = trade['symbol']
        side = trade['side'].lower()  # BUY or SELL
        price = str(trade['price'])  # Preserve precision as string
        # Preserve precision, handle sign
        quantity = str(
            trade['qty']) if side == 'buy' else str(-float(trade['qty']))
        ts = trade['time']  # Already in milliseconds
        # Preserve precision as string
        fees = str(trade.get('commission', '0.0'))

        return {
            "symbol": symbol,
            "side": side,
            "price": price,
            "quantity": quantity,
            "ts": ts,
            "fees": fees,
            "venue": venue
        }
