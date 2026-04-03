# P0 Watchdog Wiring Trace

## Scope

This trace covers only the watchdog timing knobs named in the request:
- ack_ttl_ms
- fill_ttl_ms
- check_interval_ms
- rps_limit

## Proven live chain: ack_ttl_ms and fill_ttl_ms

1. Config anchors:
   - config/aurora/trading.yaml:151 sets ack_ttl_ms=8000
   - config/aurora/trading.yaml:155 sets fill_ttl_ms=3600000
2. Typed model:
   - apps/reference/config_models.py:1555-1562 defines WatchdogConfig with ack_ttl_ms/fill_ttl_ms/check_interval_ms/rps_limit.
3. Loader in composition root:
   - apps/reference/domains/execution_position/fsm.py:544-545 extracts ack_ttl_ms and fill_ttl_ms through get_watchdog_setting.
4. Live construction:
   - apps/reference/domains/execution_position/fsm.py:594-596 constructs OrderTimeoutWatchdog with ack_ttl_ms=... and fill_ttl_ms=....
5. Material consumers:
   - apps/reference/domains/execution_position/watchdog.py:306 uses ack_ttl_ms when order is first tracked.
   - apps/reference/domains/execution_position/watchdog.py:341-347 uses fill_ttl_ms when ACK arrives and no per-order override exists.

Verdict:
- ack_ttl_ms and fill_ttl_ms are fully wired.

## Half-wired chain: check_interval_ms and rps_limit

1. Config anchors:
   - config/aurora/trading.yaml:156 sets check_interval_ms=1000
   - config/aurora/trading.yaml:157 sets rps_limit=10
2. Typed model:
   - apps/reference/config_models.py:1555-1562 includes both fields.
3. Watchdog supports both fields:
   - apps/reference/domains/execution_position/watchdog.py:62 declares constructor parameter check_interval_ms=1000.
   - apps/reference/domains/execution_position/watchdog.py:69 loads check_interval_ms from self.config if present, else constructor arg.
   - apps/reference/domains/execution_position/watchdog.py:98 loads rps_limit from self.config if present, else default 10.
   - apps/reference/domains/execution_position/watchdog.py:378 sleeps by check_interval_ms.
   - apps/reference/domains/execution_position/watchdog.py:190-205 enforces _rps_limit.
4. Broken composition link:
   - apps/reference/domains/execution_position/fsm.py:594-596 does not pass a config dict, check_interval_ms, or rps_limit into OrderTimeoutWatchdog.

Verdict:
- The fields are typed and implemented in the watchdog class, but not wired through the live composition path.

## Per-order override path

1. open_executor extracts decision.pld[valid_for_ms] at apps/reference/domains/execution_position/open_executor.py:623-626.
2. open_executor forwards that value as fill_ttl_override_ms at apps/reference/domains/execution_position/open_executor.py:633.
3. watchdog stores the override in apps/reference/domains/execution_position/watchdog.py:298-317.
4. watchdog prioritizes the override over global fill_ttl_ms in apps/reference/domains/execution_position/watchdog.py:341-347.

Verdict:
- The true execution lifetime chain for LIMIT orders is already split between global watchdog fill_ttl_ms and per-order valid_for_ms override.

## Safe remediation boundary

1. Wire check_interval_ms and rps_limit into the constructor.
2. Do not change ack_ttl_ms/fill_ttl_ms semantics in the same slice.
3. Do not touch fill_ttl_override_ms precedence in the same slice.
