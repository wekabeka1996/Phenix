# Proof Config

## FACTS

- File: `config/aurora/p46_1g_testnet_proof.yaml`.
- Environment is exactly `binance_futures_testnet`; endpoint must be canonical HTTPS Testnet root.
- Target notional `10.0`; operator maximum `20.0` quote units.
- Required bounded submit/query/cancel/flatten/total timeouts are explicit.
- Cleanup booleans are literal true; unknown or missing fields fail validation.
- This config is proof-only and supplies no production sizing default.

## INFERENCES

- Money-impacting proof policy is explicit even though venue execution is blocked.

## ASSUMPTIONS

- Future execution must still use PositionQueries and instrument SSOT.

## UNKNOWNS

- Whether any candidate symbol fits the cap cannot be proven without venue queries.
