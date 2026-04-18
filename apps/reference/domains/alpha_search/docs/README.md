# Alpha Search Domain Docs

alpha_search is not accurately described anymore as only a standalone alpha-score emitter.

In the current tree it is a bounded strategy-analysis domain with two supported runtime shapes:

- a historical standalone shadow or replay path that consumes mirrored feature snapshots
- a direct integration in apps/reference/main.py via AlphaSearchBacktestPlugin and config/alpha_search.yaml

Today alpha_search owns alpha-provider scoring, judge shadow artifact emission, the Phase 5 offline simulator subtree, and the optional shutdown-time simulator export seam. It does not own decision policy, execution_position, or Phase 6 promotion semantics.

## Reading Order

- [ATLAS.md](./ATLAS.md) — canonical What alpha_search is now entrypoint
- [ARCHITECTURE.md](./ARCHITECTURE.md) — runtime topology, config surfaces, and boundaries
- [EVENT_CONTRACTS.md](./EVENT_CONTRACTS.md) — runtime event surface versus offline or file-based contracts
- [ALGORITHMS_AND_MATH.md](./ALGORITHMS_AND_MATH.md) — scoring math and model-specific formulas
- [QUALITY_AND_DEBT.md](./QUALITY_AND_DEBT.md) — debt, gaps, and follow-up notes
- [TESTING.md](./TESTING.md) — test layout and verification guidance

## Operator Notes

- Use ../../../../../ALPHA_SEARCH_QUICKSTART.md only for the standalone runner path.
- Use apps/reference/main.py plus config/alpha_search.yaml when reasoning about the current embedded runtime.
- Use config/judge_simulator.yaml only for the offline simulator. The simulator is not registered through Aurora domains config.
