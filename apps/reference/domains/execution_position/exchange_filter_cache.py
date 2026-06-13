"""Dynamic exchange filter cache for order normalization and validation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    import yaml
except Exception:  # pragma: no cover - optional runtime dependency guard
    yaml = None


@dataclass(frozen=True)
class ExchangeFilterSnapshot:
    symbol: str
    tick_size: Decimal
    step_size: Decimal
    min_qty: Decimal
    min_notional: Decimal | None
    source: str
    updated_at_monotonic: float
    updated_at_ms: int


@dataclass(frozen=True)
class RefreshReport:
    refreshed: list[str]
    failed: list[str]
    source: str
    error: str | None = None


class ExchangeFilterCache:
    def __init__(
        self,
        *,
        fetch_exchange_info: Callable[[], dict[str, Any]] | None = None,
        static_config_path: str | Path = "config/aurora/instruments.yaml",
        monotonic_fn: Callable[[], float] = time.monotonic,
        now_ms_fn: Callable[[], int] | None = None,
        mode: str = "test",
        live_required_modes: Iterable[str] = ("live", "production"),
    ) -> None:
        self.fetch_exchange_info = fetch_exchange_info
        self.static_config_path = Path(static_config_path)
        self.monotonic_fn = monotonic_fn
        self.now_ms_fn = now_ms_fn or (lambda: int(time.time() * 1000))
        self.mode = str(mode).strip().lower()
        self.live_required_modes = {str(item).strip().lower() for item in live_required_modes}
        self._filters: dict[str, ExchangeFilterSnapshot] = {}

    def get_filter(self, symbol: str) -> ExchangeFilterSnapshot:
        key = self._symbol(symbol)
        snapshot = self._filters.get(key)
        if snapshot is None:
            snapshot = self._load_static_filter(key)
            if snapshot is not None and self.mode not in self.live_required_modes:
                self._filters[key] = snapshot
        if snapshot is None:
            raise LookupError(f"exchange filter unavailable for {key}")
        return snapshot

    def is_fresh(self, symbol: str, max_age_sec: float) -> bool:
        snapshot = self._filters.get(self._symbol(symbol))
        if snapshot is None:
            return False
        return (float(self.monotonic_fn()) - snapshot.updated_at_monotonic) <= float(max_age_sec)

    def refresh(self, symbols: Iterable[str] | None = None) -> RefreshReport:
        wanted = {self._symbol(symbol) for symbol in symbols or []}
        if self.fetch_exchange_info is None:
            return self._refresh_static(wanted)
        try:
            exchange_info = self.fetch_exchange_info()
            parsed = self._parse_exchange_info(exchange_info)
        except Exception as exc:
            if self.mode in self.live_required_modes:
                return RefreshReport(refreshed=[], failed=sorted(wanted), source="live", error=type(exc).__name__)
            return self._refresh_static(wanted, error=type(exc).__name__)

        refreshed: list[str] = []
        for symbol, snapshot in parsed.items():
            if wanted and symbol not in wanted:
                continue
            self._filters[symbol] = snapshot
            refreshed.append(symbol)
        failed = sorted(wanted - set(refreshed)) if wanted else []
        return RefreshReport(refreshed=sorted(refreshed), failed=failed, source="live")

    def require_fresh_filter(self, symbol: str, max_age_sec: float) -> ExchangeFilterSnapshot:
        key = self._symbol(symbol)
        if not self.is_fresh(key, max_age_sec):
            if self.mode in self.live_required_modes:
                raise LookupError(f"fresh live exchange filter required for {key}")
            return self.get_filter(key)
        return self.get_filter(key)

    def _refresh_static(self, wanted: set[str], error: str | None = None) -> RefreshReport:
        refreshed: list[str] = []
        for symbol, snapshot in self._load_static_filters().items():
            if wanted and symbol not in wanted:
                continue
            self._filters[symbol] = snapshot
            refreshed.append(symbol)
        failed = sorted(wanted - set(refreshed)) if wanted else []
        return RefreshReport(refreshed=sorted(refreshed), failed=failed, source="static", error=error)

    def _parse_exchange_info(self, exchange_info: dict[str, Any]) -> dict[str, ExchangeFilterSnapshot]:
        now_mono = float(self.monotonic_fn())
        now_ms = int(self.now_ms_fn())
        parsed: dict[str, ExchangeFilterSnapshot] = {}
        for raw_symbol in exchange_info.get("symbols", []) or []:
            if not isinstance(raw_symbol, dict):
                continue
            symbol = self._symbol(raw_symbol.get("symbol"))
            filters = {
                str(item.get("filterType")): item
                for item in raw_symbol.get("filters", []) or []
                if isinstance(item, dict)
            }
            price_filter = filters.get("PRICE_FILTER") or {}
            lot_filter = filters.get("LOT_SIZE") or filters.get("MARKET_LOT_SIZE") or {}
            notional_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
            tick_size = self._decimal(price_filter.get("tickSize"))
            step_size = self._decimal(lot_filter.get("stepSize"))
            min_qty = self._decimal(lot_filter.get("minQty"))
            if tick_size <= 0 or step_size <= 0 or min_qty < 0:
                continue
            min_notional_raw = notional_filter.get("minNotional") or notional_filter.get("notional")
            parsed[symbol] = ExchangeFilterSnapshot(
                symbol=symbol,
                tick_size=tick_size,
                step_size=step_size,
                min_qty=min_qty,
                min_notional=self._decimal(min_notional_raw) if min_notional_raw is not None else None,
                source="live",
                updated_at_monotonic=now_mono,
                updated_at_ms=now_ms,
            )
        return parsed

    def _load_static_filter(self, symbol: str) -> ExchangeFilterSnapshot | None:
        return self._load_static_filters().get(self._symbol(symbol))

    def _load_static_filters(self) -> dict[str, ExchangeFilterSnapshot]:
        if yaml is None or not self.static_config_path.exists():
            return {}
        raw = yaml.safe_load(self.static_config_path.read_text(encoding="utf-8")) or {}
        instruments = raw.get("instruments", raw)
        now_mono = float(self.monotonic_fn())
        now_ms = int(self.now_ms_fn())
        parsed: dict[str, ExchangeFilterSnapshot] = {}
        if isinstance(instruments, dict):
            iterator = instruments.items()
        elif isinstance(instruments, list):
            iterator = ((item.get("symbol"), item) for item in instruments if isinstance(item, dict))
        else:
            iterator = []
        for raw_symbol, cfg in iterator:
            if not isinstance(cfg, dict):
                continue
            symbol = self._symbol(raw_symbol or cfg.get("symbol"))
            tick = cfg.get("tick_size") or cfg.get("tickSize")
            step = cfg.get("step_size") or cfg.get("stepSize")
            min_qty = cfg.get("min_qty") or cfg.get("minQty") or "0"
            if tick is None or step is None:
                continue
            parsed[symbol] = ExchangeFilterSnapshot(
                symbol=symbol,
                tick_size=self._decimal(tick),
                step_size=self._decimal(step),
                min_qty=self._decimal(min_qty),
                min_notional=(
                    self._decimal(cfg.get("min_notional") or cfg.get("minNotional"))
                    if (cfg.get("min_notional") or cfg.get("minNotional")) is not None
                    else None
                ),
                source="static",
                updated_at_monotonic=now_mono,
                updated_at_ms=now_ms,
            )
        return parsed

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        return Decimal(str(value))

    @staticmethod
    def _symbol(value: Any) -> str:
        symbol = str(value or "").strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        return symbol


__all__ = ["ExchangeFilterCache", "ExchangeFilterSnapshot", "RefreshReport"]
