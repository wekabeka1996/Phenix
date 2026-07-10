# 10 Target Architecture Recommendation

This report evaluates integration options and recommends a target architecture.

## 1. Option Evaluations

### Option A: DSOS as Primary Host and Controller
- **Description**: Target A manages model calls, loops, and controller.
- **Risk**: **CRITICAL**. Requires rewriting the model-calling pipeline in TypeScript, translating the validated Python preflight and sizing logic, and resolving dual session memory.

### Option B: Phenix as Backend/Runtime; DSOS as Frontend UI
- **Description**: Target B/C owns the execution and APIs; Target A's React UI serves as the operator dashboard.
- **Risk**: **MEDIUM**. Requires mapping all React state requests to the FastAPI backend and disabling the Express backend services.

### Option C: DSOS as API-Agent Runtime; Phenix as Compatibility Bridge
- **Description**: Target A owns API-agent model calls; Target B acts as a bridge wrapper.
- **Risk**: **HIGH**. Inconsistent session files and duplicate model controllers.

### Option D: Standalone Phenix Runtime (DSOS Retired / Unused) (Recommended)
- **Description**: Retire or bypass Target A. Rely strictly on the Python `DualAgentRuntimeRunner` (Target C) and `tools/deepseek-terminal-agent` (Target B).
- **Justification**:
  - Target C already contains a fully validated, tested, and FSM-integrated dual-agent runner.
  - Target B has comprehensive unit test coverage (520+ tests passing) and a clean session store layout local to worktrees.
  - Target A has been stale since **May 24, 2026**, has no active FSM connection, and introduces memory collision risks.
  - This path requires **zero source code changes** to start runs.

---

## 2. Recommendations

### Immediate MVP Path
- Use **Option D**. Execute all runs via the Python supervisor `DualAgentRuntimeRunner` (Target C) utilizing Target B.

### Durable Long-Term Design
- Transition to **Option B**. Retain Target B/C as the sole runtime and API backend. Adapt Target A's React operator interface to connect directly to Target B's FastAPI REST endpoints, retiring the Express server and duplicate Sqlite store.
