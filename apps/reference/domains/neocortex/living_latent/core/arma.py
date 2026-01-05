# SPDX-License-Identifier: MIT
"""Simple ARMA/AR utilities (pure NumPy).

Provides ACF, Yule-Walker AR fit, Ljung-Box and a basic periodogram.
"""
from __future__ import annotations
import numpy as np
from typing import Tuple


def acf(x: np.ndarray, max_lag: int) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    n = x.size
    x = x - x.mean()
    r = np.array([np.sum(x[:n - k] * x[k:]) for k in range(max_lag + 1)])
    return r / r[0] if r[0] != 0 else r


def pacf_yw(x: np.ndarray, k: int) -> np.ndarray:
    """Partial autocorrelation via Yule-Walker (Durbin-Levinson style).
    Returns pacf up to lag k (inclusive as array length k+1, pacf[0]=1.0).
    """
    x = np.asarray(x, dtype=float)
    n = x.size
    if n <= 0:
        return np.zeros(k + 1)
    r = acf(x, k)
    pacf = np.zeros(k + 1)
    pacf[0] = 1.0
    # Levinson-Durbin recursion
    phi = np.zeros((k + 1, k + 1))
    sigma = r[0]
    for m in range(1, k + 1):
        acc = r[m]
        for j in range(1, m):
            acc -= phi[m - 1, j] * r[m - j]
        phi[m, m] = acc / sigma if sigma != 0 else 0.0
        for j in range(1, m):
            phi[m, j] = phi[m - 1, j] - phi[m, m] * phi[m - 1, m - j]
        sigma = sigma * (1.0 - phi[m, m] ** 2)
        pacf[m] = phi[m, m]
    return pacf


def fit_ar_yw(x: np.ndarray, p: int) -> dict:
    """Fit AR(p) by Yule-Walker; return dict with phi (length p), aic, bic, sigma2."""
    x = np.asarray(x, dtype=float)
    n = x.size
    if p == 0:
        mu = x.mean() if n > 0 else 0.0
        resid = x - mu
        sigma2 = float(np.sum(resid ** 2) / max(1, n))
        return {'phi': np.zeros(0).tolist(), 'aic': 2 * 0 + n * np.log(sigma2 + 1e-12), 'bic': np.log(n) * 0 + n * np.log(sigma2 + 1e-12), 'sigma2': float(sigma2)}
    r = acf(x, p)
    R = np.empty((p, p), dtype=float)
    for i in range(p):
        for j in range(p):
            R[i, j] = r[abs(i - j)]
    rhs = r[1:p + 1]
    try:
        phi = np.linalg.solve(R, rhs)
    except np.linalg.LinAlgError:
        phi = np.zeros(p)
    # compute residual variance
    sigma2 = r[0] - float(np.dot(phi, rhs))
    sigma2 = max(sigma2, 1e-12)
    # AIC/BIC (Gaussian approx)
    aic = 2 * p + n * np.log(sigma2)
    bic = np.log(n) * p + n * np.log(sigma2)
    return {'phi': phi.tolist(), 'aic': float(aic), 'bic': float(bic), 'sigma2': float(sigma2)}


def ljung_box(x: np.ndarray, lags: int) -> dict:
    """Ljung-Box Q statistic and p-value (approx via chi2)."""
    x = np.asarray(x, dtype=float)
    n = x.size
    if n <= 0:
        return {'Q': 0.0, 'pval': 1.0}
    # compute acf up to lags
    r = acf(x, lags)
    Q = 0.0
    for k in range(1, lags + 1):
        Q += (r[k] ** 2) / (n - k)
    Q *= n * (n + 2)

    # compute chi2 survival function (1 - cdf) using regularized gamma
    import math

    def _gser(a: float, x: float, itmax=100, eps=1e-12) -> float:
        # series representation for lower incomplete gamma P(a,x)
        if x <= 0:
            return 0.0
        sum_ = term = 1.0 / a
        for n in range(1, itmax):
            term *= x / (a + n)
            sum_ += term
            if term < eps * sum_:
                break
        return sum_ * math.exp(a * math.log(x) - x - math.lgamma(a))

    def _gcf(a: float, x: float, itmax=100, eps=1e-12) -> float:
        # continued fraction representation for upper incomplete gamma Q(a,x)
        # returns Q = 1 - P
        tiny = 1e-300
        b = x + 1.0 - a
        c = 1.0 / tiny
        d = 1.0 / b
        h = d
        for i in range(1, itmax):
            an = -i * (i - a)
            b += 2.0
            d = an * d + b
            if abs(d) < tiny:
                d = tiny
            c = b + an / c
            if abs(c) < tiny:
                c = tiny
            d = 1.0 / d
            delta = d * c
            h *= delta
            if abs(delta - 1.0) < eps:
                break
        return h * math.exp(a * math.log(x) - x - math.lgamma(a))

    def _chi2_sf(xv: float, df: int) -> float:
        # survival function for chi2: sf = 1 - P(a, x/2), a = df/2
        a = df / 2.0
        xx = xv / 2.0
        if xx <= 0:
            return 1.0
        # use series if x < a+1 else continued fraction
        if xx < a + 1.0:
            p = _gser(a, xx)
            return max(0.0, 1.0 - p)
        else:
            q = _gcf(a, xx)
            return max(0.0, q)

    try:
        pval = _chi2_sf(Q, lags)
    except Exception:
        pval = 1.0
    return {'Q': float(Q), 'pval': float(pval)}


def periodogram(x: np.ndarray):
    """Compute simple periodogram using FFT; returns (freqs, psd, peak_freq, peak_val)."""
    x = np.asarray(x, dtype=float)
    n = x.size
    if n <= 0:
        return ([], [], None, 0.0)
    # detrend
    x = x - x.mean()
    fft = np.fft.rfft(x)
    psd = (np.abs(fft) ** 2) / n
    freqs = np.fft.rfftfreq(n, d=1.0)  # assume unit sample spacing
    idx = int(np.argmax(psd))
    return (freqs, psd, float(freqs[idx]), float(psd[idx]))
