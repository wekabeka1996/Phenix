# Risks (P42J Real Testnet Proof Attempt 02)

## 1. Missing Testnet Credentials
- **Risk**: The runner cannot construct the real `BinanceAdapter` without local Binance Futures Testnet API credentials.
- **Mitigation**: Fail-closed by blocking execution with `BLOCKED_TESTNET_CREDENTIALS` when credentials are absent, preventing any silent fallback or raw adapter failure.
