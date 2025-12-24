import pytest


@pytest.mark.parametrize(
    "raw_reason,expected",
    [
        ("NRR-025", "NRR-025"),
        ("NRR-025: details", "NRR-025"),
        ("NRR-006", "NRR-006"),
        ("ZERO_QUANTITY", "NRR-002"),
        ("zero_quantity", "NRR-002"),
        ("MIN_QTY", "NRR-006"),
        ("min_qty", "NRR-006"),
        ("MIN_NOTIONAL", "NRR-006"),
        ("min_notional", "NRR-006"),
        ("MIN_NOTIONAL: notional too small", "NRR-006"),
        ("NRR-DATA-NOT-READY", "NRR-025"),
        ("NRR-REGIME-MISSING", "NRR-025"),
        ("NRR-ARMING-NOT-READY", "NRR-025"),
        ("NRR-ARMING-WARMUP-MISSING", "NRR-025"),
        ("NRR-ARMING-NOT-READY: warmup not full", "NRR-025"),
        ("RISK_SCORE_MISSING", "NRR-025"),
        ("RISK_SCORE_INVALID", "NRR-025"),
        ("RISK_SCORE_INVALID: nan", "NRR-025"),
    ],
)
def test_normalize_maps_sizing_short_codes(raw_reason: str, expected: str):
    from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons

    assert NormalizedRejectReasons.normalize(raw_reason) == expected
