# AGENTIC_DASHBOARD_HANDOFF_V1

Документ сформовано як handoff для перенесення контексту в інший чат ChatGPT, щоб продовжити розробку агентного API-dashboard / Agentic Project OS без повторного розгону. Вимоги до структури handoff взяті з наданого файлу. 

---

## 1. Executive Summary

Ми будуємо не звичайний AI-чат, а **Agentic Project OS / Project Agent Control Center** для великих кастомних проєктів на кшталт Aurora/Phenix.

Це локальний dashboard / workbench, де людина керує:

* API-моделями;
* агентами;
* SubAgents;
* контекстом;
* памʼяттю;
* логами;
* playbooks;
* approvals;
* reports;
* тестами;
* runtime-evidence;
* structured development workflows.

Ключова різниця від звичайного AI-чату:

```text
AI chat:
людина пише промпт → модель відповідає

Agentic Project OS:
людина запускає сценарій → система збирає контекст → запускає агентів → виконує scripts/tools → формує evidence → модель аналізує → створює report → людина приймає/відхиляє
```

Головна проблема, яку система вирішує:

```text
у великих проєктах контекст розмазаний між чатами, логами, кодом, звітами, рішеннями, тестами й памʼяттю.
```

Agentic Project OS має зробити це керованим:

```text
Project Capsule + SSOT Memory + Playbooks + Agents + Evidence + Reports + Approvals
```

---

## 2. Product Vision

Кінцевий продукт — dashboard для роботи з API-моделями й агентними системами під конкретний великий проєкт.

Він має дозволяти:

* запускати агентів під конкретний проєкт;
* керувати агентними сценаріями;
* мати **Project Capsule**;
* тримати **SSOT-памʼять**;
* підтримувати **deep checkpoint**;
* робити міжчатовий / міжзадачний пошук;
* запускати playbook-кнопки;
* використовувати hotkeys / command palette;
* виконувати script-first log analysis;
* формувати evidence-first reports;
* мати approval queue;
* контролювати tool permission registry;
* бачити trace timeline;
* зберігати structured agent reports;
* оновлювати memory тільки через patch approval.

Dashboard має бути human-friendly зовні, але всередині — строго інженерний.

Не “гарний чат”, а:

```text
операційна кабіна для керованої агентної роботи.
```

---

## 3. Core Philosophy / Doctrine

Базові принципи:

1. **Модель не є джерелом істини.**
2. Джерело істини — SSOT, structured logs, scripts, reports, decision ledger.
3. Модель інтерпретує evidence, а не вигадує факти.
4. У постійній памʼяті має бути тільки deep SSOT context, а не весь шум чатів.
5. Кожна агентна дія має trace.
6. Кожна значуща робота має завершуватись report.
7. **Немає report — задача не DONE.**
8. **Немає evidence — немає факту.**
9. **Немає approval — агент не чіпає production/config/runtime.**
10. Memory оновлюється тільки через patch/proposal і human approval.
11. Raw logs не мають хаотично аналізуватись моделлю.
12. Runtime evidence має збиратись скриптами.
13. Deprecated facts не видаляються, а маркуються.
14. Context має бути previewable перед запуском агента.
15. SubAgents — не “рольові персонажі”, а bounded workers з tool policy, timeout, output schema і hard bans.

---

## 4. Current Architecture Concept

### Frontend

Цільовий dashboard має включати:

* project selector;
* main workspace;
* left sidebar;
* right context/control panel;
* command palette;
* hotkeys;
* agent graph viewer;
* reports viewer;
* memory editor;
* log analysis center;
* approval queue;
* trace viewer;
* context preview;
* model/session controls;
* SubAgents panel;
* EvidencePack viewer.

Базовий layout:

```text
┌─────────────────────────────────────────────────────────────┐
│ Project: Aurora / Phenix                         STATUS: ...│
├───────────────┬───────────────────────┬─────────────────────┤
│ LEFT SIDEBAR  │ MAIN WORKSPACE         │ RIGHT CONTROL PANEL │
│               │                       │                     │
│ Agents        │ Active task / chat     │ Context preview     │
│ Playbooks     │ Logs / reports         │ SSOT rules          │
│ Logs          │ Trace timeline         │ Memory snippets     │
│ Reports       │ Code / diff / output   │ Tool permissions    │
│ Memory        │ Agent graph            │ Approval queue      │
│ Search        │                       │ Risk warnings       │
└───────────────┴───────────────────────┴─────────────────────┘
```

### Backend

Цільові backend-компоненти:

* agent orchestrator;
* playbook runner;
* script runner;
* model router;
* session store;
* memory service;
* report service;
* approval engine;
* tool registry;
* trace/event recorder;
* task router;
* prompt reformatter;
* context builder;
* context compressor;
* artifact store;
* SubAgent manager.

### Storage

Цільовий storage-рівень:

* Postgres для structured entities;
* pgvector або Qdrant для retrieval;
* object storage для reports/log bundles;
* git-backed memory/checkpoints;
* decision ledger;
* chat archive;
* report index;
* artifact store.

Поточна реалізація, за історією чату:

```text
UNKNOWN чи вже є Postgres/pgvector/Qdrant.
Ймовірно поточний implementation тримається на локальних файлах .agent_memory / .agent_runs.
```

### Execution Layer

Цільовий execution-рівень:

* sandbox workers;
* repo worktrees;
* test runners;
* MCP/tool servers;
* script execution containers;
* Docker Compose runtime;
* project-scoped containers;
* tool policy validators.

---

## 5. Project Capsule

**Project Capsule** — центральна машинно-читабельна одиниця проєкту.

Вона описує, що агент має знати завжди, але контрольовано.

Має містити:

* project identity;
* domain;
* current phase;
* SSOT rules;
* architecture map;
* active agents;
* allowed tools;
* active playbooks;
* memory checkpoint;
* accepted reports;
* open risks;
* frozen decisions;
* deprecated decisions;
* current implementation plan.

Приклад:

```yaml
project_capsule:
  project:
    name: "Aurora/Phenix"
    domain: "algorithmic_trading_system"
    mode: "live_runtime_sensitive"
    current_phase: "agentic_dashboard_development"

  ssot_rules:
    config:
      - "YAML + Pydantic only"
      - "extra='forbid'"
      - "no silent fallbacks"
      - "no hidden constants in business logic"
    development:
      - "contract-first"
      - "additive-only when possible"
      - "TDD required"
      - "one package = one report"
      - "agent report required before DONE"
    runtime:
      - "do not change live behavior without explicit flag"
      - "logs are evidence"
      - "scripts collect data; model interprets structured output"

  memory:
    deep_checkpoint: "enabled"
    accepted_reports_only: true
    default_agent_search_mode: "current_ssot_and_accepted_facts"

  permissions:
    production_changes: "approval_required"
    config_changes: "approval_required"
    registry_changes: "approval_required"
    memory_updates: "patch_approval_required"

  risks:
    - "agent may see wrong workspace root"
    - "raw log analysis by model can produce false facts"
    - "memory can degrade if unvalidated summaries are accepted"
```

---

## 6. Memory System

### Always Loaded

Постійно в prompt / context pack має йти тільки компактний deep context:

* `deep_checkpoint.md` на приблизно 1500–3000 токенів;
* `active_project_rules.yaml`;
* `current_phase_state.json`;
* поточна architecture map;
* critical warnings;
* accepted current decisions;
* active open risks;
* current implementation constraints.

### Retrieved On Demand

Підтягується тільки за потреби:

* accepted reports;
* chat summaries;
* decision ledger entries;
* code/context snippets;
* script outputs;
* previous task reports;
* EvidencePacks;
* TestReports;
* LogScan artifacts;
* relevant memory atoms.

### Never Loaded By Default

Не вантажиться автоматично:

* full raw chat history;
* raw logs;
* full repo;
* старі deprecated рішення;
* невалідовані summaries;
* великі stdout/stderr;
* повні runtime JSONL-файли;
* `.env`, secrets, keys.

### Міжчатовий пошук

Потрібна система:

```text
raw messages зберігаються
↓
summaries генеруються
↓
embeddings будуються
↓
keyword + vector hybrid search
↓
filters
↓
accepted/current facts mode for agents
```

Фільтри:

* project;
* domain;
* date;
* status;
* verdict;
* agent;
* type;
* accepted only;
* deprecated included/excluded;
* current SSOT only;
* report type;
* runtime window.

За замовчуванням для агентів:

```text
current SSOT + accepted facts only
```

---

## 7. Agent System

### Scout Agent

Purpose:

* read-only збір контексту;
* пошук файлів;
* grep/rg;
* коротке summary.

Allowed tools:

* read files;
* list tree;
* grep/rg/find;
* safe cat/head/tail with output limits.

Write permissions:

* none.

Required output:

* `CONTEXT_SCAN_REPORT_V1` або `EVIDENCE_PACK_V1`.

Approval:

* not required for read-only.

Failure mode:

* `INSUFFICIENT_CONTEXT`;
* `WORKSPACE_NOT_FOUND`;
* `TOOL_POLICY_BLOCKED`.

---

### Planner Agent

Purpose:

* план імплементації;
* розбиття задачі;
* ризики;
* test plan.

Allowed tools:

* read files;
* search memory;
* inspect contracts;
* inspect tests.

Write permissions:

* none.

Required output:

* `IMPLEMENTATION_PLAN_V1`.

Approval:

* plan must be approved before risky implementation.

Failure mode:

* `PLAN_BLOCKED`;
* `MISSING_EVIDENCE`;
* `DUPLICATION_RISK`.

---

### Implementer Agent

Purpose:

* мінімальні code changes;
* tests;
* report.

Allowed tools:

* edit files;
* run tests;
* run linters;
* inspect diffs.

Write permissions:

* source/tests/docs within allowed scope.

Required output:

* `AGENT_REPORT_V1`.

Approval:

* required before config/schema/registry/runtime behavior changes;
* may require approval before first write depending task policy.

Failure mode:

* `TESTS_FAILED`;
* `UNSAFE_CHANGE`;
* `SCOPE_CREEP`;
* `REPORT_MISSING`.

---

### Auditor Agent

Purpose:

* незалежна перевірка попереднього агента;
* пошук drift, duplication, silent fallbacks.

Allowed tools:

* read files;
* run tests;
* compare contracts;
* inspect logs;
* inspect changed files.

Write permissions:

* none.

Required output:

* `AUDIT_REPORT_V1`.

Approval:

* not required for read-only audit.

Failure mode:

* `INSUFFICIENT_EVIDENCE`;
* `AUDIT_BLOCKED`;
* `CONTRADICTION_FOUND`.

---

### Runtime Forensics Agent

Purpose:

* аналіз runtime logs тільки через script outputs / evidence bundles.

Allowed tools:

* run approved log scripts;
* read structured outputs;
* inspect reports.

Write permissions:

* reports/drafts only.

Required output:

* `RUNTIME_FORENSIC_REPORT_V1`.

Approval:

* required before any recommendation that changes live behavior.

Failure mode:

* `INSUFFICIENT_EVIDENCE`;
* `SCRIPT_OUTPUT_INVALID`;
* `RAW_LOG_ACCESS_DENIED`.

---

### Memory Curator

Purpose:

* пропозиції оновлення памʼяті;
* checkpoint patch;
* decision ledger patch.

Allowed tools:

* read accepted reports;
* read decision ledger;
* draft memory patches.

Write permissions:

* memory draft only.

Required output:

* `MEMORY_PATCH_V1`.

Approval:

* always required before applying memory update.

Failure mode:

* `PATCH_REJECTED`;
* `SOURCE_REPORT_MISSING`;
* `CONFLICT_WITH_EXISTING_MEMORY`.

---

### Prompt Builder

Purpose:

* формування мега-промптів для агентів-автопілотів.

Allowed tools:

* read context;
* read previous reports;
* inspect project capsule.

Write permissions:

* prompt drafts only.

Required output:

* `MEGA_PROMPT_V1`.

Approval:

* user approval before execution.

Failure mode:

* `SCOPE_UNCLEAR`;
* `RISK_NOT_SPECIFIED`;
* `DONE_CRITERIA_MISSING`.

---

### Report Writer

Purpose:

* фіналізація structured reports.

Allowed tools:

* read agent outputs;
* read tests;
* read artifacts.

Write permissions:

* reports/drafts;
* final reports only after approval if required.

Required output:

* structured report by schema.

Failure mode:

* `REPORT_SCHEMA_INVALID`;
* `MISSING_TEST_OUTPUT`;
* `MISSING_VERDICT`.

---

### Release Gatekeeper

Purpose:

* перевірка готовності;
* release/cutover gating.

Allowed tools:

* read reports;
* run tests;
* inspect configs;
* inspect risks.

Write permissions:

* none by default.

Required output:

* `RELEASE_GATE_REPORT_V1`.

Approval:

* release/change approval required.

Failure mode:

* `BLOCKED`;
* `TESTS_NOT_GREEN`;
* `OPEN_RISK_UNRESOLVED`.

---

### Config/Registry Guardian

Purpose:

* контроль SSOT/config/schema/registry.

Allowed tools:

* read configs;
* inspect schema;
* inspect registry;
* run contract tests.

Write permissions:

* none by default; write only with explicit approval.

Required output:

* `CONFIG_REGISTRY_AUDIT_V1`.

Approval:

* always for config/schema/registry changes.

Failure mode:

* `SSOT_DRIFT`;
* `UNREGISTERED_EVENT`;
* `SILENT_FALLBACK_FOUND`.

---

## 8. Playbook System

Playbook — стандартизований сценарій агентної роботи.

Кожен playbook має:

* trigger button;
* hotkey;
* input sources;
* scripts;
* agents;
* output schema;
* approval points;
* DONE criteria.

### 1. Scout Before Implementation

Trigger:

* button: `Scout Context`
* hotkey: `Ctrl+Shift+S`

Inputs:

* Project Capsule;
* current task;
* repo tree;
* relevant tests/config.

Agents:

* Scout Agent.

Output:

* `CONTEXT_SCAN_REPORT_V1`.

DONE:

* exact files inspected;
* duplicate risk checked;
* relevant tests found;
* no writes.

---

### 2. Build Implementation Plan

Trigger:

* button: `Build Plan`
* hotkey: `Ctrl+Shift+P`

Inputs:

* context scan;
* Project Capsule;
* SSOT rules.

Agents:

* Planner Agent.

Output:

* `IMPLEMENTATION_PLAN_V1`.

DONE:

* scope clear;
* risks listed;
* tests proposed;
* approval points marked.

---

### 3. Guarded Implementation

Trigger:

* button: `Implement With Tests`

Inputs:

* approved plan;
* context scan;
* tests.

Agents:

* Implementer Agent.

Output:

* `AGENT_REPORT_V1`.

Approval:

* before config/schema/registry/runtime changes.

DONE:

* patch applied;
* tests run;
* report produced;
* residual risks listed.

---

### 4. Independent Audit

Trigger:

* button: `Audit Previous Agent`
* hotkey: `Ctrl+Shift+A`

Inputs:

* agent report;
* changed files;
* tests;
* configs.

Agents:

* Auditor Agent.

Output:

* `AUDIT_REPORT_V1`.

DONE:

* drift checked;
* duplication checked;
* silent fallbacks checked;
* verdict produced.

---

### 5. Runtime Log Analysis

Trigger:

* button: `Analyze Runtime Logs`
* hotkey: `Ctrl+Shift+L`

Inputs:

* runtime window;
* structured log bundle;
* Project Capsule;
* accepted runtime rules.

Agents:

* Runtime Forensics Agent.

Scripts:

* log collector;
* lifecycle summarizer;
* reject extractor;
* evidence bundle builder.

Output:

* `RUNTIME_FORENSIC_REPORT_V1`.

DONE:

* scripts run;
* evidence bundle validated;
* no raw log hallucination;
* report cites script outputs.

---

### 6. LOW_VOL / NRR / Order Lifecycle Analysis

Trigger:

* buttons:

  * `Analyze LOW_VOL`
  * `Analyze NRR Rejects`
  * `Check Order Lifecycle`

Inputs:

* structured runtime evidence;
* accepted NRR/LVC reports;
* relevant config.

Agents:

* Runtime Forensics Agent;
* Auditor Agent optional.

Output:

* domain-specific forensic report.

DONE:

* counts/statistics from scripts;
* findings separated from inference;
* recommendation classified.

---

### 7. Generate Next Agent Prompt

Trigger:

* button: `Next Agent Prompt`
* hotkey: `Ctrl+Shift+N`

Inputs:

* current phase;
* latest reports;
* open risks;
* user goal.

Agents:

* Prompt Builder.

Output:

* `MEGA_PROMPT_V1`.

DONE:

* scope;
* constraints;
* tests;
* report schema;
* DONE criteria.

---

### 8. Update Memory Checkpoint

Trigger:

* button: `Update Checkpoint`
* hotkey: `Ctrl+Shift+M`

Inputs:

* accepted reports only;
* current checkpoint;
* decision ledger.

Agents:

* Memory Curator.

Output:

* `MEMORY_PATCH_V1`.

Approval:

* required.

DONE:

* patch approved/rejected;
* source reports cited;
* deprecated facts marked.

---

### 9. Compare Reports

Trigger:

* button: `Compare Reports`

Inputs:

* two or more reports;
* decision ledger;
* current SSOT.

Agents:

* Auditor Agent.

Output:

* `REPORT_COMPARISON_V1`.

DONE:

* contradictions found;
* superseded facts identified;
* current accepted facts listed.

---

### 10. Regression Risk Scan

Trigger:

* button: `Regression Risk`
* hotkey: `Ctrl+Shift+R`

Inputs:

* changed files;
* tests;
* previous reports;
* config/schema registry.

Agents:

* Auditor Agent;
* Config/Registry Guardian.

Output:

* `REGRESSION_RISK_REPORT_V1`.

DONE:

* risk map;
* test coverage;
* missing tests;
* recommended gates.

---

## 9. Script-first Log Analysis

Принцип:

```text
Raw logs
  ↓
trusted scripts
  ↓
normalized evidence bundle
  ↓
model interpretation
  ↓
structured report
  ↓
human approval
  ↓
memory/report ledger update
```

Обовʼязково:

* модель не повинна хаотично аналізувати raw logs;
* скрипти мають збирати:

  * tables;
  * counts;
  * windows;
  * symbols;
  * reject reasons;
  * lifecycle chains;
  * PnL summaries;
  * gate pressure;
  * timestamp ranges;
* модель отримує structured evidence bundle;
* всі висновки моделі мають посилатись на script output;
* якщо даних немає, verdict:

  * `INSUFFICIENT_EVIDENCE`;
  * не фантазія;
* raw logs можуть читатись тільки для sampling/debug, якщо explicitly allowed;
* повний dump logs у prompt заборонений.

---

## 10. UI / UX Dashboard Design

### Main Dashboard

Показує:

* project status;
* active branch;
* current runtime status;
* last accepted report;
* open risks;
* active agent runs;
* memory checkpoint version;
* SSOT status;
* Docker/runtime status;
* model provider status;
* current task graph.

### Left Sidebar

* Projects;
* Agents;
* Playbooks;
* Logs;
* Reports;
* Memory;
* Search;
* Tools;
* Approvals;
* Settings.

### Main Workspace

Режими:

1. **Chat Mode**

   * обговорення;
   * session-first context;
   * model switching.

2. **Task Mode**

   * playbook execution;
   * task graph;
   * SubAgents;
   * approvals.

3. **Evidence Mode**

   * logs;
   * reports;
   * diffs;
   * test outputs;
   * artifacts.

Елементи:

* active task;
* agent graph;
* report output;
* code/diff viewer;
* log analysis output;
* live trace.

### Right Panel

* loaded context preview;
* SSOT rules;
* retrieved memory snippets;
* allowed tools;
* model/runtime budget;
* risk warnings;
* approval requests;
* task settings;
* context pack preview.

### Command Palette / Hotkeys

Приклади команд:

```text
/logs low_vol last 6h
/agent scout
/agent audit previous
/memory update from report
/prompt next implementation
/search accepted LOW_VOL decisions
/tests focused decision_making
/report latest
/context preview
```

Приклади hotkeys:

* analyze logs;
* spawn scout;
* spawn auditor;
* generate report;
* update checkpoint;
* search memory;
* open agent graph;
* run tests;
* open context inspector;
* open approval queue.

---

## 11. Tool Registry & Permissions

Tool permission layer має описувати:

| Tool              |       Risk | Allowed Agents                   | Approval    | Audit | Rollback          |
| ----------------- | ---------: | -------------------------------- | ----------- | ----- | ----------------- |
| read_repo         |        low | scout, planner, auditor          | no          | yes   | n/a               |
| edit_file         |     medium | implementer                      | maybe/yes   | yes   | diff required     |
| run_tests         |        low | implementer, auditor, test scout | no          | yes   | n/a               |
| run_scripts       | low/medium | runtime_forensics, auditor       | depends     | yes   | n/a               |
| update_config     |       high | implementer, config guardian     | yes         | yes   | rollback required |
| update_registry   |       high | implementer, registry guardian   | yes         | yes   | rollback required |
| deploy            |   critical | release gatekeeper               | manual only | yes   | rollback required |
| update_memory     |     medium | memory curator                   | yes         | yes   | patch revert      |
| access_logs       |     medium | runtime_forensics                | controlled  | yes   | n/a               |
| call_external_api |   variable | selected agents                  | depends     | yes   | n/a               |

Правила:

* production/config/runtime зміни тільки через explicit approval;
* destructive commands manual only;
* memory update тільки через patch approval;
* tool policy має бути enforced кодом, не тільки prompt-ом;
* кожен tool call пишеться в trace;
* rollback expectations мають бути явні.

---

## 12. Reports / DONE Contract

Кожен агентний run має завершуватись structured report.

### AGENT_REPORT_V1

```yaml
AGENT_REPORT_V1:
  verdict: IMPLEMENTED_AND_VALIDATED | IMPLEMENTED_WITH_RESIDUALS | BLOCKED
  files_changed: []
  behavior_changed: true|false
  config_changed: true|false
  schema_changed: true|false
  registry_changed: true|false
  tests_run: []
  validation_result: ""
  residual_risks: []
  rollback_notes: ""
  next_recommended_step: ""
```

### AUDIT_REPORT_V1

```yaml
AUDIT_REPORT_V1:
  verdict: ACCEPTED | MIXED_NOT_READY | REJECTED | BLOCKED
  checked_scope: []
  findings: []
  contradictions: []
  duplication_risks: []
  silent_fallback_risks: []
  test_coverage: ""
  recommendations: []
```

### RUNTIME_FORENSIC_REPORT_V1

```yaml
RUNTIME_FORENSIC_REPORT_V1:
  verdict: CLEAN | MIXED | BLOCKED | BUG_CONFIRMED | INSUFFICIENT_EVIDENCE
  evidence_window: ""
  scripts_run: []
  facts: []
  inferred_findings: []
  risks: []
  recommendations: []
  insufficient_data_fields: []
```

### MEMORY_PATCH_V1

```yaml
MEMORY_PATCH_V1:
  proposed_change: ""
  source_reports: []
  reason: ""
  risk: low|medium|high
  affected_checkpoint_section: ""
  approval_required: true
```

DONE contract:

```text
Немає report → задача не DONE.
Немає evidence → факт не прийнятий.
Немає approval → risky action не виконується.
```

---

## 13. Mega Prompt Factory

Роль моделі в цьому чаті:

```text
не просто відповідати,
а формувати мега-промпти для агентів, які працюють в режимі автопілота багато ітерацій.
```

Принцип мега-промпта:

1. глибоке осмислення задачі;
2. явне формулювання scope;
3. контекст проєкту;
4. SSOT rules;
5. заборони;
6. дозволені інструменти;
7. покроковий план;
8. self-validation gates;
9. expected files / areas to inspect;
10. tests to run;
11. report schema;
12. DONE criteria;
13. residual risk section;
14. no assumptions without evidence;
15. no silent fallbacks;
16. no duplicated logic;
17. no production behavior changes unless explicitly requested.

Мега-промпт має дозволити агенту:

* самому зібрати контекст;
* самому побудувати план;
* обережно реалізувати;
* перевірити;
* надати structured report;
* не загубитися після кількох ітерацій;
* не зробити небезпечні зміни без approval.

Процес у цьому чаті далі:

```text
1. Спочатку аналіз і вузькі місця.
2. Потім контракт.
3. Потім acceptance criteria.
4. Тільки після команди користувача “формуй промт” — фінальний prompt агенту.
```

---

## 14. Autopilot Agent Iteration Logic

Агентний автопілот має працювати так:

1. Intake task.
2. Load Project Capsule.
3. Load deep checkpoint.
4. Retrieve relevant memory.
5. Якщо current code/log state unknown — run Scout Agent.
6. Якщо є ризик дублювання — explicit duplication scan.
7. Build plan.
8. Validate plan against SSOT.
9. Якщо risky — request approval.
10. Implement minimal patch.
11. Run focused tests.
12. Run broader regression tests.
13. Produce report.
14. Run independent audit if needed.
15. Propose memory patch.
16. Mark task DONE only after accepted report.

Special gates:

* якщо config/schema/registry зачеплено — окремий gate;
* якщо runtime behavior змінюється — explicit warning;
* якщо evidence недостатньо — stop with `BLOCKED` / `INSUFFICIENT_EVIDENCE`;
* якщо live/runtime-sensitive domain — no silent changes;
* якщо agent report відсутній — task incomplete;
* якщо tests не запущені — task not validated.

---

## 15. Current Phase

```yaml
current_phase:
  name: "Agentic Dashboard / DeepSeek Workbench → Project Agent OS transition"
  status: "IN_PROGRESS"

  completed:
    - "DeepSeek terminal-agent був створений як tools/deepseek-terminal-agent."
    - "Docker-based CLI agent був доведений до FULLY_WORKING за попередніми звітами."
    - "Dashboard FastAPI/Jinja2 був доданий."
    - "Dashboard background-job UI був виправлений: polling, activity feed, cancel, output, status."
    - "AGENT_REPORT_V4 зафіксував FULLY_WORKING для async dashboard: 115 tests passed, health/config-status ok, live prompt smoke ok, cancel smoke ok."
    - "Концепція session-first workbench сформована."
    - "Концепція model switching без втрати контексту сформована."
    - "Концепція MemoryAtoms / SessionSpine / ContextPack сформована."
    - "Концепція SubAgents як bounded workers із EvidencePack сформована."
    - "Концепція Agentic Project OS / Project Agent Control Center сформована."
    - "Зафіксовано doctrine: no report = not DONE; no evidence = no fact; no approval = no risky production/config/runtime change."

  in_progress:
    - "Поточний агент реалізує попередній пакет session-first /chat, model switching, memory, compression, SubAgents, TaskRouter або суміжну логіку."
    - "Фінальний звіт поточного агента ще НЕ наданий у цьому handoff."
    - "Потрібен acceptance review після отримання звіту агента."

  not_started:
    - "Project Capsule як окремий машинно-читабельний контракт."
    - "Playbook Registry."
    - "Tool Registry & Permissions UI."
    - "Approval Queue."
    - "Report Center."
    - "Decision Ledger."
    - "Memory Patch Approval UI."
    - "Runtime Forensics Center зі script-first evidence bundles."
    - "Command Palette / hotkeys."
    - "Full Agent Graph viewer."
    - "Postgres/pgvector/Qdrant storage layer."
    - "ModelProvider abstraction для DeepSeek/HF/NIM/local."
    - "NVIDIA-style provider/orchestration layer."
    - "MCP integration."
    - "Production-grade authentication."

  blockers:
    - "UNKNOWN: чи поточна реалізація /chat після agent work реально пройшла Docker full smoke."
    - "UNKNOWN: чи workspace root у Docker вже точно бачить Phenix root, а не тільки tools/deepseek-terminal-agent."
    - "UNKNOWN: чи sessions survive restart у поточному коді."
    - "UNKNOWN: чи model switch реально preserves context після restart."
    - "UNKNOWN: чи SubAgents реально виконують async evidence workflow, а не тільки мають mock/targeted tests."
    - "UNKNOWN: чи memory/compression має loss report, conflict handling, atomic writes, backup/restore."
    - "UNKNOWN: чи start_dashboard.ps1 має -Update без втрати .agent_memory."

  risks:
    - "Надмірна складність може зламати стабільний baseline."
    - "Memory може стати summary-blob без reversible source refs."
    - "SubAgents можуть стати декоративними, якщо не буде real artifacts + parent attach flow."
    - "Model switching може працювати тільки в UI, але не в реальному ContextBuilder."
    - "Raw logs можуть знову потрапити напряму в модель без trusted scripts."
    - "Dashboard без auth безпечний тільки при localhost-only."
    - "Якщо Docker reset чистить .agent_memory, persistent session і memory будуть фікцією."

  next_best_step:
    - "Дочекатися фінального звіту поточного агента."
    - "Провести acceptance review: Docker full validation, /chat smoke, model switch context, restart persistence, memory atom search, compression, SubAgent evidence pack, workspace root."
    - "Не формувати новий prompt до команди користувача."
    - "Після acceptance — сформувати наступний hardening prompt для Project Agent OS V7: Project Capsule, Playbooks, Tool Registry, Approval Queue, Report Center, Decision Ledger, Memory Patch Flow."
```

---

## 16. Notes For Next Chat

Критично важливе правило процесу:

```text
Не формувати нові великі промпти автоматично.
Спочатку аналіз → вузькі місця → контракт → acceptance criteria.
Фінальний prompt тільки після команди користувача “формуй промт”.
```

Що потрібно від користувача в наступному чаті:

1. Надати фінальний звіт поточного агента.
2. Дати команду на acceptance review.
3. Лише після review вирішити:

   * fix current implementation;
   * harden memory/subagents;
   * перейти до Agentic Project OS V7;
   * або спершу зробити UI/UX polish.

---

## 17. Immediate Acceptance Checklist For Current Agent Report

Коли користувач принесе звіт агента, перевірити:

```yaml
acceptance_checklist:
  docker:
    - docker compose build passed
    - full pytest in Docker passed
    - ruff passed
    - compileall passed
    - dashboard starts after clean compose down/up

  routes:
    - /health works
    - /config-status works
    - /models works
    - /chat works
    - old /runs still works

  workspace:
    - /workspace/project is Phenix root
    - tools/deepseek-terminal-agent exists inside workspace
    - logs/order_log_v1.jsonl checked if present without full dump

  sessions:
    - create session
    - send message
    - switch model
    - ask previous context
    - restart dashboard
    - session still remembers context

  memory:
    - memory atom add/search works
    - context pack includes relevant atoms
    - raw turns preserved
    - compression creates spine
    - compression does not delete raw history

  subagents:
    - ScoutAgent produces EvidencePack
    - TestScoutAgent produces TestReport
    - artifacts are attached to parent session
    - final answer uses artifacts
    - tool policy enforced
    - subagent cancel/timeout works if claimed

  security:
    - api key not printed
    - .env not exposed
    - raw reasoning_content not visible
    - no raw shell endpoint
    - dashboard localhost-only
    - no production trading code changed
```

This handoff is the current compressed state of the project direction.

