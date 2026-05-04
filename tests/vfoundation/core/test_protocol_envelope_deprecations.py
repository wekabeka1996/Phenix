"""Tests for Message envelope deprecation warnings — Phase 14.3."""
import warnings

import pytest

from vfoundation.core.protocol import Message
from vfoundation.core.data_ref import DataRef


VALID_SHA256 = "a" * 64


class TestEnvelopeDeprecations:
    """Phase 14.3: Deprecation warnings for trading-specific envelope fields."""

    def test_oco_group_id_emits_deprecation_warning(self):
        """Setting oco_group_id at top-level emits DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            msg = Message(
                op="CMD",
                verb="OPEN",
                src="test",
                dst="test",
                oco_group_id="oco_123",
            )
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1
            assert "oco_group_id" in str(deprecation_warnings[0].message)
            assert "deprecated" in str(deprecation_warnings[0].message).lower()

    def test_data_ref_accepts_string_list_backward_compat(self):
        """data_ref still accepts List[str] for backward compatibility."""
        msg = Message(
            op="EVT",
            verb="DATA",
            src="test",
            dst="test",
            data_ref=["s3://bucket/file.parquet", "s3://bucket/other.csv"],
        )
        assert len(msg.data_ref) == 2
        assert msg.data_ref[0] == "s3://bucket/file.parquet"
        assert isinstance(msg.data_ref[0], str)

    def test_data_ref_accepts_dataref_objects(self):
        """data_ref accepts DataRef objects alongside strings (Phase 16.3)."""
        msg = Message(
            op="EVT",
            verb="DATA",
            src="test",
            dst="test",
            data_ref=[
                "s3://bucket/simple.csv",
                {
                    "uri": "s3://bucket/structured.parquet",
                    "sha256": VALID_SHA256,
                    "bytes": 1024,
                },
            ],
        )
        assert len(msg.data_ref) == 2
        assert isinstance(msg.data_ref[0], str)
        assert isinstance(msg.data_ref[1], DataRef)
        assert msg.data_ref[1].uri == "s3://bucket/structured.parquet"
        assert msg.data_ref[1].bytes == 1024
