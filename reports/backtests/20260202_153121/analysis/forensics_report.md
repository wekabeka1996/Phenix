# Forensics Report (Refined)

## 1. Equity Structure (SSOT)
- **Initial Balance**: 1000.0
- **Peak Equity**: 2173.12 at 2023-08-18 16:55
- **Giveback**: -36.74%
- **Max Drawdown**: -37.41%

## 2. Regime & Confidence (from Intents)
### Window A (Build-up)
- Avg Confidence: 0.8035
- Counts: {'HIGH_VOLATILITY': 329, 'TREND_DOWN': 22, 'TREND_UP': 21}

### Window B (Degrade)
- Avg Confidence: 0.7976
- Counts: {'HIGH_VOLATILITY': 50, 'TREND_UP': 5, 'TREND_DOWN': 2}

## 3. The Culprit (Window B Breakdown)
- **HIGH_VOLATILITY LONG**: 12 trades, PnL -340.58
- **HIGH_VOLATILITY SHORT**: 11 trades, PnL -269.08
- **TREND_DOWN SHORT**: 2 trades, PnL -102.79
- **TREND_UP SHORT**: 1 trades, PnL -43.15
- **TREND_UP LONG**: 3 trades, PnL -28.77


## 4. Bar Quality Metrics (Artifacts)
- [Peak Window Quality CSV](analysis/peak_window_quality.csv) (±3h/12h around peak, check for `atr_slope` vs `vol_ratio` divergence)

## Evidence Links
- [Equity Curve](analysis/equity_curve.csv)
- [Keypoints](analysis/peak_degrade_keypoints.json)
- [Regime Stats](analysis/regime_distribution_by_window.json)
- [Trade Economics](analysis/trade_economics_by_window.json)
- [Peak Quality](analysis/peak_window_quality.csv)
- [Forensics Report](analysis/forensics_report.md)

