#!/usr/bin/env python3
"""Aurora control CLI helpers."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Dict, Optional, Sequence

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8080"


def _normalize_base_url(value: str) -> str:
    if not value:
        return DEFAULT_BASE_URL
    return value.rstrip("/")


def _print_rows(rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        print("No aggregated OCO rows found.")
        return

    header = "{:<10} {:<5} {:>12} {:>12} {:>12} {:<24} {:<20}".format(
        "SYMBOL", "SIDE", "QTY", "SL", "TP", "WATCHDOG", "BRACKET_ID"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            "{:<10} {:<5} {:>12} {:>12} {:>12} {:<24} {:<20}".format(
                row.get("symbol", "-"),
                row.get("side", "-"),
                row.get("position_qty", "-"),
                row.get("sl_price", "-"),
                row.get("tp_price", "-"),
                row.get("watchdog_status", "UNKNOWN"),
                row.get("bracket_set_id", "-"),
            )
        )


async def _cmd_agg_oco_state(args: argparse.Namespace) -> int:
    base_url = _normalize_base_url(args.base_url)
    url = f"{base_url}/debug/agg_oco_state"
    params: Dict[str, Any] = {}
    if args.symbol:
        params["symbol"] = args.symbol
    if args.side:
        params["side"] = args.side

    headers: Dict[str, str] = {}
    if args.token:
        headers["Authorization"] = args.token

    async with httpx.AsyncClient(timeout=args.timeout) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        payload = resp.json()

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_rows(payload.get("rows", []))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aurora control CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    agg_parser = subparsers.add_parser(
        "agg-oco-state", help="Fetch aggregated OCO runtime state dump"
    )
    agg_parser.add_argument("--symbol", help="Filter by symbol (optional)")
    agg_parser.add_argument(
        "--side",
        choices=["LONG", "SHORT"],
        help="Filter by side (optional)",
    )
    agg_parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Debug API base URL (default: {DEFAULT_BASE_URL})",
    )
    agg_parser.add_argument(
        "--token",
        help="Authorization token for debug endpoints (optional)",
    )
    agg_parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds (default: 10)",
    )
    agg_parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON output",
    )
    agg_parser.set_defaults(handler=_cmd_agg_oco_state)
    return parser


async def _async_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return await handler(args)


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        return asyncio.run(_async_main(argv))
    except httpx.HTTPStatusError as exc:
        print(
            f"Request failed: {exc.response.status_code} {exc.response.text}")
        return 1
    except KeyboardInterrupt:  # pragma: no cover - CLI path
        return 130


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
