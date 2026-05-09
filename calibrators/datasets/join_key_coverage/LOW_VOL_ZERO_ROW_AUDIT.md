# LOW_VOL_ZERO_ROW_AUDIT

- executed_trades_master rows: 0
- order_attempts_master rows: 4
- regime_confidence_audit rows: 3488
- regime values containing 'low': LOW_VOLATILITY

## Findings
- The low_vol builder begins from executed_trades_master. With zero executed-trade rows, it cannot emit any gate rows regardless of regime availability.
- The low_vol filter checks for substring 'low' in regime values, so LOW_VOLATILITY vs low_vol spelling is not the current primary blocker if regime rows exist.
- regime_confidence_audit currently exposes regime distribution: {"LOW_VOLATILITY": 763, "TREND_UP": 661, "UNCERTAIN": 647, "MEAN_REVERSION": 600, "TREND_DOWN": 492, "HIGH_VOLATILITY": 3}.
- Because order_attempts_master has rows while executed_trades_master is empty, low-vol zero rows are not explained by missing attempt metadata alone.

## Conclusion
- Current low-vol zero-row output is primarily explained by the empty executed_trades_master surface, not by a proven low-vol regime spelling defect.
- Any stronger conclusion about low-vol outcome joins would require either a populated realized-outcome surface or an alternate exact-identity bridge from order/trade logs.