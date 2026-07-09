# Root Path Decision

This document details the analysis and decision regarding the correct `.agent_memory` directory for Cockpit session context.

## Problem Statement
The prior contract read model and route initialized the reader with:
`project_root / ".agent_memory"`

However, the repository root's `.agent_memory/` is reserved for Aurora core's FSM, scenarios, and action reviews. Cockpit's session database, spines, and memory atoms are generated relative to the dashboard project directory.

## Path Audit Findings
- **Cockpit Current Directory**: The startup script `start_dashboard.ps1` sets the directory context to `tools/deepseek-terminal-agent` inside both the local shell and the docker container mapping (`/workspace/project/tools/deepseek-terminal-agent`).
- **Memory References**: Analysis of the Cockpit source code (`config.py`, `store.py`) confirms that all files (such as `model_registry.dsmodels.json`, `sessions/`, and `memory_atoms.dsmem.jsonl`) are written to `.agent_memory/` relative to `tools/deepseek-terminal-agent`.
- **Mismatch**: The route was looking in the wrong directory, leading to `404 Not Found` for otherwise valid sessions.

## Decision and Implementation
1. **Default Path Alignment**: Modified `SessionContextReadModel.__init__` to default to `tools/deepseek-terminal-agent/.agent_memory`.
2. **Route Alignment**: Updated the `/agent-session-context/v0/{session_id}` route to instantiate the read model with:
   `project_root / "tools" / "deepseek-terminal-agent" / ".agent_memory"`
3. **Fails-Closed Flow**: If this directory or its `sessions` subdirectory does not exist, the route raises a `503 Service Unavailable` error instead of a standard `404`, clearly highlighting that the memory store itself is missing.
