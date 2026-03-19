# Copilot repository instructions

Follow the project protocol in:
- docs/ai/LLM_REASONING_CONSTITUTION.md
- docs/ai/AURORA_DOMAIN_PROTOCOL.md
- docs/ai/AGENT_REPORT_SCHEMA.md
- docs/ai/DONE_CRITERIA.md
- docs/ai/VERB_EVENT_INSTRUCTIONS.md
Required behavior:
- Separate facts from inferences.
- Do not assume missing runtime behavior.
- Fail closed on missing evidence.
- Check contracts, invariants, and event order.
- Prefer minimal localized fixes.
- Do not mark work complete without validation and REPORT.

Project laws:
- YAML + Pydantic are SSOT.
- No silent fallbacks.
- No hidden business constants.
- Contract-first, additive-only.
- Register new events/commands in YAML registries.
Apply these rules when editing passports, documentation, or protocol files.

- Runtime truth outweighs documentation claims.
- If code and docs conflict, document the conflict explicitly before updating.
- Mark what is proven vs inferred vs unproven.
- Keep scope bounded to the requested document or doc set.
- Do not claim a passport is current unless inspected against the actual code/config paths in scope.
Apply these rules when editing execution / order lifecycle / FSM code.

- Preserve fail-closed trading safety.
- Any state transition change must define invariant impact.
- No implicit routing changes.
- Any order lifecycle fix must define runtime trace points.
- Validation must include integration/runtime-facing checks, not only unit tests.
