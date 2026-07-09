# P40 Runtime Evidence Matrix

## FACTS

| Question | Answer | Evidence |
|---|---|---|
| Is external testnet order proof allowed? | Yes, gate-level allowed. | P40A verdict `P40A_GATE_TESTNET_ORDER_PROOF_ALLOWED`. |
| Was one real testnet order submitted? | No. | P40E `ORDER_SUBMIT_BLOCKED`. |
| Was exchange ACK/reject captured? | No. | P40E `EXCHANGE_RESPONSE_BLOCKED`; no order sent. |
| Were fills proven? | No. | P40F says `NO_FILL_PROOF`; P40E says execution loops unproven. |
| Were memory/instruction/FSM traces complete? | P39 traces complete; P40 order-proof traces incomplete. | P40E blocked before valid session writes; P40C harness writes traces in tests only. |
| Was any result simulated? | No final result was claimed from simulation. | P40C tests are sandbox/shadow; P40E blocked instead of simulating. |
| Did system preserve no-scalping and 15m/30m rules? | No violation proven; no order was submitted. | Blocked runner produced no entry/exit intent. |

## INFERENCES

- P40 has readiness pieces but lacks the external runtime event needed for order proof.
- The correct final verdict is blocked, not ready.

## ASSUMPTIONS

- A real testnet proof requires at minimum an exchange ACK or reject from the existing adapter path.

## UNKNOWNS

- Whether the first future submit will be ACKed or rejected by exchange.
- Whether fills would occur after ACK.
