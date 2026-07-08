# Cockpit display report

The AgentFeed panel includes a read-only Action Review Memory card showing unresolved count, symbol/action, explicit execution status, expected/realized scenarios, lesson, and review ref.

The TypeScript parser validates schema, review ids/revision, scenario arrays, no-execution status text, refs, and optional outcome fields. No create/update button or write route exists. `AGENT_FEED_ACTIONS_ENABLED=false` remains unchanged.

Lint PASS; build PASS (2,186 modules); focused bridge tests PASS (3/3); forbidden 7102/8443 rejection remains tested.
