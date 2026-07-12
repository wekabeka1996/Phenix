# Residuals

## FACTS

- Missing Testnet credentials block authenticated preflight and every later phase.
- No selected symbol, proof session, sizing result, FSM instance, order, or reconciliation evidence exists.
- The preflight tool intentionally does not create an adapter or make public/authenticated network calls when credentials are absent.

## INFERENCES

- Operator action required: inject scoped Binance Futures Testnet credentials securely, then rerun preflight.

## ASSUMPTIONS

- Credentials have appropriate Testnet Futures read/write permissions when supplied.

## UNKNOWNS

- Account mode, filters, cleanliness, and cap feasibility.
