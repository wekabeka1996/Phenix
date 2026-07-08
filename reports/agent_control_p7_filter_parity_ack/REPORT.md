# P7 filter parity acknowledgement and drift history

## Problem framing

P6 exposed exchange-filter differences but did not give them durable governance state. P7 makes each observation classifiable, historically traceable, packet-visible, and explicitly operator-owned without changing YAML or execution behavior.

## FACTS

- The production owner appends bounded metadata-only rows to `ops/agent_bridge/parity_history/filter_parity_history_v1.jsonl`.
- Acknowledgement is accepted only from an explicit operator file whose symbol, venue, environment, exact state hash, and acknowledgement/status semantics match.
- No operator acknowledgement file existed during validation.
- BTCUSDT was `conservative_mismatch`, `warning`, `compatible_conservative`, `unacknowledged` during all ten polls.
- ETHUSDT was `match`, `info`, `exact_match`, `not_required` during all ten polls.
- A cache TTL boundary produced a transient `stale` transition and the subsequent public refresh produced `resolved` for ETHUSDT and `improved` for BTCUSDT, proving drift history behavior.
- Ten Cockpit GET polls returned HTTP 200 and SQLite rows increased from 50 to 60.
- Packets were 14,977-14,982 bytes and 3,745-3,746 estimated tokens, below 4,400 without truncation.
- Aurora ran in `agent_bridge_observation_only`; Cockpit remained `armed=false`, `status=stopped`.

## INFERENCES

- BTCUSDT's coarser step and higher minima are conservative relative to current testnet metadata because the step is an exact exchange-grid multiple and configured minima are higher.
- The exact-state hash prevents an acknowledgement for old metadata from silently carrying into new drift.

## ASSUMPTIONS

- The typed instrument map remains the configured SSOT for the four compared fields.
- Public Binance USD-M testnet exchange-info remains informational and does not prove order acceptance.

## UNKNOWNS

- No operator has decided whether to acknowledge BTCUSDT or revise YAML.
- Live-environment parity and exchange execution acceptance were not tested.

## Root cause vs symptom

The symptom was a P6 warning visible only in packet/report evidence. The root cause was missing durable ownership: no lifecycle, exact-state identity, acknowledgement binding, or transition history. P7 adds those governance primitives; it does not calibrate configuration.

## Implementation summary

Added typed full and compact acknowledgement contracts, conservative/risky/missing/stale classification, SHA-256 metadata/state refs, explicit-file acknowledgement loading, append-safe/idempotent JSONL history, P7 readiness publication, requested-symbol packet projection, and a read-only Cockpit display. No write API or acknowledgement button was added.

## Parity acknowledgement design

`match` maps to `not_required`; conservative mismatch remains `unacknowledged` absent an exact operator record; risky mismatch requires YAML review and an execution block before any future authority; stale/missing is never accepted. Operator records cannot mutate configuration and bind to the exact `state_ref`.

## BTCUSDT case review

Configured values are tick `0.1`, step `0.001`, min qty `0.001`, min notional `100`. Testnet values are tick `0.10`, step `0.0001`, min qty `0.0001`, min notional `50`. Result: conservative mismatch, acknowledgement required, no automatic relaxation, no authority claim.

## ETHUSDT case review

Configured and testnet values match: tick `0.01`, step `0.001`, min qty `0.001`, min notional `20`. Result: match and acknowledgement `not_required`.

## History behavior

Runtime history grew from 0 rows before the P7 process to 70 rows across seven configured symbols and periodic observations. Rows contain hashes/refs, classification, transition and acknowledgement only—no secret or full exchange payload. Duplicate calls with the same timestamp/state are idempotent; later observations append `unchanged`, `worsened`, `improved`, or `resolved` lifecycle rows.

## Packet integration

The full record stays in the atomic readiness publication. The packet includes only symbol, parity status, severity, acknowledgement status, review flag, compatibility summary, and refs. Projection is limited to requested symbols.

## Cockpit display result

The existing Execution Body card now shows parity, acknowledgement, and review status. Its parser validates all enums and refs. `AGENT_FEED_ACTIONS_ENABLED` remains false; there is no mutation route.

## Runtime observation results

Startup commands used `.venv/Scripts/python.exe -m apps.reference.main`, `.venv/Scripts/python.exe -m uvicorn apps.reference.api.main:app --host 127.0.0.1 --port 18080`, and `npx tsx server.ts` with `PORT=18081` and the Cockpit core URL set to 18080. Ten GET-only polls succeeded. Runtime logs contained zero order/create/place/cancel/modify/amend or signed/authenticated request matches.

## Latency and token budget

Cockpit round trips were 2,064-2,146 ms, mean 2,077.4 ms. Token use was 3,745-3,746/4,400, leaving at least 654 tokens of headroom.

## Files changed

See `FILES_CHANGED.md`. Unrelated pre-existing Neocortex and runtime-forensics worktree changes were not modified.

## Tests and validation

Changed Python modules compile. The focused Aurora suite passed 41/41. Cockpit lint and build passed; AgentFeed tests passed 3/3. The broader Cockpit suite remained 38/39 because of the pre-existing EZE direct-ingress assertion documented in P6. Static scans found no secret/signing surface, mutation route, or execution call in the P7 bridge.

## What is proven

Parity acknowledgement state is explicit, exact-state-bound, persisted, historically traceable, packet-visible, Cockpit-visible, bounded, and operational under the no-order profile.

## What remains unproven

No execution, agent authority, exchange acceptance, live parity, or operator acknowledgement decision is proven.

## Risks

- The ledger has a 4 MiB read bound but no compaction policy yet.
- File-based acknowledgement requires an operator workflow and audit identity policy before production use.
- A stale cache intentionally blocks acknowledgement acceptance until fresh metadata returns.

## P8 recommendation

Define authenticated operator identity, review expiry, and signed/offline acknowledgement-file provenance. Keep this separate from execution authority and YAML calibration.

## Final verdict

P7_PARITY_ACK_HISTORY_VALIDATED
