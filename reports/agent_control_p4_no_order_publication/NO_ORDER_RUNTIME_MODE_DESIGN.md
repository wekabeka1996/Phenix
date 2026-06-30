# No-order runtime mode design

`AURORA_RUNTIME_PROFILE=agent_bridge_observation_only` is process composition, not a trading-mode rewrite.

Fail-closed properties:

- only `normal` and `agent_bridge_observation_only` validate;
- an empty/unknown explicit value raises before domain construction;
- execution is built shadowed with `adapter=None` and `is_live_execution=false`;
- trade intent and external open/close/amend listeners are omitted;
- direct method calls are blocked and counted;
- adapter initialization returns before config/credential access;
- startup filter validation, DR snapshot restore, and WAL replay are skipped;
- telemetry emits `NO_ORDER_OBSERVATION_MODE_ACTIVE`.

Market data, feature engineering, regime detection, read-only GET serving, atomic publication, and advisory warning reads remain available. This profile cannot silently fall back to normal execution.
