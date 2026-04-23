# Decision Making Contradiction Matrix

## Scope

This matrix records proven or strongly evidenced contradictions inside the decision_making contract surface.

The focus is on runtime-vs-registry, local-metadata-vs-central-contract, and owner-vs-owner mismatches. Complexity by itself is not listed unless there is an actual contradiction or split truth surface.

## Evidence Discipline

- FACT: directly inspected in code, registry, metadata, schema, or startup wiring.
- INFERENCE: operational conclusion derived from the facts.
- ASSUMPTION: explicitly marked if used.
- UNKNOWN: unresolved by inspected artifacts.

## FACTS

| Surface | FACT A | FACT B | Proven contradiction | Likely risk |
| --- | --- | --- | --- | --- |
| ALPHA_SCORE_CALCULATED ownership | [apps/reference/dictionaries/verb_registry_v1.yaml](apps/reference/dictionaries/verb_registry_v1.yaml) declares owner: alpha_search | [apps/reference/domains/decision_making/event_handlers.py](apps/reference/domains/decision_making/event_handlers.py) emits EVT:ALPHA_SCORE_CALCULATED; [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py) registers local alpha models; [apps/reference/domains/alpha_search/backtest_plugin.py](apps/reference/domains/alpha_search/backtest_plugin.py) also emits the same verb | Central registry says single owner alpha_search, while runtime proves decision_making is also an emitter | Consumers cannot infer producer semantics from the verb alone; monitoring and ownership reasoning are muddied |
| ALPHA_SCORE_CALCULATED contract story | [apps/reference/dictionaries/verb_registry_v1.yaml](apps/reference/dictionaries/verb_registry_v1.yaml) points to the alpha_search schema | [apps/reference/domains/alpha_search/schemas/alpha_score_calculated_v1.json](apps/reference/domains/alpha_search/schemas/alpha_score_calculated_v1.json) explicitly says the event is emitted by Alpha Search or DecisionMaking and supports two payload variants | Schema text encodes a dual-producer reality while the registry still claims a single owner | Contract consumers must special-case payload variants; “owner” is not operationally single-valued |
| QUADRATIC_DECISION_TRACE contract registration | [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py) emits EVT:QUADRATIC_DECISION_TRACE | [apps/reference/dictionaries/verb_registry_v1.yaml](apps/reference/dictionaries/verb_registry_v1.yaml) has no QUADRATIC_DECISION_TRACE entry; local [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json) exports it anyway | Local metadata and runtime say the verb exists; the central registry does not | Unregistered event contract; contract validation and cross-domain discovery can miss it |
| HANDLER_READINESS_DIAGNOSTICS runtime proof | [apps/reference/dictionaries/verb_registry_v1.yaml](apps/reference/dictionaries/verb_registry_v1.yaml) declares HANDLER_READINESS_DIAGNOSTICS as active, owner decision_making; local [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json) exports it | Workspace search found no runtime code emission or usage of HANDLER_READINESS_DIAGNOSTICS | Central registry and local metadata declare an active verb with no inspected runtime emitter | False observability expectations; dead diagnostics contract risk |
| TRADE_INTENT_REJECTED truth path | [apps/reference/domains/decision_making/intent_emitter.py](apps/reference/domains/decision_making/intent_emitter.py) centralizes canonical reject event + WAL emission | [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py) and [apps/reference/domains/decision_making/mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py) write reject WAL rows directly for strategy-level gates; [apps/reference/domains/decision_making/md_amr_handler.py](apps/reference/domains/decision_making/md_amr_handler.py) emits EVT:TRADE_INTENT_REJECTED directly without using write_trade_intent_rejected locally | Rejected-intent truth is not owned by one shaping path in practice | Payload normalization, WAL persistence, and downstream reject semantics can diverge by strategy path |
| Gate ownership layering | [apps/reference/domains/decision_making/strategy_gateway.py](apps/reference/domains/decision_making/strategy_gateway.py) runs the canonical general gate chain, including safety_gate, then passes safety_gate_result into dm._propose_trade_intent | [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py) still has a safety-gate fallback inside _propose_trade_intent when no precomputed result is passed; [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py) performs objective and execution gating before STRATEGY_SIGNAL_PRODUCED | There is no single obvious human-readable answer to “which layer authoritatively blocked this trade?” across all paths | Divergent why-chains, inconsistent denial context, and difficult runtime forensics |

## INFERENCES

- The strongest proven contract contradictions are not “old code left behind.” They are active split-owner or split-contract surfaces.
- ALPHA_SCORE_CALCULATED is the clearest owner contradiction because both decision_making and alpha_search prove emission, while the central registry still claims alpha_search ownership.
- QUADRATIC_DECISION_TRACE and HANDLER_READINESS_DIAGNOSTICS form the opposite pair:
  - QUADRATIC_DECISION_TRACE is runtime/local-metadata present but central-registry absent.
  - HANDLER_READINESS_DIAGNOSTICS is central-registry/local-metadata present but runtime absent.
- TRADE_INTENT_REJECTED handling is the clearest split-truth path inside decision_making itself.

## ASSUMPTIONS

- None required for the contradiction statements above.

## UNKNOWNS

- No runtime log capture was performed, so the operational frequency of the contradictory paths is unknown.
- No proof was gathered that external consumers depend on QUADRATIC_DECISION_TRACE or HANDLER_READINESS_DIAGNOSTICS today; only their declaration/runtime mismatch is proven.
- Gate-layer overlap is proven structurally, but no live scenario was executed here to show the exact user-visible divergence on one concrete trade attempt.
