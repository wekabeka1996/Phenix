
import pytest
from apps.reference.domains.decision_making.schemas_decision_blocked import DecisionBlockedPayload
from pydantic import ValidationError

class TestDecisionBlockedSchema:
    def test_valid_payload(self):
        """Verify that a compliant payload passes validation."""
        payload = {
            "symbol": "BTCUSDT",
            "stage": "on_features",
            "ts_ms": 1700000000000,
            "reason_code": "NRR-CFG-001",
            "reason": "CFG_MISSING:some.path",
            "path": "some.path",
            "why": "Missing key"
        }
        model = DecisionBlockedPayload(**payload)
        assert model.symbol == "BTCUSDT"
        assert model.schema_version == 1

    def test_missing_required_fields(self):
        """Verify that missing required fields raise ValidationError."""
        payload = {
            "symbol": "BTCUSDT",
            # Missing stage, ts_ms, reason_code, etc.
        }
        with pytest.raises(ValidationError):
            DecisionBlockedPayload(**payload)
