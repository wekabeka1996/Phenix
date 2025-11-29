"""
Account Observer Domain.

Monitors user trades on Binance Testnet using read-only API keys
and emits EVT:TRADE_EXECUTED events for new trades.
"""

import decimal
import logging
import threading
from typing import Any, Set, Optional, Literal

try:
    from binance.client import Client
except ImportError:
    Client = None

from vfoundation.obs.correlation import CorrelationStore


class AccountObserver:
    """
    Account Observer component that monitors user trades on Binance Testnet.

    Uses read-only API keys to poll for recent trades and emit EVT:TRADE_EXECUTED
    events for any new trades detected.
    """

    def __init__(
        self,
        fsm: Any,
        config: dict[str, Any],
        environment: Optional[Literal["live", "testnet"]
                              ] = None,  # NEW PARAMETER
    ) -> None:
        """
        Initialize Account Observer.

        Args:
            fsm: FSM core instance
            config: Configuration dict with 'binance_api' credentials
            environment: Explicitly set the environment ('live' or 'testnet').
                         If None, it defaults to config's trading_mode.
        """
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")

        if Client is None:
            raise ImportError(
                "python-binance is required. Install with: pip install python-binance"
            )

        # Get trading mode and API config
        # Use explicit environment if provided, otherwise fall back to config's trading_mode
        resolved_environment = environment
        if resolved_environment is None:
            # Check for resolved risk_portfolio_source first (FSMP-P3-T01)
            # TODO: This might need special handling in Pydantic model
            resolved_portfolio_source = getattr(self.config, '_resolved', {}).get(
                'risk_portfolio_source') if hasattr(self.config, '_resolved') else None
            if resolved_portfolio_source:
                resolved_environment = resolved_portfolio_source
            else:
                # Handle both dict and Pydantic object access
                resolved_environment = (
                    self.config.get("trading_mode", "testnet")
                    if isinstance(self.config, dict)
                    else self.config.trading_mode
                )

        # Handle both dict and Pydantic object access for binance_api
        api_config = (
            self.config.get("binance_api", {})
            if isinstance(self.config, dict)
            else self.config.binance_api
        )

        # Get credentials based on resolved_environment
        env_config = {}
        if resolved_environment == "live":
            if isinstance(api_config, dict):
                env_config = api_config.get("live", {})
            else:
                env_config = api_config.live
        else:  # testnet or hybrid modes
            if isinstance(api_config, dict):
                env_config = api_config.get("testnet", {})
            else:
                env_config = api_config.testnet

        # Extract API credentials
        if isinstance(env_config, dict):
            api_key = env_config.get("api_key", "")
            api_secret = env_config.get("api_secret", "")
        else:
            api_key = getattr(env_config, "api_key", "")
            api_secret = getattr(env_config, "api_secret", "")

        if not api_key or not api_secret:
            raise ValueError(
                f"API configuration for account observer in '{resolved_environment}' mode is incomplete"
            )

        # Get account observer config
        account_observer_config = (
            self.config.get("account_observer", {})
            if isinstance(self.config, dict)
            else self.config.account_observer
        )

        # Determine testnet/mainnet based on resolved_environment
        self.testnet = resolved_environment != "live"

        # Initialize Binance client for testnet/mainnet
        self.client = Client(api_key, api_secret, testnet=self.testnet)

        # Track processed trade IDs to avoid duplicates
        self.processed_trade_ids: Set[int] = set()

        # Polling thread
        self._polling_thread: threading.Thread | None = None
        self._stop_polling = threading.Event()

        self.correlation_store = CorrelationStore()

        # Polling interval (seconds) - from domains config first, then account_observer config
        poll_interval = 5  # default
        try:
            # Try domains config first
            if hasattr(self.config, 'domains') and hasattr(self.config.domains, 'account_observer'):
                poll_interval = self.config.domains.account_observer.poll_interval_sec
            # Fallback to legacy account_observer config
            elif isinstance(account_observer_config, dict):
                poll_interval = account_observer_config.get("poll_interval", 5)
            else:
                poll_interval = getattr(account_observer_config, "poll_interval", 5)
        except (AttributeError, TypeError):
            pass  # Use default
        self.poll_interval = poll_interval

        # Symbols to monitor - domains config > account_observer config > trading.symbols_to_track
        explicit_symbols = []
        try:
            # Try domains config first
            if hasattr(self.config, 'domains') and hasattr(self.config.domains, 'account_observer'):
                explicit_symbols = self.config.domains.account_observer.symbols
            # Fallback to legacy account_observer config
            elif isinstance(account_observer_config, dict):
                explicit_symbols = account_observer_config.get("symbols", [])
            else:
                explicit_symbols = getattr(account_observer_config, "symbols", [])
        except (AttributeError, TypeError):
            pass  # Will use trading.symbols_to_track as fallback

        if explicit_symbols:
            self.symbols = explicit_symbols
        else:
            # Dynamically use symbols_to_track from trading config
            trading_config = (
                self.config.get("trading", {})
                if isinstance(self.config, dict)
                else self.config.trading
            )
            default_symbols = ["BTCUSDT", "ETHUSDT"]
            if isinstance(trading_config, dict):
                self.symbols = trading_config.get(
                    "symbols_to_track", default_symbols)
            else:
                self.symbols = getattr(
                    trading_config, 'symbols_to_track', default_symbols)

            self.logger.info(
                f"AccountObserver using dynamic symbols_to_track: {self.symbols}")

        # Trade limit per symbol - from config
        if isinstance(account_observer_config, dict):
            trade_limit = account_observer_config.get("trade_limit", 10)
        else:
            trade_limit = getattr(account_observer_config, "trade_limit", 10)
        self.trade_limit = trade_limit

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
            # Get recent trades for all configured symbols (limit to recent ones)
            # Note: get_my_trades requires symbol, so we need to check configured symbols
            for symbol in self.symbols:
                try:
                    trades = self.client.get_my_trades(
                        symbol=symbol, limit=self.trade_limit
                    )
                    self._process_trades(trades, "binance")
                except Exception as e:
                    self.logger.debug(
                        f"Error getting trades for {symbol}: {e}")

        except Exception as e:
            self.logger.error(f"Error in _poll_trades: {e}")

    def _process_trades(self, trades: list[dict[str, Any]], venue: str) -> None:
        """Process list of trades and emit events for new ones."""
        for trade in trades:
            trade_id = trade["id"]

            if trade_id in self.processed_trade_ids:
                continue  # Already processed

            # Mark as processed
            self.processed_trade_ids.add(trade_id)

            # Convert Binance trade to our payload format
            payload = self._trade_to_payload(trade, venue)

            # Correlation lookup
            order_id = str(trade["orderId"])
            corr_data = self.correlation_store.get_by_order_id(order_id)
            if corr_data:
                payload["corr_id"] = corr_data["corr_id"]
                payload["link_fill_id"] = order_id
                payload["oco_group_id"] = corr_data.get("oco_group_id")
                payload["parent_client_order_id"] = corr_data.get(
                    "parent_client_order_id")

            # Emit event
            self.fsm.emit(
                "EVT:FILL",
                payload=payload,
                why="Detected new user fill from Binance account.",
            )

            # Log with correlation
            corr_id_log = payload.get("corr_id", "unknown")
            self.logger.info(
                f"ORDER_STATE_CHANGED: FILL for order_id={order_id}, "
                f"corr_id={corr_id_log}, symbol={payload['symbol']}, "
                f"side={payload['side']}, qty={payload['quantity']}, "
                f"price={payload['price']}"
            )

            self.logger.info(
                f"Emitted EVT:FILL for trade {trade_id}: {payload}")

    def _trade_to_payload(self, trade: dict[str, Any], venue: str) -> dict[str, Any]:
        """Convert Binance trade dict to EVT:TRADE_EXECUTED payload."""
        # Binance trade fields:
        # 'symbol', 'id', 'orderId', 'price', 'qty', 'quoteQty', 'commission', 'commissionAsset',
        # 'time', 'isBuyer', 'isMaker', 'isBestMatch'

        symbol = trade["symbol"]
        side = "buy" if trade["isBuyer"] else "sell"
        price = str(trade["price"])  # Preserve precision as string
        quantity = (
            str(trade["qty"])
            if trade["isBuyer"]
            else str(-decimal.Decimal(trade["qty"]))
        )  # Preserve precision, handle sign
        ts = trade["time"]  # Already in milliseconds
        # Preserve precision as string
        fees = str(trade.get("commission", "0.0"))

        return {
            "symbol": symbol,
            "side": side,
            "price": price,
            "quantity": quantity,
            "ts": ts,
            "fees": fees,
            "venue": venue,
        }
