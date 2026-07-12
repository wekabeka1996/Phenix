# Harness Architecture

## FACTS

- Real components: strict Pydantic V2, canonical authority, PositionQueries, FastAPI route, TCP queue/server, global registry, FSMCore, ExecPosFSM, IntentRouter.
- Test-only fixtures: deterministic `MockClock`, isolated YAML copy and ports, authoritative account/market snapshots, bearer token, recording adapter.
- SQLite guardian storage is explicitly `:memory:` in the isolated YAML copy; snapshot/WAL paths are under pytest temporary CWD.
- The recording adapter has `network_enabled=False` and records submit/cancel/amend calls.

## INFERENCES

- Only venue/network truth is replaced; authority, sizing, registry, transport, and FSM behavior remain real.

## ASSUMPTIONS

- FastAPI TestClient is equivalent for route processing while TCP remains a real socket boundary.

## UNKNOWNS

- OS scheduling can vary, so assertions poll bounded observable counters.
