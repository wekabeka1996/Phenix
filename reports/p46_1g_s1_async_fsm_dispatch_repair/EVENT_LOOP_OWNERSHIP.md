# Event Loop Ownership

## FACTS

| Surface | Owner | Mode | Construction/lifetime |
|---|---|---|---|
| HTTP server | FastAPI/ASGI test or service runtime | async | Separate ingress runtime; does not own execution. |
| TCP IPC server | shadow telemetry bridge | worker/threaded | Deserializes and calls registered main-process handler. |
| Main execution loop | `AsyncLoopRuntime` | dedicated asyncio thread | Constructed in `apps/reference/main.py`, stopped during shutdown. |
| FSM dispatch | `AsyncSchedulingMixin._submit_async` | sync-to-async | Same-loop task or cross-thread `run_coroutine_threadsafe`. |
| Adapter methods | canonical FSM adapter | async | Invoked only by FSM decision execution. |

- Production calls `guardian_runtime.start()` before `execution_position.set_async_loop(guardian_loop)`.
- Before repair, `start()` returned without an explicit ready handshake and `_get_async_loop()` accepted a non-running loop.
- No per-request event loop was added.

## Conclusion

`CANONICAL_LOOP_ALREADY_EXISTS_BUT_NOT_PROPAGATED`

The forensic harness omitted propagation, while production also needed a bounded readiness guarantee.

## INFERENCES

- One explicit live-loop reference is sufficient; a second runtime loop is neither required nor desirable.

## ASSUMPTIONS

- `apps/reference/main.py` remains the canonical process construction site.

## UNKNOWNS

- Multiprocess restart behavior of the full service was not exercised.
