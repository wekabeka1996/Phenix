# Risks

- The local lock protocol is not a distributed lock and is unproven on network filesystems.
- Checkpoint storage is deliberately larger than active context because it retains all source references and critical evidence.
- Idempotency history grows with the session; checkpointing bounds prompt context, not durable state size.
- Dispatch-in-doubt recovery requires an operator-supplied reconciliation hook; absent hook blocks readiness.
- API routes rely on the Cockpit's existing local trust boundary; P41X adds no authentication layer.
- `ASK_SUBAGENT` records a request for the registered runtime but does not launch a hidden worker.
- The benchmark uses estimated token counts because no supported tokenizer was installed.
- No external testnet lifecycle proof exists in P41X.
