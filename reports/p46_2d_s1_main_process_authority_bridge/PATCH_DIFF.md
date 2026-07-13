# Patch Diff

Implemented:

- strict authority-query bridge YAML/Pydantic configuration;
- optional JSONL reply support and bounded request/reply client;
- semantic query/reply contracts, runtime dispatcher, handshake client;
- query branch in the existing main ingress bridge;
- FastAPI production IPC composition for read model and pure dry-run;
- focused contract, transport, side-effect, and Windows spawn tests;
- test-harness endpoint synchronization required by the new SSOT invariant.

No Cockpit source, execution FSM, adapter, exchange, provider, sizing, authority-store, or trading-business configuration was changed.

Staged package stat before commit: 25 files changed, 1155 insertions, 14 deletions.
