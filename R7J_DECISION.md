# R7J Decision

Classification: MARKET_TICK_FEED_BLOCKED_BY_CONFIG

The runtime markPrice null state is explained by the existing market-tick path being present in code but disabled in the active position-tracking profile. PositionTracking does not subscribe to EVT:MARKET_TICK_RECEIVED because enable_market_tick_subscription is false, and the snapshot code correctly returns null when no fresh mark price exists.

Secondary note: the PORTFOLIO_STATE_UPDATED / EXPOSURE_SUMMARY_UPDATED carrier drift is real, but it is separate from the mark-price feed failure.
