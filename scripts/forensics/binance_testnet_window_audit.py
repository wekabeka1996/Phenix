#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import hmac
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import urlencode, quote_plus
from zoneinfo import ZoneInfo

import requests
import yaml


UTC = dt.timezone.utc
TARGET_TZ_NAME = "Europe/Zaporozhye"
DEFAULT_START_DATE = "2026-03-25"
DEFAULT_END_DATE = "2026-03-29"
BOUNDARY_CONTEXT_DAYS = 7
EXIT_LEVEL_REL_TOL = 0.0025
EPS = 1e-12

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_project_dotenv() -> None:
    try:
        from apps.reference.config_loader import load_dotenv  # type: ignore

        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except Exception:
        return


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    try:
        value = float(text)
    except Exception:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    try:
        return int(float(text))
    except Exception:
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y"}


def _ms(value: dt.datetime) -> int:
    return int(value.timestamp() * 1000)


def _utc_iso(ms: Optional[int]) -> str:
    if ms is None:
        return ""
    return dt.datetime.fromtimestamp(ms / 1000.0, tz=UTC).isoformat()


def _local_iso(ms: Optional[int], tz: ZoneInfo) -> str:
    if ms is None:
        return ""
    return dt.datetime.fromtimestamp(ms / 1000.0, tz=UTC).astimezone(tz).isoformat()


def _local_day(ms: Optional[int], tz: ZoneInfo) -> str:
    if ms is None:
        return ""
    return dt.datetime.fromtimestamp(ms / 1000.0, tz=UTC).astimezone(tz).date().isoformat()


def _row_in_window(row: Dict[str, Any], start_ms: int, end_ms: int) -> bool:
    time_ms = _safe_int(row.get("time_ms"))
    update_time_ms = _safe_int(row.get("update_time_ms"))
    candidates = [value for value in (
        update_time_ms, time_ms) if value is not None]
    return any(start_ms <= value <= end_ms for value in candidates)


def _fmt_num(value: Optional[float], digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    head = "| " + " | ".join(headers) + " |\n"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |\n"
    body = "".join(
        "| " + " | ".join(_md_escape(cell) for cell in row) + " |\n" for row in rows
    )
    return head + sep + body


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True,
                    ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(
            fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _parse_strategy_prices(why_values: Sequence[str]) -> Tuple[Optional[float], Optional[float]]:
    for value in why_values:
        match = re.search(r"strategy_prices:sl=([^,]+),tp=([^,\s]+)", value)
        if not match:
            continue
        return _safe_float(match.group(1)), _safe_float(match.group(2))
    return None, None


def _extract_regime_hint(why_values: Sequence[str]) -> Optional[str]:
    for value in why_values:
        match = re.search(r"tpsl:regime=([A-Z_]+)", value)
        if match:
            return match.group(1)
    return None


def _resolve_local_intent_attribution(
    *,
    rid: Any,
    intent_by_rid: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    rid_text = str(rid or "")
    if not rid_text:
        return {
            "rid": None,
            "strategy_id": None,
            "regime_hint": None,
            "stop_price": None,
            "target_price": None,
            "why": [],
            "status": "UNATTRIBUTED:NO_LOCAL_RID",
        }

    intent = intent_by_rid.get(rid_text)
    if not intent:
        return {
            "rid": rid_text,
            "strategy_id": None,
            "regime_hint": None,
            "stop_price": None,
            "target_price": None,
            "why": [],
            "status": "UNATTRIBUTED:RID_NOT_IN_LOCAL_SHADOW",
        }

    return {
        "rid": rid_text,
        "strategy_id": intent.get("strategy_id"),
        "regime_hint": intent.get("regime_hint"),
        "stop_price": intent.get("stop_price"),
        "target_price": intent.get("target_price"),
        "why": list(intent.get("why") or []),
        "status": "ATTRIBUTED:LOCAL_INTENT",
    }


def _iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                yield payload


def _record_ts_ms(record: Dict[str, Any]) -> Optional[int]:
    for key in ("ts_ms", "timestamp", "time", "updateTime"):
        value = _safe_int(record.get(key))
        if value is not None:
            return value
    adapter_response = record.get("adapter_response")
    if isinstance(adapter_response, dict):
        for key in ("updateTime", "time", "transactTime"):
            value = _safe_int(adapter_response.get(key))
            if value is not None:
                return value
    return None


def _parse_config_symbols(path: Path) -> List[str]:
    if not path.exists():
        return []
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    assignments = payload.get("assignments")
    if not isinstance(assignments, dict):
        return []
    return sorted(str(symbol).upper() for symbol in assignments.keys())


@dataclass(frozen=True)
class BinanceAuth:
    api_key: str
    api_secret: bytes


class BinanceFuturesClient:
    def __init__(self, *, base_url: str, auth: BinanceAuth, timeout_sec: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self.timeout_sec = timeout_sec
        self._time_offset_ms = 0
        self._last_time_sync_monotonic = 0.0

    def server_time_ms(self) -> int:
        response = requests.get(
            f"{self.base_url}/fapi/v1/time", timeout=self.timeout_sec)
        response.raise_for_status()
        payload = response.json()
        return int(payload["serverTime"])

    def _sync_time(self, *, force: bool = False) -> None:
        ttl_sec = 120.0
        now_monotonic = time.monotonic()
        if not force and (now_monotonic - self._last_time_sync_monotonic) < ttl_sec:
            return
        try:
            server_ms = self.server_time_ms()
            local_ms = int(time.time() * 1000)
            self._time_offset_ms = server_ms - local_ms
        except Exception:
            pass
        finally:
            self._last_time_sync_monotonic = now_monotonic

    @staticmethod
    def _norm_params(params: Dict[str, Any]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, bool):
                out[str(key)] = "true" if value else "false"
            else:
                out[str(key)] = str(value)
        return out

    def _signed_params(self, params: Dict[str, Any]) -> Dict[str, str]:
        payload = self._norm_params(params)
        payload["timestamp"] = str(
            int(time.time() * 1000) + self._time_offset_ms)
        payload.setdefault("recvWindow", "5000")
        query_string = urlencode(payload, doseq=True, quote_via=quote_plus)
        payload["signature"] = hmac.new(
            self.auth.api_secret,
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return payload

    def _request(self, method: str, path: str, *, params: Dict[str, Any], signed: bool) -> Any:
        headers = {"X-MBX-APIKEY": self.auth.api_key}
        final_params = self._signed_params(
            params) if signed else self._norm_params(params)
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            params=final_params,
            timeout=self.timeout_sec,
        )
        payload: Any
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            payload = response.json()
        else:
            payload = response.text
        if response.status_code >= 400:
            raise RuntimeError(
                f"HTTP {response.status_code} {method} {path}: {payload}")
        return payload

    def income_history(self, *, start_ms: int, end_ms: int, limit: int = 1000) -> List[Dict[str, Any]]:
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
                    params={"startTime": cursor,
                            "endTime": window_end, "limit": limit},
                    signed=True,
                )
                if not isinstance(page, list):
                    raise RuntimeError(
                        f"Unexpected income response type: {type(page).__name__}")
                if not page:
                    break
                out.extend(page)
                last_time = max(_safe_int(row.get("time"))
                                or cursor for row in page)
                next_cursor = last_time + 1
                if next_cursor <= cursor:
                    break
                cursor = next_cursor
                if len(page) < limit:
                    break
            window_start = window_end + 1
        dedup: List[Dict[str, Any]] = []
        seen: set[Tuple[Any, ...]] = set()
        for row in sorted(out, key=lambda item: _safe_int(item.get("time")) or 0):
            key = (
                row.get("tranId"),
                row.get("time"),
                row.get("asset"),
                row.get("incomeType"),
                row.get("income"),
                row.get("symbol"),
            )
            if key in seen:
                continue
            seen.add(key)
            dedup.append(row)
        return dedup

    def user_trades_for_symbol(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        max_window_ms = 7 * 24 * 60 * 60 * 1000
        out: List[Dict[str, Any]] = []
        window_start = int(start_ms)
        end_ms = int(end_ms)
        while window_start <= end_ms:
            window_end = min(end_ms, window_start + max_window_ms - 1)
            from_id: Optional[int] = None
            cursor = window_start
            while True:
                params: Dict[str, Any] = {
                    "symbol": symbol,
                    "startTime": cursor,
                    "endTime": window_end,
                    "limit": limit,
                }
                if from_id is not None:
                    params["fromId"] = from_id
                try:
                    page = self._request(
                        "GET", "/fapi/v1/userTrades", params=params, signed=True)
                except RuntimeError as exc:
                    if from_id is not None and "fromId" in str(exc):
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
                last_time = max(_safe_int(row.get("time"))
                                or cursor for row in page)
                last_id: Optional[int] = None
                for row in page:
                    trade_id = _safe_int(row.get("id"))
                    if trade_id is None:
                        continue
                    last_id = trade_id if last_id is None else max(
                        last_id, trade_id)
                if from_id is not None and last_id is not None:
                    next_from_id = last_id + 1
                    if next_from_id == from_id:
                        break
                    from_id = next_from_id
                else:
                    next_cursor = last_time + 1
                    if next_cursor <= cursor:
                        break
                    cursor = next_cursor
                if len(page) < limit:
                    break
            window_start = window_end + 1
        dedup: List[Dict[str, Any]] = []
        seen: set[Tuple[Any, ...]] = set()
        for row in sorted(out, key=lambda item: _safe_int(item.get("time")) or 0):
            key = (
                row.get("id"),
                row.get("orderId"),
                row.get("time"),
                row.get("price"),
                row.get("qty"),
            )
            if key in seen:
                continue
            seen.add(key)
            dedup.append(row)
        return dedup

    def all_orders_for_symbol(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        max_window_ms = 7 * 24 * 60 * 60 * 1000
        max_search_ms = 89 * 24 * 60 * 60 * 1000
        out: List[Dict[str, Any]] = []
        end_ms = int(end_ms)
        start_ms = int(start_ms)
        if end_ms - start_ms > max_search_ms:
            start_ms = end_ms - max_search_ms
        window_start = start_ms
        while window_start <= end_ms:
            window_end = min(end_ms, window_start + max_window_ms - 1)
            cursor = window_start
            while True:
                page = self._request(
                    "GET",
                    "/fapi/v1/allOrders",
                    params={"symbol": symbol, "startTime": cursor,
                            "endTime": window_end, "limit": limit},
                    signed=True,
                )
                if not isinstance(page, list):
                    raise RuntimeError(
                        f"Unexpected allOrders response type for {symbol}: {type(page).__name__}"
                    )
                if not page:
                    break
                out.extend(page)
                last_time = max(
                    _safe_int(row.get("updateTime"))
                    or _safe_int(row.get("time"))
                    or cursor
                    for row in page
                )
                next_cursor = last_time + 1
                if next_cursor <= cursor:
                    break
                cursor = next_cursor
                if len(page) < limit:
                    break
            window_start = window_end + 1
        dedup: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for row in sorted(out, key=lambda item: (_safe_int(item.get("updateTime")) or _safe_int(item.get("time")) or 0)):
            order_id = str(row.get("orderId") or "")
            if not order_id or order_id in seen:
                continue
            seen.add(order_id)
            dedup.append(row)
        return dedup


def _discover_local_context(
    order_log_path: Path,
    shadow_path: Path,
    *,
    start_ms: int,
    end_ms: int,
) -> Dict[str, Any]:
    local_symbols: set[str] = set()
    order_log_rows: List[Dict[str, Any]] = []
    shadow_rows: List[Dict[str, Any]] = []
    placed_by_order_id: Dict[str, Dict[str, Any]] = {}
    cancel_by_order_id: Dict[str, Dict[str, Any]] = {}
    intent_by_rid: Dict[str, Dict[str, Any]] = {}

    for row in _iter_jsonl(order_log_path):
        ts_ms = _record_ts_ms(row)
        if ts_ms is None or ts_ms < start_ms or ts_ms > end_ms:
            continue
        symbol = str(row.get("symbol") or "").upper()
        if symbol:
            local_symbols.add(symbol)
        order_log_rows.append(row)
        event_type = str(row.get("event_type") or "").upper()
        order_id = str(row.get("order_id") or row.get("orderId") or "")
        if event_type == "ORDER_PLACED" and order_id:
            adapter_response = row.get("adapter_response") if isinstance(
                row.get("adapter_response"), dict) else {}
            placed_by_order_id[order_id] = {
                "order_id": order_id,
                "rid": row.get("rid"),
                "symbol": symbol,
                "side": row.get("side"),
                "qty": _safe_float(row.get("quantity") or row.get("qty_raw")),
                "client_order_id": row.get("client_order_id") or adapter_response.get("clientOrderId"),
                "timestamp_ms": ts_ms,
                "event_type": event_type,
            }
        elif event_type == "ORDER_CANCELLED" and order_id:
            current = cancel_by_order_id.get(order_id)
            current_ts = _safe_int(current.get(
                "timestamp_ms")) if current else None
            if current is None or (current_ts is not None and ts_ms >= current_ts):
                cancel_by_order_id[order_id] = {
                    "order_id": order_id,
                    "timestamp_ms": ts_ms,
                    "reason": row.get("reason"),
                    "context": row.get("context"),
                    "timeout_type": row.get("timeout_type"),
                    "adapter_reason": ((row.get("adapter_response") or {}) if isinstance(row.get("adapter_response"), dict) else {}).get("reason"),
                }

    for row in _iter_jsonl(shadow_path):
        ts_ms = _record_ts_ms(row)
        if ts_ms is None or ts_ms < start_ms or ts_ms > end_ms:
            continue
        symbol = str(row.get("symbol") or "").upper()
        if symbol:
            local_symbols.add(symbol)
        if str(row.get("event_name") or "") != "EVT:TRADE_INTENT_PROPOSED":
            continue
        shadow_rows.append(row)
        rid = str(row.get("rid") or "")
        payload_fragment = row.get("payload_fragment") if isinstance(
            row.get("payload_fragment"), dict) else {}
        why_values = payload_fragment.get("why") if isinstance(
            payload_fragment.get("why"), list) else []
        stop_price, target_price = _parse_strategy_prices(
            [str(item) for item in why_values])
        intent_by_rid[rid] = {
            "rid": rid,
            "ts_ms": ts_ms,
            "symbol": symbol,
            "side": str(row.get("side") or payload_fragment.get("side") or "").upper(),
            "strategy_id": row.get("strategy_id") or payload_fragment.get("strategy"),
            "qty": _safe_float(row.get("qty")),
            "price": _safe_float(row.get("price")),
            "stop_price": stop_price,
            "target_price": target_price,
            "regime_hint": _extract_regime_hint([str(item) for item in why_values]),
            "why": [str(item) for item in why_values],
        }

    return {
        "local_symbols": sorted(local_symbols),
        "order_log_rows": order_log_rows,
        "shadow_rows": shadow_rows,
        "placed_by_order_id": placed_by_order_id,
        "cancel_by_order_id": cancel_by_order_id,
        "intent_by_rid": intent_by_rid,
    }


def _trade_side(row: Dict[str, Any]) -> str:
    side = str(row.get("side") or "").upper()
    if side in {"BUY", "SELL"}:
        return side
    if _as_bool(row.get("buyer")):
        return "BUY"
    return "SELL"


def _order_role(order_row: Optional[Dict[str, Any]]) -> str:
    if not order_row:
        return "UNKNOWN"
    if _as_bool(order_row.get("reduce_only")) or _as_bool(order_row.get("close_position")):
        return "CLOSING"
    client_order_id = str(order_row.get("client_order_id") or "")
    if client_order_id.startswith("ENTRY-"):
        return "OPENING"
    return "OPENING_OR_FLIP"


def _proven_close_reason(order_row: Optional[Dict[str, Any]]) -> str:
    if not order_row:
        return "UNKNOWN_ORDER_CONTEXT"
    order_type = str(order_row.get("type")
                     or order_row.get("orig_type") or "").upper()
    if order_type in {"TAKE_PROFIT", "TAKE_PROFIT_MARKET"}:
        return "TAKE_PROFIT_ORDER"
    if order_type in {"STOP", "STOP_MARKET", "STOP_LOSS", "STOP_LOSS_MARKET"}:
        return "STOP_ORDER"
    if _as_bool(order_row.get("reduce_only")) or _as_bool(order_row.get("close_position")):
        if order_type == "MARKET":
            return "REDUCE_ONLY_CLOSE_MARKET"
        if order_type == "LIMIT":
            return "REDUCE_ONLY_CLOSE_LIMIT"
        return "REDUCE_ONLY_CLOSE_OTHER"
    if order_type == "MARKET":
        return "OPPOSITE_FILL_MARKET"
    if order_type == "LIMIT":
        return "OPPOSITE_FILL_LIMIT"
    return "OPPOSITE_FILL_OTHER"


def _infer_close_reason(
    *,
    direction: str,
    exit_price: Optional[float],
    stop_price: Optional[float],
    target_price: Optional[float],
    proven_close_reason: str,
) -> str:
    if proven_close_reason == "TAKE_PROFIT_ORDER":
        return "TAKE_PROFIT"
    if proven_close_reason == "STOP_ORDER":
        return "STOP_LOSS"
    if exit_price is None:
        return "UNKNOWN"
    candidates: List[Tuple[str, float]] = []
    if direction == "LONG":
        if target_price and exit_price >= target_price * (1.0 - EXIT_LEVEL_REL_TOL):
            candidates.append(
                ("TAKE_PROFIT", abs(exit_price - target_price) / target_price))
        if stop_price and exit_price <= stop_price * (1.0 + EXIT_LEVEL_REL_TOL):
            candidates.append(
                ("STOP_LOSS", abs(exit_price - stop_price) / stop_price))
    elif direction == "SHORT":
        if target_price and exit_price <= target_price * (1.0 + EXIT_LEVEL_REL_TOL):
            candidates.append(
                ("TAKE_PROFIT", abs(exit_price - target_price) / target_price))
        if stop_price and exit_price >= stop_price * (1.0 - EXIT_LEVEL_REL_TOL):
            candidates.append(
                ("STOP_LOSS", abs(exit_price - stop_price) / stop_price))
    if not candidates:
        return "UNKNOWN"
    candidates.sort(key=lambda item: item[1])
    return candidates[0][0]


def _normalize_income(income_rows: Sequence[Dict[str, Any]], tz: ZoneInfo) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in sorted(income_rows, key=lambda item: _safe_int(item.get("time")) or 0):
        ts_ms = _safe_int(row.get("time"))
        income_value = _safe_float(row.get("income")) or 0.0
        rows.append(
            {
                "time_ms": ts_ms,
                "time_utc": _utc_iso(ts_ms),
                "time_local": _local_iso(ts_ms, tz),
                "local_date": _local_day(ts_ms, tz),
                "symbol": str(row.get("symbol") or "").upper(),
                "asset": row.get("asset"),
                "income_type": row.get("incomeType"),
                "income": income_value,
                "tran_id": row.get("tranId"),
                "info": row.get("info"),
            }
        )
    return rows


def _normalize_orders(
    orders_by_symbol: Dict[str, List[Dict[str, Any]]],
    tz: ZoneInfo,
    placed_by_order_id: Dict[str, Dict[str, Any]],
    cancel_by_order_id: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[Tuple[str, str], Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for symbol in sorted(orders_by_symbol):
        for row in sorted(
            orders_by_symbol[symbol],
            key=lambda item: (_safe_int(item.get("updateTime")) or _safe_int(
                item.get("time")) or 0, str(item.get("orderId") or "")),
        ):
            order_id = str(row.get("orderId") or "")
            time_ms = _safe_int(row.get("time"))
            update_time_ms = _safe_int(row.get("updateTime"))
            placed = placed_by_order_id.get(order_id, {})
            canceled = cancel_by_order_id.get(order_id, {})
            normalized = {
                "symbol": str(row.get("symbol") or symbol).upper(),
                "order_id": order_id,
                "client_order_id": row.get("clientOrderId"),
                "time_ms": time_ms,
                "time_utc": _utc_iso(time_ms),
                "time_local": _local_iso(time_ms, tz),
                "local_date": _local_day(time_ms, tz),
                "update_time_ms": update_time_ms,
                "update_time_utc": _utc_iso(update_time_ms),
                "update_time_local": _local_iso(update_time_ms, tz),
                "status": str(row.get("status") or ""),
                "side": str(row.get("side") or "").upper(),
                "type": str(row.get("type") or "").upper(),
                "orig_type": str(row.get("origType") or "").upper(),
                "time_in_force": row.get("timeInForce"),
                "price": _safe_float(row.get("price")),
                "avg_price": _safe_float(row.get("avgPrice")),
                "stop_price": _safe_float(row.get("stopPrice")),
                "orig_qty": _safe_float(row.get("origQty")),
                "executed_qty": _safe_float(row.get("executedQty")),
                "cum_quote": _safe_float(row.get("cumQuote")),
                "position_side": row.get("positionSide"),
                "reduce_only": _as_bool(row.get("reduceOnly")),
                "close_position": _as_bool(row.get("closePosition")),
                "price_protect": _as_bool(row.get("priceProtect")),
                "working_type": row.get("workingType"),
                "local_rid": placed.get("rid"),
                "local_side": placed.get("side"),
                "local_qty": placed.get("qty"),
                "local_client_order_id": placed.get("client_order_id"),
                "local_placed_ts_ms": placed.get("timestamp_ms"),
                "local_placed_ts_utc": _utc_iso(_safe_int(placed.get("timestamp_ms"))),
                "local_cancel_reason": canceled.get("reason"),
                "local_cancel_context": canceled.get("context"),
                "local_cancel_timeout_type": canceled.get("timeout_type"),
                "local_cancel_adapter_reason": canceled.get("adapter_reason"),
            }
            normalized["order_role"] = _order_role(normalized)
            rows.append(normalized)
            lookup[(normalized["symbol"], order_id)] = normalized
    return rows, lookup


def _normalize_trades(
    trades_by_symbol: Dict[str, List[Dict[str, Any]]],
    tz: ZoneInfo,
    order_lookup: Dict[Tuple[str, str], Dict[str, Any]],
    placed_by_order_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for symbol in sorted(trades_by_symbol):
        for row in sorted(
            trades_by_symbol[symbol],
            key=lambda item: (_safe_int(item.get("time")) or 0,
                              _safe_int(item.get("id")) or 0),
        ):
            ts_ms = _safe_int(row.get("time"))
            order_id = str(row.get("orderId") or "")
            side = _trade_side(row)
            qty = _safe_float(row.get("qty")) or 0.0
            price = _safe_float(row.get("price")) or 0.0
            order_row = order_lookup.get((symbol, order_id))
            placed = placed_by_order_id.get(order_id, {})
            direction = "LONG" if side == "BUY" else "SHORT"
            rows.append(
                {
                    "symbol": symbol,
                    "trade_id": _safe_int(row.get("id")),
                    "order_id": order_id,
                    "time_ms": ts_ms,
                    "time_utc": _utc_iso(ts_ms),
                    "time_local": _local_iso(ts_ms, tz),
                    "local_date": _local_day(ts_ms, tz),
                    "side": side,
                    "direction": direction,
                    "qty": qty,
                    "signed_qty": qty if side == "BUY" else -qty,
                    "price": price,
                    "quote_qty": _safe_float(row.get("quoteQty")) or (qty * price),
                    "realized_pnl": _safe_float(row.get("realizedPnl")) or 0.0,
                    "commission": _safe_float(row.get("commission")) or 0.0,
                    "commission_asset": row.get("commissionAsset"),
                    "maker": _as_bool(row.get("maker")),
                    "buyer": _as_bool(row.get("buyer")),
                    "position_side": row.get("positionSide"),
                    "exchange_order_status": order_row.get("status") if order_row else None,
                    "exchange_order_type": order_row.get("type") if order_row else None,
                    "exchange_order_role": _order_role(order_row),
                    "exchange_reduce_only": _as_bool(order_row.get("reduce_only")) if order_row else False,
                    "exchange_close_position": _as_bool(order_row.get("close_position")) if order_row else False,
                    "exchange_client_order_id": order_row.get("client_order_id") if order_row else None,
                    "exchange_order_time_ms": order_row.get("time_ms") if order_row else None,
                    "exchange_order_time_utc": _utc_iso(_safe_int(order_row.get("time_ms"))) if order_row else "",
                    "local_rid": placed.get("rid"),
                    "local_side": placed.get("side"),
                    "local_client_order_id": placed.get("client_order_id"),
                    "local_placed_ts_ms": placed.get("timestamp_ms"),
                    "local_placed_ts_utc": _utc_iso(_safe_int(placed.get("timestamp_ms"))),
                }
            )
    return rows


def _build_episodes(
    trade_rows: Sequence[Dict[str, Any]],
    order_lookup: Dict[Tuple[str, str], Dict[str, Any]],
    intent_by_rid: Dict[str, Dict[str, Any]],
    *,
    effective_end_ms: int,
    effective_end_local_iso: str,
    tz: ZoneInfo,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    trades_by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in trade_rows:
        trades_by_symbol[str(row["symbol"])].append(row)

    episodes: List[Dict[str, Any]] = []
    boundary_events: List[Dict[str, Any]] = []
    episode_index = 0
    boundary_index = 0

    for symbol in sorted(trades_by_symbol):
        open_lots: List[Dict[str, Any]] = []
        symbol_trades = sorted(trades_by_symbol[symbol], key=lambda item: (
            item["time_ms"], item["trade_id"] or 0))
        for trade in symbol_trades:
            qty = _safe_float(trade.get("qty")) or 0.0
            if qty <= EPS:
                continue
            side = str(trade.get("side") or "")
            direction = str(trade.get("direction") or "")
            order_row = order_lookup.get(
                (symbol, str(trade.get("order_id") or "")))
            is_reduce_only = _as_bool(order_row.get(
                "reduce_only")) if order_row else False
            is_close_position = _as_bool(order_row.get(
                "close_position")) if order_row else False
            trade_commission = _safe_float(trade.get("commission")) or 0.0
            trade_realized_pnl = _safe_float(trade.get("realized_pnl")) or 0.0

            opposite_direction = "SHORT" if direction == "LONG" else "LONG"
            closable_qty_total = 0.0
            if is_reduce_only or is_close_position:
                closable_qty_total = qty
            else:
                closable_qty_total = min(
                    qty,
                    sum((_safe_float(lot.get("remaining_qty")) or 0.0)
                        for lot in open_lots if lot["direction"] == opposite_direction),
                )
            open_qty_total = max(0.0, qty - closable_qty_total)
            matched_close_qty = 0.0
            allocated_exit_commission = 0.0
            allocated_realized_pnl = 0.0

            while closable_qty_total - matched_close_qty > EPS:
                candidate_idx: Optional[int] = None
                for idx, lot in enumerate(open_lots):
                    if lot["direction"] == opposite_direction and (_safe_float(lot.get("remaining_qty")) or 0.0) > EPS:
                        candidate_idx = idx
                        break
                if candidate_idx is None:
                    break
                lot = open_lots[candidate_idx]
                lot_remaining = _safe_float(lot.get("remaining_qty")) or 0.0
                match_qty = min(
                    lot_remaining, closable_qty_total - matched_close_qty)
                close_commission = 0.0
                close_realized_pnl = 0.0
                if closable_qty_total > EPS:
                    close_commission = trade_commission * \
                        (match_qty / closable_qty_total)
                    close_realized_pnl = trade_realized_pnl * \
                        (match_qty / closable_qty_total)
                entry_commission = 0.0
                lot_original_qty = _safe_float(
                    lot.get("original_qty")) or match_qty
                if lot_original_qty > EPS:
                    entry_commission = (_safe_float(
                        lot.get("entry_commission_total")) or 0.0) * (match_qty / lot_original_qty)
                exit_price = _safe_float(trade.get("price"))
                rid = lot.get("rid")
                attribution = _resolve_local_intent_attribution(
                    rid=rid,
                    intent_by_rid=intent_by_rid,
                )
                close_reason_proven = _proven_close_reason(order_row)
                close_reason_inferred = _infer_close_reason(
                    direction=str(lot.get("direction") or ""),
                    exit_price=exit_price,
                    stop_price=_safe_float(attribution.get("stop_price")),
                    target_price=_safe_float(attribution.get("target_price")),
                    proven_close_reason=close_reason_proven,
                )
                episode_index += 1
                episodes.append(
                    {
                        "episode_id": f"EP-{episode_index:05d}",
                        "status": "CLOSED",
                        "symbol": symbol,
                        "direction": lot.get("direction"),
                        "qty": match_qty,
                        "entry_time_ms": lot.get("entry_time_ms"),
                        "entry_time_utc": _utc_iso(_safe_int(lot.get("entry_time_ms"))),
                        "entry_time_local": _local_iso(_safe_int(lot.get("entry_time_ms")), tz),
                        "entry_local_date": _local_day(_safe_int(lot.get("entry_time_ms")), tz),
                        "entry_order_id": lot.get("entry_order_id"),
                        "entry_client_order_id": lot.get("entry_client_order_id"),
                        "entry_order_role": lot.get("entry_order_role"),
                        "entry_order_time_ms": lot.get("entry_order_time_ms"),
                        "entry_order_time_utc": _utc_iso(_safe_int(lot.get("entry_order_time_ms"))),
                        "entry_price": lot.get("entry_price"),
                        "entry_rid": attribution.get("rid"),
                        "strategy_id": attribution.get("strategy_id"),
                        "regime_hint": attribution.get("regime_hint"),
                        "entry_stop_price": attribution.get("stop_price"),
                        "entry_target_price": attribution.get("target_price"),
                        "entry_why": " || ".join(attribution.get("why") or []),
                        "local_attribution_status": attribution.get("status"),
                        "exit_time_ms": trade.get("time_ms"),
                        "exit_time_utc": trade.get("time_utc"),
                        "exit_time_local": trade.get("time_local"),
                        "exit_local_date": trade.get("local_date"),
                        "exit_order_id": trade.get("order_id"),
                        "exit_client_order_id": order_row.get("client_order_id") if order_row else None,
                        "exit_order_role": _order_role(order_row),
                        "exit_order_type": order_row.get("type") if order_row else None,
                        "exit_price": exit_price,
                        "close_reason_proven": close_reason_proven,
                        "close_reason_inferred": close_reason_inferred,
                        "gross_realized_pnl": close_realized_pnl,
                        "entry_commission": entry_commission,
                        "exit_commission": close_commission,
                        "net_pnl_after_trade_fees": close_realized_pnl - entry_commission - close_commission,
                        "holding_ms": (_safe_int(trade.get("time_ms")) or 0) - (_safe_int(lot.get("entry_time_ms")) or 0),
                        "holding_minutes": ((_safe_int(trade.get("time_ms")) or 0) - (_safe_int(lot.get("entry_time_ms")) or 0)) / 60000.0,
                        "left_boundary_ambiguous": False,
                        "right_boundary_truncated": False,
                    }
                )
                lot["remaining_qty"] = lot_remaining - match_qty
                matched_close_qty += match_qty
                allocated_exit_commission += close_commission
                allocated_realized_pnl += close_realized_pnl
                if (_safe_float(lot.get("remaining_qty")) or 0.0) <= EPS:
                    open_lots.pop(candidate_idx)

            unmatched_close_qty = max(
                0.0, qty - matched_close_qty - open_qty_total)
            if is_reduce_only or is_close_position:
                unmatched_close_qty = max(0.0, qty - matched_close_qty)

            if unmatched_close_qty > EPS:
                boundary_index += 1
                unmatched_commission = trade_commission - allocated_exit_commission
                unmatched_realized_pnl = trade_realized_pnl - allocated_realized_pnl
                boundary_events.append(
                    {
                        "boundary_event_id": f"BE-{boundary_index:05d}",
                        "event_type": "BOUNDARY_CLOSE_ONLY",
                        "symbol": symbol,
                        "direction_closed": opposite_direction,
                        "qty": unmatched_close_qty,
                        "time_ms": trade.get("time_ms"),
                        "time_utc": trade.get("time_utc"),
                        "time_local": trade.get("time_local"),
                        "local_date": trade.get("local_date"),
                        "order_id": trade.get("order_id"),
                        "order_type": order_row.get("type") if order_row else None,
                        "close_reason_proven": _proven_close_reason(order_row),
                        "close_reason_inferred": "UNKNOWN",
                        "gross_realized_pnl": unmatched_realized_pnl,
                        "commission": unmatched_commission,
                        "note": "Close fill had no matchable in-window opening lot. Absolute left-boundary position is unknown because /fapi/v1/userTrades has a 7-day maximum interval.",
                    }
                )

            if open_qty_total > EPS:
                if qty > EPS and matched_close_qty > EPS and closable_qty_total > EPS:
                    open_commission_total = max(
                        0.0, trade_commission - (trade_commission * (closable_qty_total / qty)))
                else:
                    open_commission_total = trade_commission
                rid = trade.get("local_rid")
                open_lots.append(
                    {
                        "symbol": symbol,
                        "direction": direction,
                        "remaining_qty": open_qty_total,
                        "original_qty": open_qty_total,
                        "entry_time_ms": trade.get("time_ms"),
                        "entry_price": trade.get("price"),
                        "entry_order_id": trade.get("order_id"),
                        "entry_client_order_id": order_row.get("client_order_id") if order_row else trade.get("exchange_client_order_id"),
                        "entry_order_role": _order_role(order_row),
                        "entry_order_time_ms": order_row.get("time_ms") if order_row else trade.get("exchange_order_time_ms"),
                        "entry_commission_total": open_commission_total,
                        "rid": rid,
                    }
                )

        for lot in open_lots:
            episode_index += 1
            rid = lot.get("rid")
            attribution = _resolve_local_intent_attribution(
                rid=rid,
                intent_by_rid=intent_by_rid,
            )
            episodes.append(
                {
                    "episode_id": f"EP-{episode_index:05d}",
                    "status": "OPEN_AT_RIGHT_BOUNDARY",
                    "symbol": symbol,
                    "direction": lot.get("direction"),
                    "qty": lot.get("remaining_qty"),
                    "entry_time_ms": lot.get("entry_time_ms"),
                    "entry_time_utc": _utc_iso(_safe_int(lot.get("entry_time_ms"))),
                    "entry_time_local": _local_iso(_safe_int(lot.get("entry_time_ms")), tz),
                    "entry_local_date": _local_day(_safe_int(lot.get("entry_time_ms")), tz),
                    "entry_order_id": lot.get("entry_order_id"),
                    "entry_client_order_id": lot.get("entry_client_order_id"),
                    "entry_order_role": lot.get("entry_order_role"),
                    "entry_order_time_ms": lot.get("entry_order_time_ms"),
                    "entry_order_time_utc": _utc_iso(_safe_int(lot.get("entry_order_time_ms"))),
                    "entry_price": lot.get("entry_price"),
                    "entry_rid": attribution.get("rid"),
                    "strategy_id": attribution.get("strategy_id"),
                    "regime_hint": attribution.get("regime_hint"),
                    "entry_stop_price": attribution.get("stop_price"),
                    "entry_target_price": attribution.get("target_price"),
                    "entry_why": " || ".join(attribution.get("why") or []),
                    "local_attribution_status": attribution.get("status"),
                    "exit_time_ms": effective_end_ms,
                    "exit_time_utc": _utc_iso(effective_end_ms),
                    "exit_time_local": effective_end_local_iso,
                    "exit_local_date": _local_day(effective_end_ms, tz),
                    "exit_order_id": None,
                    "exit_client_order_id": None,
                    "exit_order_role": None,
                    "exit_order_type": None,
                    "exit_price": None,
                    "close_reason_proven": "RIGHT_BOUNDARY_TRUNCATED",
                    "close_reason_inferred": "UNKNOWN",
                    "gross_realized_pnl": None,
                    "entry_commission": lot.get("entry_commission_total"),
                    "exit_commission": None,
                    "net_pnl_after_trade_fees": None,
                    "holding_ms": effective_end_ms - (_safe_int(lot.get("entry_time_ms")) or effective_end_ms),
                    "holding_minutes": (effective_end_ms - (_safe_int(lot.get("entry_time_ms")) or effective_end_ms)) / 60000.0,
                    "left_boundary_ambiguous": False,
                    "right_boundary_truncated": True,
                }
            )

    episodes.sort(key=lambda row: (
        row["symbol"], row["entry_time_ms"] or 0, row["episode_id"]))
    boundary_events.sort(key=lambda row: (
        row["symbol"], row["time_ms"] or 0, row["boundary_event_id"]))
    return episodes, boundary_events


def _build_daily_summary(
    income_rows: Sequence[Dict[str, Any]],
    trade_rows: Sequence[Dict[str, Any]],
    order_rows: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    bucket: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in income_rows:
        key = (str(row["local_date"]), str(row["symbol"]))
        item = bucket.setdefault(
            key,
            {
                "local_date": key[0],
                "symbol": key[1],
                "trade_fills": 0,
                "unique_trade_orders": set(),
                "orders_total": 0,
                "orders_filled": 0,
                "orders_canceled": 0,
                "income_realized_pnl": 0.0,
                "income_commission": 0.0,
                "income_funding_fee": 0.0,
                "income_net": 0.0,
            },
        )
        income_type = str(row.get("income_type") or "")
        income_value = _safe_float(row.get("income")) or 0.0
        if income_type == "REALIZED_PNL":
            item["income_realized_pnl"] += income_value
        elif income_type == "COMMISSION":
            item["income_commission"] += income_value
        elif income_type == "FUNDING_FEE":
            item["income_funding_fee"] += income_value
        item["income_net"] += income_value
    for row in trade_rows:
        key = (str(row["local_date"]), str(row["symbol"]))
        item = bucket.setdefault(
            key,
            {
                "local_date": key[0],
                "symbol": key[1],
                "trade_fills": 0,
                "unique_trade_orders": set(),
                "orders_total": 0,
                "orders_filled": 0,
                "orders_canceled": 0,
                "income_realized_pnl": 0.0,
                "income_commission": 0.0,
                "income_funding_fee": 0.0,
                "income_net": 0.0,
            },
        )
        item["trade_fills"] += 1
        if row.get("order_id"):
            item["unique_trade_orders"].add(str(row["order_id"]))
    for row in order_rows:
        key = (str(row["local_date"]), str(row["symbol"]))
        item = bucket.setdefault(
            key,
            {
                "local_date": key[0],
                "symbol": key[1],
                "trade_fills": 0,
                "unique_trade_orders": set(),
                "orders_total": 0,
                "orders_filled": 0,
                "orders_canceled": 0,
                "income_realized_pnl": 0.0,
                "income_commission": 0.0,
                "income_funding_fee": 0.0,
                "income_net": 0.0,
            },
        )
        item["orders_total"] += 1
        if row.get("status") == "FILLED":
            item["orders_filled"] += 1
        if row.get("status") == "CANCELED":
            item["orders_canceled"] += 1
    out: List[Dict[str, Any]] = []
    for key in sorted(bucket):
        item = bucket[key]
        out.append(
            {
                "local_date": item["local_date"],
                "symbol": item["symbol"],
                "trade_fills": item["trade_fills"],
                "unique_trade_orders": len(item["unique_trade_orders"]),
                "orders_total": item["orders_total"],
                "orders_filled": item["orders_filled"],
                "orders_canceled": item["orders_canceled"],
                "income_realized_pnl": item["income_realized_pnl"],
                "income_commission": item["income_commission"],
                "income_funding_fee": item["income_funding_fee"],
                "income_net": item["income_net"],
            }
        )
    return out


def _build_direction_summary(episodes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bucket: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in episodes:
        if row.get("status") != "CLOSED":
            continue
        key = (str(row["symbol"]), str(row["direction"]))
        item = bucket.setdefault(
            key,
            {
                "symbol": key[0],
                "direction": key[1],
                "closed_episodes": 0,
                "wins": 0,
                "losses": 0,
                "gross_realized_pnl": 0.0,
                "net_pnl_after_trade_fees": 0.0,
                "avg_holding_minutes_sum": 0.0,
            },
        )
        item["closed_episodes"] += 1
        net_value = _safe_float(row.get("net_pnl_after_trade_fees")) or 0.0
        if net_value > 0:
            item["wins"] += 1
        elif net_value < 0:
            item["losses"] += 1
        item["gross_realized_pnl"] += _safe_float(
            row.get("gross_realized_pnl")) or 0.0
        item["net_pnl_after_trade_fees"] += net_value
        item["avg_holding_minutes_sum"] += _safe_float(
            row.get("holding_minutes")) or 0.0
    out: List[Dict[str, Any]] = []
    for key in sorted(bucket):
        item = bucket[key]
        closed = item["closed_episodes"]
        out.append(
            {
                "symbol": item["symbol"],
                "direction": item["direction"],
                "closed_episodes": closed,
                "wins": item["wins"],
                "losses": item["losses"],
                "win_rate": (item["wins"] / closed) if closed else None,
                "gross_realized_pnl": item["gross_realized_pnl"],
                "net_pnl_after_trade_fees": item["net_pnl_after_trade_fees"],
                "avg_holding_minutes": (item["avg_holding_minutes_sum"] / closed) if closed else None,
            }
        )
    return out


def _build_close_reason_summary(episodes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bucket: Dict[Tuple[str, str, str], int] = Counter()
    for row in episodes:
        if row.get("status") != "CLOSED":
            continue
        key = (
            str(row["symbol"]),
            str(row.get("close_reason_proven") or ""),
            str(row.get("close_reason_inferred") or ""),
        )
        bucket[key] += 1
    return [
        {
            "symbol": key[0],
            "close_reason_proven": key[1],
            "close_reason_inferred": key[2],
            "closed_episodes": count,
        }
        for key, count in sorted(bucket.items())
    ]


def _build_symbol_summary(
    *,
    symbols: Sequence[str],
    income_rows: Sequence[Dict[str, Any]],
    trade_rows: Sequence[Dict[str, Any]],
    order_rows: Sequence[Dict[str, Any]],
    episodes: Sequence[Dict[str, Any]],
    boundary_events: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    income_by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    trades_by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    orders_by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    episodes_by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    boundary_by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in income_rows:
        income_by_symbol[str(row["symbol"])].append(row)
    for row in trade_rows:
        trades_by_symbol[str(row["symbol"])].append(row)
    for row in order_rows:
        orders_by_symbol[str(row["symbol"])].append(row)
    for row in episodes:
        episodes_by_symbol[str(row["symbol"])].append(row)
    for row in boundary_events:
        boundary_by_symbol[str(row["symbol"])].append(row)

    summary_rows: List[Dict[str, Any]] = []
    for symbol in symbols:
        income = income_by_symbol.get(symbol, [])
        trades = trades_by_symbol.get(symbol, [])
        orders = orders_by_symbol.get(symbol, [])
        symbol_episodes = episodes_by_symbol.get(symbol, [])
        closed_episodes = [
            row for row in symbol_episodes if row.get("status") == "CLOSED"]
        open_boundary = [row for row in symbol_episodes if row.get(
            "status") == "OPEN_AT_RIGHT_BOUNDARY"]
        boundary = boundary_by_symbol.get(symbol, [])

        realized_pnl_income = sum((_safe_float(row.get("income")) or 0.0)
                                  for row in income if row.get("income_type") == "REALIZED_PNL")
        commission_income = sum((_safe_float(row.get("income")) or 0.0)
                                for row in income if row.get("income_type") == "COMMISSION")
        funding_income = sum((_safe_float(row.get("income")) or 0.0)
                             for row in income if row.get("income_type") == "FUNDING_FEE")
        net_income = sum((_safe_float(row.get("income")) or 0.0)
                         for row in income)
        filled_orders = [
            row for row in orders if row.get("status") == "FILLED"]
        canceled_orders = [
            row for row in orders if row.get("status") == "CANCELED"]
        wins = sum(1 for row in closed_episodes if (
            _safe_float(row.get("net_pnl_after_trade_fees")) or 0.0) > 0)
        losses = sum(1 for row in closed_episodes if (
            _safe_float(row.get("net_pnl_after_trade_fees")) or 0.0) < 0)
        closed_count = len(closed_episodes)
        unknown_close_count = sum(1 for row in closed_episodes if row.get(
            "close_reason_inferred") == "UNKNOWN")
        net_episode_pnl = sum((_safe_float(
            row.get("net_pnl_after_trade_fees")) or 0.0) for row in closed_episodes)
        avg_hold_min = (
            sum((_safe_float(row.get("holding_minutes")) or 0.0)
                for row in closed_episodes) / closed_count
            if closed_count
            else None
        )
        summary_rows.append(
            {
                "symbol": symbol,
                "income_rows": len(income),
                "trade_fills": len(trades),
                "unique_trade_orders": len({str(row.get("order_id") or "") for row in trades if row.get("order_id")}),
                "orders_total": len(orders),
                "orders_filled": len(filled_orders),
                "orders_canceled": len(canceled_orders),
                "fill_rate": (len(filled_orders) / len(orders)) if orders else None,
                "income_realized_pnl": realized_pnl_income,
                "income_commission": commission_income,
                "income_funding_fee": funding_income,
                "income_net": net_income,
                "closed_episodes": closed_count,
                "wins": wins,
                "losses": losses,
                "win_rate": (wins / closed_count) if closed_count else None,
                "episode_net_pnl_after_trade_fees": net_episode_pnl,
                "avg_holding_minutes": avg_hold_min,
                "close_reason_unknown_rate": (unknown_close_count / closed_count) if closed_count else None,
                "boundary_close_only_events": len(boundary),
                "boundary_close_only_qty": sum((_safe_float(row.get("qty")) or 0.0) for row in boundary),
                "open_at_right_boundary_events": len(open_boundary),
                "open_at_right_boundary_qty": sum((_safe_float(row.get("qty")) or 0.0) for row in open_boundary),
                "rating": None,
            }
        )

    if summary_rows:
        rated_rows = [
            row
            for row in summary_rows
            if any(
                [
                    row["income_rows"],
                    row["trade_fills"],
                    row["orders_total"],
                    row["closed_episodes"],
                ]
            )
        ]
        pnl_values = [row["income_net"]
                      for row in rated_rows] if rated_rows else []
        min_pnl = min(pnl_values) if pnl_values else 0.0
        max_pnl = max(pnl_values) if pnl_values else 0.0
        pnl_span = max_pnl - min_pnl
        for row in summary_rows:
            if row not in rated_rows:
                row["rating"] = None
                continue
            relative_pnl_score = 0.5 if pnl_span <= EPS else (
                float(row["income_net"]) - min_pnl) / pnl_span
            win_rate = float(row["win_rate"]) if row.get(
                "win_rate") is not None else 0.0
            fill_rate = float(row["fill_rate"]) if row.get(
                "fill_rate") is not None else 0.0
            evidence_score = 1.0 - float(row["close_reason_unknown_rate"]) if row.get(
                "close_reason_unknown_rate") is not None else 0.0
            activity_score = _clamp01(float(row["closed_episodes"]) / 20.0)
            rating = 100.0 * (
                0.35 * relative_pnl_score
                + 0.25 * win_rate
                + 0.15 * fill_rate
                + 0.15 * evidence_score
                + 0.10 * activity_score
            )
            row["rating"] = rating

    summary_rows.sort(key=lambda row: (row["rating"] is None, -(
        float(row["rating"]) if row["rating"] is not None else 0.0), row["symbol"]))
    return summary_rows


def _build_validation_summary(
    *,
    base_url: str,
    requested_start_ms: int,
    requested_end_ms: int,
    effective_end_ms: int,
    income_rows: Sequence[Dict[str, Any]],
    trade_rows: Sequence[Dict[str, Any]],
    order_rows: Sequence[Dict[str, Any]],
    episodes: Sequence[Dict[str, Any]],
    boundary_events: Sequence[Dict[str, Any]],
    order_lookup: Dict[Tuple[str, str], Dict[str, Any]],
) -> Dict[str, Any]:
    trade_commission_total = sum(
        (_safe_float(row.get("commission")) or 0.0) for row in trade_rows)
    income_commission_total = sum((_safe_float(row.get("income")) or 0.0)
                                  for row in income_rows if row.get("income_type") == "COMMISSION")
    trade_realized_total = sum(
        (_safe_float(row.get("realized_pnl")) or 0.0) for row in trade_rows)
    income_realized_total = sum((_safe_float(row.get("income")) or 0.0)
                                for row in income_rows if row.get("income_type") == "REALIZED_PNL")
    missing_trade_orders = [
        {"symbol": row.get("symbol"), "order_id": row.get(
            "order_id"), "trade_id": row.get("trade_id")}
        for row in trade_rows
        if (str(row.get("symbol")), str(row.get("order_id"))) not in order_lookup
    ]
    unattributed_episodes = [
        row for row in episodes
        if str(row.get("local_attribution_status") or "").startswith("UNATTRIBUTED:")
    ]
    unattributed_closed_episodes = [
        row for row in unattributed_episodes if row.get("status") == "CLOSED"
    ]
    return {
        "base_url": base_url,
        "base_url_is_testnet": "testnet" in base_url.lower(),
        "requested_start_utc": _utc_iso(requested_start_ms),
        "requested_end_utc": _utc_iso(requested_end_ms),
        "effective_end_utc": _utc_iso(effective_end_ms),
        "right_boundary_truncated": effective_end_ms < requested_end_ms,
        "left_boundary_exchange_truth": "UNKNOWN: /fapi/v1/userTrades max interval is 7 days (-4165)",
        "income_rows": len(income_rows),
        "trade_rows": len(trade_rows),
        "order_rows": len(order_rows),
        "trade_position_side_counts": dict(Counter(str(row.get("position_side") or "") for row in trade_rows)),
        "order_position_side_counts": dict(Counter(str(row.get("position_side") or "") for row in order_rows)),
        "order_status_counts": dict(Counter(str(row.get("status") or "") for row in order_rows)),
        "order_type_counts": dict(Counter(str(row.get("type") or "") for row in order_rows)),
        "reduce_only_true_orders": sum(1 for row in order_rows if _as_bool(row.get("reduce_only"))),
        "close_position_true_orders": sum(1 for row in order_rows if _as_bool(row.get("close_position"))),
        "trade_commission_total": trade_commission_total,
        "income_commission_total": income_commission_total,
        "commission_reconciliation_delta": trade_commission_total + income_commission_total,
        "trade_realized_pnl_total": trade_realized_total,
        "income_realized_pnl_total": income_realized_total,
        "realized_pnl_reconciliation_delta": trade_realized_total - income_realized_total,
        "missing_trade_order_count": len(missing_trade_orders),
        "missing_trade_orders": missing_trade_orders[:25],
        "unattributed_episode_count": len(unattributed_episodes),
        "unattributed_closed_episode_count": len(unattributed_closed_episodes),
        "unattributed_closed_episode_net_pnl": sum((_safe_float(row.get("net_pnl_after_trade_fees")) or 0.0) for row in unattributed_closed_episodes),
        "unattributed_symbols": sorted({str(row.get("symbol") or "") for row in unattributed_episodes if row.get("symbol")}),
        "boundary_close_only_events": len(boundary_events),
    }


def _build_report(
    *,
    status: str,
    requested_start_local: dt.datetime,
    requested_end_local: dt.datetime,
    requested_start_ms: int,
    requested_end_ms: int,
    effective_end_ms: int,
    server_time_ms: int,
    base_url: str,
    output_dir: Path,
    config_symbols: Sequence[str],
    local_symbols: Sequence[str],
    income_symbols: Sequence[str],
    invalid_candidate_symbols: Sequence[str],
    final_symbols: Sequence[str],
    symbol_summary: Sequence[Dict[str, Any]],
    daily_summary: Sequence[Dict[str, Any]],
    direction_summary: Sequence[Dict[str, Any]],
    close_reason_summary: Sequence[Dict[str, Any]],
    validation_summary: Dict[str, Any],
) -> str:
    lines: List[str] = []
    lines.append(
        f"# REPORT_BINANCE_TESTNET_TRADES_{requested_start_local.date().isoformat()}_{requested_end_local.date().isoformat()}"
    )
    lines.append("")
    lines.append(f"Status: **{status}**")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(
        f"- Requested local window: {requested_start_local.isoformat()} .. {requested_end_local.isoformat()}")
    lines.append(
        f"- Requested UTC window: {_utc_iso(requested_start_ms)} .. {_utc_iso(requested_end_ms)}")
    lines.append(
        f"- Effective extracted UTC end: {_utc_iso(effective_end_ms)}")
    lines.append(
        f"- Binance server time at extraction: {_utc_iso(server_time_ms)}")
    lines.append(f"- Base URL: {base_url}")
    lines.append(f"- Artifact directory: {output_dir.as_posix()}")
    lines.append("")
    lines.append("## Facts")
    lines.append("")
    lines.append(
        "- Exchange access proved against Binance Futures Testnet public time endpoint and signed user endpoints.")
    lines.append(
        "- The requested local timezone was handled via Europe/Zaporozhye, including the DST change inside the requested interval.")
    if effective_end_ms < requested_end_ms:
        lines.append(
            "- The requested right boundary extends beyond current Binance server time, so the requested interval is only partially observable right now.")
    lines.append("- Absolute left-boundary position state cannot be exchange-proved for this account because /fapi/v1/userTrades rejects intervals longer than 7 days with code -4165.")
    lines.append(
        f"- Config symbols: {', '.join(config_symbols) if config_symbols else 'none'}")
    lines.append(
        f"- Local runtime symbols in effective window: {', '.join(local_symbols) if local_symbols else 'none'}")
    lines.append(
        f"- Exchange income symbols in effective window: {', '.join(income_symbols) if income_symbols else 'none'}")
    if invalid_candidate_symbols:
        lines.append(
            f"- Candidate symbols rejected by current testnet exchangeInfo: {', '.join(invalid_candidate_symbols)}")
    lines.append(
        f"- Final fetched symbol set: {', '.join(final_symbols) if final_symbols else 'none'}")
    lines.append("")
    lines.append("## Inferences")
    lines.append("")
    lines.append("- Position episodes were reconstructed by FIFO pairing of non-reduceOnly opening fills to subsequent reducing fills inside the effective window.")
    lines.append(
        f"- close_reason_inferred uses planned strategy stop/target levels from shadow intents only when the exit price is within {EXIT_LEVEL_REL_TOL:.4%} relative tolerance of the planned level; otherwise it remains UNKNOWN.")
    lines.append("")
    lines.append("## Assumptions")
    lines.append("")
    lines.append(
        "- None for exchange-proof statements. All non-exchange lifecycle pairing is explicitly represented as inference, not fact.")
    lines.append("")
    lines.append("## Unknowns")
    lines.append("")
    lines.append("- Absolute account position at the exact requested left boundary is UNKNOWN at exchange-proof level because older than 7-day userTrades history is unavailable from the endpoint.")
    if effective_end_ms < requested_end_ms:
        lines.append(
            "- The missing right-edge slice remains UNKNOWN until Binance server time passes the requested end boundary and the extraction is rerun.")
    unattributed_count = _safe_int(validation_summary.get("unattributed_episode_count")) or 0
    if unattributed_count > 0:
        unattributed_symbols = validation_summary.get("unattributed_symbols") or []
        lines.append(
            f"- {unattributed_count} reconstructed episode(s) lack provable local intent attribution, so strategy-level blame remains incomplete for symbols: {', '.join(str(item) for item in unattributed_symbols) if unattributed_symbols else 'unknown'}.")
    lines.append("")
    lines.append("## Validation")
    lines.append("")
    validation_rows = [
        ["base_url_is_testnet", validation_summary.get("base_url_is_testnet")],
        ["right_boundary_truncated", validation_summary.get(
            "right_boundary_truncated")],
        ["left_boundary_exchange_truth", validation_summary.get(
            "left_boundary_exchange_truth")],
        ["income_rows", validation_summary.get("income_rows")],
        ["trade_rows", validation_summary.get("trade_rows")],
        ["order_rows", validation_summary.get("order_rows")],
        ["commission_reconciliation_delta", _fmt_num(_safe_float(
            validation_summary.get("commission_reconciliation_delta")), 8)],
        ["realized_pnl_reconciliation_delta", _fmt_num(_safe_float(
            validation_summary.get("realized_pnl_reconciliation_delta")), 8)],
        ["missing_trade_order_count", validation_summary.get(
            "missing_trade_order_count")],
        ["unattributed_episode_count", validation_summary.get(
            "unattributed_episode_count")],
        ["unattributed_closed_episode_count", validation_summary.get(
            "unattributed_closed_episode_count")],
        ["unattributed_closed_episode_net_pnl", _fmt_num(_safe_float(
            validation_summary.get("unattributed_closed_episode_net_pnl")), 8)],
        ["boundary_close_only_events", validation_summary.get(
            "boundary_close_only_events")],
    ]
    lines.append(_md_table(["check", "value"], validation_rows))
    lines.append("")
    lines.append("## Symbol Summary")
    lines.append("")
    symbol_rows = []
    for row in symbol_summary:
        symbol_rows.append(
            [
                row.get("symbol"),
                row.get("trade_fills"),
                row.get("orders_total"),
                _fmt_num(_safe_float(row.get("income_net")), 4),
                row.get("closed_episodes"),
                _fmt_num(_safe_float(row.get("win_rate")), 4),
                _fmt_num(_safe_float(row.get("fill_rate")), 4),
                _fmt_num(_safe_float(row.get("close_reason_unknown_rate")), 4),
                _fmt_num(_safe_float(row.get("rating")), 2),
            ]
        )
    lines.append(
        _md_table(
            [
                "symbol",
                "trade_fills",
                "orders_total",
                "income_net",
                "closed_episodes",
                "win_rate",
                "fill_rate",
                "close_unknown_rate",
                "rating",
            ],
            symbol_rows,
        )
    )
    lines.append("")
    lines.append("## Daily Summary")
    lines.append("")
    daily_rows = []
    for row in daily_summary:
        daily_rows.append(
            [
                row.get("local_date"),
                row.get("symbol"),
                row.get("trade_fills"),
                row.get("orders_total"),
                _fmt_num(_safe_float(row.get("income_realized_pnl")), 4),
                _fmt_num(_safe_float(row.get("income_commission")), 4),
                _fmt_num(_safe_float(row.get("income_funding_fee")), 4),
                _fmt_num(_safe_float(row.get("income_net")), 4),
            ]
        )
    lines.append(
        _md_table(
            [
                "local_date",
                "symbol",
                "trade_fills",
                "orders_total",
                "realized_pnl",
                "commission",
                "funding_fee",
                "income_net",
            ],
            daily_rows,
        )
    )
    lines.append("")
    lines.append("## Direction Summary")
    lines.append("")
    direction_rows = []
    for row in direction_summary:
        direction_rows.append(
            [
                row.get("symbol"),
                row.get("direction"),
                row.get("closed_episodes"),
                row.get("wins"),
                row.get("losses"),
                _fmt_num(_safe_float(row.get("win_rate")), 4),
                _fmt_num(_safe_float(row.get("net_pnl_after_trade_fees")), 4),
                _fmt_num(_safe_float(row.get("avg_holding_minutes")), 2),
            ]
        )
    lines.append(
        _md_table(
            [
                "symbol",
                "direction",
                "closed_episodes",
                "wins",
                "losses",
                "win_rate",
                "net_pnl_after_trade_fees",
                "avg_holding_minutes",
            ],
            direction_rows,
        )
    )
    lines.append("")
    lines.append("## Close Reason Summary")
    lines.append("")
    close_rows = []
    for row in close_reason_summary:
        close_rows.append(
            [
                row.get("symbol"),
                row.get("close_reason_proven"),
                row.get("close_reason_inferred"),
                row.get("closed_episodes"),
            ]
        )
    lines.append(_md_table(["symbol", "close_reason_proven",
                 "close_reason_inferred", "closed_episodes"], close_rows))
    lines.append("")
    lines.append("## Rating Formula")
    lines.append("")
    lines.append("- rating = 100 * (0.35 * relative_net_income + 0.25 * win_rate + 0.15 * fill_rate + 0.15 * evidence_score + 0.10 * activity_score)")
    lines.append(
        "- relative_net_income is min-max normalized across observed symbols in this dataset only.")
    lines.append("- evidence_score = 1 - close_reason_unknown_rate.")
    lines.append("- activity_score = min(closed_episodes / 20, 1).")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append("- raw/access_proof.json")
    lines.append("- raw/income.json")
    lines.append("- raw/orders/*.json")
    lines.append("- raw/orders_context_7d/*.json")
    lines.append("- raw/trades/*.json")
    lines.append("- raw/local_order_log_window.jsonl")
    lines.append("- raw/local_shadow_intents_window.jsonl")
    lines.append("- normalized/income.csv")
    lines.append("- normalized/orders.csv")
    lines.append("- normalized/trades.csv")
    lines.append("- normalized/episodes.csv")
    lines.append("- normalized/boundary_events.csv")
    lines.append("- normalized/daily_symbol_summary.csv")
    lines.append("- normalized/direction_summary.csv")
    lines.append("- normalized/close_reason_summary.csv")
    lines.append("- normalized/symbol_summary.csv")
    lines.append("- summary.json")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit Binance Futures Testnet trading history for a fixed local-date window.")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE,
                        help="Local start date in YYYY-MM-DD.")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE,
                        help="Local end date in YYYY-MM-DD.")
    parser.add_argument("--timezone", default=TARGET_TZ_NAME,
                        help="IANA timezone name.")
    parser.add_argument(
        "--output-dir",
        default=f"reports/binance_testnet_trades_{DEFAULT_START_DATE}_{DEFAULT_END_DATE}",
        help="Output directory for raw and normalized artifacts.",
    )
    parser.add_argument(
        "--report-file",
        default=f"REPORT_BINANCE_TESTNET_TRADES_{DEFAULT_START_DATE}_{DEFAULT_END_DATE}.md",
        help="Top-level markdown report path.",
    )
    args = parser.parse_args()

    _load_project_dotenv()

    trading_mode = (os.getenv("TRADING_MODE") or "").strip().lower()
    if trading_mode not in {"testnet", "hybrid_testnet"}:
        raise SystemExit("Refusing to run outside testnet mode.")

    api_key = (os.getenv("BINANCE_TESTNET_API_KEY") or "").strip()
    api_secret = (os.getenv("BINANCE_TESTNET_API_SECRET") or "").strip()
    if not api_key or not api_secret:
        raise SystemExit(
            "Missing BINANCE_TESTNET_API_KEY / BINANCE_TESTNET_API_SECRET.")

    base_url = (os.getenv("BINANCE_FUTURES_BASE_URL_TESTNET")
                or "https://testnet.binancefuture.com").strip()
    tz = ZoneInfo(args.timezone)
    start_date = dt.date.fromisoformat(args.start_date)
    end_date = dt.date.fromisoformat(args.end_date)
    requested_start_local = dt.datetime.combine(
        start_date, dt.time.min, tzinfo=tz)
    requested_end_local = dt.datetime.combine(end_date, dt.time.max, tzinfo=tz)
    requested_start_ms = _ms(requested_start_local.astimezone(UTC))
    requested_end_ms = _ms(requested_end_local.astimezone(UTC))

    client = BinanceFuturesClient(
        base_url=base_url,
        auth=BinanceAuth(
            api_key=api_key, api_secret=api_secret.encode("utf-8")),
    )

    public_time_response = requests.get(
        f"{base_url.rstrip('/')}/fapi/v1/time", timeout=20)
    public_time_response.raise_for_status()
    public_server_time_ms = int(public_time_response.json()["serverTime"])
    exchange_info_response = requests.get(
        f"{base_url.rstrip('/')}/fapi/v1/exchangeInfo", timeout=20)
    exchange_info_response.raise_for_status()
    exchange_info_payload = exchange_info_response.json()
    valid_exchange_symbols = {
        str(item.get("symbol") or "").upper()
        for item in exchange_info_payload.get("symbols", [])
        if isinstance(item, dict) and item.get("symbol")
    }
    server_time_ms = client.server_time_ms()
    effective_end_ms = min(requested_end_ms, server_time_ms)
    effective_end_local_iso = _local_iso(effective_end_ms, tz)

    if effective_end_ms < requested_start_ms:
        raise SystemExit(
            "Requested window starts after current Binance server time.")

    output_dir = PROJECT_ROOT / args.output_dir
    raw_dir = output_dir / "raw"
    raw_orders_dir = raw_dir / "orders"
    raw_orders_context_dir = raw_dir / "orders_context_7d"
    raw_trades_dir = raw_dir / "trades"
    normalized_dir = output_dir / "normalized"
    report_path = PROJECT_ROOT / args.report_file

    config_symbols = _parse_config_symbols(
        PROJECT_ROOT / "config" / "aurora" / "strategies.yaml")
    boundary_context_start_ms = max(
        0, requested_start_ms - (BOUNDARY_CONTEXT_DAYS * 24 * 60 * 60 * 1000))
    local_context = _discover_local_context(
        PROJECT_ROOT / "logs" / "order_log_v1.jsonl",
        PROJECT_ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl",
        start_ms=requested_start_ms,
        end_ms=effective_end_ms,
    )

    income_raw = client.income_history(
        start_ms=requested_start_ms, end_ms=effective_end_ms)
    income_symbols = sorted({str(row.get("symbol") or "").upper()
                            for row in income_raw if row.get("symbol")})
    candidate_symbols = sorted({symbol for symbol in (
        config_symbols + local_context["local_symbols"] + income_symbols) if symbol})
    invalid_candidate_symbols = sorted(
        symbol for symbol in candidate_symbols if symbol not in valid_exchange_symbols)
    final_symbols = sorted(
        symbol for symbol in candidate_symbols if symbol in valid_exchange_symbols)

    if not final_symbols:
        raise SystemExit(
            "No valid exchange symbols remained after filtering candidates through exchangeInfo.")

    trades_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    orders_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for symbol in final_symbols:
        trades_by_symbol[symbol] = client.user_trades_for_symbol(
            symbol=symbol, start_ms=requested_start_ms, end_ms=effective_end_ms)
        orders_by_symbol[symbol] = client.all_orders_for_symbol(
            symbol=symbol, start_ms=boundary_context_start_ms, end_ms=effective_end_ms)

    access_proof = {
        "trading_mode": trading_mode,
        "base_url": base_url,
        "public_time_status": public_time_response.status_code,
        "public_server_time_ms": public_server_time_ms,
        "public_server_time_utc": _utc_iso(public_server_time_ms),
        "exchange_info_status": exchange_info_response.status_code,
        "valid_exchange_symbol_count": len(valid_exchange_symbols),
        "signed_server_time_ms": server_time_ms,
        "signed_server_time_utc": _utc_iso(server_time_ms),
        "requested_start_local": requested_start_local.isoformat(),
        "requested_end_local": requested_end_local.isoformat(),
        "requested_start_utc": _utc_iso(requested_start_ms),
        "requested_end_utc": _utc_iso(requested_end_ms),
        "effective_end_utc": _utc_iso(effective_end_ms),
        "right_boundary_truncated": effective_end_ms < requested_end_ms,
        "left_boundary_exchange_truth": "UNKNOWN: /fapi/v1/userTrades max interval is 7 days (-4165)",
        "candidate_symbols": candidate_symbols,
        "invalid_candidate_symbols": invalid_candidate_symbols,
        "final_symbols": final_symbols,
    }

    _write_json(raw_dir / "access_proof.json", access_proof)
    _write_json(raw_dir / "income.json", income_raw)
    for symbol in final_symbols:
        _write_json(raw_trades_dir /
                    f"{symbol}.json", trades_by_symbol[symbol])
        _write_json(raw_orders_context_dir /
                    f"{symbol}.json", orders_by_symbol[symbol])
    _write_jsonl(raw_dir / "local_order_log_window.jsonl",
                 local_context["order_log_rows"])
    _write_jsonl(raw_dir / "local_shadow_intents_window.jsonl",
                 local_context["shadow_rows"])

    income_rows = _normalize_income(income_raw, tz)
    order_rows_all, order_lookup = _normalize_orders(
        orders_by_symbol,
        tz,
        local_context["placed_by_order_id"],
        local_context["cancel_by_order_id"],
    )
    order_rows = [row for row in order_rows_all if _row_in_window(
        row, requested_start_ms, effective_end_ms)]
    trade_rows = _normalize_trades(
        trades_by_symbol,
        tz,
        order_lookup,
        local_context["placed_by_order_id"],
    )
    episodes, boundary_events = _build_episodes(
        trade_rows,
        order_lookup,
        local_context["intent_by_rid"],
        effective_end_ms=effective_end_ms,
        effective_end_local_iso=effective_end_local_iso,
        tz=tz,
    )
    daily_summary = _build_daily_summary(income_rows, trade_rows, order_rows)
    direction_summary = _build_direction_summary(episodes)
    close_reason_summary = _build_close_reason_summary(episodes)
    symbol_summary = _build_symbol_summary(
        symbols=final_symbols,
        income_rows=income_rows,
        trade_rows=trade_rows,
        order_rows=order_rows,
        episodes=episodes,
        boundary_events=boundary_events,
    )
    validation_summary = _build_validation_summary(
        base_url=base_url,
        requested_start_ms=requested_start_ms,
        requested_end_ms=requested_end_ms,
        effective_end_ms=effective_end_ms,
        income_rows=income_rows,
        trade_rows=trade_rows,
        order_rows=order_rows,
        episodes=episodes,
        boundary_events=boundary_events,
        order_lookup=order_lookup,
    )

    for symbol in final_symbols:
        filtered_orders = [
            row
            for row in orders_by_symbol[symbol]
            if _row_in_window(
                {
                    "time_ms": _safe_int(row.get("time")),
                    "update_time_ms": _safe_int(row.get("updateTime")),
                },
                requested_start_ms,
                effective_end_ms,
            )
        ]
        _write_json(raw_orders_dir / f"{symbol}.json", filtered_orders)

    income_fields = [
        "time_ms",
        "time_utc",
        "time_local",
        "local_date",
        "symbol",
        "asset",
        "income_type",
        "income",
        "tran_id",
        "info",
    ]
    order_fields = [
        "symbol",
        "order_id",
        "client_order_id",
        "time_ms",
        "time_utc",
        "time_local",
        "local_date",
        "update_time_ms",
        "update_time_utc",
        "update_time_local",
        "status",
        "side",
        "type",
        "orig_type",
        "time_in_force",
        "price",
        "avg_price",
        "stop_price",
        "orig_qty",
        "executed_qty",
        "cum_quote",
        "position_side",
        "reduce_only",
        "close_position",
        "price_protect",
        "working_type",
        "order_role",
        "local_rid",
        "local_side",
        "local_qty",
        "local_client_order_id",
        "local_placed_ts_ms",
        "local_placed_ts_utc",
        "local_cancel_reason",
        "local_cancel_context",
        "local_cancel_timeout_type",
        "local_cancel_adapter_reason",
    ]
    trade_fields = [
        "symbol",
        "trade_id",
        "order_id",
        "time_ms",
        "time_utc",
        "time_local",
        "local_date",
        "side",
        "direction",
        "qty",
        "signed_qty",
        "price",
        "quote_qty",
        "realized_pnl",
        "commission",
        "commission_asset",
        "maker",
        "buyer",
        "position_side",
        "exchange_order_status",
        "exchange_order_type",
        "exchange_order_role",
        "exchange_reduce_only",
        "exchange_close_position",
        "exchange_client_order_id",
        "exchange_order_time_ms",
        "exchange_order_time_utc",
        "local_rid",
        "local_side",
        "local_client_order_id",
        "local_placed_ts_ms",
        "local_placed_ts_utc",
    ]
    episode_fields = [
        "episode_id",
        "status",
        "symbol",
        "direction",
        "qty",
        "entry_time_ms",
        "entry_time_utc",
        "entry_time_local",
        "entry_local_date",
        "entry_order_id",
        "entry_client_order_id",
        "entry_order_role",
        "entry_order_time_ms",
        "entry_order_time_utc",
        "entry_price",
        "entry_rid",
        "strategy_id",
        "regime_hint",
        "local_attribution_status",
        "entry_stop_price",
        "entry_target_price",
        "entry_why",
        "exit_time_ms",
        "exit_time_utc",
        "exit_time_local",
        "exit_local_date",
        "exit_order_id",
        "exit_client_order_id",
        "exit_order_role",
        "exit_order_type",
        "exit_price",
        "close_reason_proven",
        "close_reason_inferred",
        "gross_realized_pnl",
        "entry_commission",
        "exit_commission",
        "net_pnl_after_trade_fees",
        "holding_ms",
        "holding_minutes",
        "left_boundary_ambiguous",
        "right_boundary_truncated",
    ]
    boundary_fields = [
        "boundary_event_id",
        "event_type",
        "symbol",
        "direction_closed",
        "qty",
        "time_ms",
        "time_utc",
        "time_local",
        "local_date",
        "order_id",
        "order_type",
        "close_reason_proven",
        "close_reason_inferred",
        "gross_realized_pnl",
        "commission",
        "note",
    ]

    _write_csv(normalized_dir / "income.csv", income_fields, income_rows)
    _write_csv(normalized_dir / "orders.csv", order_fields, order_rows)
    _write_csv(normalized_dir / "trades.csv", trade_fields, trade_rows)
    _write_csv(normalized_dir / "episodes.csv", episode_fields, episodes)
    _write_csv(normalized_dir / "boundary_events.csv",
               boundary_fields, boundary_events)
    _write_csv(normalized_dir / "daily_symbol_summary.csv",
               list(daily_summary[0].keys()) if daily_summary else ["local_date", "symbol"], daily_summary)
    _write_csv(normalized_dir / "direction_summary.csv", list(direction_summary[0].keys(
    )) if direction_summary else ["symbol", "direction"], direction_summary)
    _write_csv(normalized_dir / "close_reason_summary.csv", list(close_reason_summary[0].keys()) if close_reason_summary else [
               "symbol", "close_reason_proven", "close_reason_inferred", "closed_episodes"], close_reason_summary)
    _write_csv(normalized_dir / "symbol_summary.csv",
               list(symbol_summary[0].keys()) if symbol_summary else ["symbol"], symbol_summary)

    status = "PARTIAL_FAIL_CLOSED" if effective_end_ms < requested_end_ms else "COMPLETE_WITH_LEFT_BOUNDARY_UNKNOWN"
    report_text = _build_report(
        status=status,
        requested_start_local=requested_start_local,
        requested_end_local=requested_end_local,
        requested_start_ms=requested_start_ms,
        requested_end_ms=requested_end_ms,
        effective_end_ms=effective_end_ms,
        server_time_ms=server_time_ms,
        base_url=base_url,
        output_dir=output_dir,
        config_symbols=config_symbols,
        local_symbols=local_context["local_symbols"],
        income_symbols=income_symbols,
        invalid_candidate_symbols=invalid_candidate_symbols,
        final_symbols=final_symbols,
        symbol_summary=symbol_summary,
        daily_summary=daily_summary,
        direction_summary=direction_summary,
        close_reason_summary=close_reason_summary,
        validation_summary=validation_summary,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.md").write_text(report_text, encoding="utf-8")
    report_path.write_text(report_text, encoding="utf-8")

    summary_payload = {
        "status": status,
        "timezone": args.timezone,
        "requested_start_local": requested_start_local.isoformat(),
        "requested_end_local": requested_end_local.isoformat(),
        "requested_start_utc": _utc_iso(requested_start_ms),
        "requested_end_utc": _utc_iso(requested_end_ms),
        "server_time_utc": _utc_iso(server_time_ms),
        "effective_end_utc": _utc_iso(effective_end_ms),
        "config_symbols": config_symbols,
        "local_symbols": local_context["local_symbols"],
        "income_symbols": income_symbols,
        "invalid_candidate_symbols": invalid_candidate_symbols,
        "final_symbols": final_symbols,
        "rating_formula": {
            "relative_net_income": 0.35,
            "win_rate": 0.25,
            "fill_rate": 0.15,
            "evidence_score": 0.15,
            "activity_score": 0.10,
            "activity_cap_closed_episodes": 20,
        },
        "close_reason_inference_relative_tolerance": EXIT_LEVEL_REL_TOL,
        "validation": validation_summary,
        "symbol_summary": symbol_summary,
    }

    artifact_hashes: Dict[str, str] = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            relative_path = str(path.relative_to(
                PROJECT_ROOT)).replace("\\", "/")
            if relative_path.endswith("/summary.json"):
                continue
            artifact_hashes[relative_path] = _sha256_file(path)
    artifact_hashes[str(report_path.relative_to(PROJECT_ROOT)).replace(
        "\\", "/")] = _sha256_file(report_path)
    summary_payload["artifact_sha256"] = artifact_hashes
    summary_payload["artifact_hash_note"] = "summary.json is excluded from artifact_sha256 to avoid recursive self-hashing."
    _write_json(output_dir / "summary.json", summary_payload)

    print(json.dumps({
        "status": status,
        "effective_end_utc": _utc_iso(effective_end_ms),
        "requested_end_utc": _utc_iso(requested_end_ms),
        "symbols": final_symbols,
        "output_dir": str(output_dir),
        "report_file": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
