"""Tests for vfoundation.core.why_codes — WhyCode enum and helpers."""
from __future__ import annotations

from vfoundation.core.why_codes import (
    WhyCode,
    get_why_description,
    format_why_with_details,
    create_why_payload,
)


class TestWhyCodeEnum:
    def test_all_values_are_strings(self) -> None:
        for code in WhyCode:
            assert isinstance(code.value, str)

    def test_enum_count_minimum(self) -> None:
        # At least 40 codes exist
        assert len(WhyCode) >= 40

    def test_categories_present(self) -> None:
        values = [c.value for c in WhyCode]
        for prefix in ("SPREAD_", "RISK_", "LIQ_", "MARGIN_", "REGIME_",
                        "GUARD_", "FSM_", "EXCHANGE_", "IDEMPOTENCY_",
                        "TIMEOUT_", "CONFIG_", "VALIDATION_"):
            assert any(v.startswith(prefix) for v in values), f"Missing category: {prefix}"

    def test_nrr_codes_present(self) -> None:
        nrr = [c for c in WhyCode if c.value.startswith("NRR")]
        assert len(nrr) >= 5

    def test_success_codes_present(self) -> None:
        success = [c for c in WhyCode if c.value.startswith("SUCCESS")]
        assert len(success) >= 2


class TestGetWhyDescription:
    def test_known_code_returns_description(self) -> None:
        desc = get_why_description(WhyCode.SPREAD_TOO_WIDE)
        assert "spread" in desc.lower()
        assert len(desc) > 10

    def test_all_codes_have_descriptions(self) -> None:
        for code in WhyCode:
            desc = get_why_description(code)
            assert "Unknown WHY code" not in desc, f"Missing desc for {code}"

    def test_description_is_string(self) -> None:
        for code in WhyCode:
            desc = get_why_description(code)
            assert isinstance(desc, str)


class TestFormatWhyWithDetails:
    def test_without_details(self) -> None:
        result = format_why_with_details(WhyCode.RISK_SCORE_HIGH)
        assert result == "RISK_SCORE_HIGH"

    def test_with_details(self) -> None:
        result = format_why_with_details(WhyCode.RISK_SCORE_HIGH, "score=0.95")
        assert result == "RISK_SCORE_HIGH: score=0.95"

    def test_none_details_same_as_no_details(self) -> None:
        a = format_why_with_details(WhyCode.FSM_STATE_INVALID, None)
        b = format_why_with_details(WhyCode.FSM_STATE_INVALID)
        assert a == b


class TestCreateWhyPayload:
    def test_basic_payload(self) -> None:
        payload = create_why_payload(WhyCode.EXCHANGE_ORDER_REJECTED)
        assert payload["why_code"] == "EXCHANGE_ORDER_REJECTED"
        assert "why_description" in payload
        assert "why_details" not in payload

    def test_payload_with_details(self) -> None:
        details = {"exchange": "binance", "msg": "INVALID_PRICE"}
        payload = create_why_payload(WhyCode.EXCHANGE_INVALID_PRICE, details)
        assert payload["why_code"] == "EXCHANGE_INVALID_PRICE"
        assert payload["why_details"] == details

    def test_payload_keys(self) -> None:
        payload = create_why_payload(WhyCode.TIMEOUT_ORDER_EXPIRED)
        assert set(payload.keys()) == {"why_code", "why_description"}

    def test_payload_keys_with_details(self) -> None:
        payload = create_why_payload(WhyCode.TIMEOUT_ORDER_EXPIRED, {"timeout_ms": 5000})
        assert set(payload.keys()) == {"why_code", "why_description", "why_details"}
