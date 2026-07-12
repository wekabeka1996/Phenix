# P46-1F Single FSM Runtime Acceptance Proof

## FACTS

- Starting SHA: `7b6e0c2acd2cb5724ebac30413bae6fe54bf5a7e`; local/remote matched, required ancestors present, clean, ahead/behind `0/0`.
- Production-component harness proved HTTP V2 -> TCP JSONL -> main bridge -> registered `CMD:EXTERNAL_OPEN_REQUEST_V1` -> one `ExecPosFSM` -> `DEC:OPEN` with `OPEN_OK`.
- Phenix derived `qty=0.2`; the HTTP intent contained no quantity.
- Counts: one HTTP-produced TCP envelope, one V2 bridge handler, one registered command emission, one command listener, one `ExecPosFSM.handle`, zero recording-adapter calls.
- `legacy_execution_routes_enabled: false` removes V1/EZE HTTP routes and rejects legacy TCP kinds before FSM.
- No provider, Cockpit, Binance, Testnet, or real exchange network operation ran.

## INFERENCES

- One deterministic V2 execution path now reaches the canonical FSM without a parallel caller-sized HTTP ingress.

## ASSUMPTIONS

- Shadow-mode acceptance is sufficient for this no-network FSM boundary proof.

## UNKNOWNS

- Exchange submission, ACK, fill, reconciliation, and position lifecycle remain unproven.
- Idempotency ownership is process-local; restart durability is not claimed.

## Verdict

`P46_1F_SINGLE_FSM_RUNTIME_PATH_VALIDATED`
