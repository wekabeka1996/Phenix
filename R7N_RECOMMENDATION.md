# R7N Recommendation

## Facts
- Seven filled lifecycles were available for counterfactual testing.
- Fixed `1 USDT` and `2 USDT` arms only light up the BTCUSDT `1777767904005` lifecycle before suppression; `3 USDT` and above do not arm any lifecycle in the conservative scan.
- `0.02%` and `0.05%` of notional behave similarly, but with correct scale normalization.
- ROI-like arming only becomes interesting at `0.5% of margin`, and even then the best case still misses the `50%` giveback trigger.

## Inference
- No candidate family in this slice produces a useful 50% giveback trigger, so there is no evidence for a live threshold change.
- A shadow percent-of-notional arm is the safest next observation family because it is the least arbitrary normalization of the observed economics.

## Decision
ADD_SHADOW_PERCENT_NOTIONAL_ARM
