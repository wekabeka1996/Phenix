# POSITION_POLICY_SIDECAR_V1_DECISION_LEDGER

| Decision | Alternatives considered | Why chosen | Operational tradeoff | Blocked future extension if any |
| --- | --- | --- | --- | --- |
| Place the sidecar in `execution_position` | `decision_making`, strategy-local overlay, separate domain/service | closest to open-position truth, bracket state, and close suppression | tighter coupling to EP internals | none; this is the least-damaging starting point |
| Keep the sidecar as a separate file/module | extend `ManageFlowFSM`, extend `ExitManager` | preserves modularity without reassigning state ownership | one more internal module to wire and observe | none |
| Phase 1 is recommendation-only | EP-internal request, direct `CMD:CLOSE`, hybrid action | safest diagnosable first rollout under current weak identity/attribution contracts | no immediate business action | direct action waits for later phase |
| Phase-1 scope is soft early-loss governance only | profitable-position management, target extension, partial reduce | lowest overlap with brackets, trailing, and TP ownership | defers some upside optimization | profitable lifecycle optimization waits |
| Exclude partial-reduce requests from Phase 1 | use existing `qty` close semantics | partial reduce is real technically, but policy ownership is too ambiguous today | less flexibility | future partial-reduce contract remains open |
| Exclude bracket mutation from Phase 1 | stop tightening, TP replace, TP extension | current bracket/trailing owners are active incumbents | limited lifecycle control | bracket mutation requires future contract work |
| Keep Phase-1 action-bearing logic bar-aligned | tick-driven action evaluation | aligns with local structural regime and reduces churn | slower reaction to very fast adverse changes | tick-driven path could be revisited later |
| Use local-symbol context only for Phase-1 action logic | include BTC/anchor/macro features | avoids hidden double-count with existing macro surfaces | may miss broader context | macro-aware phase waits for dedicated contract review |
| Treat `regime_exhaustion_hint` as policy interpretation only | make it a new regime truth field | detector does not currently own explicit lifecycle semantics | less expressive than a true lifecycle model | true lifecycle modeling requires separate regime contract work |
| Require incumbent precedence before sidecar evaluation | allow sidecar to evaluate first | avoids races against bracket, max-hold, and close-in-progress logic | sidecar can miss some same-event opportunities | none |
| Define sidecar local cache as derived-only | let it own lifecycle state snapshot | preserves SSOT boundaries | repeated reads from incumbent state may be needed | none |
| Use structured sidecar telemetry in Phase 1 | rely on logs only | recommendations must be explainable before any action rollout | more telemetry surface to maintain | none |
| Defer EP-internal request path to Phase 2 | ship direct action in Phase 1 | current contracts and attribution are not strong enough | slower business impact | none |
| Defer exact lifecycle targeting entirely | invent close-by-id now | current runtime does not support it | precise targeting unavailable | close-by-id requires new identity contract |
