# Dual-Agent View Contract

Source of truth:

- identities/ownership: P42 runtime YAML at configured `arena_config_path`;
- active state: configured append/update snapshot path;
- event detail: existing `SessionStore` event ledger;
- code provenance: current Git `HEAD`.

Per-agent output includes agent identity/number, API or CLI kind, heartbeat freshness, owned symbols, state, instruction ACK, analysis/publication/command/FSM/exchange evidence, and degraded state.

Shared output includes active session, testnet label, portfolio, orders, positions, pending commands, ownership, kill switch, reconciliation, collective publications, integration SHA, and evidence class.

Missing source data remains `null`, `UNKNOWN`, or `BLOCKED`. Empty venue data is accepted only when the runtime snapshot explicitly supplies an empty list.

Evidence rules:

| Badge | Meaning |
|---|---|
| `REAL_EXTERNAL` | explicitly externally verified and free of stub/shadow/test markers |
| `SHADOW` | shadow adapter/result |
| `STUB` | stub or synthetic reference/result |
| `TEST` | test fixture/mock evidence |
| `BLOCKED` | rejected before submit or blocked runtime |
| `UNKNOWN` | insufficient evidence |

