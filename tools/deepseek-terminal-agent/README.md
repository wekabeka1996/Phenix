# deepseek-terminal-agent

A production-grade local agent that uses DeepSeek V4 Pro as a coding/terminal
AI with full tool-calling access to a sandboxed workspace.

---

## What This Is

`deepseek-terminal-agent` wraps DeepSeek's OpenAI-compatible Chat Completions
API into an autonomous coding agent.  The agent can:

- Explore your repository (`ls`, `git log`, `cat`, `rg`, `find`)
- Run tests (`pytest`, `npm test`, etc.)
- Apply code changes via heredoc or Python file writes
- Diagnose failures and propose patches
- Operate in interactive chat or single-shot `run` mode
- Operate in dry-run mode (shows commands, does not execute)

---

## Why Docker Sandbox

The `terminal_exec` tool gives the model shell access.  Running that directly
on your host machine would let the model affect your environment.

Inside the Docker container:
- The model runs as a non-root user (`agent`, UID 1000)
- No `docker.sock` is mounted — no host Docker access
- The container has only the tools installed explicitly (`bash`, `git`, `rg`, `curl`, `build-essential`)
- Dangerous commands are blocked or require human approval (see **Safety Model**)

The container mount (`../../:/workspace/project`) gives the model access to the
full Phenix repo. The agent package itself still lives in
`tools/deepseek-terminal-agent`, and the terminal tool remains confined to the
repo root at `/workspace/project`.

---

## Requirements

- Python 3.11+
- Docker + Docker Compose (for sandboxed mode)
- A DeepSeek API key — get one at https://platform.deepseek.com

---

## Quickstart

### 1. Set up your environment

```bash
cd tools/deepseek-terminal-agent
cp .env.example .env
# Edit .env: set DEEPSEEK_API_KEY=sk-your-key-here
```

### 2. Run with Docker (recommended)

```bash
make docker-build
make docker-run           # opens interactive chat
```

Or single-shot:
```bash
docker compose run --rm deepseek-agent run "Analyse this repo and run the tests."
```

### 3. Run locally (no Docker)

```bash
make setup               # installs dependencies
# Set AGENT_WORKSPACE to your target project directory in .env
make run                 # opens interactive chat
```

---

## Dashboard Mode on Windows

The web dashboard gives you a browser UI to run the agent without the CLI.
Each prompt becomes a background job: `POST /runs` returns a `run_id` immediately,
and the page polls status, events, and output until the run reaches a terminal state.

### One-command start

```powershell
cd C:\Users\user\Music\Phenix\tools\deepseek-terminal-agent
powershell -ExecutionPolicy Bypass -File .\scripts\start_dashboard.ps1
```

For a full rebuild with memory backup (after code changes):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_dashboard.ps1 -Update
```

See [COMMANDS.md](COMMANDS.md) for all commands, flags, and clean-start order.

The script:
1. Checks Docker is installed and running
2. Verifies `.env` exists and `DEEPSEEK_API_KEY` is set (value is never printed)
3. Builds the Docker image
4. Starts the `dashboard` container in the background
5. Waits for the server to be ready
6. Opens `http://127.0.0.1:8787` in your default browser

### Open the dashboard

```
http://127.0.0.1:8787
```

### Open the session-first workbench

```
http://127.0.0.1:8787/chat
```

The new workbench keeps the existing `/runs` dashboard untouched and adds a
session-first DeepSeek UI with local session persistence under `.agent_memory/`:

- persistent sessions with per-turn model profile snapshots
- model/profile switching without losing history
- deterministic local context assembly and context inspection
- pinned and retrieved memory atoms
- memory atom search for session-scoped recall checks
- manual session compression into session spines
- bounded Scout-style subagents that write attachable evidence artifacts
- a deterministic Task Router that classifies repo search, test runs, doc writes, log scans, and mixed evidence+test tasks (spawns two subagents in one prompt)
- compact EvidencePack attachment so the parent session stays the source of truth
- Agent OS operator panels: Playbooks, Tools, Approvals, Reports, Decisions, Memory Patches, Evidence Bundles

### Stop the dashboard

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_dashboard.ps1
```

### Run all tests + lint

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_dashboard.ps1
```

### Dashboard endpoints

| Route | Purpose |
|-------|---------|
| `GET /` | Home page shell: prompt panel, live status, activity feed, output, recent runs |
| `POST /runs` | Create a background run and return `run_id` immediately |
| `GET /runs` | JSON list of recent dashboard runs |
| `GET /runs/{run_id}/status` | Current status, phase, elapsed time, exit code, latest event |
| `GET /runs/{run_id}/output` | Redacted combined output plus stdout/stderr buffers |
| `GET /runs/{run_id}/events` | Ordered redacted activity feed events |
| `POST /runs/{run_id}/cancel` | Cancel a running prompt |
| `GET /health` | Liveness: `{"ok": true}` |
| `GET /config-status` | Sanitised config (no API key) |
| `GET /chat` | Session-first workbench UI |
| `GET /models` | Top-level model catalog alias used by acceptance checks |
| `GET /chat/models` | Model catalog plus default workbench profiles |
| `GET /chat/sessions` | List saved chat sessions |
| `POST /chat/sessions` | Create a new session |
| `GET /chat/sessions/{session_id}` | Session detail: turns, events, memory, artifacts, subagents |
| `POST /chat/sessions/{session_id}/message` | Send a user message through the session runtime |
| `POST /chat/sessions/{session_id}/profile` | Switch the active model/profile |
| `GET /chat/sessions/{session_id}/memory` | List session-relevant memory atoms |
| `GET /chat/sessions/{session_id}/memory/search?q=...` | Search session-relevant memory atoms without exposing hidden reasoning |
| `POST /chat/sessions/{session_id}/memory` | Create a memory atom |
| `POST /chat/sessions/{session_id}/context` | Inspect the assembled prompt context |
| `POST /chat/sessions/{session_id}/compress` | Manually compact older turns into a session spine |
| `GET /chat/sessions/{session_id}/subagents` | List subagent runs for the session |
| `POST /chat/sessions/{session_id}/subagents` | Spawn a bounded subagent |
| `GET /chat/playbooks` | List operator playbooks |
| `GET /chat/tools` | List registered agent tools |
| `GET /chat/approvals` | List pending operator approvals |
| `POST /chat/approvals/{id}/approve` | Approve a pending action |
| `POST /chat/approvals/{id}/reject` | Reject a pending action |
| `GET /chat/reports` | List validation reports |
| `POST /chat/reports/scan` | Trigger a new report scan |
| `GET /chat/decisions` | List operator decisions |
| `POST /chat/decisions` | Add a new decision |
| `POST /chat/decisions/{id}/deprecate` | Deprecate a decision |
| `GET /chat/memory-patches` | List memory patch proposals |
| `POST /chat/memory-patches` | Create a memory patch |
| `POST /chat/memory-patches/{id}/approve` | Approve a memory patch |
| `POST /chat/memory-patches/{id}/reject` | Reject a memory patch |
| `GET /chat/evidence-bundles` | List evidence bundles |
| `POST /chat/evidence-bundles/scan` | Trigger evidence bundle scan |

### Task Router and Evidence Packs

The `/chat` workbench can now route bounded task classes before the parent
model answers:

- `repo_search` → read-only scout evidence gathering
- `test_run` → tests-only validation and compact test reports
- `doc_write` → read-only context gathering before drafting operator notes
- `log_scan` → read-only log inspection without printing full files
- `mixed` → both EvidencePack and TestReport requested; spawns two subagents in parallel (ScoutAgent + TestScoutAgent)

Each routed child writes an untrusted artifact under `.agent_memory/artifacts/`.
The parent session may attach those artifacts and then consume only a compact
EvidencePack view: summary, a few findings with evidence refs, and key risks or
open questions. Raw hidden reasoning is still excluded from the UI, context
inspector, and artifact rendering.

### Dashboard runtime model

The dashboard now shows the run as an explicit state machine:

- `queued`
- `running`
- `waiting_model`
- `tool_call`
- `executing_command`
- `finalizing`
- `succeeded`
- `failed`
- `cancelled`

The UI polls every second and updates:

- status badge
- current phase
- elapsed time
- latest event
- activity feed
- live output
- recent runs table

When the run reaches `succeeded`, `failed`, or `cancelled`, the polling stops,
the spinner disappears, and the `Run` button becomes active again.

### Activity feed and hidden reasoning

The dashboard shows operational trace only:

- model-visible assistant notes
- tool calls
- terminal command start/end
- command output excerpts
- final answer
- errors and status transitions

It does **not** show raw hidden chain-of-thought or raw `reasoning_content`.
`reasoning_content` is still preserved inside the DeepSeek API loop where needed,
but it is not rendered in dashboard events or output.

### Cancel and refresh

- `Cancel` is available only while a run is active.
- `Refresh` forces an immediate status/output/events poll.
- `Copy output` copies the current output tab.
- Recent runs can be reopened from the table for inspection.

### Dashboard security notes

- **Localhost only**: dashboard binds to `127.0.0.1:8787` by default.
  Changing `DASHBOARD_HOST=0.0.0.0` in `.env` exposes it on the network — only do this behind a firewall or VPN.
- **No API key exposure**: `/config-status` returns `api_key_present: true/false` but never the key value.
- **No arbitrary shell**: the only user input is a prompt string passed to `deepseek-agent run`.
  The full agent safety layer (`safety.py`, `terminal_tool.py`) still applies.
- **Secret redaction**: stdout/stderr from the agent are run through the same redaction patterns as the CLI before being shown in the UI.
- **No raw hidden reasoning**: the dashboard does not render raw `reasoning_content` as user-visible thoughts.
- **Docker sandbox**: prompts run inside the same non-root Docker container as the CLI.

### Dashboard logs

Dashboard metadata is stored under:

- `.agent_runs/dashboard_runs.jsonl` — recent run summaries for the UI
- `.agent_runs/<timestamp>/conversation.jsonl` — redacted agent conversation
- `.agent_runs/<timestamp>/terminal.log` — redacted terminal tool results
- `.agent_runs/<timestamp>/summary.md` — final answer

### Clean daily restart with preserved history

If you want a clean daily restart, remove old containers and start the dashboard again.
This does **not** delete dashboard history, because the project bind-mount keeps
`.agent_runs/` and `.env` on the host filesystem, outside the container lifecycle.

Recommended daily start on Windows:

```powershell
cd C:\Users\user\Music\Phenix\tools\deepseek-terminal-agent
$env:PATH += ";C:\Program Files\Docker\Docker\resources\bin"
docker compose down --remove-orphans
powershell -ExecutionPolicy Bypass -File .\scripts\start_dashboard.ps1
```

If the code or dependencies changed and you want a fully fresh image first:

```powershell
cd C:\Users\user\Music\Phenix\tools\deepseek-terminal-agent
$env:PATH += ";C:\Program Files\Docker\Docker\resources\bin"
docker compose down --remove-orphans
docker compose build
powershell -ExecutionPolicy Bypass -File .\scripts\start_dashboard.ps1
```

Recommended end-of-day stop:

```powershell
cd C:\Users\user\Music\Phenix\tools\deepseek-terminal-agent
$env:PATH += ";C:\Program Files\Docker\Docker\resources\bin"
powershell -ExecutionPolicy Bypass -File .\scripts\stop_dashboard.ps1
```

What is preserved across container cleanup:

- `.agent_runs/` history, including recent runs, conversation logs, terminal logs, and summaries
- `.env` configuration, including `DEEPSEEK_API_KEY`
- Docker images, unless you delete them explicitly

What is **not** preserved automatically:

- a live model conversation state between separate dashboard runs
- hidden model reasoning reused as a future prompt context

Each dashboard run starts as a new agent execution. The preserved "memory" is the
host-side operational history and artifacts, not an automatically resumed chat session.

Avoid starting ad-hoc containers manually with `docker run` unless you also pass the
same environment and mount configuration. The supported path is `start_dashboard.ps1`,
which checks `.env`, verifies `DEEPSEEK_API_KEY`, builds the images, starts the
dashboard, and waits for `/health`.

### If the UI still shows Running

If the page ever appears stale after a run should be finished:

1. Click `Refresh` in the dashboard.
2. Check `GET /runs/{run_id}/status` and confirm the backend status.
3. Inspect container logs:

```powershell
docker compose logs dashboard
```

If `status` is already `succeeded`, `failed`, or `cancelled`, the frontend should
reset the button and stop polling automatically. If it does not, treat that as a
frontend regression.

### PowerShell PATH note

If Docker is not found automatically, add it to the session PATH first:

```powershell
$env:PATH += ";C:\Program Files\Docker\Docker\resources\bin"
```

The `start_dashboard.ps1` script does this automatically if needed.

---

## .env Setup

All required and optional environment variables:

```bash
# Required
DEEPSEEK_API_KEY=sk-your-key-here

# Optional — override config/agent.yaml values
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro          # or deepseek-v4-flash, deepseek-chat
DEEPSEEK_REASONING_ENABLED=true
DEEPSEEK_REASONING_EFFORT=high           # high | medium | low

AGENT_WORKSPACE=/workspace/project       # path inside container
AGENT_MAX_ITERATIONS=20
AGENT_COMMAND_TIMEOUT_SEC=120
AGENT_MAX_COMMAND_OUTPUT_CHARS=20000
AGENT_REQUIRE_APPROVAL_FOR_DANGEROUS=true
AGENT_ALLOW_NETWORK=true
```

---

## Running Locally Without Docker

```bash
cd tools/deepseek-terminal-agent
make setup

# Point workspace at your project
export AGENT_WORKSPACE=/path/to/your/project
export DEEPSEEK_API_KEY=sk-...

deepseek-agent chat
# or:
deepseek-agent run "Run the test suite and summarise failures."
```

> Note: `terminal_exec` calls `bash -lc`, which requires bash on PATH.
> On Windows, use Git Bash or WSL, or run inside Docker.

---

## Running With Docker

```bash
make docker-build
make docker-run
```

The full Phenix repo root is mounted at `/workspace/project` inside the
container. The agent package code stays in
`/workspace/project/tools/deepseek-terminal-agent`, so the dashboard launcher
and CLI still start from that subdirectory while the terminal tool can read
`/workspace/project/logs/order_log_v1.jsonl`. The agent runs as non-root user
`agent`.

---

## Recommended Docker Workflow

### First-time setup

```bash
cd tools/deepseek-terminal-agent

# 1. Copy the example config and add your API key
cp .env.example .env
# Edit .env: set DEEPSEEK_API_KEY=sk-your-key-here

# 2. Build the Docker image (~90 s on first build, cached after that)
docker compose build
```

### Interactive chat session

```bash
docker compose run --rm deepseek-agent
# or:
docker compose run --rm deepseek-agent deepseek-agent chat
```

### Single-shot run

```bash
docker compose run --rm deepseek-agent deepseek-agent run "Analyse this repo and run tests."
docker compose run --rm deepseek-agent deepseek-agent run "What failing tests exist and why?"
docker compose run --rm deepseek-agent deepseek-agent run --dry-run "How would you fix the lint errors?"
```

### Running the test suite inside Docker

```bash
# Full suite (307 tests, 9 skipped — all bash tests run in Linux)
docker compose run --rm --entrypoint pytest deepseek-agent -q

# Verbose with short tracebacks
docker compose run --rm --entrypoint pytest deepseek-agent -v --tb=short
```

### Linting inside Docker

```bash
docker compose run --rm --entrypoint ruff deepseek-agent check src/ tests/
```

### Byte-compile sanity check

```bash
docker compose run --rm --entrypoint python deepseek-agent -m compileall src/
```

### Key `docker compose` flags

| Flag | Purpose |
|------|---------|
| `--rm` | Remove the container after exit |
| `--entrypoint <cmd>` | Override the `deepseek-agent` entrypoint (needed for pytest, ruff, python) |
| `-it` | Attach a TTY for interactive sessions (added automatically for `chat`) |

### Docker troubleshooting

| Symptom | Fix |
|---------|-----|
| `docker: command not found` in Git Bash / WSL | Run `export PATH="/c/Program Files/Docker/Docker/resources/bin:$PATH"` |
| `Cannot connect to the Docker daemon` | Start Docker Desktop, wait for whale icon |
| `No such command 'pytest'` | Use `--entrypoint pytest` — the container ENTRYPOINT is `deepseek-agent` |
| `401 Unauthorized` on first run | `DEEPSEEK_API_KEY` missing or wrong in `.env` |
| `400 invalid_request_error` with reasoning | Set `DEEPSEEK_REASONING_ENABLED=false` or upgrade `openai` package |
| Volume permission errors on Windows | Run Docker Desktop as Administrator or check Hyper-V/WSL2 sharing |
| Image not rebuilt after code change | Run `docker compose build` again (the `src/` layer invalidates cache) |

---

## CLI Commands

```
deepseek-agent [OPTIONS] COMMAND [ARGS]

Options:
  --config PATH       config/agent.yaml path      (default: config/agent.yaml)
  --workspace DIR     override workspace root
  --verbose           per-iteration debug output
  --env-file PATH     .env file to load            (default: .env)

Commands:
  chat                Interactive multi-turn session
  run PROMPT          Single-shot run, prints result
    --dry-run         Show commands without executing
```

Examples:
```bash
deepseek-agent chat
deepseek-agent run "Analyse this repo."
deepseek-agent run --dry-run "What commands would you run to fix failing tests?"
deepseek-agent --workspace /my/project --verbose chat
deepseek-agent --config /custom/agent.yaml run "Run pytest."
```

---

## Config Reference

`config/agent.yaml` (values shown are defaults):

```yaml
deepseek:
  base_url: "https://api.deepseek.com"
  model: "deepseek-v4-pro"
  reasoning_enabled: true
  reasoning_effort: "high"    # high | medium | low
  temperature: 0.2
  max_tokens: 8192

terminal:
  workspace_root: "/workspace/project"
  default_timeout_sec: 120
  max_output_chars: 20000
  shell: "bash"
  require_approval_for_dangerous: true
  allow_network: true

agent:
  max_iterations: 20
  log_dir: ".agent_runs"
  system_prompt_path: "src/deepseek_terminal_agent/prompts/system.md"
```

Env vars always override YAML.  Unknown model IDs are **never** silently
replaced — the API returns a 404 and the agent reports it clearly.

### Reasoning mode

Reasoning is passed via `extra_body={"reasoning_effort": "high"}` to the
OpenAI-compatible endpoint.  If your SDK version or DeepSeek API version does
not support this parameter, set `DEEPSEEK_REASONING_ENABLED=false`.

If the parameter name changes in a future DeepSeek API version, edit
`deepseek_client._reasoning_extra_body()` and update this section.

---

## Safety Model

The agent classifies every command before execution using pattern matching in
`safety.py`.

**Dangerous patterns** (blocked or require approval):
- `rm -rf /`, `rm -fr`, force-delete at root
- `sudo`, `su -`, privilege escalation
- `mkfs`, `dd if=`, disk operations
- `shutdown`, `reboot`, `halt`, `poweroff`
- fork bomb `:(){ :|:& };:`
- `chmod -R 777 /`, `chown -R ... /`
- `curl ... | bash`, `wget ... | sh`, pipe to shell
- `docker.sock` access
- `cat .env`, `printenv`, bare `env`, credential file access

**When `AGENT_REQUIRE_APPROVAL_FOR_DANGEROUS=true` (default)**:
- Interactive mode (`chat`): human is prompted `[y/N]` before execution
- Non-interactive mode (`run`): dangerous command is **blocked** (not executed)
- Dry-run mode: dangerous command is **blocked**

The block is hard — `terminal_exec` returns `{"ok": false, "blocked": true}`
and the command is never executed.

---

## Logs

Each run creates a timestamped directory:

```
.agent_runs/
  2026-04-30T10-15-00/
    conversation.jsonl   — all messages (API keys redacted)
    terminal.log         — each terminal_exec call
    summary.md           — final answer
```

All log content is secret-redacted before writing (`sk-*` keys, Bearer tokens,
`api_key=` patterns).

---

## Running Tests

```bash
# Local (bash tests skip if bash not on PATH)
make test

# Full suite (inside Docker — all tests run)
docker compose run --rm deepseek-agent pytest -q

# With coverage
pytest --cov=deepseek_terminal_agent tests/
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `401 Unauthorized` | Invalid API key | Check `DEEPSEEK_API_KEY` in `.env` |
| `Model 'X' not found` | Wrong model name | Check `DEEPSEEK_MODEL`; try `deepseek-chat` |
| `Docker not running` | Docker daemon down | Start Docker Desktop or daemon |
| `Permission denied on mounted volume` | Windows volume permissions | Run Docker Desktop as administrator |
| `Command timed out` | Command exceeded `AGENT_COMMAND_TIMEOUT_SEC` | Increase timeout or optimise the command |
| `BLOCKED: dangerous command` | Safety classifier triggered | Check `safety.py` patterns; approve manually in chat mode |
| `Reasoning parameter unsupported` | Old SDK or API version | Set `DEEPSEEK_REASONING_ENABLED=false` or `pip install --upgrade openai` |
| `bash not found` | Running on Windows without bash | Use Docker, Git Bash, or WSL |
| `[CONFIG ERROR] DEEPSEEK_API_KEY is required` | Key not set | `cp .env.example .env` and set the key |

---

## Example Session

```
You: Analyse this repository, run tests, find failures, and propose a patch.

Agent: [runs terminal_exec: ls, git log, pytest -q, ...]

## Final Report
**Verdict**: COMPLETED

**Summary**: Found 2 failing tests in tests/unit/test_config.py due to a
missing env var. Applied patch to default the value. Tests now pass.

**Files Changed**:
- `src/app/config.py` — added default for TIMEOUT env var

**Commands Run**:
- `ls` → exit_code: 0
- `pytest -q` → 3 failed, 42 passed
- `git diff` → shows the patch

**Tests Run**: 45 passed, 0 failed (after fix)

**Next Recommended Step**: Review the patch and commit.
```

---

## Switching Models

```bash
# In .env:
DEEPSEEK_MODEL=deepseek-v4-flash    # faster, cheaper
DEEPSEEK_MODEL=deepseek-chat        # default chat model
DEEPSEEK_MODEL=deepseek-v4-pro      # most capable (default)
```

The agent never silently falls back to another model — if the model is not
found, it prints an error and exits.

---

## Limitations

- `terminal_exec` is the only tool — no web search, no image analysis
- No streaming output (responses appear after the full API call)
- Conversation history grows each turn; for very long sessions, consider
  restarting to avoid hitting `max_tokens`
- The bash tests are skipped on Windows without bash — run in Docker for
  full test coverage
- DeepSeek API availability and model names may change; check
  https://platform.deepseek.com/api-docs for current model IDs
