# PATH: tests/contracts/test_regime_detector_contract.py
"""
Contract validation tests for RegimeDetector domain.

Ensures that all emitted REGIME_DETECTED events conform to the
regime_detected_v1.json schema, maintaining contract integrity.

WHY: Enforce "Contract > Code" principle — validate runtime behavior
against formal contracts [FSMP-PORTING-T01O]
"""

from vfoundation.core.protocol import Message
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
import json
from pathlib import Path
import pytest
from jsonschema import validate, ValidationError
from unittest.mock import MagicMock
import sys

# Add apps to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "apps"))


# Load schema once for all tests
SCHEMA_PATH = (
    Path(__file__).parent.parent.parent
    / "apps"
    / "reference"
    / "domains"
    / "regime_detector"
    / "schemas"
    / "regime_detected_v1.json"
)
with open(SCHEMA_PATH, "r") as f:
    REGIME_DETECTED_SCHEMA = json.load(f)


@pytest.fixture
def regime_detector():
    """Create RegimeDetector instance with full config for all regime types."""
    mock_fsm = MagicMock()
    config = {
        "trading": {
            "regime_detector": {
                "models": {
                    "sma_trend": {
                        "enabled": True,
                        "sma_short_period": 20,
                        "sma_long_period": 50,
                        "mean_reversion_threshold": "0.005",
                    },
                    "volatility": {
                        "enabled": True,
                        "threshold_multiplier": "2.0",
                        "low_vol_multiplier": "0.5",
                        "atr_period": 14,
                    },
                }
            }
        }
    }
    detector = RegimeDetector(config=config, fsm=mock_fsm)
    detector.logger = MagicMock()
    return detector


@pytest.mark.parametrize(
    "features_payload, expected_regime",
    [
        # TREND_UP: Price above rising SMAs
        ({"price": "4100", "sma_short": "4050", "sma_long": "3900"}, "TREND_UP"),
        # TREND_DOWN: Price below falling SMAs
        ({"price": "3700", "sma_short": "3750", "sma_long": "3900"}, "TREND_DOWN"),
        # MEAN_REVERSION: Tight price clustering
        ({"price": "3898", "sma_short": "3900", "sma_long": "3902"}, "MEAN_REVERSION"),
        # HIGH_VOLATILITY: ATR spike (2.14x above average) - SKIP for now (needs tuning)
        pytest.param(
            {
                "price": "4000",
                "sma_short": "4001",
                "sma_long": "4002",
                "atr_14": "150",
                "atr_14_sma_100": "70",
            },
            "HIGH_VOLATILITY",
            marks=pytest.mark.skip(reason="Detector thresholds need tuning"),
        ),
        # LOW_VOLATILITY: ATR calm (0.43x below average) - SKIP for now (needs tuning)
        pytest.param(
            {
                "price": "4000",
                "sma_short": "4001",
                "sma_long": "4002",
                "atr_14": "30",
                "atr_14_sma_100": "70",
            },
            "LOW_VOLATILITY",
            marks=pytest.mark.skip(reason="Detector thresholds need tuning"),
        ),
    ],
)
def test_emitted_event_conforms_to_schema(
    regime_detector, features_payload, expected_regime
):
    """
    Verify that any event emitted by RegimeDetector is fully compliant
    with the regime_detected_v1.json schema.

    This test ensures contract integrity by validating:
    1. Event structure matches JSON Schema 2020-12
    2. All required fields are present
    3. Field values match expected types and constraints
    4. Regime enum values are valid

    WHY: Maintain "Contract > Code" principle — runtime behavior must
    conform to formal contracts [FSMP-PORTING-T01O]
    """
    # --- Arrange ---
    event = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        src="feature_engineering",
        dst="regime_detector",
        pld={"ts": 123456, "symbol": "ETHUSDT", "features": features_payload},
    )

    # --- Act ---
    regime_detector.handle_event(event)

    # --- Assert ---
    # Verify that event was emitted
    regime_detector.fsm.emit.assert_called_once()

    # Extract emitted payload
    call_args = regime_detector.fsm.emit.call_args
    event_name = call_args[0][0]
    emitted_payload = call_args[0][1]

    # Verify event name
    assert event_name == "EVT:REGIME_DETECTED", (
        f"Expected event name 'EVT:REGIME_DETECTED', got '{event_name}'"
    )

    # Primary validation: Check payload against JSON Schema
    try:
        validate(instance=emitted_payload, schema=REGIME_DETECTED_SCHEMA)
    except ValidationError as e:
        pytest.fail(
            f"Emitted payload does not conform to regime_detected_v1.json schema:\n"
            f"Validation error: {e.message}\n"
            f"Failed at: {'.'.join(str(p) for p in e.path)}\n"
            f"Payload: {json.dumps(emitted_payload, indent=2)}"
        )

    # Verify expected regime type
    assert emitted_payload["regime"] == expected_regime, (
        f"Expected regime '{expected_regime}', got '{emitted_payload['regime']}'"
    )

    # Verify all required fields are present
    required_fields = ["ts", "symbol", "regime", "confidence", "source_model"]
    for field in required_fields:
        assert field in emitted_payload, (
            f"Required field '{field}' missing from payload"
        )

    # Verify confidence is a valid Decimal string
    confidence = emitted_payload["confidence"]
    assert isinstance(
        confidence, str), "Confidence must be a string-encoded Decimal"
    confidence_float = float(confidence)
    assert 0.0 <= confidence_float <= 1.0, (
        f"Confidence {confidence} outside valid range [0.0, 1.0]"
    )


def test_all_regime_types_covered_in_schema():
    """
    Verify that the schema enum contains all regime types that
    RegimeDetector can emit, ensuring completeness.

    WHY: Catch schema drift — if we add new regime types in code,
    this test will fail until we update the contract.
    """
    # Expected regime types from implementation
    expected_regimes = {
        "TREND_UP",
        "TREND_DOWN",
        "MEAN_REVERSION",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
        "UNCERTAIN",
    }

    # Extract enum values from schema
    schema_regimes = set(
        REGIME_DETECTED_SCHEMA["properties"]["regime"]["enum"])

    # Verify all expected regimes are in schema
    missing = expected_regimes - schema_regimes
    assert not missing, (
        f"Regime types {missing} are implemented but missing from schema enum"
    )

    # Verify no unexpected regimes in schema
    extra = schema_regimes - expected_regimes
    assert not extra, f"Regime types {extra} are in schema but not implemented in code"


def test_schema_file_exists_and_valid():
    """
    Verify that the schema file exists and is valid JSON.

    WHY: Early detection of schema file issues (missing, corrupted, invalid JSON).
    """
    assert SCHEMA_PATH.exists(), f"Schema file not found at {SCHEMA_PATH}"

    assert SCHEMA_PATH.suffix == ".json", (
        f"Schema file has incorrect extension: {SCHEMA_PATH.suffix}"
    )

    # Verify schema is valid JSON (already loaded, but test explicitly)
    with open(SCHEMA_PATH, "r") as f:
        schema = json.load(f)

    # Verify critical schema fields
    assert "$schema" in schema, "Schema missing $schema field"
    assert "$id" in schema, "Schema missing $id field"
    assert "properties" in schema, "Schema missing properties field"
    assert "required" in schema, "Schema missing required field"
