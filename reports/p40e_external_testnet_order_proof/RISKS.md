# Risks (P40E Testnet Order Proof Runner)

## 1. Safety Gate Fail-Closed
- **Risk**: Proceeding with external testnet submissions without the integration branch's gate rules.
- **Mitigation**: Fail-closed by blocking execution immediately if the gate file is missing or inaccessible.

## 2. Leakage of API Keys or Real Funds
- **Risk**: Submitting real orders to Binance mainnet.
- **Mitigation**: The `FSMHandoffGateway` validation checks reject any adapter whose capability descriptor indicates a non-testnet environment, preventing accidental leakage.
