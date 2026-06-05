import numpy as np
from typing import Dict, Any, List

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    """
    Computes anti-overfit regime metrics.
    y_true, y_pred: numpy arrays of string labels
    """
    classes = sorted(list(set(y_true) | set(y_pred)))
    
    # confusion matrix
    cm = {c: {c2: 0 for c2 in classes} for c in classes}
    for t, p in zip(y_true, y_pred):
        cm[t][p] += 1
        
    n = len(y_true)
    uncertain_ratio = float(np.mean(y_pred == 'UNCERTAIN')) if n > 0 else 0.0
    
    # churn
    changes = np.sum(y_pred[1:] != y_pred[:-1])
    churn_per_1000 = float(changes / n * 1000) if n > 0 else 0.0
    
    # metrics per class
    f1_scores = {}
    coverages = {}
    for c in classes:
        tp = cm[c][c]
        fp = sum(cm[c2][c] for c2 in classes if c2 != c)
        fn = sum(cm[c][c2] for c2 in classes if c2 != c)
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        f1_scores[c] = float(f1)
        coverages[c] = float(np.mean(y_pred == c)) if n > 0 else 0.0
        
    valid_classes = [c for c in classes if c != 'UNCERTAIN']
    macro_f1 = float(np.mean([f1_scores[c] for c in valid_classes])) if valid_classes else 0.0
    
    # f1_trend
    f1_trend = (f1_scores.get('TREND_UP', 0.0) + f1_scores.get('TREND_DOWN', 0.0)) / 2.0
    
    # avg_regime_duration
    durations = []
    curr_len = 0
    for i in range(1, n):
        curr_len += 1
        if y_pred[i] != y_pred[i-1]:
            durations.append(curr_len)
            curr_len = 0
    if curr_len > 0:
        durations.append(curr_len)
    avg_duration = float(np.mean(durations)) if durations else 0.0
    
    return {
        'uncertain_ratio': uncertain_ratio,
        'churn_per_1000': churn_per_1000,
        'macro_f1': macro_f1,
        'f1_trend': f1_trend,
        'f1_scores': f1_scores,
        'coverages': coverages,
        'avg_regime_duration_bars': avg_duration,
        'confusion_matrix': cm
    }

def format_confusion_matrix(cm: Dict[str, Dict[str, int]]) -> str:
    classes = sorted(list(cm.keys()))
    header = "True \\ Pred | " + " | ".join(f"{c[:8]:8}" for c in classes)
    lines = [header]
    for c_true in classes:
        row = f"{c_true[:10]:10} | " + " | ".join(f"{cm[c_true][c_pred]:8d}" for c_pred in classes)
        lines.append(row)
    return "\n".join(lines)
