# R7M Recommendation

## Facts
- Seven filled lifecycles were observed after R7K/R7L.
- Best current edge in the slice was `2.99 USDT`; no lifecycle reached `5 USDT`, `10 USDT`, or `25 USDT`.
- The best BTCUSDT lifecycle reached only about `0.07%` favorable excursion vs notional; the 25 USDT arm corresponds to roughly `0.34%` to `0.67%` of notional across the filled lifecycles.
- No Sidecar recommendation or close-request row was emitted, and all closes were downstream `POSITION_CLOSED_DETECTED` paths.

## Inference
- The live runtime does not show a broken trigger. It shows a trigger that is never reached under the observed market/size/hold profile.
- A fixed-dollar arm is only loosely normalized by position size here; a ROI-based arm would be more contractually aligned, but that is a separate config-only calibration question.

## Recommendation
- Keep observing before any live threshold change.
- Do not treat the absent trigger as a defect.
- If a later calibration step is opened, evaluate a config-only ROI / percent-of-notional arm on a broader sample, then validate separately.

## Decision
FIXED_25_USD_TOO_HIGH_FOR_CURRENT_SIZING
