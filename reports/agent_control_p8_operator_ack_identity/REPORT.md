# P8 operator acknowledgement identity and parity review provenance

## Problem framing

P7 made parity drift acknowledgements exact-state-bound, but its offline record did not establish durable operator identity, mandatory review expiry, canonical file provenance, or explicit invalidation reasons. P8 adds those governance properties without creating authority or configuration mutation.

## FACTS

- The operator-authored schema requires ack id, explicit operator id, created/expiry/review timestamps, reason, exact symbol/venue/environment/state, parity semantics, and offline provenance.
- Conservative acknowledgement lifetime is capped at 30 days.
- A normalized manifest SHA-256, opaque file ref, load time, and matching state ref are computed at load.
- Validation states are `valid`, `expired`, `state_mismatch`, `rejected`, `missing`, `invalid_file`, `invalid_semantics`, and `not_required`.
- No real operator acknowledgement file existed during runtime validation.
- BTCUSDT remained `unacknowledged/missing` with no operator identity in all ten packets.
- ETHUSDT remained `not_required/not_required` in all ten packets.
- Cockpit persisted ten packets, increasing SQLite rows 61 → 71.
- Packets were 15,418-15,421 bytes and 3,855-3,856 estimated tokens, below the 4,400 cap without truncation.
- Aurora used `agent_bridge_observation_only`; Cockpit remained `armed=false`, `status=stopped`.

## INFERENCES

- Canonical hashing makes whitespace/key-order changes provenance-equivalent while any semantic file change changes the hash.
- Exact-state and semantic validation prevent an old or mis-scoped acknowledgement from silently surviving metadata drift.

## ASSUMPTIONS

- Operator ids are organizational identifiers supplied in the offline file; no OS username is inferred.
- Local file custody is an operator process concern until detached signature verification is separately designed.

## UNKNOWNS

- No real operator has accepted or rejected BTCUSDT drift.
- Operator identity issuance, revocation, and detached-signature trust roots are not yet defined.
- Live-environment parity and exchange order acceptance were not tested.

## Root cause vs symptom

The symptom was an exact-state file that could express acknowledgement. The root cause was insufficient review provenance: no required identity, bounded lifetime, canonical file hash, or auditable invalid reason. P8 closes that governance gap while leaving all execution gates untouched.

## Implementation summary

P8 separates strict operator-authored input from the validated runtime record; enforces lifecycle and parity/ack semantics; computes dependency-free SHA-256 provenance; rejects malformed, wrong-scope, stale, expired, and drifted records; adds identity/provenance fields to history and readiness; projects compact state into AgentFeedPacket; and renders it read-only in Cockpit.

## Operator ack model design

`OperatorParityAcknowledgementInputV0` is the offline entry. `OperatorParityAcknowledgementV0` is the validated record and adds `file_hash`, validation status/reason, and computed provenance. `acknowledged_ok_to_trade` is not in the schema. `not_required` is valid only for a match; `acknowledged_conservative` requires a compatible conservative mismatch.

## Provenance and expiry behavior

The loader parses a bounded 64 KiB manifest, validates unique ack ids, hashes normalized validated JSON, and records `aurora-operator://...#sha256:<hash>`, load timestamp, and expected state ref. Expiry occurs when either expiry or mandatory review-by time passes. Conservative lifetime above 30 days is schema-invalid.

## BTCUSDT case review

Current BTCUSDT state remains `conservative_mismatch/compatible_conservative`. The real loader found no file, so effective status is `unacknowledged`, validation is `missing`, operator id is absent, and reason is `operator_acknowledgement_file_missing`. A synthetic exact-state file validated successfully only in an isolated test/sample.

## ETHUSDT case review

ETHUSDT remains an exact match. Runtime derives `not_required/not_required` and ignores acknowledgement input; no operator identity is needed.

## Validation matrix

Synthetic tests prove valid conservative acknowledgement, wrong state, wrong symbol, wrong environment, expired review, stale/missing rejection, risky-review-with-authority-block, duplicate ids, forbidden trade-authority status, and match behavior. See `ACK_VALIDATION_MATRIX.md` and the JSON sample.

## Packet integration

Each requested symbol projects ack status, optional operator id, created/expiry times, exact state ref, validation state, review flag, compact reason, and provenance ref. Full files and validated records remain outside the packet.

## Cockpit display result

The Execution Body card now shows acknowledgement state, validation result, operator id (or `none`), expiry (or `n/a`), and review requirement. No buttons or mutation routes were added; agent actions remain disabled.

## Runtime observation results

Aurora main, read host 18080, and Cockpit 18081 completed ten GET-only polls. Public testnet exchange-info refreshed, the P8 history/loader published, and all packets contained P8 compact state. Runtime logs contained zero order/create/place/cancel/modify/amend or signed/authenticated request matches. Cockpit never targeted 7102 or 8443.

## Latency and token budget

Round trips were 2,050-2,134 ms, mean 2,080.3 ms. Estimated tokens were 3,855-3,856, leaving at least 544 tokens of headroom.

## Files changed

See `FILES_CHANGED.md`. Unrelated pre-existing Neocortex and runtime-forensics worktree changes remain untouched.

## Tests and validation

Changed Python modules compile; 49 focused Aurora tests pass. Cockpit lint/build and three focused bridge tests pass. Static scans show only the intentional detached-signature placeholder word, no signing implementation, secret read, mutation route, or execution surface.

## What is proven

Operator identity, exact-state binding, mandatory expiry, normalized file provenance, drift invalidation, packet visibility, read-only display, and no-order runtime safety are validated.

## What remains unproven

No real BTCUSDT acknowledgement, operator identity authenticity, detached signature verification, execution authority, agent authority, YAML calibration, live parity, or exchange acceptance is proven.

## Risks

- Offline identity remains asserted metadata until a trust-root/signature policy exists.
- A compromised local file custodian could replace both content and hash; P8 detects changes but does not authenticate the author cryptographically.
- History remains bounded by file-size read policy rather than archival rotation.

## P9 recommendation

Define a lightweight detached-signature verification policy and an offline lint/generate command that never touches YAML or execution. Bind trusted reviewer ids to public verification keys outside the packet and preserve the existing exact-state/expiry rules.

## Final verdict

P8_OPERATOR_ACK_IDENTITY_VALIDATED
