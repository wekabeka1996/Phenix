# Existing Surface Inventory

## FACTS
| Surface | Owner | Access | Reuse decision |
|---|---|---|---|
| shadow telemetry FastAPI host | Phenix | mixed existing host | reused for additive namespace |
| `/agent-feed/v0`, `/agent-memory/v0` | agent bridge projections | GET | retained; insufficient aggregate lifecycle contract |
| V1/V2 intent routes | execution ingress | POST | excluded |
| `TradingSessionAuthorityStore` | session/participant/lease | read/write internal | reused through new read-only methods |
| existing Cockpit `PhenixApiClient` | Cockpit | mixed read/write | not reused for this trust boundary |

## INFERENCES
- A versioned aggregate namespace was necessary; no parallel HTTP host was created.

## ASSUMPTIONS
- Existing host authentication and deployment policy remain authoritative.

## UNKNOWNS
- Some lifecycle source implementations require later canonical runtime composition.
