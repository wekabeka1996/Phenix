"""Data contract: required columns/dtypes + semantic invariants for data sources.

Phase 0.0 — offline tooling. Used by backtest engine and data-prep scripts
to fail-fast when dataframes violate the contract.

Supports:
  - OHLCV (price bars)
  - L2 (orderbook snapshots)

Design rules:
  - No silent fallbacks: missing column → ValueError at load time.
  - Dtype check accepts float32/float64 (both numeric), not pinned to float64.
  - Semantic invariants (bid < ask, spread > 0, qty >= 0) checked post-load.
"""

from __future__ import annotations

from typing import List, Literal, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


# ═══════════════════════════════════════════════════════════════════
# Column specification
# ═══════════════════════════════════════════════════════════════════

class ColumnSpec(BaseModel):
    """Single column requirement."""
    model_config = ConfigDict(extra='forbid', frozen=True)

    name: str = Field(description='Column name in DataFrame')
    dtype_class: Literal["numeric", "datetime"] = Field(
        description='Expected dtype class. numeric = float32/float64/int64. datetime = datetime64[ns, UTC].'
    )
    nullable: bool = Field(
        default=False,
        description='Whether NaN/NaT is allowed in this column'
    )


# ═══════════════════════════════════════════════════════════════════
# OHLCV contract
# ═══════════════════════════════════════════════════════════════════

_OHLCV_COLUMNS: List[ColumnSpec] = [
    ColumnSpec(name="timestamp", dtype_class="datetime", nullable=False),
    ColumnSpec(name="open", dtype_class="numeric", nullable=False),
    ColumnSpec(name="high", dtype_class="numeric", nullable=False),
    ColumnSpec(name="low", dtype_class="numeric", nullable=False),
    ColumnSpec(name="close", dtype_class="numeric", nullable=False),
    ColumnSpec(name="volume", dtype_class="numeric", nullable=False),
]


class OHLCVContract(BaseModel):
    """Required columns/dtypes for OHLCV (price bar) data."""
    model_config = ConfigDict(extra='forbid', frozen=True)

    required_columns: List[ColumnSpec] = Field(default_factory=lambda: list(_OHLCV_COLUMNS))


# ═══════════════════════════════════════════════════════════════════
# L2 (orderbook) contract
# ═══════════════════════════════════════════════════════════════════

_L2_COLUMNS: List[ColumnSpec] = [
    ColumnSpec(name="timestamp", dtype_class="datetime", nullable=False),
    ColumnSpec(name="bid_price", dtype_class="numeric", nullable=False),
    ColumnSpec(name="bid_qty", dtype_class="numeric", nullable=False),
    ColumnSpec(name="ask_price", dtype_class="numeric", nullable=False),
    ColumnSpec(name="ask_qty", dtype_class="numeric", nullable=False),
]


class L2Contract(BaseModel):
    """Required columns/dtypes for L2 (orderbook snapshot) data."""
    model_config = ConfigDict(extra='forbid', frozen=True)

    required_columns: List[ColumnSpec] = Field(default_factory=lambda: list(_L2_COLUMNS))


# ═══════════════════════════════════════════════════════════════════
# Top-level DataContract
# ═══════════════════════════════════════════════════════════════════

class DataContract(BaseModel):
    """Fail-fast data contract: validate DataFrame columns + semantics at load time.

    Usage::

        contract = DataContract()
        contract.validate_dataframe(ohlcv_df, source="ohlcv")

        # With L2 enabled:
        contract = DataContract(l2=L2Contract())
        contract.validate_dataframe(l2_df, source="l2")
    """
    model_config = ConfigDict(extra='forbid', frozen=True)

    ohlcv: OHLCVContract = Field(default_factory=OHLCVContract)
    l2: Optional[L2Contract] = Field(default=None)

    def validate_dataframe(
        self,
        df: pd.DataFrame,
        *,
        source: Literal["ohlcv", "l2"] = "ohlcv",
        check_semantics: bool = True,
    ) -> None:
        """Validate df against the contract. Raises ValueError on violation.

        Args:
            df: DataFrame to validate.
            source: Which contract to validate against.
            check_semantics: Whether to run semantic invariant checks.

        Raises:
            ValueError: On missing columns, wrong dtypes, null violations,
                or semantic invariant failures.
        """
        if source == "ohlcv":
            contract = self.ohlcv
        elif source == "l2":
            contract = self.l2
        else:
            raise ValueError(f"Unknown source: {source!r}")

        if contract is None:
            raise ValueError(
                f"No contract defined for source={source!r}. "
                "Set l2=L2Contract() to enable L2 validation."
            )

        errors: List[str] = []

        # 1) Missing columns
        required_names = [c.name for c in contract.required_columns]
        missing = [name for name in required_names if name not in df.columns]
        if missing:
            errors.append(f"missing columns: {missing}")

        # 2) Dtype class check (only for columns that exist)
        for col_spec in contract.required_columns:
            if col_spec.name not in df.columns:
                continue
            col = df[col_spec.name]
            if col_spec.dtype_class == "numeric":
                if not pd.api.types.is_numeric_dtype(col):
                    errors.append(
                        f"column '{col_spec.name}': expected numeric, got {col.dtype}"
                    )
            elif col_spec.dtype_class == "datetime":
                if not pd.api.types.is_datetime64_any_dtype(col):
                    errors.append(
                        f"column '{col_spec.name}': expected datetime, got {col.dtype}"
                    )

        # 3) Null check (only for columns that exist)
        for col_spec in contract.required_columns:
            if col_spec.name not in df.columns:
                continue
            if not col_spec.nullable and df[col_spec.name].isna().any():
                null_count = int(df[col_spec.name].isna().sum())
                errors.append(
                    f"column '{col_spec.name}': {null_count} null(s) in non-nullable column"
                )

        # 4) Semantic invariants (only if no structural errors — dtype mismatch
        #    would cause comparison crashes in semantic checks)
        if check_semantics and not missing and not errors:
            semantic_errors = self._check_semantics(df, source=source)
            errors.extend(semantic_errors)

        if errors:
            raise ValueError(
                f"DataContract violation ({source}): " + "; ".join(errors)
            )

    @staticmethod
    def _check_semantics(
        df: pd.DataFrame,
        *,
        source: str,
    ) -> List[str]:
        """Check semantic invariants beyond column existence/dtype."""
        errors: List[str] = []

        if source == "ohlcv":
            # high >= low
            if "high" in df.columns and "low" in df.columns:
                bad = (df["high"] < df["low"]).sum()
                if bad > 0:
                    errors.append(f"OHLCV invariant: {bad} rows with high < low")
            # high >= open, high >= close
            if "high" in df.columns and "open" in df.columns:
                bad = (df["high"] < df["open"]).sum()
                if bad > 0:
                    errors.append(f"OHLCV invariant: {bad} rows with high < open")
            if "high" in df.columns and "close" in df.columns:
                bad = (df["high"] < df["close"]).sum()
                if bad > 0:
                    errors.append(f"OHLCV invariant: {bad} rows with high < close")
            # low <= open, low <= close
            if "low" in df.columns and "open" in df.columns:
                bad = (df["low"] > df["open"]).sum()
                if bad > 0:
                    errors.append(f"OHLCV invariant: {bad} rows with low > open")
            if "low" in df.columns and "close" in df.columns:
                bad = (df["low"] > df["close"]).sum()
                if bad > 0:
                    errors.append(f"OHLCV invariant: {bad} rows with low > close")
            # volume >= 0
            if "volume" in df.columns:
                bad = (df["volume"] < 0).sum()
                if bad > 0:
                    errors.append(f"OHLCV invariant: {bad} rows with volume < 0")
            # timestamp UTC check
            if "timestamp" in df.columns:
                ts_col = df["timestamp"]
                if hasattr(ts_col.dtype, 'tz') and ts_col.dtype.tz is not None:
                    tz_name = str(ts_col.dtype.tz)
                    if tz_name != "UTC":
                        errors.append(
                            f"OHLCV invariant: timestamp timezone is {tz_name}, expected UTC"
                        )

        elif source == "l2":
            # bid_price < ask_price (strict)
            if "bid_price" in df.columns and "ask_price" in df.columns:
                bad = (df["bid_price"] >= df["ask_price"]).sum()
                if bad > 0:
                    errors.append(f"L2 invariant: {bad} rows with bid_price >= ask_price")
            # qty >= 0
            for qty_col in ("bid_qty", "ask_qty"):
                if qty_col in df.columns:
                    bad = (df[qty_col] < 0).sum()
                    if bad > 0:
                        errors.append(f"L2 invariant: {bad} rows with {qty_col} < 0")
            # timestamp UTC check
            if "timestamp" in df.columns:
                ts_col = df["timestamp"]
                if hasattr(ts_col.dtype, 'tz') and ts_col.dtype.tz is not None:
                    tz_name = str(ts_col.dtype.tz)
                    if tz_name != "UTC":
                        errors.append(
                            f"L2 invariant: timestamp timezone is {tz_name}, expected UTC"
                        )

        return errors
