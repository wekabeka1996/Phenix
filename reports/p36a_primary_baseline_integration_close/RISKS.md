# Risks and Residuals

We audited the proposal ledger, cadence FSM, and timer runner integrations.

## Audited Risks
1.  **Stale proposal executions**:
    - Risk: If the FSM execution loops lag, proposals could be evaluated using outdated ticker packet bounds.
    - Mitigation: The compiler strictly validates proposal timestamps and rejects any entries older than 300 seconds.
2.  **Concurrency racing in timer registration**:
    - Risk: Multiple agent threads scheduling timers at once might experience lock collision on the timer manifest.
    - Mitigation: The timer manifest uses atomic file updates and standard directory-level isolation.
