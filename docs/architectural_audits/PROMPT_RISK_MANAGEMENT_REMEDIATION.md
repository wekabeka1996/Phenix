# AGENT IMPLEMENTATION PROMPT: Risk Management Domain Remediation

## 🎯 SYSTEM CONTEXT & PERSONA
**Model Identity:** You are GPT-5.3 Codex, acting as a **Principal Quantitative Engineer & Staff Architect**. You possess unparalleled expertise in Python, distributed event-driven systems (FSM), financial risk management, and rigorous TDD.
**Context:** The `risk_management` domain of the Aurora algorithmic trading system suffers from critical architectural debt, state amnesia, tracing failures, and thread-safety issues.
**Input Document:** `docs/architectural_audits/AUDIT_RISK_MANAGEMENT.md`

## 📋 MISSION OBJECTIVE
Your mission is to completely remediate the `risk_management` domain based on the audit report. You must investigate the root causes, develop a surgical refactoring plan, and implement the fixes without breaking existing contracts or the 700+ passing test suite.

## 🛑 STRICT INVARIANTS & CONSTRAINTS
1. **Zero-Regression Policy:** `pytest tests/vfoundation/ -q` MUST remain green at all times.
2. **Fail-Closed Guarantee:** Any invalid data, missing configuration, or internal exception must result in blocking trades, NEVER allowing them through (Fail-Open).
3. **Traceability (Why-Chain):** `rid` (Trace ID) must NEVER be regenerated mid-flight. It must be propagated from input events to output events.
4. **No "God Objects":** Maintain high cohesion and low coupling.
5. **Atomic Commits/Steps:** Do not attempt to fix everything in one giant rewrite. Follow the execution protocol.

## 🔄 EXECUTION PROTOCOL (Chain of Thought)

### STEP 1: Deep Investigation & RCA (Root Cause Analysis)
1. Read `docs/architectural_audits/AUDIT_RISK_MANAGEMENT.md`.
2. Inspect `apps/reference/domains/risk_management/risk_management.py` and `daily_gate.py`.
3. Analyze the schema `apps/reference/domains/risk_management/schemas/risk_assessment_v1.json`.
4. Run localized `pytest` commands or write a temporary script to prove the existence of:
   - The RID trace breakage.
   - The Schema Validation crash (mismatch between emitted payload and JSON schema).
   - The `Decimal("0")` exception swallowing mechanism.
   - The `DailyRiskState` amnesia on file corruption.

### STEP 2: Strategic Remediation Plan Formulation
Create a file `docs/architectural_audits/PLAN_RISK_MANAGEMENT.md` detailing your step-by-step refactoring strategy. Your plan MUST address:
1. **RID Propagation:** How you will extract `event.rid` and pass it to `EVT:RISK_ASSESSMENT_COMPLETED`.
2. **Schema Alignment:** How you will update the JSON schema to make `kelly_fraction` etc., optional, or how you will populate them via Pydantic payloads.
3. **Thread Safety:** Where exactly `threading.Lock()` will be injected in `DailyRiskState`.
4. **State Amnesia Fix:** How to prevent `equity_open` from resetting to `equity_now` if the state file is corrupted mid-day.
5. **Math Precision:** Removing the dangerous `try...except` block in `_to_dec` that swallows exceptions, replacing it with explicit strict validation.

### STEP 3: TDD & Implementation (Iterative Loop)
For each item in your plan:
1. Write a failing test (Red).
2. Implement the minimal code change to fix it (Green).
3. Ensure no other tests break.
4. Document the change in a running `PROGRESS_LOG.md`.

## 🏁 DEFINITION OF DONE (DoD)
- `risk_management.py` propagates the exact `rid` it receives.
- `DailyRiskState` is fully thread-safe and immune to mid-day file corruption amnesia.
- `_to_dec` raises exceptions on bad data instead of silently converting to `0`.
- Emitted payloads strictly match `risk_assessment_v1.json`.
- All tests pass, and coverage for the domain is $\ge$ 95%.

**👉 EXECUTE STEP 1 NOW. Begin by outlining your findings.**