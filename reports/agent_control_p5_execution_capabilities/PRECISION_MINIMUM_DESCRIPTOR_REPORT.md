# Precision and minimum descriptor report

BTCUSDT and ETHUSDT each report `precision_minimum_normalization=ready/runtime_owner`.

Proven local capabilities:

- resolve the requested symbol from loaded typed config;
- floor quantity to step size;
- quantize protection price to tick size;
- reject rounded-zero and below-minimum quantity;
- check minimum notional;
- fail closed for an unknown symbol.

This readiness describes deterministic execution-owner normalization. It does not upgrade config-only values to exchange-confirmed filters.
