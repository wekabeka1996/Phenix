# Risks (P42J Real Testnet Proof Attempt 02)

## 1. Isolated Wallet Debt Blocking
- **Risk**: Losses from filled trades are deducted from the isolated wallet, leaving it with a negative balance. Any subsequent margin or order requests are blocked by the exchange.
- **Mitigation**: Cleared debt via manual margin addition before executing the proof order.

## 2. Minimum Notional Requirement
- **Risk**: Testnet orders below 5.0 USDT are rejected by the exchange.
- **Mitigation**: Configured order size of 10.0 XRP at 0.60 price (notional value of 6.0 USDT) to pass exchange validation.
