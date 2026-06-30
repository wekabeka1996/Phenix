# Cockpit consumer notes

Cockpit is located at `C:\Users\wekab\Music\deepseek-agent-os-workspace-changes` and is not itself a Git repository in this environment.

The typed contract and runtime parser are in `src/shared/contracts/agentFeed.ts`. `AuroraAgentFeedClient` uses GET only, applies a timeout, validates payloads, and fails closed on malformed or over-budget packets. It rejects ports 7102 and 8443.

Express proxies two read-only endpoints under `/api/agent-feed/v0/`. The packet route persists validated packet metadata plus the compact payload in the existing runtime SQLite database. Failed fetches return a visible 502 error and are not converted to empty data.

`AgentFeedPanel` polls every 15 seconds and renders six cards, freshness, byte/token use, missing fields, advisory warnings, and mechanical invariants. `AGENT_FEED_ACTIONS_ENABLED` is `false`, and the only P1 action control is disabled. Existing trading dispatch code was not connected to this path or modified.

The Aurora base URL reuses the already-required `PHENIX_CORE_API_URL`; no shared filesystem path or new active runtime configuration is required.
