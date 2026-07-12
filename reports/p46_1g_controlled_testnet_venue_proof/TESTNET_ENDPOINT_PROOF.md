# Testnet Endpoint Proof

## FACTS

- YAML/Pydantic endpoint: `https://testnet.binancefuture.com`.
- Mainnet endpoint values fail proof-config validation.
- Required Testnet key and secret environment variables were both absent.
- No real `.env` exists in the worktree or parent; only `.env.example` exists.
- Fingerprint: absent. Secret values were never printed.

## INFERENCES

- Static endpoint identity is proven; authenticated Testnet account identity is not.

## ASSUMPTIONS

- Credentials must be injected by the operator's secure runtime mechanism.

## UNKNOWNS

- Credential account ownership and permissions cannot be evaluated.
