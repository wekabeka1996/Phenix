# RFC_REGIME_LIFECYCLE_AND_BTC_LEADER_INFLUENCE

Date: 2026-03-30

## Goal

Define an additive-only design for two missing context layers:

1. Local regime lifecycle metadata for each symbol.
2. BTC leader influence context for non-anchor instruments.

This RFC is intentionally design-only. It does not change raw structural regime truth and does not propose mutating the meaning of EVT:REGIME_DETECTED.

## FACTS THAT CONSTRAIN THE DESIGN

- The current live structural regime is produced by RegimeDetector and emitted as structural plus per_symbol plus bar.
- Downstream strategies already depend on that raw structural label, its confidence, and its warmup semantics.
- Current regime_age_sec in downstream objective inputs measures last-heartbeat freshness, not stable-regime dwell time.
- BTC and anchor influence already exists through anchor-derived warmup, macro_resid, and Aurora anchor_shock_veto.
- ExecutionPosition already distinguishes structural per-symbol regime from global execution-style context and only adapts exposure for global execution_micro or global_backdrop regime payloads.

These facts force one architectural rule:

- Do not overwrite raw structural regime with BTC context or lifecycle interpretation.

## Non-Goals

- No rewrite of RegimeDetector classification logic.
- No mutation of the semantic meaning of EVT:REGIME_DETECTED.
- No direct replacement of map_to_flat_regime behavior for MR.
- No hidden business constants outside config and typed contracts.
- No silent fallback if lifecycle or leader context is missing or stale.

## Design Principles

1. Raw structural regime remains the single source of truth for local structural state.
2. Lifecycle and leader-follow state are derived layers, not substitute labels.
3. Missing context must fail closed or degrade to no-effect, never silently invent state.
4. New policy must be auditable with explicit trace points and reason codes.
5. The design must avoid double counting against existing macro_resid and anchor_shock_veto behavior.
6. New events and config must be additive and registered in the existing YAML registries when implemented.

## Proposed Additive Architecture

### A. LocalRegimeLifecycle as a derived per-symbol context

Proposed producer:

- A small derived-context helper that consumes EVT:REGIME_DETECTED and maintains lifecycle state per symbol.

Recommended location:

- DecisionMaking-side helper or a dedicated lightweight context service near the current central regime cache.

Reason for that placement:

- Lifecycle derives from regime heartbeats, changed flags, and structural refs, not from raw market data.
- DecisionMaking already owns the central per-symbol regime cache and warmup/trade gating flow.

Proposed event or cache contract:

- EVT:LOCAL_REGIME_LIFECYCLE_UPDATED

Proposed fields:

- symbol
- regime
- structural_regime_ref
- regime_confidence
- current_heartbeat_ts_ms
- last_changed_ts_ms
- stable_since_ts_ms
- bars_in_state
- heartbeats_in_state
- previous_regime
- previous_structural_regime_ref
- lifecycle_phase
- ready
- stale
- evidence_version

Proposed lifecycle_phase enum:

- UNKNOWN
- FRESH
- ESTABLISHED
- AGING
- STALE

Semantics:

- stable_since_ts_ms changes only when the stable structural label changes.
- current_heartbeat_ts_ms updates on every EVT:REGIME_DETECTED heartbeat.
- bars_in_state increments only while the stable structural regime remains unchanged.
- lifecycle_phase is derived from bars_in_state, freshness, and staleness rules from config.

Fail-closed rule:

- If timestamps are missing, out of order, or insufficient to derive stable_since correctly, ready=false and downstream policy must not use lifecycle modulation.

### B. LeaderInfluence as a separate cross-asset context

Proposed producer:

- A FeatureEngineering-side or adjacent derived helper that consumes anchor updates and local feature history.

Reason for that placement:

- Leader-follow context depends on anchor transport, anchor freshness, and local-versus-anchor price behavior.
- Those ingredients already live closest to FeatureEngineering and the anchor/macro_resid path.

Proposed event or cache contract:

- EVT:LEADER_INFLUENCE_UPDATED

Proposed fields:

- symbol
- leader_symbol
- ts_ms
- ready
- stale
- leader_impulse_window_sec
- leader_return
- leader_impulse_sigma
- follower_lag_score
- alignment_score
- influence_state
- influence_confidence
- source_anchor_ref
- evidence_version

Proposed influence_state enum:

- NEUTRAL
- LEADER_SUPPORTS_LONG
- LEADER_SUPPORTS_SHORT
- LEADER_ADVERSE_LONG
- LEADER_ADVERSE_SHORT
- LEADER_SHOCK
- UNKNOWN

Critical semantic rule:

- LeaderInfluence is not a regime label.
- It is a separate cross-asset policy context.
- It must not rewrite local structural regime, regime_confidence, or map_to_flat_regime output.

Fail-closed rule:

- If anchor data is stale, insufficient, or inconsistent, ready=false and downstream policy must behave as if leader context were unavailable.

## Why this must not override raw regime

Overriding raw regime would be a design error for four reasons.

1. The current structural regime is symbol-local truth derived from that symbol's own bar features.
2. BTC context is cross-asset context, not the same ontology as local structure.
3. MR, MD-AMR, Aurora, and ExecutionPosition already use structural regime in different downstream ways; mutating the upstream label would destroy auditability.
4. The runtime contract already distinguishes structural from broader context layers conceptually. A BTC-led overlay belongs in additive context, not in a rewritten structural label.

If the system eventually needs a true market-wide backdrop label, that should be introduced as a separate producer and contract, not smuggled into the structural per-symbol label.

## Proposed Consumer Policy

### Aurora

Recommended first consumer.

Allowed uses:

- lifecycle_phase may tighten or delay entries immediately after a fresh structural flip
- leader influence may veto or delay entries when leader context is fresh and adverse
- leader influence may relax thresholds only when no existing anchor_shock_veto or macro_resid conflict exists

Disallowed use:

- replacing state.regime with a leader-derived label
- adding leader influence as another unrestricted directional score on top of macro_resid in the same scoring lane

### Mean Reversion

Recommended initial mode:

- observe only

Allowed future use:

- optional timing filter around fresh regime inception for flat regimes

Disallowed use:

- changing flat-regime mapping logic
- interpreting leader influence as a flat-regime substitute

### MD-AMR

Recommended mode after Aurora observe-only proves stable:

- narrow gate or timing overlay only

Allowed use:

- extra filter on entry timing when regime is already allowed

Disallowed use:

- replacing allowed_regimes semantics

### ExecutionPosition

Not recommended as an initial consumer.

Rationale:

- The current EP path already has a semantics mismatch around cancel_on_regime_change versus payload.changed.
- EP should only consume lifecycle later if a separate invariant and trace plan is added.

## Double-Count Protections

This is the most important policy part of the RFC.

1. LeaderInfluence must not become another free-form directional score on the same BTC move already captured by macro_resid.
2. If LeaderInfluence is used as a gate or delay, macro_resid should remain the directional feature and anchor_shock_veto should remain the binary extreme-shock veto.
3. If LeaderInfluence is ever promoted to a directional score, then macro_resid use in that same decision lane must be reduced, isolated, or removed to keep the contribution orthogonal.
4. All overlap cases must emit explicit reason codes so audits can distinguish:
   - blocked_by_low_regime_confidence
   - blocked_by_anchor_shock_veto
   - blocked_by_leader_adverse_fresh_regime
   - blocked_by_lifecycle_inception_hold

Recommended policy shape for the first implementation:

- Lifecycle is timing context.
- LeaderInfluence is timing or veto context.
- macro_resid remains the anchor-relative directional feature.
- anchor_shock_veto remains the extreme adverse-shock override.

That separation minimizes overlap.

## Required Contract and Config Additions When Implemented

Typed config additions should be explicit and additive, for example:

- domains.decision_making.regime_lifecycle
- domains.feature_engineering.leader_influence
- strategy-level toggles for Aurora, then optional later toggles for MD-AMR and MR

Implementation-time registry work required by project law:

- register new EVT verbs in apps/reference/dictionaries/verb_registry_v1.yaml
- update any domain dictionaries or schema registries that gate allowed events
- add Pydantic models in apps/reference/config_models.py
- add JSON schema contracts for the new events if they follow the existing schema pattern

No hidden constants:

- bar thresholds for FRESH and AGING phases
- leader impulse windows
- staleness TTLs
- minimum sample counts
- overlap policies

All of those must live in typed config.

## Recommended Rollout Order

1. Add lifecycle and leader context in observe-only mode with traces and no trading effect.
2. Make Aurora the only active consumer first.
3. Keep MR observe-only until parity and overlap audits are clean.
4. Keep MD-AMR behind a separate toggle until Aurora evidence is stable.
5. Defer any ExecutionPosition integration until cancel semantics are clarified.

## ASSUMPTIONS

- The present repo architecture remains event-driven and additive event registration remains the preferred integration style.
- Aurora is the best first consumer because it already owns the strongest direct BTC-anchor influence path.

## UNKNOWNS AND RISKS

- The current anchor_update_from_ticks config split could complicate live-versus-replay parity for a leader context until config ownership is cleaned up.
- If production relies on the unproven global decision.regime_thresholds surface, later cleanup may reveal hidden coupling.
- Any attempt to use leader context both as a directional weight and as a veto without overlap accounting will likely inflate double counting.

## Bottom Line

The correct additive design is not a new regime label. It is a pair of derived contexts layered on top of the existing raw structural regime: a true local lifecycle clock and a separate BTC leader-influence context. Raw structural regime remains the SSOT. New policy should operate on timing and gating, not on rewriting the structural truth.
