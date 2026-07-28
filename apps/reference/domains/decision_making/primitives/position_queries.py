"""Read portfolio state and compute margin-first sizing for decision paths."""

from __future__ import annotations

import decimal
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Optional

from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import (
    NormalizedRejectReasons,
)
from apps.reference.shared.decision_primitives.sizing_margin_first import (
    compute_notional_target,
    compute_qty,
    validate_exchange_constraints,
)

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig


def _field(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


class PositionQueries:
    """Expose read-only portfolio queries and margin-first sizing helpers."""

    def __init__(
        self,
        config: "AuroraConfig",
        get_portfolio: Callable[[], Optional[dict[str, Any]]],
        min_pos_size_usd: Decimal,
        liq_cap_usd: Decimal,
        logger: logging.Logger,
    ) -> None:
        self.config = config
        self._get_portfolio = get_portfolio
        self.min_pos_size_usd = min_pos_size_usd
        self.liq_cap_usd = liq_cap_usd
        self.logger = logger

    @staticmethod
    def safe_decimal(
        value: Any, default: Optional[Decimal] = None
    ) -> Optional[Decimal]:
        if value is None:
            return default
        if isinstance(value, Decimal):
            return value if value.is_finite() else default
        try:
            parsed = Decimal(str(value))
        except Exception:
            return default
        return parsed if parsed.is_finite() else default

    @staticmethod
    def _extract_signed_position_qty(position: dict[str, Any]) -> Optional[Decimal]:
        for key in (
            "net_position",
            "positionAmt",
            "position_amount",
            "position_amt",
            "qty",
            "quantity",
        ):
            if key not in position:
                continue
            raw_value = position.get(key)
            if raw_value in (None, ""):
                continue
            return PositionQueries.safe_decimal(raw_value)
        return None

    def get_position_state(self, symbol: str) -> str:
        qty_signed, _ = self.get_portfolio_position_qty_signed(symbol)
        if qty_signed is None:
            return "UNKNOWN"

        tol = decimal.Decimal("1e-9")
        if abs(qty_signed) < tol:
            return "FLAT"

        return "LONG" if qty_signed > 0 else "SHORT"

    def get_portfolio_position_qty_signed(
        self, symbol: str
    ) -> tuple[Optional[Decimal], Optional[dict[str, Any]]]:
        portfolio = self._get_portfolio()
        if not isinstance(portfolio, dict):
            return None, None

        positions = portfolio.get("positions")
        if not isinstance(positions, list):
            return None, None

        curr_pos = next(
            (
                pos
                for pos in positions
                if isinstance(pos, dict) and pos.get("symbol") == symbol
            ),
            None,
        )
        if not curr_pos:
            return decimal.Decimal("0"), None

        qty_dec = self._extract_signed_position_qty(curr_pos)
        if qty_dec is None:
            return None, curr_pos
        return qty_dec, curr_pos

    def check_symbol_is_flat(self, symbol: str) -> bool:
        try:
            portfolio = self._get_portfolio()
            if not isinstance(portfolio, dict):
                self.logger.warning(
                    "[%s] _check_symbol_is_flat: No portfolio data, FAIL-CLOSED (NRR-PORTFOLIO-UNKNOWN)",
                    symbol,
                )
                return False

            positions = portfolio.get("positions")
            if not isinstance(positions, list):
                self.logger.warning(
                    "[%s] _check_symbol_is_flat: Malformed positions snapshot, FAIL-CLOSED (NRR-PORTFOLIO-UNKNOWN)",
                    symbol,
                )
                return False

            curr_pos = next(
                (
                    pos
                    for pos in positions
                    if isinstance(pos, dict) and pos.get("symbol") == symbol
                ),
                None,
            )
            if curr_pos is None:
                return True

            qty_signed = self._extract_signed_position_qty(curr_pos)
            if qty_signed is None:
                self.logger.warning(
                    "[%s] _check_symbol_is_flat: Position qty unreadable, FAIL-CLOSED (NRR-PORTFOLIO-UNKNOWN)",
                    symbol,
                )
                return False

            return abs(qty_signed) <= decimal.Decimal("1e-9")
        except Exception as exc:
            self.logger.warning(
                "[%s] _check_symbol_is_flat error: %s, FAIL-CLOSED (NRR-PORTFOLIO-UNKNOWN)",
                symbol,
                exc,
            )
            return False

    def calculate_position_size(
        self,
        symbol: str,
        price: decimal.Decimal,
        side: str,
        context: dict[str, Any],
        *,
        margin_pct_mult: decimal.Decimal | None = None,
    ) -> tuple[Optional[Decimal], str, Optional[str], dict[str, Any]]:
        del side

        portfolio = context.get("portfolio") if isinstance(
            context, dict) else None
        if not isinstance(portfolio, dict):
            return None, "portfolio_missing", "PORTFOLIO_MISSING", {}

        equity = self.safe_decimal(
            portfolio.get("equity", "0"), default=decimal.Decimal("0")
        )
        if equity <= 0:
            return None, f"equity_invalid:{equity}", "ZERO_EQUITY", {"equity": str(equity)}

        if price <= 0:
            return None, "price_invalid", "INVALID_PRICE", {"price": str(price)}

        instruments = _field(self.config, "instruments")
        try:
            spec = instruments[symbol]
        except Exception as exc:
            return None, f"unknown_instrument:{symbol}:{exc}", "UNKNOWN_INSTRUMENT", {"symbol": str(symbol)}

        sizing = _field(spec, "sizing")
        execution = _field(spec, "execution")
        margin_pct_base = decimal.Decimal(str(_field(sizing, "margin_pct")))
        fee_buffer = self.safe_decimal(_field(sizing, "fee_buffer_fraction"))
        if fee_buffer is None or fee_buffer < 0 or fee_buffer >= 1:
            return (
                None,
                "missing_or_invalid_fee_buffer_fraction",
                "CONFIG_REGIME_SIZING_INVALID",
                {"fee_buffer_fraction": str(
                    _field(sizing, "fee_buffer_fraction"))},
            )
        margin_pct = margin_pct_base
        if margin_pct_mult is not None:
            try:
                if margin_pct_mult <= 0:
                    return (
                        None,
                        f"invalid_margin_pct_mult:{margin_pct_mult}",
                        "CONFIG_REGIME_SIZING_INVALID",
                        {"margin_pct_mult": str(margin_pct_mult)},
                    )
                margin_pct = margin_pct_base * margin_pct_mult
                if margin_pct > decimal.Decimal("1"):
                    margin_pct = decimal.Decimal("1")
            except Exception as exc:
                return (
                    None,
                    f"invalid_margin_pct_mult:{margin_pct_mult}:{exc}",
                    "CONFIG_REGIME_SIZING_INVALID",
                    {"margin_pct_mult": str(
                        margin_pct_mult), "error": str(exc)},
                )

        leverage = int(_field(execution, "target_leverage"))
        step_size = self.safe_decimal(_field(spec, "step_size"))
        min_qty = self.safe_decimal(_field(spec, "min_qty"))
        min_notional = self.safe_decimal(_field(spec, "min_notional"))
        if step_size is None or min_qty is None or min_notional is None:
            return (
                None,
                "invalid_exchange_constraints",
                "CONFIG_REGIME_SIZING_INVALID",
                {
                    "step_size": str(_field(spec, "step_size")),
                    "min_qty": str(_field(spec, "min_qty")),
                    "min_notional": str(_field(spec, "min_notional")),
                },
            )

        margin_usdt, notional_target = compute_notional_target(
            equity=equity,
            margin_pct=margin_pct,
            leverage=leverage,
            notional_cap=self.liq_cap_usd,
            fee_buffer=fee_buffer,
        )
        raw_qty, rounded_qty = compute_qty(
            notional_target=notional_target,
            price=price,
            step_size=step_size,
        )
        order_notional = rounded_qty * price

        sizing_dbg: dict[str, Any] = {
            "equity": str(equity),
            "margin_pct_base": str(margin_pct_base),
            "margin_pct_mult": str(margin_pct_mult) if margin_pct_mult is not None else None,
            "margin_pct": str(margin_pct),
            "fee_buffer_fraction": str(fee_buffer),
            "margin_usdt": str(margin_usdt),
            "leverage": int(leverage),
            "notional_target": str(notional_target),
            "price": str(price),
            "raw_qty": str(raw_qty),
            "rounded_qty": str(rounded_qty),
            "order_notional": str(order_notional),
            "step_size": str(step_size),
            "min_qty": str(min_qty),
            "min_notional": str(min_notional),
            "liq_cap_usd": str(self.liq_cap_usd),
            "min_position_size_usd": str(self.min_pos_size_usd),
        }

        reject_code, constraint_why = validate_exchange_constraints(
            qty=rounded_qty,
            price=price,
            min_qty=min_qty,
            min_notional=min_notional,
        )
        if reject_code is not None:
            reject_reason = f"exchange_constraints:{reject_code}:{constraint_why}"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            return (
                None,
                f"{reject_reason} (NRR: {normalized_reason})",
                reject_code,
                sizing_dbg,
            )

        if order_notional < self.min_pos_size_usd:
            reject_reason = (
                f"position notional {order_notional} is below minimum {self.min_pos_size_usd}"
            )
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            return (
                None,
                f"{reject_reason} (NRR: {normalized_reason})",
                "MIN_POSITION_USD",
                sizing_dbg,
            )

        return rounded_qty, "margin_first_ok", None, sizing_dbg
