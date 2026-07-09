# Merge Sequence

We merged the following branches sequentially using `--no-ff` commits:

1.  **Merge 1: Event FSM Surface Discovery**
    - Branch: `p37a-event-fsm-surface-discovery-primary-20260709`
    - Result: Merged cleanly. Added P37a discovery reports.
2.  **Merge 2: Agent Arena Event Contract**
    - Branch: `p37b-agent-arena-event-contract-primary-20260709`
    - Result: Merged cleanly. Added schemas and Pydantic validator models for arena events.
3.  **Merge 3: Cockpit Agent Event Buttons**
    - Branch: `p37c-cockpit-agent-event-buttons-primary-20260709`
    - Result: Merged cleanly. Adds Cockpit event post endpoints and static registries.
4.  **Merge 4: Secondary Combined Reports & Event Audit**
    - Branch: `origin/p37-secondary-combined-report-20260709`
    - Result: Merged cleanly. Adds `agent_action_audit.py` and secondary logs.
5.  **Merge 5: Brain Strategy Disable Map**
    - Branch: `origin/p37d-secondary-brain-strategy-disable-node-watch-20260709`
    - Result: Already up to date (commits present in Merge 4).
