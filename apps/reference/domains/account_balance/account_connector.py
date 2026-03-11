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
from apps.reference.config_contract import ConfigContractError
from apps.reference.config_loader import AuroraConfig

if TYPE_CHECKING:
    from vfoundation.core import FSMCore

LOG = logging.getLogger(__name__)

_MIN_UPDATE_INTERVAL_SEC = 5


def _dget(d: Dict[str, Any], key: str, default: Any) -> Any:
    """Defaulting dict access without using the default-arg form of `dict.get` (TASK25 policy)."""
    return d[key] if key in d else default


class AccountConnector:
    """
    Connects to Binance REST API via BinanceAdapter to retrieve account data.
    """

    def __init__(self, fsm: "FSMCore", config: AuroraConfig) -> None:
        """
        Initialize connector.

        Args:
            fsm: FSM core instance for event emission.
            config: AuroraConfig (strict object config).
        """
        self.fsm = fsm
        if isinstance(config, dict):
            raise TypeError("AccountConnector requires AuroraConfig, got dict")
        self.config = config
        self.thread: Optional[threading.Thread] = None
        self.running = False

        self.update_interval = self._resolve_update_interval_sec(config)

        # Initialize the BinanceAdapter based on the trading_mode
        mode = str(self.config.trading_mode)
        api_config = self.config.binance_api

        if mode == "live":
            env_config = api_config.live
            LOG.info(
                "AccountConnector is configured for LIVE execution environment.")
        else:  # testnet or hybrid
            env_config = api_config.testnet
            LOG.info(
                f"AccountConnector is configured for TESTNET execution environment (mode: {mode})."
            )

        # Extract API credentials from env_config
        api_key = env_config.api_key
        api_secret = env_config.api_secret
        rest_url = env_config.rest_url
        if not api_key or not api_secret or not rest_url:
            raise ConfigContractError(
                path=f"binance_api.{mode}",
                why="API configuration incomplete (api_key, api_secret, rest_url required).",
            )

        self.adapter = BinanceAdapter(
            api_key=api_key,
            api_secret=api_secret,
            rest_url=rest_url,
        )

        # Store latest balance data from /fapi/v2/balance endpoint
        self._latest_balance_data: Optional[List[Dict[str, Any]]] = None

    @staticmethod
    def _clamp_update_interval(value: Any) -> int:
        try:
            interval = int(float(value))
        except Exception as exc:
            raise ConfigContractError(
                path="trading.market_data.poll_interval_sec",
                why=f"Invalid account polling interval: {value!r}",
            ) from exc
        return max(_MIN_UPDATE_INTERVAL_SEC, interval)

    @classmethod
    def _resolve_update_interval_sec(cls, config: Any) -> int:
        trading = getattr(config, "trading", None)
        market_data = getattr(trading, "market_data",
                              None) if trading is not None else None
        poll_interval_sec = getattr(
            market_data, "poll_interval_sec", None) if market_data is not None else None
        if poll_interval_sec is not None:
            return cls._clamp_update_interval(poll_interval_sec)

        if isinstance(config, AuroraConfig):
            raise ConfigContractError(
                path="trading.market_data.poll_interval_sec",
                why="Missing required poll interval for account_balance polling.",
            )

        account_balance_cfg = getattr(config, "account_balance", None)
        if isinstance(account_balance_cfg, dict) and "poll_interval_seconds" in account_balance_cfg:
            return cls._clamp_update_interval(account_balance_cfg["poll_interval_seconds"])
        poll_interval_seconds = getattr(
            account_balance_cfg, "poll_interval_seconds", None)
        if poll_interval_seconds is not None:
            return cls._clamp_update_interval(poll_interval_seconds)

        legacy_observer_cfg = getattr(config, "account_observer", None)
        legacy_poll_interval = getattr(
            legacy_observer_cfg, "poll_interval", None)
        if legacy_poll_interval is not None:
            return cls._clamp_update_interval(legacy_poll_interval)

        raise ConfigContractError(
            path="trading.market_data.poll_interval_sec",
            why="Missing required poll interval for account_balance polling.",
        )

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
                            f"   💰 USDT balance: {_dget(usdt_asset, 'balance', 'N/A')}")
                        LOG.info(
                            f"   📊 USDT crossWalletBalance: {_dget(usdt_asset, 'crossWalletBalance', 'N/A')}")
                        LOG.info(
                            f"   📈 USDT crossUnPnl: {_dget(usdt_asset, 'crossUnPnl', 'N/A')}")
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
                        float(_dget(p, "position_amount", _dget(p, "positionAmt", 0)))) > 0.0001)
                    LOG.info(
                        f"✅ Fetched positions: {non_zero} non-zero out of {len(positions_list)} total")
                    # Log each non-zero position
                    for pos in positions_list:
                        amt = float(_dget(pos, "position_amount",
                                    _dget(pos, "positionAmt", 0)))
                        if abs(amt) > 0.0001:
                            LOG.info(
                                f"   📊 {pos.get('symbol')}: {amt} @ "
                                f"{_dget(pos, 'entry_price', _dget(pos, 'entryPrice', 'N/A'))}")

                    # 🔴 DIAGNOSTIC: Check for divergence (API empty but internal has data)
                    if api_position_count == 0:
                        LOG.info(
                            "ℹ️ API returned EMPTY positions list (no open positions on exchange).")
                        LOG.debug(
                            "   → System will clear internal position state.")

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
                "balance": str(decimal.Decimal(_dget(asset, "balance", "0"))),
                "crossUnPnl": str(decimal.Decimal(_dget(asset, "crossUnPnl", "0"))),
                "crossWalletBalance": str(
                    decimal.Decimal(_dget(asset, "crossWalletBalance", "0"))
                ),
                "updateTime": _dget(asset, "updateTime", 0),
            }
            for asset in balance_data
            if decimal.Decimal(_dget(asset, "balance", "0")) > 0
        ]

        if not assets:
            return

        payload = {
            "assets": assets,
            "updateTime": max(
                ((asset["updateTime"] if "updateTime" in asset else 0) for asset in assets), default=0
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

        open_positions: List[Dict[str, Any]] = []
        for pos in positions_data:
            position_amt_raw = (
                pos["position_amount"]
                if "position_amount" in pos
                else (pos["positionAmt"] if "positionAmt" in pos else "0")
            )
            if decimal.Decimal(position_amt_raw) == 0:
                continue

            entry_price_raw = (
                pos["entry_price"]
                if "entry_price" in pos
                else (pos["entryPrice"] if "entryPrice" in pos else "0")
            )
            unrealized_pnl_raw = (
                pos["unrealized_pnl"]
                if "unrealized_pnl" in pos
                else (pos["unRealizedProfit"] if "unRealizedProfit" in pos else "0")
            )
            mark_price_raw = (
                pos["mark_price"]
                if "mark_price" in pos
                else (pos["markPrice"] if "markPrice" in pos else "0")
            )
            liquidation_price_raw = (
                pos["liquidation_price"]
                if "liquidation_price" in pos
                else (pos["liquidationPrice"] if "liquidationPrice" in pos else "0")
            )

            open_positions.append(
                {
                    "symbol": pos["symbol"],
                    "positionAmt": str(decimal.Decimal(position_amt_raw)),
                    "entryPrice": str(decimal.Decimal(entry_price_raw)),
                    "unRealizedProfit": str(decimal.Decimal(unrealized_pnl_raw)),
                    "leverage": int(_dget(pos, "leverage", 1)),
                    "marginType": _dget(pos, "marginType", "cross"),
                    "markPrice": str(decimal.Decimal(mark_price_raw)),
                    "liquidationPrice": str(decimal.Decimal(liquidation_price_raw)),
                }
            )

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
                    _dget(usdt_asset, "balance", "0")))
                unrealized_profit = str(
                    decimal.Decimal(_dget(usdt_asset, "crossUnPnl", "0"))
                )
                # crossWalletBalance = balance - unrealizedProfit (approximately)
                cross_wallet_balance = str(
                    decimal.Decimal(
                        _dget(usdt_asset, "crossWalletBalance", "0"))
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
