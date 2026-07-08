# Corpus generation policy

- Sources: 10 archived P9 fresh packets and 10 archived P10 stale packets.
- Windows used: 3 P9 pairs and 2 P10 pairs.
- Cartesian review scope per window: BTC/ETH × micro/scalp = 4 completed reviews.
- Proposed action cycles deterministically through OBSERVE, WAIT and NO_ACTION.
- Micro close threshold: 0.05%; scalp threshold: 0.15%.
- Volatility expansion/compression threshold: ±25%.
- Stale+missing greater than fresh forces `data_stale_or_missing`.
- Otherwise below-threshold movement becomes `no_clear_scenario`.
- Every review is no-model, no-execution, packet-linked and has no PnL claim.
- Review ids make repeated generation idempotent.
