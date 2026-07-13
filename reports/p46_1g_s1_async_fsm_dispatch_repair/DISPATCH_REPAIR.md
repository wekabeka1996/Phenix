# Dispatch Repair

## FACTS

- `AsyncLoopRuntime.start()` now publishes readiness from the loop thread and fails if the loop is not running within five seconds.
- `set_async_loop()` rejects closed or stopped loops with `AsyncDispatchUnavailableError`.
- `_get_async_loop()` returns only a running, open loop.
- `_submit_async()` returns the scheduled handle, uses `create_task` only on the owning loop, uses `run_coroutine_threadsafe` cross-thread, closes rejected coroutine objects, and raises a typed error.
- `ExecPosFSM.shutdown()` waits for cross-thread guardian stop with a bounded timeout.
- No `asyncio.run()` per production command, direct adapter fallback, second FSM, or second TCP listener was introduced.

## INFERENCES

- Dispatch failure is now observable and cannot silently mutate the adapter when no canonical loop is available.

## ASSUMPTIONS

- A five-second infrastructure startup/shutdown bound is operationally sufficient; it does not affect trading policy.

## UNKNOWNS

- Shutdown under an actual blocked exchange client was not network-tested.
