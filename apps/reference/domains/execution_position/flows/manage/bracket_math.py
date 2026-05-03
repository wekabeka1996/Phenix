from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Union

DecimalLike = Union[Decimal, float, int, str]


@dataclass(frozen=True)
class BracketTargets:
    sl_price: Decimal
    tp1_price: Decimal
    tp2_price: Optional[Decimal] = None


def _to_decimal(value: DecimalLike) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def compute_bracket_targets(
    *,
    reference_price: DecimalLike,
    position_side: str,
    sl_pct: DecimalLike,
    tp_low_ratio: DecimalLike,
    tp_high_ratio: Optional[DecimalLike] = None,
) -> BracketTargets:
    """Compute raw TP/SL targets without quantization or safety offsets."""
    reference_price_dec = _to_decimal(reference_price)
    sl_pct_dec = _to_decimal(sl_pct)
    tp_low_ratio_dec = _to_decimal(tp_low_ratio)
    tp_high_ratio_dec = _to_decimal(
        tp_high_ratio) if tp_high_ratio is not None else None

    side = str(position_side or "").upper()
    if side not in {"BUY", "SELL"}:
        raise ValueError(
            f"Unsupported position side for bracket math: {position_side}")

    tp1_offset = sl_pct_dec * tp_low_ratio_dec
    tp2_offset = sl_pct_dec * tp_high_ratio_dec if tp_high_ratio_dec is not None else None

    if side == "BUY":
        return BracketTargets(
            sl_price=reference_price_dec * (Decimal("1") - sl_pct_dec),
            tp1_price=reference_price_dec * (Decimal("1") + tp1_offset),
            tp2_price=(
                reference_price_dec * (Decimal("1") + tp2_offset)
                if tp2_offset is not None
                else None
            ),
        )

    return BracketTargets(
        sl_price=reference_price_dec * (Decimal("1") + sl_pct_dec),
        tp1_price=reference_price_dec * (Decimal("1") - tp1_offset),
        tp2_price=(
            reference_price_dec * (Decimal("1") - tp2_offset)
            if tp2_offset is not None
            else None
        ),
    )
