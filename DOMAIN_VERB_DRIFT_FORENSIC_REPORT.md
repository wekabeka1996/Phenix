# DOMAIN_VERB_DRIFT_FORENSIC_REPORT

## 1. Executive Summary

This forensic audit investigates the drift of 35 Event-Driven Architecture (EDA) verbs (14 `runtime_not_in_registry` and 21 `registry_not_in_runtime`) reported in `VF-VERB-REG-02_diff.json`.

**Key Structural Findings:**
1. **The Static Analysis Illusion (False Positives for Missing Runtime Verbs):** The `execution_position` domain has a strong structural habit of dynamically emitting verbs via parameter passing (e.g., `verb="BATCH"`, `verb="EXECUTION_FAILED"`) rather than writing the full literal string `"DEC:BATCH"`. As a result, static text/AST searches that look for the fully qualified string (e.g., `ERR:EXECUTION_FAILED`) fail to find them, incorrectly classifying active verbs as "missing from runtime." 
2. **Comment Scanning (False Positives for Extra Runtime Verbs):** The script that generated `VF-VERB-REG-02` incorrectly flagged `EVT:PROCESS_STRATEGY` as an unmapped runtime verb simply because it appeared in a Python code comment inside `md_amr_handler.py`.
3. **Framework Bleed:** 11 of the 14 verbs flagged as "Runtime Not In Registry" do not originate in `apps/reference/domains/` at all. They belong to the underlying `vfoundation` system (e.g., FSM lifecycle events, Topology Auditor signals). The audit script scanned them as part of the overarching execution "runtime", but from a strict domain-boundary perspective, they are framework-level signals.
4. **True Dead Code:** 10 out of the 21 verbs in the registry are unequivocally dead code (never mapped, emitted, or dynamically resolved anywhere in `.py` files).

---

## 2. Domain-by-Domain Breakdown

### Execution Position Domain (`apps/reference/domains/execution_position`)

**False Positives from Registry (Actively emitted dynamically, evading static analysis):**
- `DEC:BATCH`
  - *Proof:* `apps/reference/domains/execution_position/fsm_manage.py:1075` (`verb="BATCH"`)
- `ERR:EXECUTION_FAILED`
  - *Proof:* `apps/reference/domains/execution_position/fsm.py:1896` (`verb="EXECUTION_FAILED"`)
- `ERR:FATAL_CONFIG_MISMATCH`
  - *Proof:* `apps/reference/domains/execution_position/fsm.py:1770` (`verb="FATAL_CONFIG_MISMATCH"`)
- `EVT:EXPOSURE_MISMATCH`
  - *Proof:* `apps/reference/domains/execution_position/exposure_manager.py:236` (`verb="EXPOSURE_MISMATCH"`)
- `EVT:FALLBACK_MODE_ENTERED`
  - *Proof:* `apps/reference/domains/execution_position/exposure_guard.py:256` (`verb="FALLBACK_MODE_ENTERED"`)
- `EVT:FALLBACK_MODE_EXITED`
  - *Proof:* `apps/reference/domains/execution_position/exposure_guard.py:324` (`verb="FALLBACK_MODE_EXITED"`)
- `EVT:LIMIT_ORDER_TIMEOUT`
  - *Proof:* `apps/reference/domains/execution_position/limit_order_monitor.py:268` (`verb="LIMIT_ORDER_TIMEOUT"`)
- `EVT:MANAGE_SKIPPED`
  - *Proof:* `apps/reference/domains/execution_position/fsm_manage.py:665` (`verb="MANAGE_SKIPPED"`)
- `EVT:ORDER_TIMEOUT`
  - *Proof:* `apps/reference/domains/execution_position/entry_manager.py:310` (`verb="ORDER_TIMEOUT"`)
- `EVT:PENDING_BRACKETS_CLEARED`
  - *Proof:* `apps/reference/domains/execution_position/pending_brackets_wal.py:93` (`VERB_CLEARED = "PENDING_BRACKETS_CLEARED"`)
- `EVT:PENDING_BRACKETS_STORED`
  - *Proof:* `apps/reference/domains/execution_position/pending_brackets_wal.py:44` (`VERB_STORED = "PENDING_BRACKETS_STORED"`)
- `EVT:PENDING_EXPOSURE_EXPIRED`
  - *Proof:* `apps/reference/domains/execution_position/event_handlers.py:352` (`verb="PENDING_EXPOSURE_EXPIRED"`)

**Unmapped Runtime Verbs (Code lacks YAML Registry):**
- `EVT:DOMAIN_STATUS`
  - *Proof:* `apps/reference/domains/execution_position/health_metrics.py:127` (`self._domain_bridge.emit_status()`). Note: this is also co-emitted by the Decision Making domain (`decision_making/decision_making.py:502`).

**DEAD CODE / STALE REGISTRY:**
- `DEC:CANCEL` (Not found via text search/AST)
- `EVT:ORDER_EXECUTED` (Not found via text search/AST)

---

### Decision Making Domain (`apps/reference/domains/decision_making`)

**Unmapped Runtime Verbs (Code lacks YAML Registry):**
- `EVT:QUADRATIC_DECISION_TRACE`
  - *Proof:* `apps/reference/domains/decision_making/aurora_decision.py:529` (`self.emit_fn("EVT:QUADRATIC_DECISION_TRACE", ...)`)
- `EVT:PROCESS_STRATEGY`
  - *Proof:* `apps/reference/domains/decision_making/md_amr_handler.py:1117`
  - *Symptom:* Only exists as a comment (`# In a real system, we'd emit EVT:PROCESS_STRATEGY or signal re-eval here`). The analysis script erroneously captured this as a live runtime token.

**DEAD CODE / STALE REGISTRY:**
- `EVT:HANDLER_READINESS_DIAGNOSTICS` (Found in `domain_dict.json` but not actively emitted in Python code)
- `EVT:INTENT_DROPPED` (Not found via text search/AST)
- `EVT:MR_SIGNAL_PRODUCED` (Not found via text search/AST)

---

### Market Data Domain (`apps/reference/domains/market_data`)

**DEAD CODE / STALE REGISTRY:**
- `EVT:MARKET_TICK_FORWARDED` (Found in `domain_dict.json:13` explicitly marked with `"reason": "No active emitter; removed from production paths"`)
- `EVT:TICK_RECEIVED` (Not found via text search/AST)

---

### Neocortex Domain (`apps/reference/domains/neocortex`)

**DEAD CODE / STALE REGISTRY:**
- `EVT:NEOCORTEX_STATE_UPDATED` (Only present in READMEs, `.md` files, and `domain.yaml`; not physically emitted by Python runtime)

---

### Core Framework (Outside Domain Boundary)

These 11 unmapped runtime verbs and 1 dead registry verb were aggregated by the `VF-VERB-REG-02` audit, but they do NOT live in `apps/reference/domains/`. They are foundational elements generated by the overarching `vfoundation/` infrastructure logic. 

**Unmapped Framework Runtime Verbs (Code lacks YAML Registry):**
- `CMD:CANCEL` - `vfoundation/core/fsm_v2.py:18`
- `CMD:FORCE_RECOVER` - `vfoundation/core/meta_fsm_v2.py:103`
- `CMD:SWITCH_TO_LOW_RISK_MODE` - `vfoundation/core/meta_fsm_v2.py:58`
- `ERR:NO_TRANSITION` - `vfoundation/core/fsm_v2.py:189`
- `ERR:REJECT` - `vfoundation/core/payloads.py:66`
- `EVT:COOLDOWN_ELAPSED` - `vfoundation/core/meta_fsm_v2.py:95`
- `EVT:ENTROPY_SPIKE` - `vfoundation/core/meta_fsm_v2.py:84`
- `EVT:RECOVERY_SIGNAL` - `vfoundation/core/meta_fsm_v2.py:99`
- `EVT:STABILIZED` - `vfoundation/core/meta_fsm_v2.py:92`
- `EVT:STATE_TRANSITION` - `vfoundation/core/fsm_v2.py:288`
- `EVT:TOPOLOGY_DRIFT_DETECTED` - `vfoundation/obs/topology_auditor.py:129`

**DEAD CODE / STALE REGISTRY:**
- `EVT:ORCHESTRATOR_ERROR` (Not found anywhere)

---

## 3. Agent Conclusion

This audit unequivocally pinpoints *why* the verb registry drift appeared so severe:

1. **Static Analysis Brittle Constraints:** 11 of the "missing" registry verbs (primarily in `execution_position`) are actually **alive and well**. The disconnect is strictly structural. `vfoundation` protocols enable passing `{op="EVT", verb="MANAGE_SKIPPED"}`, while the baseline audit script was seemingly looking for full literal concatenations (`"EVT:MANAGE_SKIPPED"`).
2. **Comment Parsing Fallacy:** The script is vulnerable to commented-out pseudocode, evident by `EVT:PROCESS_STRATEGY` being mistakenly recorded as a runtime token. 
3. **Framework Transgression:** The registry validation was executed over global system boundaries, while the definitions were evaluated across strictly domain boundaries. 11 unmapped "runtime" verbs discovered belong solely to `vfoundation/` state machines rather than the domain apps. 
4. **Historical Residue (10 True Deletions):** `EVT:NEOCORTEX_STATE_UPDATED`, `EVT:MARKET_TICK_FORWARDED`, `DEC:CANCEL`, and 7 other verbs represent genuine un-garbage-collected entries left in the `verb_registry_v1.yaml` during refactors or deprecated features.