# Query API report

GET-only endpoints:

- `/agent-memory/v0/health`
- `/agent-memory/v0/index`
- `/agent-memory/v0/query`
- `/agent-memory/v0/summary`

Query types: latest, completed, unresolved, scenario accuracy, confusion, lessons and packet linkage. Symbol, horizon, scenario, packet id, limit and token budget are validated. Actual completed BTC query returned one compact item at 251 tokens; BTC/ETH summary used 153 tokens.
