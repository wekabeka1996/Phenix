# FastAPI Edge Composition

Production CLI construction now creates `MainProcessAuthorityQueryClient` from strict YAML and passes it into `create_shadow_telemetry_app`.

The edge performs:

- HTTP auth and strict proposal validation;
- startup/first-use compatibility handshake;
- thread-offloaded bounded TCP query;
- strict response/correlation/generation validation;
- Pydantic validation of read-model and dry-run reply payloads.

It does not construct a session authority, cache accepted dry-run authority, invoke V2 execution processing, or call FSM/adapter/exchange. Explicit local service injection remains only for focused tests.
