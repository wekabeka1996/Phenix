"""Strategy plugins (allowlist registry).

Phase 1 (TASK32):
- Strategies are wired via an explicit allowlist registry (no dynamic imports).
- Strategies emit `EVT:STRATEGY_SIGNAL_PRODUCED` and DecisionMaking applies gates.
"""

