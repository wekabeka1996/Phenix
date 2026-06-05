#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from apps.reference.adapters.binance_adapter import BinanceAdapter
from apps.reference.config_loader import get_config
from apps.reference.domains.execution_position.utils import generate_client_order_id
from vfoundation.core.adapters.base import ExchangeOrderParams


LOG = logging.getLogger("close_all_positions")
_ALLOWED_POSITION_SIDES = frozenset({"BOTH", "LONG", "SHORT"})


@dataclass(frozen=True)
class CloseTarget:
    symbol: str
    position_side: str
    close_side: str
    quantity: str


@dataclass
class FlattenSummary:
    initial_targets: list[CloseTarget] = field(default_factory=list)
    refreshed_targets: list[CloseTarget] = field(default_factory=list)
    cancelled_orders: int = 0
    submitted_closes: int = 0
    cancel_failures: list[str] = field(default_factory=list)
    close_failures: list[str] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return bool(self.cancel_failures or self.close_failures)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Close all non-zero Binance Futures positions via reduce-only MARKET orders."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("config", "testnet", "live"),
        default="config",
        help=(
            "Execution environment. 'config' resolves from Aurora config trading_mode "
            "and fails closed when the mapping is ambiguous."
        ),
    )
    parser.add_argument(
        "--symbol",
        action="append",
        default=[],
        help="Optional symbol filter. Repeat to close only selected symbols.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be cancelled/closed without sending exchange writes.",
    )
    parser.add_argument(
        "--keep-open-orders",
        action="store_true",
        help=(
            "Do not cancel open orders for symbols being flattened before submitting "
            "reduce-only closes."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def _normalize_symbol_filter(symbols: Sequence[str]) -> set[str]:
    return {
        str(symbol).strip().upper()
        for symbol in symbols
        if str(symbol).strip()
    }


def _to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    raise TypeError(f"Unsupported exchange payload type: {type(obj)!r}")


def _format_abs_decimal(value: Decimal) -> str:
    normalized = value.copy_abs().normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def resolve_effective_mode(config: Any, requested_mode: str) -> str:
    requested = str(requested_mode or "config").strip().lower()
    if requested in {"testnet", "live"}:
        return requested

    config_mode = str(getattr(config, "trading_mode", "") or "").strip().lower()
    if config_mode in {"live", "production"}:
        return "live"
    if config_mode in {"testnet", "hybrid_live_data_testnet_exec", "hybrid"}:
        return "testnet"
    if "testnet" in config_mode:
        return "testnet"

    raise ValueError(
        "Config trading_mode cannot be mapped safely to an exchange environment. "
        "Pass explicit --mode testnet or --mode live."
    )


def _resolve_api_credentials(config: Any, mode: str) -> tuple[str, str, str]:
    api_env = config.binance_api.live if mode == "live" else config.binance_api.testnet

    api_key = str(getattr(api_env, "api_key", "") or "").strip()
    api_secret = str(getattr(api_env, "api_secret", "") or "").strip()
    rest_url = str(
        getattr(api_env, "rest_url", None)
        or getattr(api_env, "base_url", None)
        or ""
    ).strip()

    if not api_key or not api_secret or not rest_url:
        raise ValueError(
            f"Incomplete Binance API config for mode={mode}: api_key/api_secret/rest_url are required."
        )

    return api_key, api_secret, rest_url


def collect_close_targets(
    positions: Iterable[Any],
    symbol_filter: set[str] | None = None,
) -> list[CloseTarget]:
    targets: list[CloseTarget] = []

    for raw_position in positions:
        position = _to_dict(raw_position)
        symbol = str(position.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        if symbol_filter and symbol not in symbol_filter:
            continue

        amount_raw = position.get("positionAmt")
        if amount_raw is None:
            amount_raw = position.get("position_amount")

        try:
            amount = Decimal(str(amount_raw or "0"))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid position amount for {symbol}: {amount_raw!r}") from exc

        if amount == 0:
            continue

        position_side = str(
            position.get("positionSide") or position.get("position_side") or "BOTH"
        ).strip().upper()
        if position_side not in _ALLOWED_POSITION_SIDES:
            raise ValueError(
                f"Unsupported positionSide for {symbol}: {position_side!r}"
            )

        close_side = "SELL" if amount > 0 else "BUY"
        targets.append(
            CloseTarget(
                symbol=symbol,
                position_side=position_side,
                close_side=close_side,
                quantity=_format_abs_decimal(amount),
            )
        )

    targets.sort(key=lambda item: (item.symbol, item.position_side))
    return targets


async def cancel_orders_for_symbols(
    adapter: BinanceAdapter,
    symbols: Iterable[str],
    *,
    dry_run: bool,
) -> tuple[int, list[str]]:
    cancelled_orders = 0
    failures: list[str] = []

    for symbol in sorted({str(item).strip().upper() for item in symbols if str(item).strip()}):
        open_orders = await adapter.get_open_orders(symbol)
        for raw_order in open_orders:
            order = _to_dict(raw_order)
            order_id = str(order.get("orderId") or order.get("order_id") or "").strip() or None
            client_order_id = str(
                order.get("clientOrderId") or order.get("client_order_id") or ""
            ).strip() or None

            if not order_id and not client_order_id:
                message = f"{symbol}: open order missing order_id and client_order_id"
                failures.append(message)
                LOG.error(message)
                continue

            order_ref = order_id or client_order_id or "unknown"

            if dry_run:
                LOG.info("[DRY-RUN] Would cancel open order %s on %s", order_ref, symbol)
                cancelled_orders += 1
                continue

            try:
                await adapter.cancel_order(
                    symbol=symbol,
                    order_id=order_id,
                    client_order_id=None if order_id else client_order_id,
                )
                cancelled_orders += 1
                LOG.info("Cancelled open order %s on %s", order_ref, symbol)
            except Exception as exc:
                message = f"{symbol}: failed to cancel order {order_ref}: {exc}"
                failures.append(message)
                LOG.error(message)

    return cancelled_orders, failures


def _client_order_id_for_target(target: CloseTarget) -> str:
    return generate_client_order_id(
        "CLOSE",
        target.symbol,
        idempotent_key=(
            f"close-all:{target.symbol}:{target.position_side}:"
            f"{target.close_side}:{target.quantity}"
        ),
    )


async def submit_close_targets(
    adapter: BinanceAdapter,
    targets: Sequence[CloseTarget],
    *,
    dry_run: bool,
) -> tuple[int, list[str]]:
    submitted_closes = 0
    failures: list[str] = []

    for target in targets:
        client_order_id = _client_order_id_for_target(target)

        if dry_run:
            LOG.info(
                "[DRY-RUN] Would close %s positionSide=%s side=%s qty=%s clientOrderId=%s",
                target.symbol,
                target.position_side,
                target.close_side,
                target.quantity,
                client_order_id,
            )
            submitted_closes += 1
            continue

        try:
            if target.position_side == "BOTH":
                response = await adapter.place_market_reduce_only(
                    target.symbol,
                    target.close_side,
                    target.quantity,
                    new_client_order_id=client_order_id,
                )
            else:
                quantized_qty = await adapter.quantize_quantity(target.symbol, target.quantity)
                response = await adapter.create_order(
                    ExchangeOrderParams(
                        symbol=target.symbol,
                        side=target.close_side,
                        order_type="MARKET",
                        quantity=quantized_qty,
                        time_in_force="",
                        reduce_only=True,
                        client_order_id=client_order_id,
                        position_side=target.position_side,
                    )
                )

            response_dict = _to_dict(response)
            response_ref = (
                response_dict.get("orderId")
                or response_dict.get("clientOrderId")
                or client_order_id
            )
            submitted_closes += 1
            LOG.info(
                "Submitted reduce-only MARKET close for %s positionSide=%s side=%s qty=%s ref=%s",
                target.symbol,
                target.position_side,
                target.close_side,
                target.quantity,
                response_ref,
            )
        except Exception as exc:
            message = (
                f"{target.symbol}/{target.position_side}: failed to submit reduce-only close "
                f"side={target.close_side} qty={target.quantity}: {exc}"
            )
            failures.append(message)
            LOG.error(message)

    return submitted_closes, failures


async def flatten_positions(
    adapter: BinanceAdapter,
    *,
    symbol_filter: set[str] | None = None,
    cancel_open_orders: bool = True,
    dry_run: bool = False,
) -> FlattenSummary:
    summary = FlattenSummary()

    initial_positions = await adapter.get_open_positions()
    summary.initial_targets = collect_close_targets(initial_positions, symbol_filter)
    if not summary.initial_targets:
        return summary

    for target in summary.initial_targets:
        LOG.info(
            "Detected open position %s positionSide=%s closeSide=%s qty=%s",
            target.symbol,
            target.position_side,
            target.close_side,
            target.quantity,
        )

    if cancel_open_orders:
        summary.cancelled_orders, summary.cancel_failures = await cancel_orders_for_symbols(
            adapter,
            {target.symbol for target in summary.initial_targets},
            dry_run=dry_run,
        )

    refreshed_positions = await adapter.get_open_positions()
    summary.refreshed_targets = collect_close_targets(refreshed_positions, symbol_filter)
    if not summary.refreshed_targets:
        LOG.info("No non-zero positions remain after refresh; nothing to close.")
        return summary

    summary.submitted_closes, summary.close_failures = await submit_close_targets(
        adapter,
        summary.refreshed_targets,
        dry_run=dry_run,
    )
    return summary


async def _async_main(args: argparse.Namespace) -> int:
    config = get_config()
    effective_mode = resolve_effective_mode(config, args.mode)
    api_key, api_secret, rest_url = _resolve_api_credentials(config, effective_mode)
    symbol_filter = _normalize_symbol_filter(args.symbol)

    LOG.info(
        "Starting close_all_positions mode=%s dry_run=%s cancel_open_orders=%s symbols=%s",
        effective_mode,
        args.dry_run,
        not args.keep_open_orders,
        sorted(symbol_filter) if symbol_filter else "ALL",
    )
    LOG.info("Using Binance REST URL: %s", rest_url)

    async with BinanceAdapter(
        api_key=api_key,
        api_secret=api_secret,
        rest_url=rest_url,
    ) as adapter:
        summary = await flatten_positions(
            adapter,
            symbol_filter=symbol_filter or None,
            cancel_open_orders=not args.keep_open_orders,
            dry_run=args.dry_run,
        )

    if not summary.initial_targets:
        LOG.info("No open positions matched the current filter.")
        return 0

    LOG.info(
        "Summary: initial_targets=%d refreshed_targets=%d cancelled_orders=%d submitted_closes=%d",
        len(summary.initial_targets),
        len(summary.refreshed_targets),
        summary.cancelled_orders,
        summary.submitted_closes,
    )

    if summary.cancel_failures:
        for failure in summary.cancel_failures:
            LOG.error("Cancel failure: %s", failure)
    if summary.close_failures:
        for failure in summary.close_failures:
            LOG.error("Close failure: %s", failure)

    if summary.has_failures:
        return 1
    return 0


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)

    try:
        return asyncio.run(_async_main(args))
    except KeyboardInterrupt:
        LOG.error("Interrupted by user.")
        return 130
    except Exception as exc:
        LOG.error("close_all_positions failed: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())