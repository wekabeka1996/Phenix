# tests/units/test_metrics_update.py
from apps.reference.telemetry.metrics import (
    update_exposure,
    generate_latest,
)
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_update_exposure_exports_values():
    update_exposure(5000, 300, 200, 0.2)
    data = generate_latest().decode("utf-8")
    assert "exposure_equity_usd" in data
    assert "exposure_positions_usd" in data
    assert "exposure_pending_usd" in data
    assert "exposure_limit_usd" in data
