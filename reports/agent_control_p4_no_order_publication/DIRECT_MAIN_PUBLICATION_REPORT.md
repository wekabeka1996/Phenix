# Direct main publication report

At the natural 12:05 300s close, Aurora main published:

- BTCUSDT: price 59,849.95, regime `UNCERTAIN`, source `aurora_main_event_bus`;
- ETHUSDT: price 1,573.585, regime `UNCERTAIN`, source `aurora_main_event_bus`.

Both rows have complete compact feature families, no missing card fields, `publisher_version=p4.v0`, and reducer ownership `direct_main_publication`. The index heartbeat reports `publication_status=ready` and covers all configured symbols. No relay process ran during P4.

The live window also exposed and fixed a narrow selection defect: the 12-row cap previously favored alphabetical symbol/timeframe tuples. P4 now retains canonical 300s rows for configured symbols before optional extra timeframes.
