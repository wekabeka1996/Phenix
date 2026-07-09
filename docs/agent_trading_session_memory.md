# Agent Trading Session Memory Specification

This document defines the durable schema and operational rules for agent trading-session memories.

## Conceptual Overview

In the Agent Arena context, external agents act as the primary decision makers. To ensure continuity, safety, and accountability across sequential runs, agents must maintain a structured session memory.

Each trading session has a target budget (metadata only) of **1M tokens**, with **300k tokens** explicitly reserved for self-reflection, feature trust adjustments, and decision-impact analysis.

## Memory Models

The schema consists of three core Pydantic models:

1. **`AgentTradingSessionMemory`**: The root container for a single session. Holds tracking metadata, append-only reference lists (`active_context_refs`, `event_refs`, `trade_refs`, `reflection_refs`), and the ordered list of `reflections`.
2. **`ReflectionEntry`**: Represents a single point-in-time assessment or audit log.
3. **`FeatureTrustNote`**: Documents shifting confidence in specific data points or alpha signals.

## Operational Rules

- **Append-only writes**: New reflections can be added, but existing reflections cannot be modified or silently overwritten. Attempts to append an existing `reflection_id` will raise a `ValueError`.
- **Identity Integrity**: Reflections appended to a session memory must match the memory's `session_id` and `agent_id` exactly.
- **Deduplication**: Appending event, trade, or context references is idempotent.
- **Carryover Markdown**: The memory can generate a standardized carryover markdown block containing the state, budget, cumulative trust shifts, and last reflections for injection into the next session.
