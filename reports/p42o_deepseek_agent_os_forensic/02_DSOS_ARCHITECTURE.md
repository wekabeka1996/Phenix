# 02 DeepSeek Agent OS (DSOS) Architecture

This report maps the architecture and implementation of `deepseek-agent-os (10)`.

## 1. Components and Entrypoints

### package.json
- **Dev Script**: `tsx server.ts` starts the Express backend and Vite frontend dev server.
- **Bridge Script**: `tsx src/bridge-daemon/server/BridgeDaemonServer.ts` starts the workspace execution bridge daemon.
- **Core Dependencies**: React 19, Vite 6, Express 4, dotenv, tailwindcss, Lucide React, and Google GenAI.

### Express Backend (`server.ts`)
- **Port**: Listens on `PORT` (defaults to `3000`).
- **Trading Agent Service**: Imports `PhenixTradingAgentService` and calls `start()` at boot.
- **API Routes**:
  - `GET /api/model-profiles` and `POST /api/model-profiles/readiness-check`
  - `GET/POST /api/sessions` and `GET /api/sessions/:id/state` (reads session state, active runs, events, attachments, memory patches, and artifacts).
  - `GET /api/events/stream` (SSE event emitter).
  - `POST /api/approvals/:id/approve` and `POST /api/approvals/:id/reject`.
  - `GET /api/system/execution-capabilities` and `GET /api/bridge/health` (queries local bridge daemon).
  - `POST /api/workspace/files/read` and `POST /api/workspace/files/write` (reads/writes workspace files via bridge).

### Bridge Daemon (`BridgeDaemonServer.ts`)
- **Port**: Listens on `LOCAL_BRIDGE_PORT` / `PORT` (defaults to `8787`).
- **Role**: Exposes endpoints allowing the main server to read/write files and execute CLI commands within the local workspace (`LOCAL_WORKSPACE_ROOT`), bypassing sandboxed limits if `ALLOW_LOCAL_WORKSPACE_BRIDGE=true`.
- **Security**: Requires bearer authentication token `LOCAL_WORKSPACE_BRIDGE_TOKEN` and checks `x-agent-os-project-id`.

### Model Providers (`providerProfiles.ts`)
- Registers model profiles for DeepSeek (`deepseek-v4-pro` and `deepseek-v4-flash`), Google Gemini (`gemini-3.1-flash-lite-preview`), Anthropic, OpenAI, and xAI.

### Data Stores
- **JSON files**: Stores metadata like `sessions.json`, `runs.json`, `approvals.json`, and `attachments.json` in `.agent_workspace/runtime_store/`.
- **SQLite**: Backs session memory, trading context packets, dispatches, and trading model usage records in `.agent_workspace/runtime_store/runtime.sqlite`.
