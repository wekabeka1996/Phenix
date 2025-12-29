"""
Place TP/SL (closePosition) orders on Binance testnet for all open positions.

Prereqs:
- .env contains BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET (or BINANCE_API_KEY / BINANCE_API_SECRET).
- Positions already open on testnet.

Usage:
    python scripts/manual_place_brackets_testnet.py

Safety:
- Uses closePosition=true, no explicit quantity.
- Prices are derived from current mark price with +/-1% offsets (adjust as needed).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

# Ensure project root is on sys.path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.reference.adapters.binance_adapter import BinanceAdapter
from apps.reference.domains.execution_position.shadow_execpos.execution_service import ExecutionService


def load_env(path: Path = Path(".env")) -> None:
    """Load a minimal .env (key=value) without extra deps."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k and v and k not in os.environ:
            os.environ[k.strip()] = v.strip()


async def cancel_existing_brackets(exec_service: ExecutionService, symbol: str) -> None:
    """Cancel existing closePosition SL/TP to avoid duplicates."""
    adapter = exec_service.adapter
    try:
        open_orders = await adapter.get_open_orders(symbol)
    except Exception as e:
        print(f"Failed to fetch open orders for {symbol}: {e}")
        return

    bracket_orders = [
        o for o in open_orders
        if getattr(o, "order_type", "") in ("STOP_MARKET", "TAKE_PROFIT_MARKET")
        and getattr(o, "close_position", False)
    ]
    if not bracket_orders:
        return

    for o in bracket_orders:
        try:
            res = await exec_service.cancel_order(
                symbol=o.symbol,
                order_id=o.order_id,
                client_order_id=o.client_order_id,
            )
            print(f"  Cancel {o.symbol} {o.order_type} id={o.order_id} res={res}")
        except Exception as e:
            print(f"  Failed cancel {o.symbol} id={o.order_id}: {e}")


async def place_brackets_for_positions() -> None:
    load_env()

    api_key = (
        os.environ.get("BINANCE_TESTNET_API_KEY")
        or os.environ.get("BINANCE_API_KEY")
    )
    api_secret = (
        os.environ.get("BINANCE_TESTNET_API_SECRET")
        or os.environ.get("BINANCE_API_SECRET")
    )

    if not api_key or not api_secret:
        print("❌ API keys not found in env (.env: BINANCE_TESTNET_API_KEY/SECRET).")
        return

    adapter = BinanceAdapter(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://testnet.binancefuture.com",
        shadow_mode=False,
    )
    exec_service = ExecutionService(adapter)

    print("Fetching open positions...")
    positions = await adapter.get_open_positions()
    if not positions:
        print("No open positions found.")
        return

    for pos in positions:
        try:
            amt = float(pos.position_amount)
        except Exception:
            continue

        if abs(amt) < 1e-9:
            continue

        symbol = pos.symbol
        side_open = "LONG" if amt > 0 else "SHORT"
        exit_side = "SELL" if side_open == "LONG" else "BUY"

        mark = await adapter.get_mark_price(symbol)
        # Simple 1% offsets; adjust if needed.
        sl_price = mark * (0.99 if side_open == "LONG" else 1.01)
        tp_price = mark * (1.01 if side_open == "LONG" else 0.99)

        print(f"{symbol} {side_open} amt={amt} mark={mark:.4f} SL@{sl_price:.4f} TP@{tp_price:.4f}")

        # Cancel existing closePosition SL/TP to prevent duplicates
        await cancel_existing_brackets(exec_service, symbol)

        # PLACE SL
        sl_res = await exec_service.place_order(
            symbol=symbol,
            side=exit_side,
            order_type="STOP_MARKET",
            quantity=None,  # closePosition=true -> no qty
            stop_price=str(sl_price),
            client_order_id=None,
            reduce_only=False,
            close_position=True,
        )
        print(f"  SL result: {sl_res}")

        # PLACE TP
        tp_res = await exec_service.place_order(
            symbol=symbol,
            side=exit_side,
            order_type="TAKE_PROFIT_MARKET",
            quantity=None,
            stop_price=str(tp_price),
            client_order_id=None,
            reduce_only=False,
            close_position=True,
        )
        print(f"  TP result: {tp_res}")


if __name__ == "__main__":
    asyncio.run(place_brackets_for_positions())
