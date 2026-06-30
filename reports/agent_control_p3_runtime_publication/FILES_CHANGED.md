# Files changed

## Aurora

- Agent Bridge contracts now define atomic market/readiness/index publications, source ownership, compact feature families, and reducer timings.
- New publication module implements atomic storage, event-bus publisher, and fixed-file reader.
- Reducer now prioritizes publications, reports ownership, and profiles phases.
- Main composition registers the publisher and ticks readiness publication.
- New safe runner relays the active main-owned feature mirror without restarting or importing live execution objects.
- Focused publication tests cover atomicity, schema validation, priority/fallback, event-bus wiring, budget, and no execution behavior.
- `.gitignore` tracks only the required P3 report directory.

## Cockpit

No P3 code change. Existing GET-only client, validator, persistence, six-card component, forbidden-port guards, and disabled actions were reused and revalidated.

No strategy, business gate, credential, execution adapter, dispatch, action, or order-routing behavior was changed.
