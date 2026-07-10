# RISKS — Safety & Security Evaluation

This document outlines key operational and security risks associated with the real external testnet execution bridge.

---

## 1. Operational Risks & Mitigation

### Risk 1: Credentials Leakage / Key Exposure
- **Details**: Plaintext API keys stored in configuration files or logs could expose testnet environments to abuse.
- **Mitigation**: Environmental variable substitution (`${BINANCE_TESTNET_API_KEY}`) is enforced at the `config_loader` level. Git ignore rules prevent `.env` files from being committed.

### Risk 2: Mainnet Exposure / URL Leakage
- **Details**: Malicious or accidental configuration drift might redirect API traffic to mainnet exchange endpoints.
- **Mitigation**: The codebase enforces multiple redundant locks. The `verify_handoff_safety` boundary raises a hard block if a production URL is detected. The `BinanceAdapter` checks `config.trading_mode` and throws a validation error if anything other than `testnet` is configured for test API credentials.

### Risk 3: Rate Limiting & Network Latency
- **Details**: Parallel command bursts from multiple external agents could exceed the Binance Testnet rate limits (IP limits or request weight limits), causing HTTP `429` blocks or long timeouts.
- **Mitigation**: Standard retry backing is integrated into `BinanceAdapter` with Jittered Exponential Backoff.

---

## 2. Fallback Logic

If testnet credentials (API key/secret) are missing or set to placeholder strings:
1. The execution engine refuses to instantiate the exchange-facing client.
2. The `AdapterInitMixin` falls back to `self.shadow_mode = True`, making `self.adapter = None`.
3. Incoming orders in the harness are blocked and return `BLOCKED_CONFIG` rather than failing silently or trying to execute stub code.
This ensures the system fails closed when key parameters are absent.
