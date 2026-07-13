# P46-1G-S2 Sizing and Exposure Coherence

## FACTS

- Starting branch tip and remote: `5bd3c81b2020d917f0e4627261aae3ac35bf65ff`, divergence `0/0`.
- Required ancestors `605d66c8` and `a68d8749` were present.
- The pre-existing untracked forensic script remained unchanged at SHA256 `6b5a05ec066cfd1cef3f68ba731ae8c131250fff4b82b65267f05541d5499771`.
- Primary root cause: `CONFIG_SSOT_INCOHERENCE`. The active sizing helper applied a hidden `0.001` fee buffer after the proof harness projected a pre-buffer `10.0` target.
- The prior chain was reproduced deterministically: `10.0 → 9.99 → raw qty 138.365650... → qty 138 → 9.9636 USDT → SOFT_LIMIT_BELOW_CLIP_MIN`.
- Production clip minimum remains `10` USDT. It was not disabled or lowered.
- `fee_buffer_fraction` is now required by instrument YAML/Pydantic and by active margin-first sizing. Account and market snapshot age limits are explicit and fail closed.
- The proof-only target is explicitly `11.0` USDT under the unchanged `20.0` cap.
- One canonical Binance Futures Testnet DOGEUSDT order was submitted: exchange order `1560242837`, opening status `NEW`, derived quantity `152`, derived notional `10.978960` USDT.
- Duplicate submit count was `0`. Canonical `DEC:CANCEL_ORDER` canceled the unfilled order. Independent venue reconciliation returned `CANCELED`, position `0`, open orders `0`.
- No caller quantity, direct success bypass, emergency containment, provider call, Cockpit work, or mainnet access occurred.

## INFERENCES

- Sizing and guard units are coherent for the canonical proof path, and the unchanged risk floor correctly approves the representable 11 USDT proof size.

## ASSUMPTIONS

- Binance Futures Testnet responses were authoritative at their recorded timestamps.

## UNKNOWNS

- The success does not prove fills, close-after-fill behavior, mainnet readiness, or long-running concurrency.
- The runtime bus observer copied the external command before ExposureManager mutation, so the exposure ID in final evidence is deterministically reconstructed as `exposure:<client_intent_id>`; this capture-timing gap remains documented.

## Documentation Implications

- Instrument sizing documentation must describe required `fee_buffer_fraction` and distinguish pre-buffer policy targets from post-buffer executable notional.
- V2 authority documentation must require timestamped account/market snapshots and configured age limits.

## Verdict

`P46_1G_CANONICAL_TESTNET_LIFECYCLE_VALIDATED`
