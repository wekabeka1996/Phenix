# Clock alignment report

Aurora and Cockpit ran on the same Windows host, so the host wall clock is shared. A direct bridge-health probe compared the client midpoint with Aurora `produced_ts_ms`:

- health request duration: 36 ms;
- Aurora produced timestamp minus client midpoint: +12 ms.

Across packet polls, packet production occurred 2,084–2,393 ms after Cockpit request start and only 7–50 ms before Cockpit receive time. This is consistent with bounded reducer processing followed by local transport, not a multi-second clock skew.

Freshness classification is therefore trustworthy with respect to host clock alignment. The large `oldest_source_age_ms` (about 345 million ms) reflects genuinely old decision evidence, not clock disagreement. BTCUSDT/ETHUSDT market cards remained stale and feature cards remained missing throughout all ten polls.
