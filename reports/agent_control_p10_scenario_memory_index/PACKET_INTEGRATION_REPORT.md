# Packet integration report

AgentFeedPacket contains only:

- scenario-memory index ref;
- unresolved count by requested symbol;
- latest compact review id/revision/ref;
- one short latest lesson and realized label.

It does not contain full reviews, index, confusion matrix or query results. Observed packet use: 4,168/4,400 tokens, 232-token headroom, no truncation. Existing P9 Cockpit parser fields were retained for compatibility.
