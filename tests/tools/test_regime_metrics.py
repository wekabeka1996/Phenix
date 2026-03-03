import numpy as np
from tools.regime_calibration.metrics import compute_metrics, format_confusion_matrix

def test_metrics_basic():
    y_true = np.array(['TREND_UP', 'TREND_UP', 'UNCERTAIN', 'HIGH_VOLATILITY'])
    y_pred = np.array(['TREND_UP', 'UNCERTAIN', 'UNCERTAIN', 'HIGH_VOLATILITY'])
    
    m = compute_metrics(y_true, y_pred)
    assert m['uncertain_ratio'] == 0.5
    assert m['churn_per_1000'] > 0
    assert m['coverages']['TREND_UP'] == 0.25
    
def test_confusion_matrix_format():
    cm = {
        'TREND_UP': {'TREND_UP': 5, 'UNCERTAIN': 1},
        'UNCERTAIN': {'TREND_UP': 0, 'UNCERTAIN': 10}
    }
    fmt = format_confusion_matrix(cm)
    assert 'TREND_UP' in fmt
    assert 'UNCERTAIN' in fmt
