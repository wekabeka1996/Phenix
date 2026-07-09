# Trading Session Memory Contract

## Schema Models and Fields

### 1. `AgentTradingSessionMemory`
Holds the state of the active agent trading session.

- **`schema_version`** (int): Default `1`. Schema versioning.
- **`session_id`** (str): Globally unique session identifier.
- **`agent_id`** (str): Target agent identifier.
- **`agent_number`** (int): Canonical non-negative identifier.
- **`started_at`** (datetime): UTC session start timestamp.
- **`instruction_manifest_version`** (str): The manifest version controlling the agent.
- **`context_budget_target_tokens`** (int): Default `1000000`. Full context budget.
- **`reflection_budget_target_tokens`** (int): Default `300000`. Reflection budget.
- **`tokens_consumed_estimate`** (int): Cumulative estimate of token usage.
- **`active_context_refs`** (list[str]): References to context inputs.
- **`event_refs`** (list[str]): References to FSM events processed.
- **`trade_refs`** (list[str]): References to testnet order identifiers.
- **`reflection_refs`** (list[str]): Index list of reflection IDs.
- **`reflections`** (list[ReflectionEntry]): List of sequential reflection records.

### 2. `ReflectionEntry`
A single reflection record.

- **`reflection_id`** (str): Unique reflection ID.
- **`session_id`** (str): Target session ID matching the parent.
- **`agent_id`** (str): Target agent ID matching the parent.
- **`created_at`** (datetime): UTC creation timestamp.
- **`kind`** (str): Kind of reflection. One of:
  - `opening_assumptions`
  - `feature_trust_update`
  - `decision_review`
  - `session_self_audit`
  - `behavior_drift`
- **`related_event_ids`** (list[str]): Optional list of event IDs linked to this reflection.
- **`related_command_ids`** (list[str]): Optional list of command IDs linked to this reflection.
- **`feature_influence_notes`** (list[FeatureTrustNote]): Discovered feature trust shifts.
- **`confidence_before`** (float, optional): Estimated confidence before.
- **`confidence_after`** (float, optional): Estimated confidence after.
- **`content`** (str): Substantive markdown content describing reasoning.

### 3. `FeatureTrustNote`
Documents an update in trust level for a specific data feature or alpha signal.

- **`feature_name`** (str): Feature name.
- **`trust_delta`** (float): Shift in trust. Range: `[-1.0, 1.0]`.
- **`reason`** (str): Detailed reason.
- **`supporting_event_ids`** (list[str]): Event references.
- **`observed_effect`** (str): Actual market reaction.

## Operational Guarantees

1. **Append-Only reflections**: The `append_reflection()` method validates that the appended reflection ID is unique. If a duplicate exists, a `ValueError` is raised, preventing silent overwrite.
2. **Attribution Integrity**: Any reflection appended to `AgentTradingSessionMemory` is checked against the parent's `session_id` and `agent_id`.
3. **Idempotence**: `active_context_refs`, `event_refs`, and `trade_refs` use checks to avoid duplicates on append calls.
4. **Token Budget Tracking**: The token budgets are metadata targets. Estimates are incremented on reflection append and never decremented, providing a clear indication of context occupancy.
