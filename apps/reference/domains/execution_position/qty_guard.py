from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Callable, Dict, Optional

from apps.reference.config_symbols import resolve_instrument_profile

DEFAULT_STEP_SIZE = Decimal("0.000001")
DEFAULT_MIN_QTY = Decimal("0.000001")
DEFAULT_MIN_NOTIONAL = Decimal("5")


@dataclass(frozen=True)
class QtyGuardResult:
    """Outcome of a quantity guard evaluation."""

    allowed: bool
    normalized_qty: Optional[Decimal]
    raw_qty: Optional[Decimal]
    reason: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)

    def qty_str(self) -> Optional[str]:
        """Return normalized quantity formatted for DEC payloads."""
        if self.normalized_qty is None:
            return None
        return format(self.normalized_qty.normalize(), "f")


class ExecutionQtyGuard:
    """Quantization guard that fail-closes unsafe DEC quantities."""

    def __init__(
        self,
        *,
        config: Any = None,
        instrument_lookup: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._config = config
        self._instrument_lookup = instrument_lookup
        self._profile_cache: Dict[str, Any] = {}

    def evaluate(
        self,
        *,
        symbol: str,
        qty: Any,
        price: Any | None = None,
    ) -> QtyGuardResult:
        """Validate and normalize a reduce-only quantity."""

        symbol_key = symbol.upper()
        raw_qty = self._to_decimal(qty, "qty")
        if raw_qty <= 0:
            return QtyGuardResult(
                allowed=False,
                normalized_qty=None,
                raw_qty=raw_qty,
                reason="non_positive_qty",
                metadata={"symbol": symbol_key, "raw_qty": str(raw_qty)},
            )

        profile = self._resolve_instrument_profile(symbol_key)
        step_size = self._extract_decimal(
            profile, "step_size", DEFAULT_STEP_SIZE)
        min_qty = self._extract_decimal(profile, "min_qty", DEFAULT_MIN_QTY)
        min_notional = self._extract_decimal(
            profile, "min_notional", DEFAULT_MIN_NOTIONAL
        )

        metadata = {
            "symbol": symbol_key,
            "raw_qty": self._decimal_to_str(raw_qty),
            "step_size": self._decimal_to_str(step_size),
            "min_qty": self._decimal_to_str(min_qty),
            "min_notional": self._decimal_to_str(min_notional),
            "profile_source": self._extract_str(profile, "source", "unknown"),
        }

        if raw_qty < min_qty:
            metadata["violation"] = "below_min_qty"
            return QtyGuardResult(
                allowed=False,
                normalized_qty=None,
                raw_qty=raw_qty,
                reason="below_min_qty",
                metadata=metadata,
            )

        normalized_qty = self._round_to_step(raw_qty, step_size)
        metadata["normalized_qty"] = self._decimal_to_str(normalized_qty)

        if normalized_qty <= 0:
            metadata["violation"] = "qty_rounds_to_zero"
            return QtyGuardResult(
                allowed=False,
                normalized_qty=None,
                raw_qty=raw_qty,
                reason="qty_rounds_to_zero",
                metadata=metadata,
            )

        if normalized_qty < min_qty:
            metadata["violation"] = "below_min_qty"
            return QtyGuardResult(
                allowed=False,
                normalized_qty=None,
                raw_qty=raw_qty,
                reason="below_min_qty",
                metadata=metadata,
            )

        price_dec = self._to_decimal(
            price, "price") if price is not None else None
        if price_dec is not None and price_dec > 0:
            metadata["price"] = self._decimal_to_str(price_dec)
            notional = normalized_qty * price_dec
            metadata["notional"] = self._decimal_to_str(notional)
            if notional < min_notional:
                metadata["violation"] = "below_min_notional"
                return QtyGuardResult(
                    allowed=False,
                    normalized_qty=None,
                    raw_qty=raw_qty,
                    reason="below_min_notional",
                    metadata=metadata,
                )

        return QtyGuardResult(
            allowed=True,
            normalized_qty=normalized_qty,
            raw_qty=raw_qty,
            metadata=metadata,
        )

    def invalidate(self, symbol: str) -> None:
        """Drop cached instrument metadata for symbol."""
        self._profile_cache.pop(symbol.upper(), None)

    def _resolve_instrument_profile(self, symbol: str) -> Any:
        if symbol in self._profile_cache:
            return self._profile_cache[symbol]

        profile = None
        if self._instrument_lookup:
            try:
                profile = self._instrument_lookup(symbol)
            except Exception:
                profile = None

        if profile is None and self._config is not None:
            try:
                profile = resolve_instrument_profile(self._config, symbol)
            except Exception:
                profile = None

        if profile is not None:
            self._profile_cache[symbol] = profile
        return profile

    @staticmethod
    def _round_to_step(qty: Decimal, step_size: Decimal) -> Decimal:
        if step_size <= 0:
            return qty
        steps = (qty / step_size).to_integral_value(rounding=ROUND_DOWN)
        return (steps * step_size).normalize()

    @staticmethod
    def _extract_decimal(source: Any, field: str, default: Decimal) -> Decimal:
        value = ExecutionQtyGuard._extract_value(source, field)
        if value is None:
            return default
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return default

    @staticmethod
    def _extract_str(source: Any, field: str, default: str) -> str:
        value = ExecutionQtyGuard._extract_value(source, field)
        if value is None:
            return default
        return str(value)

    @staticmethod
    def _extract_value(source: Any, field: str) -> Any:
        if source is None:
            return None

        if isinstance(source, dict):
            if field in source:
                return source[field]
            return ExecutionQtyGuard._extract_from_nested_mappings(source, field)

        value = ExecutionQtyGuard._safe_getattr(source, field)
        if value is not None:
            return value

        return ExecutionQtyGuard._extract_from_nested_attrs(source, field)

    @staticmethod
    def _extract_from_nested_mappings(container: Dict[str, Any], field: str) -> Any:
        nested_keys = (
            "limits",
            "instrument",
            "spec",
            "profile",
        )
        for nested_key in nested_keys:
            nested = container.get(nested_key)
            value = ExecutionQtyGuard._extract_value(nested, field)
            if value is not None:
                return value
        return None

    @staticmethod
    def _extract_from_nested_attrs(source: Any, field: str) -> Any:
        nested_attr_names = (
            "limits",
            "instrument",
            "spec",
            "profile",
        )
        for attr_name in nested_attr_names:
            nested = ExecutionQtyGuard._safe_getattr(source, attr_name)
            value = ExecutionQtyGuard._extract_value(nested, field)
            if value is not None:
                return value

        shadow_dict = getattr(source, "__dict__", None)
        if isinstance(shadow_dict, dict) and field in shadow_dict:
            return shadow_dict[field]
        return None

    @staticmethod
    def _safe_getattr(source: Any, field: str) -> Any:
        try:
            return getattr(source, field)
        except AttributeError:
            return None

    @staticmethod
    def _to_decimal(value: Any, field: str) -> Decimal:
        if value is None:
            raise ValueError(f"{field} cannot be None")
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str):
            try:
                return Decimal(value)
            except InvalidOperation as exc:
                raise ValueError(f"{field} must be numeric: {value}") from exc
        raise ValueError(f"Unsupported {field} type: {type(value).__name__}")

    @staticmethod
    def _decimal_to_str(value: Decimal) -> str:
        return format(value.normalize(), "f")
