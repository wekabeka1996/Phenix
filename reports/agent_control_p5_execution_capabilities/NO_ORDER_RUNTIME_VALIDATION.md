# No-order runtime validation

Launch environment, with no secret values:

```text
AURORA_RUNTIME_PROFILE=agent_bridge_observation_only
PYTHONUNBUFFERED=1
PYTHONIOENCODING=utf-8
.venv/Scripts/python.exe -m apps.reference.main
```

Before launch, only `ops/wal/*.json` was targeted; zero matching files existed or were deleted. Aurora PIDs are 23880/13604.

Startup evidence:

- no-order profile active;
- shadow mode true, live execution false, adapter absent;
- consequential execution listeners omitted;
- authenticated startup filter validation skipped;
- snapshot/WAL replay skipped;
- direct publisher registered as `p5.v0`;
- market pipeline active.

Bounded runtime safety scan found only HTTP GET requests and zero create/place/cancel/modify/amend or blocked-action signatures. Cockpit action constant remains false.
