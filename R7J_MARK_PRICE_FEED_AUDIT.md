# R7J Mark Price Feed To PositionTracking Audit

## Decision
Classification: MARKET_TICK_FEED_BLOCKED_BY_CONFIG

## Facts
- MarketDataProxy emits EVT:MARKET_TICK_RECEIVED with price, bid, ask, mid, bid_size, ask_size, buy_volume, and sell_volume in [apps/reference/domains/market_data/proxy.py](apps/reference/domains/market_data/proxy.py#L250).
- PositionTracking only subscribes to EVT:MARKET_TICK_RECEIVED when enable_market_tick_subscription is true; the listener registration is behind that gate in [apps/reference/domains/position_tracking/position_tracking.py](apps/reference/domains/position_tracking/position_tracking.py#L132).
- The active domain config sets enable_market_tick_subscription to false in [config/aurora/domains.yaml](config/aurora/domains.yaml#L392).
- _get_positions_snapshot() reads a fresh cached mark price via _fresh_mark_price() and emits markPrice as null when no usable value exists in [apps/reference/domains/position_tracking/position_tracking.py](apps/reference/domains/position_tracking/position_tracking.py#L1371).
- The captured runtime trace for an open XRPUSDT lifecycle shows mark_price as null in both position_snapshot and peak_giveback_snapshot in [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L17641).
- Runtime logs show repeated EVT:MARKET_TICK_RECEIVED entropy-spike detections, which confirms the topic exists in the runtime slice, but no PositionTracking handler hit was found in the captured logs in [logs/aurora_core.log.9](logs/aurora_core.log.9#L1254).

## Inference
- The cache stays empty because the market-tick listener is not registered in the active profile.
- The null markPrice path is therefore ingress-gated, not a snapshot formatting bug.
- The separate PORTFOLIO_STATE_UPDATED versus EXPOSURE_SUMMARY_UPDATED carrier drift is real, but it does not explain the null markPrice.

## Smallest Safe Corrective Action
- If runtime should populate mark price, enable position_tracking.enable_market_tick_subscription in the active runtime profile and verify with a narrow smoke test that PositionTracking logs Updated mark price for ... and exports non-null markPrice.
- Do not change sidecar thresholds, close routing, or policy math.
