"""PKG-3 offline notional / qty / leverage helpers for Judge.

Pure read-only utilities used by the Judge outcomes materializer (PKG-1)
and any downstream USD ROI diagnostic. These helpers reuse the production
quantity normalizer (`apps/reference/domains/execution_position/guards/qty_normalizer.py`)
which has zero live-trading dependencies (stdlib only).

NO LIVE SIZING IS MUTATED HERE. This module is import-safe in offline tools.

Contract authority: `config/judge_simulator.yaml#judge_simulator.economics`
(EconomicsConfig in apps/reference/domains/alpha_search/judge/simulator/config_models.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Optional

import yaml

from apps.reference.domains.alpha_search.judge.simulator.config_models import (
    EconomicsConfig,
)
from apps.reference.domains.execution_position.guards.qty_normalizer import (
    QtyNormalizeResult,
    normalize_qty,
)


@dataclass(frozen=True)
class InstrumentPrecision:
    """Per-symbol precision snapshot loaded from config/aurora/instruments.yaml."""

    symbol: str
    step_size: Decimal
    min_qty: Decimal
    min_notional: Decimal
    target_leverage: Optional[int] = None


@dataclass(frozen=True)
class NotionalDerivationResult:
    """Outcome of qty derivation for one (symbol, entry_price) pair.

    ok=True iff a valid normalized qty was produced. ok=False carries an
    NRR code in `why` (mirrors qty_normalizer semantics). USD ROI is only
    computable when ok=True.
    """

    ok: bool
    symbol: str
    notional_usd: Decimal
    entry_price: Decimal
    raw_qty: Decimal
    normalized_qty: Optional[Decimal]
    realized_notional: Optional[Decimal]
    leverage: Optional[int]
    why: str = ""

    def to_manifest_dict(self) -> dict:
        out = {
            "ok": self.ok,
            "symbol": self.symbol,
            "notional_usd": str(self.notional_usd),
            "entry_price": str(self.entry_price),
            "raw_qty": str(self.raw_qty),
            "normalized_qty": (
                str(self.normalized_qty) if self.normalized_qty is not None else None
            ),
            "realized_notional": (
                str(self.realized_notional)
                if self.realized_notional is not None
                else None
            ),
            "leverage": self.leverage,
        }
        if self.why:
            out["why"] = self.why
        return out


def load_instrument_precision_map(
    instruments_config_path: str | Path,
) -> dict[str, InstrumentPrecision]:
    """Load per-symbol precision + leverage from config/aurora/instruments.yaml.

    Returns an immutable-style dict keyed by symbol (upper-case as written).
    Missing optional fields (target_leverage) become None — no fabrication.

    Raises FileNotFoundError if the path does not exist.
    Raises KeyError if a symbol entry is missing required precision fields.
    """
    path = Path(instruments_config_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Instruments config not found: {path} "
            "(PKG-3 fail-closed: cannot fabricate precision)"
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    instruments = raw.get("instruments") or {}
    if not isinstance(instruments, dict):
        raise ValueError(
            f"Instruments config root key 'instruments' must be a mapping in {path}"
        )

    out: dict[str, InstrumentPrecision] = {}
    for symbol, spec in instruments.items():
        if not isinstance(spec, dict):
            raise ValueError(
                f"Instrument entry for {symbol!r} must be a mapping in {path}"
            )
        for required in ("step_size", "min_qty", "min_notional"):
            if required not in spec:
                raise KeyError(
                    f"Instrument {symbol!r} missing required field {required!r} "
                    f"in {path} (PKG-3 fail-closed: no precision fabrication)"
                )
        execution = spec.get("execution") or {}
        leverage_raw = execution.get("target_leverage")
        leverage = int(leverage_raw) if leverage_raw is not None else None
        out[str(symbol)] = InstrumentPrecision(
            symbol=str(symbol),
            step_size=Decimal(str(spec["step_size"])),
            min_qty=Decimal(str(spec["min_qty"])),
            min_notional=Decimal(str(spec["min_notional"])),
            target_leverage=leverage,
        )
    return out


def derive_raw_qty(notional_usd: float | Decimal, entry_price: float | Decimal) -> Decimal:
    """qty = notional_usd / entry_price (no normalization, no rounding)."""
    notional_d = Decimal(str(notional_usd))
    price_d = Decimal(str(entry_price))
    if price_d <= 0:
        raise ValueError("entry_price must be > 0")
    if notional_d <= 0:
        raise ValueError("notional_usd must be > 0")
    return notional_d / price_d


def derive_notional_for_outcome(
    *,
    symbol: str,
    entry_price: float | Decimal,
    economics: EconomicsConfig,
    precision_map: dict[str, InstrumentPrecision],
) -> NotionalDerivationResult:
    """Derive qty / realized-notional / leverage for one outcome.

    Honors `economics.qty_normalization`, `economics.min_notional_policy`,
    and `economics.leverage_source`. Returns a structured result; callers
    decide whether to skip the outcome based on `result.ok`.

    Never silently bumps qty above min_qty. Never fabricates leverage.
    """
    notional_d = Decimal(str(economics.notional_usd_per_trade))
    price_d = Decimal(str(entry_price))
    raw_qty = derive_raw_qty(notional_d, price_d)

    if symbol not in precision_map:
        return NotionalDerivationResult(
            ok=False,
            symbol=symbol,
            notional_usd=notional_d,
            entry_price=price_d,
            raw_qty=raw_qty,
            normalized_qty=None,
            realized_notional=None,
            leverage=None,
            why="NRR-JUDGE-PRECISION-MISSING",
        )
    precision = precision_map[symbol]

    leverage: Optional[int]
    if economics.leverage_source == "instruments_yaml":
        leverage = precision.target_leverage  # None passes through; no fabrication
    else:
        leverage = None

    if economics.qty_normalization == "raw":
        realized = raw_qty * price_d
        if (
            economics.min_notional_policy == "fail_closed"
            and realized < precision.min_notional
        ):
            return NotionalDerivationResult(
                ok=False,
                symbol=symbol,
                notional_usd=notional_d,
                entry_price=price_d,
                raw_qty=raw_qty,
                normalized_qty=None,
                realized_notional=realized,
                leverage=leverage,
                why="NRR-NOTIONAL-BELOW-MIN",
            )
        return NotionalDerivationResult(
            ok=True,
            symbol=symbol,
            notional_usd=notional_d,
            entry_price=price_d,
            raw_qty=raw_qty,
            normalized_qty=raw_qty,
            realized_notional=realized,
            leverage=leverage,
        )

    # qty_normalization == "instrument_step_size"
    norm: QtyNormalizeResult = normalize_qty(
        raw_qty=raw_qty,
        price=price_d,
        step_size=precision.step_size,
        min_qty=precision.min_qty,
        min_notional=precision.min_notional,
    )
    if not norm.ok:
        return NotionalDerivationResult(
            ok=False,
            symbol=symbol,
            notional_usd=notional_d,
            entry_price=price_d,
            raw_qty=raw_qty,
            normalized_qty=norm.rounded_qty,
            realized_notional=norm.notional,
            leverage=leverage,
            why=norm.why,
        )
    return NotionalDerivationResult(
        ok=True,
        symbol=symbol,
        notional_usd=notional_d,
        entry_price=price_d,
        raw_qty=raw_qty,
        normalized_qty=norm.qty,
        realized_notional=norm.notional,
        leverage=leverage,
    )


def compute_roi_usd(
    *,
    entry_price: float | Decimal,
    exit_price: float | Decimal,
    qty: Decimal,
    side: str,
    leverage: Optional[int] = None,
) -> dict[str, Optional[Decimal]]:
    """Compute absolute and (optional) margin USD ROI for one closed trade.

    side must be "LONG" or "SHORT" (case-insensitive). Leverage, when
    provided, populates `roi_usd_margin`; otherwise that field is None.

    Returns a small dict so PKG-1 can record it in outcomes_manifest.json
    without inventing a new dataclass per call.
    """
    s = side.upper()
    if s not in {"LONG", "SHORT"}:
        raise ValueError(f"Unsupported side: {side}")
    entry_d = Decimal(str(entry_price))
    exit_d = Decimal(str(exit_price))
    if entry_d <= 0 or exit_d <= 0:
        raise ValueError("entry_price and exit_price must be > 0")
    price_diff = exit_d - entry_d if s == "LONG" else entry_d - exit_d
    roi_abs = price_diff * qty
    roi_margin = roi_abs * Decimal(leverage) if leverage else None
    return {"roi_usd_absolute": roi_abs, "roi_usd_margin": roi_margin}


def manifest_pointer_strings(economics_present: bool) -> dict[str, Optional[str]]:
    """Canonical PKG-1 manifest pointer strings for the notional contract.

    PKG-1 must record these strings in outcomes_manifest.json so the contract
    is auditable from the manifest alone (no need to read the YAML).
    """
    if not economics_present:
        return {
            "notional_source": None,
            "notional_mode": "pct_only",
            "fixed_notional_usd": None,
            "leverage_source": None,
            "qty_normalization": None,
            "min_notional_policy": None,
            "roi_usd_targets": None,
        }
    return {
        "notional_source": "config/judge_simulator.yaml#judge_simulator.economics",
        "notional_mode": "explicit_usd",
        "fixed_notional_usd": "config/judge_simulator.yaml#judge_simulator.economics.notional_usd_per_trade",
        "leverage_source": "config/judge_simulator.yaml#judge_simulator.economics.leverage_source",
        "qty_normalization": "config/judge_simulator.yaml#judge_simulator.economics.qty_normalization",
        "min_notional_policy": "config/judge_simulator.yaml#judge_simulator.economics.min_notional_policy",
        "roi_usd_targets": "config/judge_simulator.yaml#judge_simulator.economics.roi_usd_targets",
    }
