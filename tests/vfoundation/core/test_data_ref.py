"""Tests for DataRef Model — Phase 16.3."""
import pytest

from vfoundation.core.data_ref import DataRef, coerce_data_ref


VALID_SHA256 = "a" * 64


class TestDataRefModel:
    """Phase 16.3: DataRef Pydantic model tests."""

    def test_creation_valid(self):
        """Create a valid DataRef with all fields."""
        ref = DataRef(
            uri="s3://bucket/data.parquet",
            sha256=VALID_SHA256,
            bytes=1234567,
            ctype="application/parquet",
            ttl_ms=600_000,
        )
        assert ref.uri == "s3://bucket/data.parquet"
        assert ref.sha256 == VALID_SHA256
        assert ref.bytes == 1234567
        assert ref.ctype == "application/parquet"
        assert ref.ttl_ms == 600_000

    def test_sha256_validation_rejects_short(self):
        """sha256 must be exactly 64 hex characters."""
        with pytest.raises(ValueError, match="64 hex"):
            DataRef(uri="s3://x", sha256="abc123")

    def test_sha256_validation_rejects_non_hex(self):
        """sha256 must contain only hex characters."""
        with pytest.raises(ValueError, match="64 hex"):
            DataRef(uri="s3://x", sha256="g" * 64)  # 'g' is not hex

    def test_bytes_negative_rejected(self):
        """bytes must be >= 0."""
        with pytest.raises(ValueError):
            DataRef(uri="s3://x", sha256=VALID_SHA256, bytes=-1)

    def test_ttl_range_lower_bound(self):
        """ttl_ms must be >= 1."""
        with pytest.raises(ValueError):
            DataRef(uri="s3://x", sha256=VALID_SHA256, ttl_ms=0)

    def test_ttl_range_upper_bound(self):
        """ttl_ms must be <= 86_400_000 (24h)."""
        with pytest.raises(ValueError):
            DataRef(uri="s3://x", sha256=VALID_SHA256, ttl_ms=86_400_001)

    def test_defaults(self):
        """Default values: bytes=0, ctype=octet-stream, ttl=600000."""
        ref = DataRef(uri="s3://x", sha256=VALID_SHA256)
        assert ref.bytes == 0
        assert ref.ctype == "application/octet-stream"
        assert ref.ttl_ms == 600_000

    def test_serialization_roundtrip(self):
        """DataRef can be serialized to dict and back."""
        ref = DataRef(uri="s3://bucket/file", sha256=VALID_SHA256, bytes=100)
        data = ref.model_dump()
        restored = DataRef(**data)
        assert restored == ref


class TestCoerceDataRef:
    """Phase 16.3: coerce_data_ref() conversion tests."""

    def test_coerce_string_passthrough(self):
        """String values pass through unchanged."""
        result = coerce_data_ref("s3://bucket/file.parquet")
        assert result == "s3://bucket/file.parquet"
        assert isinstance(result, str)

    def test_coerce_dict_creates_dataref(self):
        """Dict values are parsed into DataRef instances."""
        result = coerce_data_ref({
            "uri": "s3://bucket/file",
            "sha256": VALID_SHA256,
            "bytes": 500,
        })
        assert isinstance(result, DataRef)
        assert result.uri == "s3://bucket/file"
        assert result.bytes == 500

    def test_coerce_dataref_passthrough(self):
        """DataRef instances pass through unchanged."""
        ref = DataRef(uri="s3://x", sha256=VALID_SHA256)
        result = coerce_data_ref(ref)
        assert result is ref

    def test_coerce_invalid_type_raises(self):
        """Non-str/dict/DataRef raises TypeError."""
        with pytest.raises(TypeError, match="Cannot coerce"):
            coerce_data_ref(42)
