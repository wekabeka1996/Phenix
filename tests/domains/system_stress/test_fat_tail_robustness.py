import pytest
from collections import deque
import numpy as np
from apps.reference.domains.system_stress.system_stress_overlay import _SymbolStressState


def test_fat_tail_false_positive_reduction():
    """MAD robustness on raw data: outliers inflate std but not MAD.

    Tests _z_robust directly on Student-t data (fat tails) vs Gaussian data.
    On fat-tail data, Gaussian std gets inflated by outliers, making the
    denominator larger and suppressing z-scores for ALL data points.
    MAD is resistant to this — its denominator stays stable, so z-scores
    for normal bars remain properly calibrated.

    We verify this by checking that on fat-tail data, the Gaussian z-score
    variance is MORE affected (suppressed) than MAD z-scores.
    """
    np.random.seed(42)

    # Generate Student-t(3) data — heavy tails typical of crypto returns
    data = np.random.standard_t(3, 600) * 0.01
    baseline = deque(maxlen=100)

    # Warmup: fill baseline with first 100 points
    for v in data[:100]:
        baseline.append(v)

    # Now compute z-scores for remaining data
    gauss_z_list = []
    mad_z_list = []

    for v in data[100:]:
        z_gauss = _SymbolStressState._z_robust(v, baseline, method="none")
        z_mad = _SymbolStressState._z_robust(v, baseline, method="mad")
        gauss_z_list.append(abs(z_gauss))
        mad_z_list.append(abs(z_mad))
        baseline.append(v)

    # Count exceedances above threshold 2.0
    exceed_gauss = sum(1 for z in gauss_z_list if z > 2.0)
    exceed_mad = sum(1 for z in mad_z_list if z > 2.0)

    # On Student-t data, MAD should detect MORE outliers (higher sensitivity)
    # because Gaussian std gets inflated by outliers, suppressing z-scores
    assert exceed_mad > exceed_gauss, (
        f"MAD should flag more outliers on fat-tail data (std inflation suppresses Gaussian): "
        f"MAD={exceed_mad}, Gaussian={exceed_gauss}"
    )


def test_gaussian_data_both_methods_agree():
    """On pure Gaussian data, MAD and Gaussian _z_robust should agree within tolerance."""
    np.random.seed(123)
    data = np.random.normal(0, 0.01, 600)
    baseline = deque(maxlen=100)

    # Warmup
    for v in data[:100]:
        baseline.append(v)

    exceed_gauss = 0
    exceed_mad = 0

    for v in data[100:]:
        z_gauss = _SymbolStressState._z_robust(v, baseline, method="none")
        z_mad = _SymbolStressState._z_robust(v, baseline, method="mad")
        if abs(z_gauss) > 2.0:
            exceed_gauss += 1
        if abs(z_mad) > 2.0:
            exceed_mad += 1
        baseline.append(v)

    # On clean Gaussian data, both methods should produce comparable exceedance rates.
    # Allow difference of at most 20 (out of 500).
    assert abs(exceed_mad - exceed_gauss) <= 20, (
        f"On Gaussian data, MAD and Gaussian should agree: "
        f"MAD={exceed_mad}, Gaussian={exceed_gauss}, diff={abs(exceed_mad - exceed_gauss)}"
    )
