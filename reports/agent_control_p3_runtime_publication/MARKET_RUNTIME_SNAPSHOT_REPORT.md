# Market runtime snapshot report

The market publication contains BTCUSDT and ETHUSDT at 300 seconds with runtime-owned close price, bar/feature timestamps, regime label/confidence, five compact feature families, missing fields, source owner, and opaque event refs.

Observed published values included:

- BTCUSDT close `59970.95`, regime `UNCERTAIN`;
- ETHUSDT close `1579.165`, regime `UNCERTAIN`.

Both symbol and feature cards were `fresh` and `runtime_publication`. Compact card projections included direction/impulse, volatility/cost, regime/structure, order-flow, and liquidity values. No full feature vector or raw log record entered AgentFeedPacket.

The source owner was `aurora_main_feature_mirror_relay`: the main Aurora process owns and continuously updates the mirror, while the safe relay performs the atomic schema projection without importing or restarting the live runtime.
