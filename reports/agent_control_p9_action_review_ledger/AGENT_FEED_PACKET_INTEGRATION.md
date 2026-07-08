# AgentFeedPacket integration

Top-level `action_review_memory` contains only:

- latest review id by requested symbol;
- compact latest revision, proposed action, and non-submission status;
- expected and realized scenario ids;
- bounded lesson;
- unresolved flag/count;
- packet, review, and ledger refs.

Full review text stays in JSONL. Budget enforcement trims memory to one latest row before other card reductions if needed. Runtime packets included one completed BTCUSDT memory and no full review payload.
