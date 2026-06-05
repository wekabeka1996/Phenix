# NRR062_OVERRIDE_REPLAY_VS_RUNTIME

## Executive Summary
Package F identified an offline candidate surface of 79 rows with estimated net replay PnL 825.2672997047. The current runtime window observed 1 realized override trade and 22.6742616 net quote across the realized override cohort.

## Proven Facts
- Package F candidate rows: 79
- Package F TP / SL / TIMEOUT: 25 / 2 / 52
- trade_lifecycle malformed lines skipped: 7
- Package F estimated net quote: 825.2672997047
- Package F profit factor: 4.9243439044
- Package F timeout share: 0.6582278481
- Runtime realized override rows: 1
- Runtime wins / losses / unresolved: 1 / 0 / 0
- Runtime net quote: 22.6742616
- Runtime sample fraction vs Package F candidate rows: 0.0126582278

## Inference
Runtime evidence is directionally aligned with the positive replay hypothesis, but the live sample remains far below the volume needed to treat runtime as a replacement for the offline candidate study.
