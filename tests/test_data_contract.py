"""Tests for DataContract (Phase 0.0) — column/dtype/semantic validation.

PKG-0.0B: tools/parquet_contract/data_contract.py.
"""

import numpy as np
import pandas as pd
import pytest

from tools.parquet_contract.data_contract import (
    ColumnSpec,
    DataContract,
    L2Contract,
    OHLCVContract,
)


# ═══════════════════════════════════════════════════════════════════
# Helpers — valid fixture dataframes
# ═══════════════════════════════════════════════════════════════════

def _valid_ohlcv_df(n: int = 5) -> pd.DataFrame:
    """Minimal valid OHLCV DataFrame."""
    ts = pd.date_range("2025-01-01", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts,
        "open": np.linspace(100.0, 105.0, n),
        "high": np.linspace(106.0, 110.0, n),
        "low": np.linspace(99.0, 100.0, n),
        "close": np.linspace(101.0, 104.0, n),
        "volume": np.linspace(1000.0, 5000.0, n),
    })


def _valid_l2_df(n: int = 5) -> pd.DataFrame:
    """Minimal valid L2 orderbook DataFrame."""
    ts = pd.date_range("2025-01-01", periods=n, freq="1s", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts,
        "bid_price": np.linspace(99.0, 100.0, n),
        "bid_qty": np.full(n, 10.0),
        "ask_price": np.linspace(100.1, 101.0, n),
        "ask_qty": np.full(n, 8.0),
    })


# ═══════════════════════════════════════════════════════════════════
# ColumnSpec tests
# ═══════════════════════════════════════════════════════════════════

class TestColumnSpec:
    def test_valid_numeric(self):
        cs = ColumnSpec(name="open", dtype_class="numeric")
        assert cs.name == "open"
        assert cs.nullable is False

    def test_valid_datetime(self):
        cs = ColumnSpec(name="timestamp", dtype_class="datetime", nullable=False)
        assert cs.dtype_class == "datetime"

    def test_frozen(self):
        cs = ColumnSpec(name="open", dtype_class="numeric")
        with pytest.raises(Exception):  # frozen=True
            cs.name = "close"

    def test_extra_field_forbidden(self):
        with pytest.raises(Exception):
            ColumnSpec(name="open", dtype_class="numeric", extra_field="bad")


# ═══════════════════════════════════════════════════════════════════
# OHLCV validation
# ═══════════════════════════════════════════════════════════════════

class TestOHLCVContract:
    def test_valid_ohlcv_passes(self):
        contract = DataContract()
        df = _valid_ohlcv_df()
        contract.validate_dataframe(df, source="ohlcv")  # no exception

    def test_missing_column_raises(self):
        contract = DataContract()
        df = _valid_ohlcv_df().drop(columns=["close"])
        with pytest.raises(ValueError, match="missing columns.*close"):
            contract.validate_dataframe(df, source="ohlcv")

    def test_multiple_missing_columns(self):
        contract = DataContract()
        df = _valid_ohlcv_df().drop(columns=["close", "volume"])
        with pytest.raises(ValueError, match="missing columns"):
            contract.validate_dataframe(df, source="ohlcv")

    def test_wrong_dtype_string_column(self):
        contract = DataContract()
        df = _valid_ohlcv_df()
        df["open"] = "not_a_number"
        with pytest.raises(ValueError, match="expected numeric"):
            contract.validate_dataframe(df, source="ohlcv")

    def test_float32_accepted(self):
        """float32 is valid numeric — not pinned to float64."""
        contract = DataContract()
        df = _valid_ohlcv_df()
        df["open"] = df["open"].astype(np.float32)
        contract.validate_dataframe(df, source="ohlcv")  # no exception

    def test_null_in_non_nullable_raises(self):
        contract = DataContract()
        df = _valid_ohlcv_df()
        df.loc[0, "close"] = np.nan
        with pytest.raises(ValueError, match="null.*non-nullable"):
            contract.validate_dataframe(df, source="ohlcv")

    def test_high_less_than_low_raises(self):
        contract = DataContract()
        df = _valid_ohlcv_df()
        df.loc[0, "high"] = 50.0  # high < low
        with pytest.raises(ValueError, match="high < low"):
            contract.validate_dataframe(df, source="ohlcv")

    def test_high_less_than_open_raises(self):
        contract = DataContract()
        df = _valid_ohlcv_df()
        df.loc[0, "high"] = 90.0  # below open=100
        df.loc[0, "low"] = 89.0   # keep low consistent
        with pytest.raises(ValueError, match="high < open"):
            contract.validate_dataframe(df, source="ohlcv")

    def test_negative_volume_raises(self):
        contract = DataContract()
        df = _valid_ohlcv_df()
        df.loc[0, "volume"] = -100.0
        with pytest.raises(ValueError, match="volume < 0"):
            contract.validate_dataframe(df, source="ohlcv")

    def test_non_utc_timezone_raises(self):
        contract = DataContract()
        df = _valid_ohlcv_df()
        df["timestamp"] = df["timestamp"].dt.tz_convert("US/Eastern")
        with pytest.raises(ValueError, match="expected UTC"):
            contract.validate_dataframe(df, source="ohlcv")

    def test_semantics_skip(self):
        """check_semantics=False skips invariant checks."""
        contract = DataContract()
        df = _valid_ohlcv_df()
        df.loc[0, "high"] = 50.0  # high < low — would fail semantics
        # Should NOT raise because semantics are disabled
        contract.validate_dataframe(df, source="ohlcv", check_semantics=False)


# ═══════════════════════════════════════════════════════════════════
# L2 validation
# ═══════════════════════════════════════════════════════════════════

class TestL2Contract:
    def test_l2_not_configured_raises(self):
        """L2 disabled by default → requesting source='l2' raises."""
        contract = DataContract()  # l2=None
        df = _valid_l2_df()
        with pytest.raises(ValueError, match="No contract defined for source='l2'"):
            contract.validate_dataframe(df, source="l2")

    def test_valid_l2_passes(self):
        contract = DataContract(l2=L2Contract())
        df = _valid_l2_df()
        contract.validate_dataframe(df, source="l2")  # no exception

    def test_l2_missing_column(self):
        contract = DataContract(l2=L2Contract())
        df = _valid_l2_df().drop(columns=["ask_price"])
        with pytest.raises(ValueError, match="missing columns.*ask_price"):
            contract.validate_dataframe(df, source="l2")

    def test_bid_ge_ask_raises(self):
        """bid_price >= ask_price → semantic violation."""
        contract = DataContract(l2=L2Contract())
        df = _valid_l2_df()
        df.loc[0, "bid_price"] = 200.0  # bid > ask
        with pytest.raises(ValueError, match="bid_price >= ask_price"):
            contract.validate_dataframe(df, source="l2")

    def test_negative_qty_raises(self):
        contract = DataContract(l2=L2Contract())
        df = _valid_l2_df()
        df.loc[0, "bid_qty"] = -5.0
        with pytest.raises(ValueError, match="bid_qty < 0"):
            contract.validate_dataframe(df, source="l2")

    def test_l2_non_utc_raises(self):
        contract = DataContract(l2=L2Contract())
        df = _valid_l2_df()
        df["timestamp"] = df["timestamp"].dt.tz_convert("Europe/London")
        with pytest.raises(ValueError, match="expected UTC"):
            contract.validate_dataframe(df, source="l2")


# ═══════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════

class TestDataContractEdgeCases:
    def test_unknown_source_raises(self):
        contract = DataContract()
        df = _valid_ohlcv_df()
        with pytest.raises(ValueError, match="Unknown source"):
            contract.validate_dataframe(df, source="futures")

    def test_empty_dataframe_passes_if_columns_present(self):
        """Empty df with correct columns/dtypes → pass (no rows to violate)."""
        contract = DataContract()
        df = _valid_ohlcv_df().iloc[:0]
        contract.validate_dataframe(df, source="ohlcv")  # no exception

    def test_ohlcv_contract_default_column_count(self):
        contract = OHLCVContract()
        assert len(contract.required_columns) == 6

    def test_l2_contract_default_column_count(self):
        contract = L2Contract()
        assert len(contract.required_columns) == 5

    def test_contract_frozen(self):
        contract = DataContract()
        with pytest.raises(Exception):
            contract.ohlcv = OHLCVContract()
