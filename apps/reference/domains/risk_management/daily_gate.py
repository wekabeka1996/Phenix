from decimal import Decimal


def _fmt_pct(val) -> str:
    return f"{float(val):.1f}"   # рівно 1 знак після крапки


def _d(x) -> float:
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, (int, float)):
        return float(x)
    return float(Decimal(str(x)))

# у місці формування підсумку:
# summary["drawdown_pct"] = _fmt_pct(summary["drawdown_pct"])
