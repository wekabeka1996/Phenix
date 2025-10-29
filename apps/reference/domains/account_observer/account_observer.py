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
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        if Client is None:
            raise ImportError("python-binance is required. Install with: pip install python-binance")

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
            raise ValueError(f"API configuration for account observer in '{mode}' mode is incomplete")

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
        self.symbols = account_observer_config.get('symbols', ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'])

        # Trade limit per symbol - from config
        self.trade_limit = account_observer_config.get('trade_limit', 50)

        self.logger.info("AccountObserver initialized with testnet client")

    def start(self) -> None:
        """Start the account monitoring process."""
        if self._polling_thread is not None:
            self.logger.warning("AccountObserver already started")
            return

        self._stop_polling.clear()
        self._polling_thread = threading.Thread(target=self._poll_loop, daemon=True)
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
            # Get recent trades for all configured symbols (limit to recent ones)
            # Note: get_my_trades requires symbol, so we need to check configured symbols
            for symbol in self.symbols:
                try:
                    trades = self.client.get_my_trades(symbol=symbol, limit=self.trade_limit)
                    self._process_trades(trades, 'binance')
                except Exception as e:
                    self.logger.debug(f"Error getting trades for {symbol}: {e}")

        except Exception as e:
            self.logger.error(f"Error in _poll_trades: {e}")

    def _process_trades(self, trades: list[dict[str, Any]], venue: str) -> None:
        """Process list of trades and emit events for new ones."""
        for trade in trades:
            trade_id = trade['id']

            if trade_id in self.processed_trade_ids:
                continue  # Already processed

            # Mark as processed
            self.processed_trade_ids.add(trade_id)

            # Convert Binance trade to our payload format
            payload = self._trade_to_payload(trade, venue)

            # Emit event
            self.fsm.emit(
                "EVT:TRADE_EXECUTED",
                payload=payload,
                why="Detected new user trade from Binance account."
            )

            self.logger.info(f"Emitted TRADE_EXECUTED for trade {trade_id}: {payload}")

    def _trade_to_payload(self, trade: dict[str, Any], venue: str) -> dict[str, Any]:
        """Convert Binance trade dict to EVT:TRADE_EXECUTED payload."""
        # Binance trade fields:
        # 'symbol', 'id', 'orderId', 'price', 'qty', 'quoteQty', 'commission', 'commissionAsset',
        # 'time', 'isBuyer', 'isMaker', 'isBestMatch'

        symbol = trade['symbol']
        side = 'buy' if trade['isBuyer'] else 'sell'
        price = str(trade['price'])  # Preserve precision as string
        quantity = str(trade['qty']) if trade['isBuyer'] else str(-decimal.Decimal(trade['qty']))  # Preserve precision, handle sign
        ts = trade['time']  # Already in milliseconds
        fees = str(trade.get('commission', '0.0'))  # Preserve precision as string

        return {
            "symbol": symbol,
            "side": side,
            "price": price,
            "quantity": quantity,
            "ts": ts,
            "fees": fees,
            "venue": venue
        }