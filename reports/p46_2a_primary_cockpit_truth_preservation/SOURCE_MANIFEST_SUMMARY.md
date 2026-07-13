# Source Manifest Summary

## FACTS

| Metric | Baseline | Snapshot |
|---|---:|---:|
| Included source/config/test/doc files | 422 | 432 |
| Excluded entries | 32 | 10,558 |
| Snapshot-only | - | 10 |
| Substantive same-path modifications | - | 4 |
| Line-ending-only differences | - | 418 |
| Baseline-only | 0 | - |

Substantive modified files: `server.ts`, `src/App.tsx`, `src/client/api/agentOsClient.ts`, and `src/shared/contracts/index.ts`.

Snapshot-only files:

- `scripts/p2-agent-feed-observation-host.ts`
- `scripts/p2-observe-agent-feed.ts`
- `src/components/agentFeed/AgentFeedPanel.tsx`
- `src/components/agentFeed/DryRunPanel.tsx`
- `src/server/agentFeed/AgentFeedStore.ts`
- `src/server/agentFeed/AuroraAgentFeedClient.ts`
- `src/shared/contracts/agentFeed.ts`
- `src/shared/contracts/agentIntentDryRun.ts`
- `tests/trading-agent/AgentFeedBridge.test.ts`
- `tests/trading-agent/AgentIntentDryRun.test.ts`

The JSON manifests retain byte SHA256. The normalized comparison maps CRLF/CR to LF only for semantic-difference classification.

## INFERENCES

The 14 files are a complete source-bearing preservation closure.

## ASSUMPTIONS

Text line-ending normalization is appropriate for these Git-managed source/doc formats.

## UNKNOWNS

None in the enumerated trees.
