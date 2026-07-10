# CANONICAL_BASELINE

This document records the baseline verification for the unified dual-agent trading runtime release.

---

## 1. Selected Baseline Commit
The release branch has been checked out and built upon the canonical baseline commit:

- **Baseline SHA**: `9af369b7657e631b22519785ae09e54b8e9c28b8`
- **Author**: deepseek-terminal-agent
- **Commit Message**: "Create P40R integration ready reports"

---

## 2. Baseline Drift Rejection
- We explicitly rejected using the older `985b4800` commit (the P39 runtime baseline) as our release baseline, which was used as the starting point for P42B.
- The `9af369b7` baseline contains critical upstream fixes to align the `AgentOrderLifecycleHarness` test suite with the `AdapterCapabilityDescriptor` configuration parameters.
- Rebuilding on the `9af369b7` baseline ensures full schema compatibility and zero regression issues with older FSM parameters.
