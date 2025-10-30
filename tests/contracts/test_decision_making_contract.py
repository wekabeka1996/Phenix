# PATH: tests/contracts/test_decision_making_contract.py
"""
Contract validation tests for DecisionMaking domain.

Ensures that all emitted TRADE_INTENT_PROPOSED events conform to the
trade_intent_v1.json schema, maintaining contract integrity.

WHY: Enforce "Contract > Code" principle — validate runtime behavior
against formal contracts [FSMP-PORTING-T02A]
"""

import json
from pathlib import Path
import pytest
from jsonschema import validate
from unittest.mock import MagicMock
import sys

# Add apps to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "apps"))

from reference.domains.decision_making.decision_making import DecisionMaking
from vfoundation.core.protocol import Message

# Load schema once for all tests
SCHEMA_PATH = (
    Path(__file__).parent.parent.parent
    / "apps"
    / "reference"
    / "domains"
    / "decision_making"
    / "schemas"
    / "trade_intent_v1.json"
)
with open(SCHEMA_PATH, "r") as f:
    TRADE_INTENT_SCHEMA = json.load(f)


@pytest.fixture
def decision_domain_for_contract_test():
    """Create a DecisionMaking domain with full config for contract testing."""
    # Simple FSM mock to track emit() calls
    mock_fsm = MagicMock()

    # Full config with all required sections
    config = {
        "system": {"kelly": {"fraction_cap": 0.85}},
        "trading": {
            "instruments": {
                "ETHUSDT": {
                    "lot_step": 0.001,
                    "tick_size": 0.01,
                    "min_qty": 0.001,
                    "step_size": "0.001",
                }
            },
            "decision": {
                "signal_weights": {"obi": 0.4, "tfi": 0.4, "absorption": 0.2},
                "probability_bounds": {"base": 0.5, "max_prob": 0.9, "min_prob": 0.1},
                "signal_threshold": 0.1,
                "p_calibration_version": "calibrated_v1",
                "payoff_ratio_r": 2.0,
                "position_sizing": {
                    "kelly_conservative_factor": 0.1,
                    "kelly_alpha": 0.5,
                    "min_position_size_usd": 10.0,
                    "max_position_size_usd": 1000.0,
                    "default_notional_cap_usd": 1000.0,
                    "liquidity_based_cap_usd": 100.0,  # Base size for test
                },
                "sizing_modifiers": {},  # No modifiers for clean contract test
                "calib_metrics_placeholder": "ECE=0.05, Brier=0.08",
            },
            "tca_prefs": {
                "max_slippage_bps": 50.0,
                "max_latency_ms": 5000,
                "maker_preference": "allow",
            },
            "risk_budgets": {
                "trade_cvar95_max_bps": 100.0,
                "session_cvar95_max_bps": 200.0,
            },
        },
    }

    domain = DecisionMaking(config=config, fsm=mock_fsm)
    domain.logger = MagicMock()
    return domain


def test_emitted_trade_intent_conforms_to_schema(decision_domain_for_contract_test):
    """
    Verify that a trade intent emitted by DecisionMaking under ideal conditions
    is fully compliant with the trade_intent_v1.json schema.

    WHY: "Ensure TradeIntent output contract integrity through automated validation [FSMP-PORTING-T02A]"
    """
    # --- Arrange ---
    domain = decision_domain_for_contract_test

    # Pre-fill required data streams
    domain.latest_portfolio = {"equity": "10000"}
    domain.latest_risk = {"risk_parameters": {"is_trading_allowed": True}}

    # Create features with strong BUY signal (OBI, TFI positive)
    features_event = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        src="feature_engineering",
        dst="decision_making",
        pld={
            "ts": 123456,
            "symbol": "ETHUSDT",
            "features": {
                "obi": 0.9,  # Strong positive order book imbalance
                "tfi": 0.9,  # Strong positive trade flow imbalance
                "absorption": 0.5,  # Positive absorption
                "price": "4000",
            },
        },
    )

    # --- Act ---
    risk_payload = {
        "symbol": "ETHUSDT",
        "risk_parameters": {"is_trading_allowed": True},
    }
    portfolio_payload = {"equity": "50000", "positions": {}}

    risk_event = Message(
        op="EVT",
        verb="RISK_ASSESSMENT_COMPLETED",
        src="risk",
        dst="decision",
        pld=risk_payload,
    )
    portfolio_event = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="portfolio",
        dst="decision",
        pld=portfolio_payload,
    )

    domain.on_risk(risk_event)
    domain.on_portfolio(portfolio_event)
    domain.on_features(features_event)

    # --- Assert ---
    domain.fsm.emit.assert_called_once()
    emit_args = domain.fsm.emit.call_args

    # Extract arguments (emit called as: emit(event_name, payload=..., why=...))
    emitted_event_name = emit_args[0][0]  # Positional arg
    emitted_payload = emit_args[1]["payload"]  # Keyword arg

    # Verify event name
    assert emitted_event_name == "EVT:TRADE_INTENT_PROPOSED", (
        "Event name must be EVT:TRADE_INTENT_PROPOSED"
    )

    # 🎯 MAIN CONTRACT VALIDATION: JSON Schema compliance
    validate(instance=emitted_payload, schema=TRADE_INTENT_SCHEMA)

    # Additional assertions for expected behavior
    assert emitted_payload["side"] == "buy", (
        "Positive features should generate buy intent"
    )
    assert emitted_payload["instrument"] == "ETHUSDT", (
        "Instrument should match input symbol"
    )
