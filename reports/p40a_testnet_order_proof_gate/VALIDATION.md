# Validation

We performed static checks on the configuration and launch profile maps.

## 1. Profiles & Enums
- Checked: [runtime_profile.py](file:///C:/Users/wekab/Music/Phenix-p40-testnet-order-proof-integrated/apps/reference/runtime_profile.py)
- Matches: `deepseek_agent_only_testnet` launch profile disables `no_order_observation`.

## 2. Invariant Gates
- Checked: [agent_action_audit.py](file:///C:/Users/wekab/Music/Phenix-p40-testnet-order-proof-integrated/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py)
- Matches: Environment must be `"testnet"` or `"sandbox"`, quantity/notional must be present, and base URL must not contain production subdomains.

## 3. Unit Tests
- All 500+ unit and integration tests pass cleanly.
