# DAILY_GATE_POLICY_REPLAY_RUNBOOK

## Purpose

Run a 24h gate/policy replay after each trading day to measure whether active
gates protected capital or blocked profitable opportunities.

This is the daily answer to:

- which proposals were accepted;
- which proposals were blocked;
- which gate/policy blocked each proposal;
- whether the blocked proposal would have hit TP, SL, or timeout;
- which gate has positive protective value;
- which gate is overblocking market opportunity.

## Command

```powershell
python tools/analysis/current_event_gate_replay.py --window-hours 24 --daily
```

The command writes to:

```text
calibrators/datasets/daily_gate_policy_replay/YYYY-MM-DD/
```

## Outputs

- `CURRENT_EVENT_GATE_REPLAY_REPORT.md`: human-readable daily summary.
- `current_event_gate_replay_summary.json`: machine-readable gate metrics.
- `current_event_gate_replay_rows.csv`: row-level decision, gate, market, and replay data.

## Daily Review

Review these sections first:

- rejected intents by NRR code;
- directional follow-through by 1/3/6/12 bars;
- bracket replay by gate where geometry exists;
- top profitable blocked trades;
- top losing blocked trades;
- `block_suppressed_by_config` count.

## Decision Rules

If a gate has positive protective value:

- keep it active;
- preserve examples as correctly blocked losers.

If a gate has persistent positive missed PnL:

- do not delete the gate immediately;
- create a bounded shadow or canary policy;
- require symbol/regime/side segmentation;
- add fill freshness and partial-fill protection requirements.

If a gate is disabled from the decision chain:

- keep telemetry enabled;
- require daily `would_block` and `block_suppressed_by_config` tracking;
- compare accepted real outcomes against suppressed-gate counterfactuals.

## NRR-062 Experiment

NRR-062 can be removed from the active decision chain with:

```yaml
decision_making:
  low_vol_cost_floor_gate:
    decision_chain_enabled: false
```

This does not remove telemetry. The gate still records `threshold_failed`,
`would_block`, violations, and `block_suppressed_by_config`.

Do not treat one day as proof. Promotion or rollback should use at least 3-7
daily reports unless the loss profile is immediately unacceptable.
