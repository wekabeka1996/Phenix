# Duplication and Bypass Audit

## FACTS

| Occurrence | Classification | Result |
|---|---|---|
| V2 HTTP/TCP/bridge | `CANONICAL_ACTIVE_PATH` | retained |
| V1 `/intents/llm/v1` | `BYPASS_TO_ISOLATE` | route absent when policy false |
| EZE routes/kinds | `BYPASS_TO_ISOLATE` | routes absent; TCP rejected |
| V1 mapper | `LEGACY_INACTIVE` | code retained, no canonical route/kind ingress |
| terminal `dual_agent_runner.fsm_ref` | `LEGACY_INACTIVE` | not constructed by Aurora main; emits strategy event, not raw exchange |
| P42 lifecycle harness adapter | `TEST_ONLY` | not production composition |
| account/market Binance adapters | `CANONICAL_ACTIVE_PATH` for their domains | not execution authority duplicates |

- Production registry has one listener for `CMD:EXTERNAL_OPEN_REQUEST_V1`.

## INFERENCES

- No second active caller-sized HTTP/TCP execution path remains under current YAML policy.

## ASSUMPTIONS

- Operators do not override `legacy_execution_routes_enabled` without an explicit migration decision.

## UNKNOWNS

- Historical manual runners can still be launched separately; they are outside main composition.
