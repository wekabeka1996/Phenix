# Acknowledgement validation matrix

| Case | Effective status | Validation | Safety result |
|---|---|---|---|
| Valid exact conservative | acknowledged_conservative | valid | identity/expiry projected; no authority |
| Wrong state ref / metadata drift | expired | state_mismatch | requires new review |
| Wrong symbol | rejected | rejected | no application |
| Wrong environment | rejected | rejected | no application |
| Expiry or review-by passed | expired | expired | no acceptance |
| Malformed/oversized file | unacknowledged | invalid_file | fail closed |
| Future created timestamp | unacknowledged | invalid_semantics | fail closed |
| Stale/missing metadata | rejected | rejected | authority block retained |
| Risky mismatch reviewed | acknowledged_requires_review | valid | YAML review and authority block retained |
| Match | not_required | not_required | operator input unnecessary |
| No runtime file | unacknowledged | missing | no identity inferred |

Duplicate ack ids and the nonexistent `acknowledged_ok_to_trade` status fail schema validation.
