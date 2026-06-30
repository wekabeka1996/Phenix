# Source ownership comparison

| Card family | P2 | P3 |
|---|---|---|
| BTC/ETH market | stale bounded decision fallback; price missing | fresh runtime publication with close price and regime |
| BTC/ETH features | missing | fresh runtime publication, all five compact card projections present |
| Global market | bounded portfolio plus missing market | mixed runtime market publication + bounded portfolio |
| Position life | bounded portfolio fallback | bounded portfolio fallback |
| Business warnings | bounded order tail | bounded order tail |
| Execution body | bounded trace + missing runtime | atomic runtime publication, explicitly partial/no runtime |

Freshness changed from P2 `fresh=3, stale=3, missing=2` to P3 `fresh=8, stale=0, missing=0` for each of ten packets. Execution invariant statuses remain missing inside a fresh publication envelope; card freshness means the diagnostic is current, not that execution is ready.
