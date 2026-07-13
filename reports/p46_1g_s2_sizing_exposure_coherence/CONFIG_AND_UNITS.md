# Config and Units

## FACTS

- Every canonical instrument now declares `sizing.fee_buffer_fraction: "0.001"`.
- `InstrumentSizingConfig` requires `0 <= fee_buffer_fraction < 1`; unknown fields remain forbidden.
- Active `compute_notional_target` requires an explicit fee buffer argument.
- Authority policy explicitly declares account and market snapshot maximum age as `15` seconds.
- Proof-only YAML declares target `11.0` USDT and cap `20.0` USDT.
- Units: `margin_pct` and `fee_buffer_fraction` are fractions; price is quote/base; quantity is base units; notional and clip/cap values are quote USDT.

## INFERENCES

- Missing fee, snapshot timestamp, age policy, or instrument filter now fails closed.

## ASSUMPTIONS

- The 15-second authority TTL aligns with the existing position staleness gate and bounded Testnet proof cadence.

## UNKNOWNS

- Production telemetry producers may need follow-up wiring if they do not populate the timestamp keys consumed by the authority provider.
