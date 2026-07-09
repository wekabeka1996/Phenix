# P40 Tech Debt Delta

## FACTS

- RETIRED: None at final coordination level; coordinator made no code changes.
- MITIGATED: P40B added adapter capability checks that fail closed for mainnet/unknown/missing descriptors and no-order mode.
- MITIGATED: P40C added lifecycle proof harness tests and trace surfaces.
- CONVERTED_TO_RUNTIME_CHECK: P40E converted missing run-ready gate into `ORDER_SUBMIT_BLOCKED` and `EXCHANGE_RESPONSE_BLOCKED`.
- DEFERRED_WITH_REASON: Real exchange ACK/reject remains deferred because no external submit was attempted.

## INFERENCES

- The most important blocking debt is integration sequencing: the runner must see the gate branch/spec before submit.

## ASSUMPTIONS

- No further debt should be burned until a single tiny testnet submit path is rerun against the now-visible gate.

## UNKNOWNS

- Whether descriptor production and credential validity will become the next blocker after gate visibility is fixed.
