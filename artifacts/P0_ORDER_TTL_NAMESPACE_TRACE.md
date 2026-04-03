# P0 Order TTL Namespace Trace

## Question

Which namespace actually controls the execution timeout surface historically associated with default_ttl_seconds?

## Facts

1. Canonical typed location:
   - apps/reference/config_models.py:1905 defines default_ttl_seconds on OrdersConfig under ExecutionConfig.orders.
   - That corresponds to trading.execution.orders.default_ttl_seconds, not trading.orders.default_ttl_seconds.
2. Current config state:
   - config/aurora/trading.yaml:160-162 contains comments describing the field as removed and fill_ttl_ms as SSOT.
   - No live default_ttl_seconds value exists in current trading.yaml.
3. Live runtime read path:
   - apps/reference/domains/execution_position/fsm.py:555-558 probes trading.orders.default_ttl_seconds.
   - apps/reference/domains/execution_position/fsm.py:573-578 probes root orders.default_ttl_seconds.
4. Runtime effect if alias exists:
   - apps/reference/domains/execution_position/fsm.py:580-590 converts default_ttl_seconds to candidate_ms and compares it to fill_ttl_ms.
   - apps/reference/domains/execution_position/fsm.py:588 can still assign fill_ttl_ms = candidate_ms when candidate_ms is not smaller.
5. Downstream consumer:
   - apps/reference/domains/execution_position/watchdog.py:341-347 consumes whatever fill_ttl_ms survives after construction.
6. Doc-side acknowledgement:
   - config/docs/trading_passport.md:1366-1371 already documents the namespace mismatch.
7. Validation signal:
   - tests/domains/execution_position/test_fill_pipeline_fix.py:26-47 and 76-88 encode the intended direction: default_ttl_seconds must not silently reduce watchdog fill_ttl_ms and should be absent from trading.yaml.

## Verdict

1. trading.execution.orders.default_ttl_seconds is not the live runtime owner today.
2. trading.orders.default_ttl_seconds and root orders.default_ttl_seconds are legacy shadow namespaces that can still affect runtime if they appear.
3. The cleanest safe next slice is to remove these shadow probes from ExecPosFSM rather than invent a new semantic for default_ttl_seconds.

## Boundaries

1. Do not repurpose default_ttl_seconds as a synonym for pending-entry TTL.
2. Do not fold it into fill_ttl_override_ms semantics.
3. Do not change the external valid_for_ms fallback chain while cleaning up namespace drift.
