# Latency profile

P4 round trip: 9-40 ms, mean 19 ms. P5: 20-57 ms, mean 28.5 ms.

P5 reducer phase means:

- direct publication/decision check: 0.770 ms;
- order warning tail: 3.996 ms;
- portfolio tail: 5.611 ms;
- positions: 0.005 ms;
- market sources: 0.275 ms;
- complete cards: 12.000 ms.

The increase is consistent with larger descriptor serialization plus variable bounded fallback tails. Direct market lookup remains sub-millisecond and no broad latency optimization was added.
