"""
PositionQueries — Position state, sizing, and portfolio queries.

Extracted from decision_making.py (Phase 14A decomposition).
Pure queries against portfolio cache and config. No FSM side effects.

LOC budget: ≤500 (Constitution §3).
"""

import decimal
import logging
from decimal import Decimal
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from .normalized_reject_reasons import NormalizedRejectReasons
from .sizing_margin_first import (
    compute_notional_target,
    compute_qty,
    validate_exchange_constraints,
)

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig


class PositionQueries:
    """
    Position state, sizing computation, and portfolio queries.

    Dependencies are injected to keep the module decoupled from facade state.
    `get_portfolio` is a callable that returns the latest portfolio dict (mutable).
    """

    def __init__(
        self,
        config: "AuroraConfig",
        get_portfolio: Callable[[], Optional[Dict]],
        min_pos_size_usd: Decimal,
        liq_cap_usd: Decimal,
        logger: logging.Logger,
    ) -> None:
        self.config = config
        self._get_portfolio = get_portfolio
        self.min_pos_size_usd = min_pos_size_usd
        self.liq_cap_usd = liq_cap_usd
        self.logger = logger

    # ── Utility ──────────────────────────────────────────────────────

    @staticmethod
    def safe_decimal(
        value: Any,
        default: Optional[Decimal] = None,
    ) -> Optional[Decimal]:
        """Best-effort Decimal parser for untrusted inputs. Never raises."""
        if value is None:
            return default
        if isinstance(value, Decimal):
            return value if value.is_finite() else default
        try:
            d = Decimal(str(value))
        except Exception:
            return default
        return d if d.is_finite() else default

    # ── Position State ───────────────────────────────────────────────

    def get_position_state(self, symbol: str) -> str:
        """
        Get current position state from SSOT (latest_portfolio).
        Returns: FLAT, LONG, SHORT, UNKNOWN
        """
        qty_signed, _ = self.get_portfolio_position_qty_signed(symbol)
        if qty_signed is None:
            return "UNKNOWN"

        try:
            tol = decimal.Decimal("1e-9")
        except Exception:
            tol = decimal.Decimal(str(1e-9))

        if abs(qty_signed) < tol:
            return "FLAT"

        return "LONG" if qty_signed > 0 else "SHORT"

    def get_portfolio_position_qty_signed(
        self, symbol: str
    ) -> tuple:
        """Return signed position qty for a symbol from latest_portfolio (SSOT), or None if unknown."""
        portfolio = self._get_portfolio()
        if not isinstance(portfolio, dict):
            return None, None

        positions = portfolio.get("positions")
        if not isinstance(positions, list):
            return None, None

        curr_pos = next(
            (p for p in positions if isinstance(p, dict) and p.get("symbol") == symbol), None
        )
        if not curr_pos:
            return decimal.Decimal("0"), None

        qty_val: Any = None
        for key in (
            "net_position",
            "positionAmt",
            "position_amount",
            "position_amt",
            "qty",
            "quantity",
        ):
            if key in curr_pos and curr_pos.get(key) not in (None, ""):
                qty_val = curr_pos.get(key)
                break

        if qty_val in (None, ""):
            return None, curr_pos

        try:
            return decimal.Decimal(str(qty_val)), curr_pos
        except Exception:
            return None, curr_pos

    def check_symbol_is_flat(self, symbol: str) -> bool:
        """
        Check if portfolio position for symbol is FLAT (no position).

        STRICT SEQUENTIAL TRADING CONTRACT:
        Per-symbol check - ETH position doesn't block DOGE OPEN.

        FAIL-CLOSED (Commit 4.1):
        - Unknown portfolio -> NOT FLAT -> DEFER
        - Exception -> NOT FLAT -> DEFER
        """
        try:
            portfolio = self._get_portfolio()
            if not portfolio:
                self.logger.warning(
                    f"[{symbol}] _check_symbol_is_flat: No portfolio data, "
                    f"FAIL-CLOSED (NRR-PORTFOLIO-UNKNOWN)"
                )
                return False

            positions = portfolio["positions"] if (isinstance(portfolio, dict) and "positions" in portfolio) else []
            if not positions:
                return True

            for pos in positions:
                pos_symbol = pos["symbol"] if "symbol" in pos else ""
                if pos_symbol != symbol:
                    continue

                qty_str = pos["positionAmt"] if "positionAmt" in pos else "0"
                try:
                    qty = abs(float(qty_str))
                except (ValueError, TypeError):
                    qty = 0.0

                flat_threshold = 1e-9
                if qty > flat_threshold:
                    self.logger.debug(f"[{symbol}] _check_symbol_is_flat: Position exists, qty={qty}")
                    return False

            return True

        except Exception as e:
            self.logger.warning(
                f"[{symbol}] _check_symbol_is_flat error: {e}, "
                f"FAIL-CLOSED (NRR-PORTFOLIO-UNKNOWN)"
            )
            return False

    # ── Sizing ───────────────────────────────────────────────────────

    def calculate_position_size(
        self,
        symbol: str,
        price: decimal.Decimal,
        side: str,
        context: dict,
        *,
        margin_pct_mult: decimal.Decimal | None = None,
    ) -> tuple:
        """Compute order quantity using margin-first SSOT.

        SSOT inputs:
        - instruments.<SYM>.sizing.margin_pct
        - instruments.<SYM>.execution.target_leverage
        - instruments.<SYM>.{step_size,min_qty,min_notional}

        Margin-first:
        - margin_usdt = equity * margin_pct
        - notional_target = margin_usdt * leverage
        - qty = floor_to_step(notional_target / price, step_size)
        """
        portfolio = context.get("portfolio") if isinstance(context, dict) else None
        if not isinstance(portfolio, dict):
            return None, "portfolio_missing", "PORTFOLIO_MISSING", {}

        equity = self.safe_decimal(portfolio.get("equity", "0"), default=decimal.Decimal("0"))
        if equity is None:
            return None, "equity_invalid:None", "ZERO_EQUITY", {"equity": str(portfolio.get("equity"))}
        if equity <= 0:
            return None, f"equity_invalid:{equity}", "ZERO_EQUITY", {"equity": str(equity)}

        if price <= 0:
            return None, "price_invalid", "INVALID_PRICE", {"price": str(price)}

        try:
            spec = self.config.instruments[symbol]
        except Exception as e:
            return None, f"unknown_instrument:{symbol}:{e}", "UNKNOWN_INSTRUMENT", {"symbol": str(symbol)}
        margin_pct_base = decimal.Decimal(str(spec.sizing.margin_pct))
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
            except Exception as e:
                return (
                    None,
                    f"invalid_margin_pct_mult:{margin_pct_mult}:{e}",
                    "CONFIG_REGIME_SIZING_INVALID",
                    {"margin_pct_mult": str(margin_pct_mult), "error": str(e)},
                )
        leverage = int(spec.execution.target_leverage)
        step_size = self.safe_decimal(spec.step_size)
        min_qty = self.safe_decimal(spec.min_qty)
        min_notional = self.safe_decimal(spec.min_notional)
        if step_size is None or min_qty is None or min_notional is None:
            return (
                None,
                "invalid_exchange_constraints",
                "CONFIG_REGIME_SIZING_INVALID",
                {
                    "step_size": str(getattr(spec, "step_size", None)),
                    "min_qty": str(getattr(spec, "min_qty", None)),
                    "min_notional": str(getattr(spec, "min_notional", None)),
                },
            )

        margin_usdt, notional_target = compute_notional_target(
            equity=equity,
            margin_pct=margin_pct,
            leverage=leverage,
            notional_cap=self.liq_cap_usd,
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

        self.logger.info(
            f"[{symbol}] MARGIN_FIRST_SIZING: equity=${equity}, margin_pct={margin_pct}, "
            f"margin_usdt=${margin_usdt}, leverage={leverage}, notional_target=${notional_target}, "
            f"liq_cap=${self.liq_cap_usd}"
        )
        self.logger.info(
            f"[{symbol}] QTY_CALC: price=${price}, raw_qty={raw_qty}, step_size={step_size}, "
            f"rounded_qty={rounded_qty}, notional=${order_notional}, "
            f"min_qty={min_qty}, min_notional={min_notional}"
        )

        reject_code, constraint_why = validate_exchange_constraints(
            qty=rounded_qty,
            price=price,
            min_qty=min_qty,
            min_notional=min_notional,
        )
        if reject_code is not None:
            reject_reason = f"exchange_constraints:{reject_code}:{constraint_why}"
            normalized_reason = NormalizedRejectReasons.normalize(reject_reason)
            return None, f"{reject_reason} (NRR: {normalized_reason})", reject_code, sizing_dbg

        if order_notional < self.min_pos_size_usd:
            reject_reason = f"position notional {order_notional} is below minimum {self.min_pos_size_usd}"
            normalized_reason = NormalizedRejectReasons.normalize(reject_reason)
            return None, f"{reject_reason} (NRR: {normalized_reason})", "MIN_POSITION_USD", sizing_dbg

        return rounded_qty, "margin_first_ok", None, sizing_dbg
