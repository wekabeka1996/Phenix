# Risks and Recommendations

We evaluated the combined P37 event arena surface for risks.

## Audited Risks
1.  **Strict schema constraints bypass**:
    - Risk: If custom commands are pushed directly to `/chat/sessions/{session_id}/agent-events` without validation, malformed payloads could cause downstream parsing crashes.
    - Mitigation: The endpoints strictly validate fields against schemas defined in the dictionary v1 YAML first.
2.  **Autonomous strategy leakage**:
    - Risk: If internal strategies are not disabled, they might deploy signals concurrently with agent proposals.
    - Mitigation: Ensure `strategies.*.enabled == False` is statically verified on testnet.
