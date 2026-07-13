# Root Cause

## FACTS

Primary classification: `CONFIG_SSOT_INCOHERENCE`.

- `compute_notional_target` had a Python default `fee_buffer=0.001`.
- `PositionQueries` did not read a fee buffer from YAML/Pydantic.
- The S1 harness solved margin percentage as `target / (equity × leverage)`, while active sizing subsequently multiplied equity by `0.999`.
- The guard compared `qty × price` in quote USDT against the explicit 10 USDT clip floor; units were correct.
- Fee was subtracted once, exposure/reservations were zero, and quantity was correctly rounded down to the exchange step.
- DOGEUSDT met exchange min-notional `5` but failed Phenix policy floor `10`; S1 symbol selection checked only exchange minimums.

Contributing factors: intended policy floor, proof symbol-selection incoherence, hidden fee default, and absent snapshot-age policy.

## Falsification Results

- `10` pre-buffer: below clip after buffer/rounding.
- A representable explicit target below cap exists: `11`.
- Sizing and guard use the same reference price in the command.
- No quantity/notional unit mismatch was found.
- No double fee or double exposure reservation was reproduced.
- Clip minimum is global explicit risk policy, not a Testnet override.

## INFERENCES

- Lowering the production clip floor would have hidden the actual contract mismatch.

## ASSUMPTIONS

- Existing 10 USDT floor is approved policy because it is explicit in canonical trading YAML.

## UNKNOWNS

- No semantic claim is made about whether 11 USDT is economically useful; it is only a bounded proof value.
