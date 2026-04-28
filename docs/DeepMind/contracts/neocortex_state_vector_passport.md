# Neocortex State Vector Passport

```yaml
passport_id: "neocortex.state_vector_passport.v1"
scope: "Hot-path state aggregation and baseline inference"
source_surfaces:
  - "apps/reference/domains/neocortex/logic/ingest/state_aggregator_v2.py"
  - "apps/reference/domains/neocortex/main.py"
  - "apps/reference/domains/neocortex/logic/brain/baseline_inference.py"
vector_composition:
  ordered_parts:
    - name: "feature_vector"
      source: "config.ingest.feature_list order"
      required: true
      causal_time_required: true
      trainable_required: true
      missingness_semantics: "missing feature rows are rejected upstream; no silent zero business value"
      alias_rules: "feature aliases resolve only through the upstream parsers and must not collapse into neutral values"
      model_input: true
    - name: "context_vector.regime_confidence"
      source: "NeocortexStateSnapshot.regime_confidence"
      required: true
      causal_time_required: true
      trainable_required: true
      missingness_semantics: "defaulted only after explicit upstream absence; no silent truth fabrication"
      alias_rules: "regime / confidence aliases are resolved explicitly in the snapshot payload builder"
      model_input: true
    - name: "context_vector.position_qty"
      source: "portfolio payload quantity / position quantity"
      required: true
      causal_time_required: true
      trainable_required: true
      missingness_semantics: "absence remains visible through the snapshot fields"
      alias_rules: "quantity | position_qty | portfolio_position_amt"
      model_input: true
    - name: "context_vector.mark_price"
      source: "portfolio payload mark price"
      required: true
      causal_time_required: true
      trainable_required: true
      missingness_semantics: "no synthetic zero truth; missingness stays explicit"
      alias_rules: "mark_price | mid_price"
      model_input: true
    - name: "context_vector.unrealized_pnl"
      source: "portfolio payload unrealized / realized pnl"
      required: true
      causal_time_required: true
      trainable_required: true
      missingness_semantics: "support-quality gate remains explicit"
      alias_rules: "unrealized_pnl_usdt | unrealized_pnl | realized_pnl_net"
      model_input: true
    - name: "context_vector.intent_quantity"
      source: "intent payload quantity"
      required: true
      causal_time_required: true
      trainable_required: true
      missingness_semantics: "missing intent quantity is visible, not zero-filled as truth"
      alias_rules: "quantity | proposed_quantity | intent_quantity"
      model_input: true
    - name: "context_vector.position_side"
      source: "portfolio payload side"
      required: true
      causal_time_required: true
      trainable_required: true
      missingness_semantics: "non-causal or absent side is diagnostics-only upstream"
      alias_rules: "side | position_side"
      model_input: true
    - name: "context_vector.intent_side"
      source: "intent payload side"
      required: true
      causal_time_required: true
      trainable_required: true
      missingness_semantics: "no neutral business value for unknown intent side"
      alias_rules: "side | intent_side"
      model_input: true
    - name: "context_vector.feature_freshness"
      source: "tick_ts_ms - feature_event_ts_ms"
      required: true
      causal_time_required: true
      trainable_required: true
      missingness_semantics: "freshness is explicit metadata, not an inferred default"
      alias_rules: "feature_event_ts_ms | timestamp_ms | ts"
      model_input: true
    - name: "context_vector.regime_freshness"
      source: "tick_ts_ms - regime_event_ts_ms"
      required: true
      causal_time_required: true
      trainable_required: true
      missingness_semantics: "None remains visible until a causal regime row exists"
      alias_rules: "regime_event_ts_ms | regime_ts_ms"
      model_input: true
    - name: "context_vector.portfolio_freshness"
      source: "tick_ts_ms - portfolio_event_ts_ms"
      required: true
      causal_time_required: true
      trainable_required: true
      missingness_semantics: "portfolio absence is explicit, not zero truth"
      alias_rules: "portfolio_event_ts_ms | portfolio_ts_ms"
      model_input: true
    - name: "context_vector.bar_trigger_flag"
      source: "trigger_event_type"
      required: true
      causal_time_required: true
      trainable_required: true
      missingness_semantics: "trigger event remains semantic metadata"
      alias_rules: "BAR_CLOSED | EVT:BAR_CLOSED"
      model_input: true
  context_dim: 11
  total_state_dim: "len(config.ingest.feature_list) + 11"
observation_envelope_link:
  builder: "apps/reference/domains/neocortex/contracts/observation_envelope.py"
  causal_only: true
  trainable_only: true
  diagnostics_only_rejected_for_model_input: true
```

## Notes

- The ordered feature portion is configuration-owned and must match `config.ingest.feature_list`.
- The context portion is fixed by `NeocortexStateAggregator.CONTEXT_DIM = 11`.
- Any alias is only allowed to resolve to a documented canonical field; unknown aliases fail closed.
