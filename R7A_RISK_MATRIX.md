# R7A RISK MATRIX

**Package**: R7A — Sidecar Peak-Giveback
**Date**: 2026-04-21
**Status**: Independent Audit Complete

---

| # | Risk Area | Severity | Status | Evidence | Operational Impact | Smallest Safe Corrective Action |
|---|-----------|----------|--------|----------|-------------------|-------------------------------|
| 1 | **Schema `const` vs emitted `policy_source`** | MODERATE | **PROVEN** | Schema declares `const: "position_policy_sidecar"` but peak giveback emits `"position_policy_sidecar:peak_giveback"`. Lines: schema L45, sidecar L666. | No runtime failure today (no runtime schema validation). Would fail if schema validation is ever enforced. Contract truth is violated. | Change schema `const` to `pattern: "^position_policy_sidecar"` — 1 line edit |
| 2 | **Mediator validation widened to `startswith()`** | LOW | **PROVEN** | Mediator L57 uses `.startswith("position_policy_sidecar")` instead of exact match. Accepts any string with that prefix. | Theoretical risk only — command topic is internal-only (self → self). No external surface can inject fake requests. | Accept as-is. Add comment explaining the prefix-match rationale. |
| 3 | **Double-fire on same lifecycle** | NONE | **DISPROVEN** | State reset after trigger (L680-681: `is_armed=False, peak_edge_usd=0.0`). Entry reset (L353-354). Tests prove single-fire. | None | None needed |
| 4 | **Fire during close-in-progress** | NONE | **DISPROVEN** | `close_in_progress` suppression (L701-706) checked BEFORE peak giveback evaluation (L466). | None | None needed |
| 5 | **Fire on stale/missing data** | NONE | **DISPROVEN** | All freshness, warmup, and portfolio checks in suppression chain block before peak giveback evaluation. | None | None needed |
| 6 | **Hidden runtime business fallback** | NONE | **DISPROVEN** | Config model: `extra='forbid'`, all fields `Field(...)`. No `default=` or `default_factory` on any business field. | None | None needed |
| 7 | **Split-brain close ownership** | NONE | **DISPROVEN** | Close request goes through standard Mediator → CMD:CLOSE → CloseFlowFSM → DEC:CLOSE. No new close execution path. ManageFlowFSM remains sole position lifecycle owner. | None | None needed |
| 8 | **Concurrent max_hold_close + peak_giveback** | LOW | **SUSPECTED** | Not tested. Both paths could attempt CMD:CLOSE simultaneously. Idempotent_key mechanism should prevent duplicate execution, but no test proves it. | Theoretical at testnet scale — unlikely to have both triggers fire within same event loop tick. | Add integration test — not an R7A blocker |
| 9 | **Rapid oscillation re-triggering** | LOW | **SUSPECTED** | After trigger + reset, price could re-climb above arm threshold and re-trigger. This is by-design (new peak cycle), but no test verifies controlled behavior. | Position would experience multiple close attempts across different peak cycles. Each individually bounded. | Monitor telemetry at testnet — not a code fix |
| 10 | **Report contamination from previous agent** | LOW | **PROVEN** | Previous acceptance report mixed XRP TOCTOU finding into R7A package. | Perceived severity inflation. Does not affect code correctness. | Cleanly scope R7A reporting. Ignore unrelated findings. |
| 11 | **Config missing from YAML** | NONE | **DISPROVEN** | `peak_giveback_close` block present in domains.yaml L638-641. All 3 required fields present. | Startup fail-closed if removed. | None needed |
| 12 | **Downstream `policy_source` exact-match consumers** | LOW | **UNKNOWN** | Forensics tools check `record_kind == "position_policy_sidecar"` not `policy_source`. But not exhaustively verified for all consumers. | If any tool filters on exact `policy_source == "position_policy_sidecar"`, peak giveback events would be silently excluded from analysis. | Audit downstream consumers after schema fix |

---

## Summary

| Category | Count |
|----------|-------|
| **PROVEN blockers** | 1 (schema `const` mismatch) |
| **PROVEN non-blockers** | 2 (mediator widening, report contamination) |
| **DISPROVEN risks** | 6 |
| **SUSPECTED, non-blocking** | 2 (concurrent close, oscillation) |
| **UNKNOWN** | 1 (downstream consumers) |

**The only actionable blocker is Risk #1: a single schema `const` → `pattern` change.**
