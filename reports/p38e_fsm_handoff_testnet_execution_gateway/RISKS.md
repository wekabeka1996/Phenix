# Operational Risks and Mitigations

## 1. Mainnet Leakage (High Severity)
- **Risk**: A misconfigured adapter base URL could route external LLM commands to a production account.
- **Mitigation**: The `FSMHandoffGateway` explicitly validates that the adapter URL contains `"testnet"`. Production base URLs like `fapi.binance.com` are blocked at the validation stage, shifting rejections left before calling `create_order`.

## 2. Quantity/Notional Formatting Errors
- **Risk**: External agents might pass invalid string formatting or scientific notation for sizes, which could cause calculations in execution code to fail silently or result in invalid fills.
- **Mitigation**: Quantity/notional values are validated to be float-castable and strictly positive (`> 0`) in the validation gate.

## 3. Secondary Coordinator Thread Safety
- **Risk**: Asynchronous order execution task runs in the background (`asyncio.create_task`) and might experience race conditions on fast concurrent requests.
- **Mitigation**: Every command has a unique `command_id` and tracks status state transitions linearly. The FSM journal logs each transition to maintain a sequential audit trail.
