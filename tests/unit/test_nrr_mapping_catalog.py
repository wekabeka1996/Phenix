"""Test NRR code catalog completeness."""

import pytest
from vfoundation.core.why_codes import WhyCode


class TestNRRCatalog:
    """Test NRR code definitions and coverage."""

    def test_nrr_codes_exist(self):
        """Test that all expected NRR codes are defined."""
        expected_enum_names = [
            "NRR_011_EXPOSURE_LIMIT_EXCEEDED",
            "NRR_012_RATE_LIMIT_EXCEEDED",
            "NRR_013_EXPOSURE_BLOCK_COOLDOWN_ACTIVE",
            "NRR_014_SYMBOL_COOLDOWN_ACTIVE",
            "NRR_015_EXCHANGE_ORDER_REJECTED",
            "NRR_016_ORDER_TIMEOUT_EXPIRED",
            "NRR_017_SYMBOL_COOLDOWN_ACTIVE",
            "NRR_018_EXCHANGE_REJECTED_ORDER",
            "NRR_019_ORDER_TIMEOUT_EXPIRED",
        ]

        for enum_name in expected_enum_names:
            assert hasattr(WhyCode, enum_name)
            enum_value = getattr(WhyCode, enum_name)
            expected_code = f"NRR-{enum_name.split('_')[1]}"
            assert enum_value.value == expected_code

    def test_nrr_descriptions_exist(self):
        """Test that all NRR codes have descriptions."""
        from vfoundation.core.why_codes import get_why_description

        nrr_codes = [
            WhyCode.NRR_011_EXPOSURE_LIMIT_EXCEEDED,
            WhyCode.NRR_012_RATE_LIMIT_EXCEEDED,
            WhyCode.NRR_013_EXPOSURE_BLOCK_COOLDOWN_ACTIVE,
            WhyCode.NRR_014_SYMBOL_COOLDOWN_ACTIVE,
            WhyCode.NRR_015_EXCHANGE_ORDER_REJECTED,
            WhyCode.NRR_016_ORDER_TIMEOUT_EXPIRED,
            WhyCode.NRR_017_SYMBOL_COOLDOWN_ACTIVE,
            WhyCode.NRR_018_EXCHANGE_REJECTED_ORDER,
            WhyCode.NRR_019_ORDER_TIMEOUT_EXPIRED,
        ]

        for code in nrr_codes:
            description = get_why_description(code)
            assert description is not None
            assert len(description.strip()) > 0
            assert description != f"Unknown WHY code: {code.value}"

    def test_nrr_code_format(self):
        """Test NRR code format compliance."""
        import re

        nrr_codes = [
            WhyCode.NRR_011_EXPOSURE_LIMIT_EXCEEDED,
            WhyCode.NRR_012_RATE_LIMIT_EXCEEDED,
            WhyCode.NRR_013_EXPOSURE_BLOCK_COOLDOWN_ACTIVE,
            WhyCode.NRR_014_SYMBOL_COOLDOWN_ACTIVE,
            WhyCode.NRR_015_EXCHANGE_ORDER_REJECTED,
            WhyCode.NRR_016_ORDER_TIMEOUT_EXPIRED,
            WhyCode.NRR_017_SYMBOL_COOLDOWN_ACTIVE,
            WhyCode.NRR_018_EXCHANGE_REJECTED_ORDER,
            WhyCode.NRR_019_ORDER_TIMEOUT_EXPIRED,
        ]

        pattern = re.compile(r"^NRR-\d{3}$")

        for code in nrr_codes:
            assert pattern.match(
                code.value), f"NRR code {code.value} does not match pattern"

    def test_no_duplicate_nrr_codes(self):
        """Test that NRR codes are unique."""
        nrr_codes = [
            WhyCode.NRR_011_EXPOSURE_LIMIT_EXCEEDED,
            WhyCode.NRR_012_RATE_LIMIT_EXCEEDED,
            WhyCode.NRR_013_EXPOSURE_BLOCK_COOLDOWN_ACTIVE,
            WhyCode.NRR_014_SYMBOL_COOLDOWN_ACTIVE,
            WhyCode.NRR_015_EXCHANGE_ORDER_REJECTED,
            WhyCode.NRR_016_ORDER_TIMEOUT_EXPIRED,
            WhyCode.NRR_017_SYMBOL_COOLDOWN_ACTIVE,
            WhyCode.NRR_018_EXCHANGE_REJECTED_ORDER,
            WhyCode.NRR_019_ORDER_TIMEOUT_EXPIRED,
        ]

        values = [code.value for code in nrr_codes]
        assert len(values) == len(set(values)), "Duplicate NRR codes found"

    def test_nrr_code_sequential(self):
        """Test that NRR codes are sequential from 011 to 019."""
        expected_codes = [f"NRR-{str(i).zfill(3)}" for i in range(11, 20)]

        actual_codes = [
            WhyCode.NRR_011_EXPOSURE_LIMIT_EXCEEDED.value,
            WhyCode.NRR_012_RATE_LIMIT_EXCEEDED.value,
            WhyCode.NRR_013_EXPOSURE_BLOCK_COOLDOWN_ACTIVE.value,
            WhyCode.NRR_014_SYMBOL_COOLDOWN_ACTIVE.value,
            WhyCode.NRR_015_EXCHANGE_ORDER_REJECTED.value,
            WhyCode.NRR_016_ORDER_TIMEOUT_EXPIRED.value,
            WhyCode.NRR_017_SYMBOL_COOLDOWN_ACTIVE.value,
            WhyCode.NRR_018_EXCHANGE_REJECTED_ORDER.value,
            WhyCode.NRR_019_ORDER_TIMEOUT_EXPIRED.value,
        ]

        assert actual_codes == expected_codes, f"NRR codes not sequential: expected {expected_codes}, got {actual_codes}"
