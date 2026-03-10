#!/usr/bin/env python3
"""Fetch Binance USDT-M Futures TESTNET transaction history and save as Markdown.

What it does (minimal, focused):
- Loads secrets from project `.env` (no secrets printed).
- Pulls FUTURES income history (no symbol required).
- Pulls FUTURES user trades for a list of symbols.
- Optionally pulls FUTURES order history for a list of symbols.
- Writes a single Markdown report.

Env vars used (preferred):
- TRADING_MODE=testnet   (or USE_TESTNET=true)
- BINANCE_TESTNET_API_KEY / BINANCE_TESTNET_API_SECRET
- BINANCE_FUTURES_BASE_URL_TESTNET (default: https://testnet.binancefuture.com)
- SANDBOX_BRIDGE_SYMBOLS (fallback symbol list)

Usage:
  python scripts/fetch_binance_testnet_transactions_md.py --days 7 --out reports/testnet_tx_7d.md
  python scripts/fetch_binance_testnet_transactions_md.py --symbols BTCUSDT,ETHUSDT
    python scripts/fetch_binance_testnet_transactions_md.py --include-orders
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from urllib.parse import urlencode, quote_plus

import requests


# Ensure project imports work when running as a script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_project_dotenv() -> None:
    """Load `.env` from repo root (fail-open, since script can rely on already-set env)."""
    try:
        from apps.reference.config_loader import load_dotenv  # type: ignore

        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except Exception:
        # If python-dotenv isn't available, ConfigLoader provides a fallback.
        # If import fails entirely, we just proceed with current environment.
        return


def _is_testnet_mode() -> bool:
    trading_mode = (os.getenv("TRADING_MODE") or "").strip().lower()
    if trading_mode in ("testnet", "hybrid_testnet"):
        return True

    use_testnet = (os.getenv("USE_TESTNET") or "").strip().lower()
    if use_testnet in ("1", "true", "yes", "y"):
        return True

    # Default to testnet for safety.
    return True


def _mask(s: str, keep: int = 6) -> str:
    if not s:
        return ""
    if len(s) <= keep:
        return "*" * len(s)
    return f"{s[:keep]}…"  # no secrets, only prefix


def _ms(ts: dt.datetime) -> int:
    return int(ts.timestamp() * 1000)


def _parse_symbols(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    parts = [p.strip().upper() for p in raw.split(",")]
    return [p for p in parts if p]


DEFAULT_TRADE_SYMBOLS = ["SOLUSDT", "DOGEUSDT", "XRPUSDT", "BTCUSDT"]


@dataclass(frozen=True)
class BinanceAuth:
    api_key: str
    api_secret: bytes


class BinanceFuturesClient:
    def __init__(self, *, base_url: str, auth: BinanceAuth, timeout_sec: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self.timeout_sec = timeout_sec

        self._time_offset_ms: int = 0
        self._last_time_sync_monotonic: float = 0.0

    def _sync_time(self, *, force: bool = False) -> None:
        """Best-effort server time sync (TTL ~2 minutes)."""
        ttl_sec = 120.0
        now_mono = time.monotonic()
        if not force and (now_mono - self._last_time_sync_monotonic) < ttl_sec:
            return

        try:
            url = f"{self.base_url}/fapi/v1/time"
            r = requests.get(url, timeout=self.timeout_sec)
            r.raise_for_status()
            data = r.json() if r.headers.get("content-type",
                                             "").startswith("application/json") else {}
            server_ms = int(data.get("serverTime"))
            local_ms = int(time.time() * 1000)
            self._time_offset_ms = server_ms - local_ms
        except Exception:
            # Fail-open (use local time)
            pass
        finally:
            self._last_time_sync_monotonic = now_mono

    @staticmethod
    def _norm_params(params: Dict[str, Any]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for k, v in params.items():
            if v is None:
                continue
            if isinstance(v, bool):
                out[str(k)] = "true" if v else "false"
            else:
                out[str(k)] = str(v)
        return out

    def _signed_params(self, params: Dict[str, Any]) -> Dict[str, str]:
        base = self._norm_params(params)
        ts = int(time.time() * 1000) + int(self._time_offset_ms)
        base["timestamp"] = str(ts)
        base.setdefault("recvWindow", "5000")

        # Sign exactly the URL-encoded query string we are going to send.
        qs = urlencode(base, doseq=True, quote_via=quote_plus)
        sig = hmac.new(self.auth.api_secret, qs.encode(
            "utf-8"), hashlib.sha256).hexdigest()
        base["signature"] = sig
        return base

    def _request(self, method: str, path: str, *, params: Dict[str, Any], signed: bool) -> Any:
        url = f"{self.base_url}{path}"
        headers = {"X-MBX-APIKEY": self.auth.api_key}

        if signed:
            self._sync_time(force=False)
            final_params = self._signed_params(params)
        else:
            final_params = self._norm_params(params)

        resp = requests.request(
            method,
            url,
            headers=headers,
            params=final_params,
            timeout=self.timeout_sec,
        )

        # Binance often returns JSON error payloads.
        ctype = resp.headers.get("content-type", "")
        if ctype.startswith("application/json"):
            data = resp.json()
        else:
            data = resp.text

        if resp.status_code >= 400:
            raise RuntimeError(
                f"HTTP {resp.status_code} {method} {path}: {data}")
        return data

    def income_history(self, *, start_ms: int, end_ms: int, limit: int = 1000) -> List[Dict[str, Any]]:
        # Binance may enforce a max time interval on some endpoints; keep windows <= 7 days.
        max_window_ms = 7 * 24 * 60 * 60 * 1000

        out: List[Dict[str, Any]] = []
        window_start = int(start_ms)
        end_ms = int(end_ms)

        while window_start <= end_ms:
            window_end = min(end_ms, window_start + max_window_ms - 1)
            cursor = window_start

            while True:
                page = self._request(
                    "GET",
                    "/fapi/v1/income",
                    params={
                        "startTime": str(cursor),
                        "endTime": str(window_end),
                        "limit": str(limit),
                    },
                    signed=True,
                )
                if not isinstance(page, list):
                    raise RuntimeError(
                        f"Unexpected income response type: {type(page).__name__}")

                if not page:
                    break

                out.extend(page)

                # Advance cursor by last event time (+1ms) to avoid loops.
                last_time = max(int(x.get("time", cursor)) for x in page)
                next_cursor = last_time + 1
                if next_cursor <= cursor:
                    break
                cursor = next_cursor

                if len(page) < limit:
                    break

            window_start = window_end + 1

        # De-dup by (tranId,time,asset,incomeType,income,symbol)
        seen: set[Tuple[Any, ...]] = set()
        dedup: List[Dict[str, Any]] = []
        for x in sorted(out, key=lambda r: int(r.get("time", 0))):
            key = (
                x.get("tranId"),
                x.get("time"),
                x.get("asset"),
                x.get("incomeType"),
                x.get("income"),
                x.get("symbol"),
            )
            if key in seen:
                continue
            seen.add(key)
            dedup.append(x)
        return dedup

    def user_trades_for_symbol(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        # Endpoint enforces max interval of 7 days (code -4165). Chunk requests.
        max_window_ms = 7 * 24 * 60 * 60 * 1000

        out: List[Dict[str, Any]] = []
        window_start = int(start_ms)
        end_ms = int(end_ms)

        while window_start <= end_ms:
            window_end = min(end_ms, window_start + max_window_ms - 1)

            # Try paginating with fromId if supported; otherwise fallback to time cursor.
            from_id: Optional[int] = None
            cursor = window_start

            while True:
                params = {
                    "symbol": symbol,
                    "startTime": str(cursor),
                    "endTime": str(window_end),
                    "limit": str(limit),
                }
                if from_id is not None:
                    params["fromId"] = str(from_id)

                try:
                    page = self._request(
                        "GET", "/fapi/v1/userTrades", params=params, signed=True)
                except RuntimeError as e:
                    msg = str(e)
                    # Some environments reject fromId; retry without it.
                    if "fromId" in msg and from_id is not None:
                        from_id = None
                        continue
                    raise

                if not isinstance(page, list):
                    raise RuntimeError(
                        f"Unexpected userTrades response type for {symbol}: {type(page).__name__}"
                    )

                if not page:
                    break

                out.extend(page)

                # Determine next cursor.
                last_time = max(int(x.get("time", cursor)) for x in page)
                last_id = None
                for x in page:
                    if "id" in x:
                        try:
                            last_id = max(last_id or 0, int(x["id"]))
                        except Exception:
                            pass

                if from_id is not None and last_id is not None:
                    next_from = last_id + 1
                    if next_from == from_id:
                        break
                    from_id = next_from
                elif last_time >= cursor:
                    next_cursor = last_time + 1
                    if next_cursor <= cursor:
                        break
                    cursor = next_cursor
                else:
                    break

                if len(page) < limit:
                    break

            window_start = window_end + 1

        # De-dup by (id, orderId, time, price, qty)
        seen: set[Tuple[Any, ...]] = set()
        dedup: List[Dict[str, Any]] = []
        for x in sorted(out, key=lambda r: int(r.get("time", 0))):
            key = (x.get("id"), x.get("orderId"), x.get(
                "time"), x.get("price"), x.get("qty"))
            if key in seen:
                continue
            seen.add(key)
            dedup.append(x)
        return dedup

    def all_orders_for_symbol(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Fetch order history (includes canceled/new/filled). Chunked to <= 7 days."""
        max_window_ms = 7 * 24 * 60 * 60 * 1000

        # Binance restricts search to recent ~90 days (code -4166). Clamp startTime.
        # Use a conservative 89-day window to avoid edge failures due to clock skew.
        max_search_ms = 89 * 24 * 60 * 60 * 1000

        out: List[Dict[str, Any]] = []
        end_ms = int(end_ms)
        start_ms = int(start_ms)
        if end_ms - start_ms > max_search_ms:
            start_ms = end_ms - max_search_ms
        window_start = start_ms

        while window_start <= end_ms:
            window_end = min(end_ms, window_start + max_window_ms - 1)
            # This endpoint doesn't support fromId; we page by moving startTime forward.
            cursor = window_start

            while True:
                page = self._request(
                    "GET",
                    "/fapi/v1/allOrders",
                    params={
                        "symbol": symbol,
                        "startTime": str(cursor),
                        "endTime": str(window_end),
                        "limit": str(limit),
                    },
                    signed=True,
                )

                if not isinstance(page, list):
                    raise RuntimeError(
                        f"Unexpected allOrders response type for {symbol}: {type(page).__name__}"
                    )
                if not page:
                    break

                out.extend(page)

                # Advance by max(updateTime, time) + 1ms
                last_time = max(
                    int(x.get("updateTime") or x.get("time") or cursor) for x in page
                )
                next_cursor = last_time + 1
                if next_cursor <= cursor:
                    break
                cursor = next_cursor

                if len(page) < limit:
                    break

            window_start = window_end + 1

        # De-dup by orderId
        seen: set[Any] = set()
        dedup: List[Dict[str, Any]] = []
        for x in sorted(out, key=lambda r: int(r.get("updateTime") or r.get("time") or 0)):
            oid = x.get("orderId")
            if oid in seen:
                continue
            seen.add(oid)
            dedup.append(x)
        return dedup


def _md_escape_cell(value: Any) -> str:
    s = "" if value is None else str(value)
    s = s.replace("\n", " ").replace("\r", " ")
    s = s.replace("|", "\\|")
    return s


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    head = "| " + " | ".join(headers) + " |\n"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |\n"
    body = "".join(
        "| " + " | ".join(_md_escape_cell(c) for c in row) + " |\n" for row in rows
    )
    return head + sep + body


def _fmt_ts_ms(ms: Any) -> str:
    try:
        n = int(ms)
    except Exception:
        return ""
    return dt.datetime.utcfromtimestamp(n / 1000).strftime("%Y-%m-%d %H:%M:%S UTC")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Binance Futures TESTNET transactions (last N days) into Markdown")
    parser.add_argument("--days", type=int, default=7,
                        help="How many days back to fetch (default: 7)")
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbols for userTrades (e.g. BTCUSDT,ETHUSDT). Defaults to SANDBOX_BRIDGE_SYMBOLS.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="reports/testnet_transactions_7d.md",
        help="Output markdown path (default: reports/testnet_transactions_7d.md)",
    )
    parser.add_argument(
        "--include-orders",
        action="store_true",
        help="Also fetch Futures order history (/fapi/v1/allOrders) for the same symbols.",
    )
    args = parser.parse_args()

    _load_project_dotenv()

    if not _is_testnet_mode():
        print("Refusing to run: TRADING_MODE/USE_TESTNET indicates non-testnet.")
        print("Set TRADING_MODE=testnet or USE_TESTNET=true to proceed.")
        return 2

    api_key = (os.getenv("BINANCE_TESTNET_API_KEY") or "").strip()
    api_secret = (os.getenv("BINANCE_TESTNET_API_SECRET") or "").strip()

    base_url = (os.getenv("BINANCE_FUTURES_BASE_URL_TESTNET")
                or "https://testnet.binancefuture.com").strip()

    if not api_key or not api_secret:
        print(
            "Missing BINANCE_TESTNET_API_KEY / BINANCE_TESTNET_API_SECRET in environment.")
        return 2

    symbols = _parse_symbols(args.symbols)
    if not symbols:
        # Explicit default per user request.
        symbols = list(DEFAULT_TRADE_SYMBOLS)

    now = dt.datetime.utcnow()
    start = now - dt.timedelta(days=max(1, int(args.days)))

    start_ms = _ms(start)
    end_ms = _ms(now)

    client = BinanceFuturesClient(
        base_url=base_url,
        auth=BinanceAuth(
            api_key=api_key, api_secret=api_secret.encode("utf-8")),
    )

    # Fetch
    print(f"Base URL: {base_url}")
    print("API key configured: YES")
    # Use ASCII to avoid Windows console encoding issues (cp1252 can't encode '→').
    print(f"Range: {_fmt_ts_ms(start_ms)} -> {_fmt_ts_ms(end_ms)}")

    income = client.income_history(start_ms=start_ms, end_ms=end_ms)

    trades: List[Dict[str, Any]] = []
    if symbols:
        for sym in symbols:
            sym_trades = client.user_trades_for_symbol(
                symbol=sym, start_ms=start_ms, end_ms=end_ms)
            trades.extend(sym_trades)
    else:
        print("No symbols provided; skipping userTrades (income history will still be exported).")

    trades_sorted = sorted(trades, key=lambda r: int(r.get("time", 0)))

    orders_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    if args.include_orders and symbols:
        for sym in symbols:
            orders_by_symbol[sym] = client.all_orders_for_symbol(
                symbol=sym, start_ms=start_ms, end_ms=end_ms)

    # Render
    out_path = (PROJECT_ROOT / args.out).resolve() if not Path(
        args.out).is_absolute() else Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("# Binance Futures TESTNET — Transaction History\n")
    lines.append(
        f"Generated: {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    lines.append(f"Base URL: `{base_url}`\n")
    lines.append(f"Range: `{_fmt_ts_ms(start_ms)}` -> `{_fmt_ts_ms(end_ms)}`\n")

    # Income section
    lines.append("## Income (fapi/v1/income)\n")
    lines.append(f"Count: **{len(income)}**\n")

    income_rows: List[List[Any]] = []
    for x in income:
        income_rows.append(
            [
                _fmt_ts_ms(x.get("time")),
                x.get("asset"),
                x.get("incomeType"),
                x.get("income"),
                x.get("symbol"),
                x.get("tranId"),
                x.get("info"),
            ]
        )

    if income_rows:
        lines.append(
            _md_table(
                ["time", "asset", "incomeType", "income",
                    "symbol", "tranId", "info"],
                income_rows,
            )
        )
    else:
        lines.append("(No income records in this period.)\n")

    # Trades section
    lines.append("\n## Trades (fapi/v1/userTrades)\n")
    lines.append(f"Symbols: `{','.join(symbols) if symbols else ''}`\n")
    lines.append(f"Count: **{len(trades_sorted)}**\n")

    trade_rows: List[List[Any]] = []
    for t in trades_sorted:
        trade_rows.append(
            [
                _fmt_ts_ms(t.get("time")),
                t.get("symbol"),
                "BUY" if bool(t.get("buyer")) else "SELL",
                t.get("qty"),
                t.get("price"),
                t.get("realizedPnl"),
                t.get("commission"),
                t.get("commissionAsset"),
                t.get("orderId"),
                t.get("id"),
            ]
        )

    if trade_rows:
        lines.append(
            _md_table(
                [
                    "time",
                    "symbol",
                    "side",
                    "qty",
                    "price",
                    "realizedPnl",
                    "commission",
                    "commissionAsset",
                    "orderId",
                    "tradeId",
                ],
                trade_rows,
            )
        )
    else:
        lines.append(
            "(No trade records in this period, or symbols list was empty.)\n")

    # Orders section (optional)
    if args.include_orders:
        lines.append("\n## Orders (fapi/v1/allOrders)\n")
        if not symbols:
            lines.append("(No symbols provided; skipping orders.)\n")
        else:
            # Summary counts per symbol/status
            summary_rows: List[List[Any]] = []
            for sym in symbols:
                orders = orders_by_symbol.get(sym, [])
                statuses: Dict[str, int] = {}
                filled = 0
                for o in orders:
                    st = str(o.get("status", ""))
                    statuses[st] = statuses.get(st, 0) + 1
                    if st == "FILLED":
                        filled += 1
                summary_rows.append([sym, len(orders), filled, ", ".join(
                    f"{k}:{v}" for k, v in sorted(statuses.items()))])
            lines.append(
                _md_table(["symbol", "orders", "filled", "status_counts"], summary_rows))

            # Entry orders (clientOrderId startswith ENTRY-). This is the most useful slice
            # for fill-rate / time-to-fill or time-to-cancel analysis.
            entry_rows: List[List[Any]] = []
            for sym in symbols:
                for o in orders_by_symbol.get(sym, []):
                    coid = str(o.get("clientOrderId") or "")
                    if not coid.startswith("ENTRY-"):
                        continue

                    placed_ms = o.get("time")
                    update_ms = o.get("updateTime") or placed_ms
                    entry_rows.append(
                        [
                            _fmt_ts_ms(placed_ms),
                            _fmt_ts_ms(update_ms),
                            o.get("symbol"),
                            o.get("side"),
                            o.get("type"),
                            o.get("timeInForce"),
                            o.get("origQty"),
                            o.get("executedQty"),
                            o.get("avgPrice"),
                            o.get("status"),
                            coid,
                            o.get("orderId"),
                        ]
                    )

            if entry_rows:
                # Sort oldest -> newest for stable diffs.
                entry_rows_sorted = sorted(entry_rows, key=lambda r: r[0])
                lines.append("\n### Entry orders (all)\n")
                lines.append(
                    _md_table(
                        [
                            "time",
                            "update_time",
                            "symbol",
                            "side",
                            "type",
                            "tif",
                            "origQty",
                            "executedQty",
                            "avgPrice",
                            "status",
                            "clientOrderId",
                            "orderId",
                        ],
                        entry_rows_sorted,
                    )
                )

            # Show only FILLED orders (if any), capped to recent 200 for readability
            filled_rows: List[List[Any]] = []
            for sym in symbols:
                for o in orders_by_symbol.get(sym, []):
                    if str(o.get("status")) != "FILLED":
                        continue
                    ts_ms = o.get("updateTime") or o.get("time")
                    filled_rows.append(
                        [
                            _fmt_ts_ms(ts_ms),
                            o.get("symbol"),
                            o.get("side"),
                            o.get("type"),
                            o.get("origQty"),
                            o.get("executedQty"),
                            o.get("avgPrice"),
                            o.get("status"),
                            o.get("orderId"),
                        ]
                    )
            if filled_rows:
                # newest last
                filled_rows_sorted = sorted(filled_rows, key=lambda r: r[0])
                tail = filled_rows_sorted[-200:]
                lines.append("\n### Filled orders (last 200)\n")
                lines.append(
                    _md_table(
                        ["time", "symbol", "side", "type", "origQty",
                            "executedQty", "avgPrice", "status", "orderId"],
                        tail,
                    )
                )
            else:
                lines.append(
                    "\n(No FILLED orders in this period for these symbols.)\n")

    out_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nWrote markdown report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
