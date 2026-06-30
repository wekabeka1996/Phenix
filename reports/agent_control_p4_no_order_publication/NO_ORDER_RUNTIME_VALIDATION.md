# No-order runtime validation

Final launch environment, without secret values:

```text
AURORA_RUNTIME_PROFILE=agent_bridge_observation_only
PYTHONUNBUFFERED=1
PYTHONIOENCODING=utf-8
.venv/Scripts/python.exe -m apps.reference.main
```

Final main PIDs: 9092 parent and 7472 worker. Startup logged the profile, `adapter=None`, omitted consequential listeners, skipped authenticated filter validation, skipped DR/WAL replay, registered the publisher, started market data, released warmup, and reached `AURORA CORE IS ACTIVE`.

Three controlled launches were needed: the first localized an old non-JSON WAL replay loop; the second proved direct publication and exposed timeframe-selection displacement; the third validated the corrected final composition. Immediately before every launch the exact `ops/wal/*.json` pattern was removed. It matched zero files each time.

Final bounded runtime evidence:

- HTTP requests logged: 394 GET, zero non-GET;
- order/create/place/cancel/modify log matches: zero;
- blocked-action count: zero because consequential listeners were not registered;
- adapter present: false;
- live execution: false.

The no-order Aurora process remains active for observation. Temporary read-host and Cockpit processes are cleaned up after evidence collection.
