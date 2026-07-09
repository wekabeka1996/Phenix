# P40B Validation

## FACTS
- Command run:
```powershell
python -m pytest tools\deepseek-terminal-agent\tests\test_agent_action_audit.py -q
```
- Result:
```text
13 passed in 0.16s
```
- Validation covered:
  - Missing descriptor rejects.
  - Mainnet descriptor rejects.
  - Unknown descriptor rejects.
  - Testnet descriptor allows gateway pre-submit validation when explicit quantity is present.
  - `no_order_observation_mode=True` blocks submit before exchange path.
  - `order_submit_enabled=False` blocks submit before exchange path.
  - Testnet-looking URL string alone is insufficient.
  - Audit rejection record preserves identity fields and rationale.

## INFERENCES
- The capability guard is unit-test validated at the agent audit/FSM handoff safety boundary.

## ASSUMPTIONS
- Full runtime order proof belongs to P40 execution-proof work, not P40B.

## UNKNOWNS
- No external testnet order submit, ACK, reject, or fill was produced.
- No browser/Cockpit smoke was run for this adapter capability contract.
