# Config Requirements for P40 Testnet Order Proof

To ensure safety during the single order proof, the following strict configuration limits must be configured:

## 1. Safety Envelope Limits
- **Max Notional Per Order**: `25.0 USD`
- **Max Total Notional**: `25.0 USD`
- **Max Session Orders**: `1`
- **Allowed Symbols**: `ETHUSDT` / `SOLUSDT` only.
- **Allowed Time Horizon**: `swing` (min 15m/30m decision window, no scalping).

## 2. Launch Environment Profile
- **Environment Variable**: `AURORA_RUNTIME_PROFILE="deepseek_agent_only_testnet"`
- **Launch Profile Name**: `deepseek_agent_only_testnet`
- **FSM Mode**: `no_order_observation_mode = False` (active for the duration of this single order test only).
- **Exchange Adapter Base URL**: `https://testnet.binancefuture.com` (must be confirmed; live API domains are strictly blocked).
