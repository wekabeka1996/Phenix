"""Credential-free public exchange metadata cache and filter parity diagnostics."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


CACHE_FILENAME = "public_exchange_info_cache_v0.json"
CACHE_REF = "aurora-publication://exchange-info/public-exchange-info-cache/v0"
PARITY_REF = "aurora-publication://exchange-info/filter-parity/v0"
ALLOWED_ENDPOINTS = {
    "live": "https://fapi.binance.com/fapi/v1/exchangeInfo",
    "testnet": "https://testnet.binancefuture.com/fapi/v1/exchangeInfo",
}
REQUIRED_FIELDS = ("tick_size", "step_size", "min_qty", "min_notional")

FieldParityState = Literal["match", "mismatch", "exchange_missing", "configured_missing"]
ParitySeverity = Literal[
    "match",
    "minor_mismatch",
    "material_mismatch",
    "exchange_missing",
    "configured_missing",
    "stale_exchange_info",
]


class PublicExchangeInfoSymbolV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    source_ts_ms: Optional[int] = None
    fetched_ts_ms: int
    freshness: Literal["fresh", "stale"]
    tick_size: Optional[str] = None
    step_size: Optional[str] = None
    min_qty: Optional[str] = None
    max_qty: Optional[str] = None
    min_notional: Optional[str] = None
    max_notional: Optional[str] = None
    filter_names: list[str] = Field(default_factory=list, max_length=24)
    missing_filters: list[str] = Field(default_factory=list, max_length=8)
    unsupported_filters: list[str] = Field(default_factory=list, max_length=16)
    fetch_status: Literal["ok", "error"] = "ok"
    error_code: Optional[str] = None
    error_message: Optional[str] = Field(default=None, max_length=256)


class PublicExchangeInfoCacheV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["public-exchange-info-cache/v0"] = "public-exchange-info-cache/v0"
    venue: Literal["binance_usdm"] = "binance_usdm"
    environment: Literal["live", "testnet"]
    endpoint: str
    attempted_ts_ms: int
    last_success_ts_ms: Optional[int] = None
    fetch_status: Literal["ok", "error", "missing"]
    error_code: Optional[str] = None
    error_message: Optional[str] = Field(default=None, max_length=256)
    symbols: list[PublicExchangeInfoSymbolV0] = Field(default_factory=list, max_length=12)


class FilterParitySymbolV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    severity: ParitySeverity
    fields: dict[str, FieldParityState] = Field(default_factory=dict, max_length=4)
    exchange_values: dict[str, Optional[str]] = Field(default_factory=dict, max_length=4)
    source_ts_ms: Optional[int] = None
    raw_ref: str = PARITY_REF


def _text_decimal(value: Any) -> Optional[str]:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return format(number, "f")


def compare_filter_parity(
    symbol: str,
    configured: Any | None,
    exchange: PublicExchangeInfoSymbolV0 | None,
) -> FilterParitySymbolV0:
    configured_values = {
        name: _text_decimal(getattr(configured, name, None)) if configured is not None else None
        for name in REQUIRED_FIELDS
    }
    exchange_values = {
        name: getattr(exchange, name, None) if exchange is not None else None
        for name in REQUIRED_FIELDS
    }
    fields: dict[str, FieldParityState] = {}
    minor = False
    material = False
    for name in REQUIRED_FIELDS:
        cfg = configured_values[name]
        ex = exchange_values[name]
        if cfg is None:
            fields[name] = "configured_missing"
            continue
        if ex is None:
            fields[name] = "exchange_missing"
            continue
        cfg_dec, ex_dec = Decimal(cfg), Decimal(ex)
        if cfg_dec == ex_dec:
            fields[name] = "match"
            continue
        fields[name] = "mismatch"
        if name in {"tick_size", "step_size"}:
            compatible_stricter = ex_dec > 0 and cfg_dec > ex_dec and cfg_dec % ex_dec == 0
            minor = minor or compatible_stricter
            material = material or not compatible_stricter
        else:
            minor = minor or cfg_dec > ex_dec
            material = material or cfg_dec < ex_dec

    if exchange is not None and exchange.freshness == "stale":
        severity: ParitySeverity = "stale_exchange_info"
    elif any(value == "configured_missing" for value in fields.values()):
        severity = "configured_missing"
    elif any(value == "exchange_missing" for value in fields.values()):
        severity = "exchange_missing"
    elif material:
        severity = "material_mismatch"
    elif minor:
        severity = "minor_mismatch"
    else:
        severity = "match"
    return FilterParitySymbolV0(
        symbol=str(symbol).upper(),
        severity=severity,
        fields=fields,
        exchange_values=exchange_values,
        source_ts_ms=exchange.source_ts_ms if exchange is not None else None,
    )


class PublicExchangeInfoCache:
    """Bounded public-only cache. It has no adapter, credential, or command surface."""

    def __init__(
        self,
        *,
        directory: Path,
        symbols: Iterable[str],
        environment: Literal["live", "testnet"],
        endpoint: str,
        ttl_sec: int = 900,
        retry_sec: int = 60,
        timeout_sec: float = 10.0,
        max_response_bytes: int = 2 * 1024 * 1024,
        max_cache_bytes: int = 64 * 1024,
        max_symbols: int = 12,
        fetch_fn: Optional[Callable[[str, float, int], Mapping[str, Any]]] = None,
        now_ms_fn: Optional[Callable[[], int]] = None,
    ) -> None:
        expected = ALLOWED_ENDPOINTS.get(environment)
        if expected is None or endpoint != expected:
            raise ValueError("public exchange-info endpoint is not allowlisted")
        self.directory = Path(directory).resolve()
        self.path = self.directory / CACHE_FILENAME
        self.symbols = list(dict.fromkeys(str(s).strip().upper() for s in symbols if str(s).strip()))[:max_symbols]
        self.environment = environment
        self.endpoint = endpoint
        self.ttl_ms = max(1, int(ttl_sec)) * 1000
        self.retry_sec = max(1, int(retry_sec))
        self.timeout_sec = max(0.1, float(timeout_sec))
        self.max_response_bytes = int(max_response_bytes)
        self.max_cache_bytes = int(max_cache_bytes)
        self.fetch_fn = fetch_fn or self._public_get
        self.now_ms_fn = now_ms_fn or (lambda: int(time.time() * 1000))
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._snapshot = self._load()

    @staticmethod
    def _public_get(endpoint: str, timeout_sec: float, max_bytes: int) -> Mapping[str, Any]:
        with httpx.Client(follow_redirects=False, timeout=timeout_sec) as client:
            with client.stream("GET", endpoint, headers={"Accept": "application/json"}) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise ValueError("exchange_info_response_too_large")
        parsed = json.loads(bytes(body))
        if not isinstance(parsed, Mapping):
            raise ValueError("exchange_info_response_not_object")
        return parsed

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="public-exchange-info", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=min(5.0, self.timeout_sec + 1.0))

    def _run(self) -> None:
        while not self._stop.is_set():
            current = self.snapshot()
            due = current is None or current.last_success_ts_ms is None or (
                self.now_ms_fn() - current.last_success_ts_ms >= self.ttl_ms
            )
            wait_sec = self.retry_sec
            if due:
                ok = self.refresh()
                wait_sec = max(1, self.ttl_ms // 1000) if ok else self.retry_sec
            elif current.last_success_ts_ms is not None:
                wait_sec = max(1, (self.ttl_ms - (self.now_ms_fn() - current.last_success_ts_ms)) // 1000)
            self._stop.wait(wait_sec)

    def refresh(self) -> bool:
        now = self.now_ms_fn()
        try:
            payload = self.fetch_fn(self.endpoint, self.timeout_sec, self.max_response_bytes)
            model = self._parse(payload, now)
            self._write(model)
            with self._lock:
                self._snapshot = model
            return True
        except Exception as exc:
            code = type(exc).__name__[:64]
            message = str(exc).replace("\r", " ").replace("\n", " ")[:256] or code
            with self._lock:
                previous = self._snapshot
                rows = [] if previous is None else [
                    row.model_copy(update={
                        "freshness": "stale",
                        "fetch_status": "error",
                        "error_code": code,
                        "error_message": message,
                    }) for row in previous.symbols
                ]
                failed = PublicExchangeInfoCacheV0(
                    environment=self.environment,
                    endpoint=self.endpoint,
                    attempted_ts_ms=now,
                    last_success_ts_ms=previous.last_success_ts_ms if previous else None,
                    fetch_status="error",
                    error_code=code,
                    error_message=message,
                    symbols=rows,
                )
                self._snapshot = failed
            self._write(failed)
            return False

    def snapshot(self, now_ms: Optional[int] = None) -> Optional[PublicExchangeInfoCacheV0]:
        with self._lock:
            current = self._snapshot
        if current is None:
            return None
        now = int(now_ms if now_ms is not None else self.now_ms_fn())
        rows = [
            row.model_copy(update={
                "freshness": "fresh"
                if current.fetch_status == "ok" and now - row.fetched_ts_ms <= self.ttl_ms
                else "stale"
            }) for row in current.symbols
        ]
        return current.model_copy(update={"symbols": rows})

    def get_symbol(self, symbol: str, now_ms: Optional[int] = None) -> Optional[PublicExchangeInfoSymbolV0]:
        current = self.snapshot(now_ms)
        if current is None:
            return None
        key = str(symbol).strip().upper()
        return next((row for row in current.symbols if row.symbol == key), None)

    def _parse(self, payload: Mapping[str, Any], now: int) -> PublicExchangeInfoCacheV0:
        raw_rows = payload.get("symbols")
        if not isinstance(raw_rows, list):
            raise ValueError("exchange_info_symbols_missing")
        wanted = set(self.symbols)
        source_ts = payload.get("serverTime")
        source_ts_ms = int(source_ts) if isinstance(source_ts, (int, float)) else None
        rows: list[PublicExchangeInfoSymbolV0] = []
        for raw in raw_rows:
            if not isinstance(raw, Mapping):
                continue
            symbol = str(raw.get("symbol") or "").upper()
            if symbol not in wanted:
                continue
            filters = {
                str(item.get("filterType")): item
                for item in (raw.get("filters") or [])
                if isinstance(item, Mapping) and item.get("filterType")
            }
            price = filters.get("PRICE_FILTER") or {}
            lot = filters.get("LOT_SIZE") or {}
            notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL") or {}
            values = {
                "tick_size": _text_decimal(price.get("tickSize")),
                "step_size": _text_decimal(lot.get("stepSize")),
                "min_qty": _text_decimal(lot.get("minQty")),
                "max_qty": _text_decimal(lot.get("maxQty")),
                "min_notional": _text_decimal(notional.get("minNotional") or notional.get("notional")),
                "max_notional": _text_decimal(notional.get("maxNotional")),
            }
            missing = []
            if "PRICE_FILTER" not in filters:
                missing.append("PRICE_FILTER")
            if "LOT_SIZE" not in filters:
                missing.append("LOT_SIZE")
            if not ({"MIN_NOTIONAL", "NOTIONAL"} & set(filters)):
                missing.append("MIN_NOTIONAL|NOTIONAL")
            supported = {"PRICE_FILTER", "LOT_SIZE", "MIN_NOTIONAL", "NOTIONAL"}
            rows.append(PublicExchangeInfoSymbolV0(
                symbol=symbol,
                source_ts_ms=source_ts_ms,
                fetched_ts_ms=now,
                freshness="fresh",
                filter_names=sorted(filters),
                missing_filters=missing,
                unsupported_filters=sorted(set(filters) - supported),
                **values,
            ))
        found = {row.symbol for row in rows}
        for symbol in self.symbols:
            if symbol not in found:
                rows.append(PublicExchangeInfoSymbolV0(
                    symbol=symbol,
                    source_ts_ms=source_ts_ms,
                    fetched_ts_ms=now,
                    freshness="fresh",
                    missing_filters=["symbol"],
                ))
        return PublicExchangeInfoCacheV0(
            environment=self.environment,
            endpoint=self.endpoint,
            attempted_ts_ms=now,
            last_success_ts_ms=now,
            fetch_status="ok",
            symbols=rows,
        )

    def _write(self, model: PublicExchangeInfoCacheV0) -> None:
        encoded = model.model_dump_json(exclude_none=True).encode("utf-8")
        if len(encoded) > self.max_cache_bytes:
            raise ValueError("exchange_info_cache_too_large")
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{CACHE_FILENAME}.", suffix=".tmp", dir=str(self.directory))
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temp_path), str(self.path))
            self._fsync_parent()
        finally:
            temp_path.unlink(missing_ok=True)

    def _fsync_parent(self) -> None:
        if os.name == "nt":
            return
        try:
            descriptor = os.open(str(self.directory), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            pass

    def _load(self) -> Optional[PublicExchangeInfoCacheV0]:
        try:
            size = self.path.stat().st_size
            if size <= 0 or size > self.max_cache_bytes:
                return None
            model = PublicExchangeInfoCacheV0.model_validate_json(self.path.read_bytes())
            if model.environment != self.environment or model.endpoint != self.endpoint:
                return None
            return model
        except (FileNotFoundError, OSError, ValidationError, ValueError, json.JSONDecodeError):
            return None


__all__ = [
    "ALLOWED_ENDPOINTS",
    "CACHE_FILENAME",
    "CACHE_REF",
    "PARITY_REF",
    "FilterParitySymbolV0",
    "PublicExchangeInfoCache",
    "PublicExchangeInfoCacheV0",
    "PublicExchangeInfoSymbolV0",
    "compare_filter_parity",
]
