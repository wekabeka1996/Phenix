import pytest
import pandas as pd
import numpy as np

# A basic smoke test. We do not run the full CLI via subprocess here
# because of missing config context, but we check if everything can be imported.


def test_smoke_imports():
    from tools.regime_calibration.oracle import compute_oracle_labels
    from tools.regime_calibration.metrics import compute_metrics
    from tools.regime_calibration.io import load_recorder_data
    from tools.regime_calibration.search import evaluate_overlay, generate_random_overlay
    assert True


def test_passes_gates_rejects_below_coverage():
    """BUG-3 regression: passes_gates must return False when a covered class is below min_coverage."""
    from tools.regime_calibration.search import passes_gates

    metrics_low_coverage = {
        'uncertain_ratio': 0.10,
        'churn_per_1000': 50.0,
        'coverages': {
            'TREND_UP': 0.0,    # below any positive threshold
            'TREND_DOWN': 0.40,
        },
    }
    # gate: min_coverage=0.05 but TREND_UP has 0.0 -> must reject
    assert passes_gates(metrics_low_coverage, max_uncertain=0.5,
                        max_churn=200.0, min_coverage=0.05) is False


def test_passes_gates_accepts_above_coverage():
    """Positive path: passes_gates allows through when all coverages meet threshold."""
    from tools.regime_calibration.search import passes_gates

    metrics_ok = {
        'uncertain_ratio': 0.10,
        'churn_per_1000': 50.0,
        'coverages': {
            'TREND_UP': 0.20,
            'TREND_DOWN': 0.15,
        },
    }
    assert passes_gates(metrics_ok, max_uncertain=0.5,
                        max_churn=200.0, min_coverage=0.05) is True


def test_passes_gates_rejects_high_uncertain():
    """passes_gates rejects when uncertain_ratio exceeds max."""
    from tools.regime_calibration.search import passes_gates

    metrics = {
        'uncertain_ratio': 0.80,
        'churn_per_1000': 10.0,
        'coverages': {'TREND_UP': 0.20},
    }
    assert passes_gates(metrics, max_uncertain=0.55,
                        max_churn=200.0, min_coverage=0.0) is False


def test_message_accepts_src_dst():
    """BUG-2 regression: Message with src/dst must not raise ValidationError."""
    from vfoundation.core.protocol import Message

    msg = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        src="tools.regime_calibration.search",
        dst="any",
        pld={"symbol": "BTCUSDT", "ts": 1000,
             "tf_sec": 300, "features": {"price": 50000.0}},
    )
    assert msg.src == "tools.regime_calibration.search"
    assert msg.dst == "any"
    assert msg.verb == "FEATURES_CALCULATED"
