# BTCUSDT parity case review

- Configured: tick `0.1`, step `0.001`, min qty `0.001`, min notional `100`.
- Testnet: tick `0.10`, step `0.0001`, min qty `0.0001`, min notional `50`.
- Differences: configured step is 10× coarser and grid-compatible; configured min qty is 10× higher; configured minimum notional is 2× higher.
- Classification: `conservative_mismatch`, severity `warning`, compatibility `compatible_conservative`.
- Acknowledgement: `unacknowledged`; no matching operator file exists.
- YAML review: not mechanically required by classification, but operator acknowledgement/review remains required.
- Future authority block: false for the conservative values themselves; all wider authority gates remain unchanged.

Nothing was relaxed or written to YAML.
