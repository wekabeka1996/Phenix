# Files changed

- `scenario_corpus.py`: packet-only heuristics and deterministic review-pair generation.
- `scenario_memory.py`: budget-safe one-row packet projection after corpus growth.
- `build_p11_memory_corpus.py`: idempotent append, rebuild and evidence generation.
- `test_scenario_corpus.py`: heuristic, linkage, corpus, idempotency, index and budget tests.
- `.gitignore`: P11 evidence allowlist.
- Production ActionReview ledger/index and required P11 reports/samples.

No YAML, strategy, Cockpit, model-provider or execution code changed.
