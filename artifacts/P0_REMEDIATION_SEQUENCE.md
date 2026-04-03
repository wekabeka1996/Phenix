# P0 SSOT Runtime Drift Remediation Sequence

## Scope rule
This sequence is planning only. It defines the order in which drift surfaces should be repaired so that execution safety is not destabilized while ownership is being collapsed.

## Phase 0. Freeze and classify
Objective: lock evidence, decide canonical owners, and protect already-correct surfaces.

Actions:
- Freeze the current evidence set: P0 ledger, timer census, negative findings, OBI/TFI report, and this package.
- Mark each audited surface as one of: keep active, wire, demote from SSOT, or remove from operator-facing docs.
- Treat strategies.aurora.decision.reentry_cooldown_sec as a control surface. Do not refactor it while adjacent cooldown or trailing work is ongoing.

Validation gates:
- Static owner map exists for every P0/P1 surface.
- No implementation begins until each surface has exactly one proposed canonical owner.

## Phase 1. Critical execution timeout cleanup
Objective: remove false safety and miswired timeout knobs from the execution path first.

Surfaces:
- hardening.ttl_config.entry_place_ttl_ms
- hardening.ttl_config.bracket_place_ttl_ms
- hardening.ttl_config.cancel_ttl_ms
- trading.execution.orders.default_ttl_seconds
- trading.execution.watchdog.check_interval_ms
- trading.execution.watchdog.rps_limit
- trading.execution.cooldown_ms fallback path
- execution_position.order_index.entry_guard_ttl_sec

Required decisions:
- Decide whether hardening.ttl_config.* becomes real execution SSOT or is explicitly demoted to metadata-only and removed from operator guidance.
- Decide whether default_ttl_seconds remains a supported override. If yes, fix the namespace read. If no, delete the override surface and rely on watchdog.fill_ttl_ms only.
- Decide whether watchdog cadence fields are live controls or dead config. Do not keep them half-wired.
- Decide whether OrderIndex.entry_guard_ttl_sec is promoted to SSOT or kept as an explicit code policy.

Validation gates:
- Focused execution_position tests for timeout behavior.
- Synthetic timeout trace proving which field owns fill timeout, check interval, and REST poll throttle.
- No silent fallback remains on an execution-critical timeout surface unless explicitly documented as a compatibility contract.

## Phase 2. Exposure and trailing ownership collapse
Objective: eliminate duplicate risk-control ownership and split protective-exit ownership.

Surfaces:
- trading.execution.exposure.pending_ttl_sec
- trading.execution.exposure.post_fill_hold_ttl_sec
- domains.position_tracking.positions_stale_ttl_sec vs domains.execution_position.exposure_guard.stale_ttl_sec
- system.trailing.min_update_interval_sec
- strategies.aurora.assets.<SYMBOL>.trailing_stop.* vs AuroraConfig.instruments.* compatibility probe

Required decisions:
- Keep exactly one owner for ExposureGuard TTLs. The current live consumer points to domains.execution_position.exposure_guard.*.
- Preserve the semantic distinction between position_tracking.positions_stale_ttl_sec and exposure_guard.stale_ttl_sec. They are similarly named, not necessarily duplicates.
- Choose one trailing owner model. Either execution_position and Aurora handler both consume strategies.aurora.assets.<SYMBOL>.trailing_stop.*, or both consume a real global abstraction. Compatibility probing must not remain a third owner.
- If system.trailing.min_update_interval_sec is not part of the chosen model, retire or clearly demote it.

Validation gates:
- ExposureGuard tests prove the active TTL owner.
- Trailing-stop integration test with at least one symbol having trailing enabled and one disabled.
- Cross-domain trace shows Aurora handler and execution_position agreeing on effective trailing enablement and cadence.

## Phase 3. Freshness semantics unification
Objective: make stale data semantics explicit and consistent across RegimeDetector and DecisionMaking.

Surfaces:
- system.market_data.tick_ttl_ms
- system.market_data.bar_ttl_ms
- system.market_data.bar_event_age_mode

Required decisions:
- Decide whether tick-level events are part of the live regime freshness contract. If not, demote tick_ttl_ms from operator-facing SSOT for that path.
- Remove or justify the hidden 10000ms fallback for bar_ttl_ms.
- Decide whether RegimeDetector and DecisionMaking should share the same age-mode semantics, or document them as intentionally different.

Validation gates:
- Replay stale tick and stale bar events across both domains.
- Explicit tests for missing bar_ttl_ms and missing bar_event_age_mode behavior.
- Passport language updated only after the final domain semantics are proven.

## Phase 4. Strategy-specific contract cleanup
Objective: clean up inert or partially proven strategy knobs after core execution and freshness surfaces are stable.

Surfaces:
- domains.decision_making.entry_plan.obi_missing_policy
- strategies.md_amr.reconciliation.interval_sec
- strategies.llm_microstructure.timeframe_sec
- strategies.llm_microstructure.enabled

Required decisions:
- Either honor obi_missing_policy in AuroraConfigLoader or remove the field from operator-facing SSOT.
- Prove the scheduler owner for md_amr.reconciliation.interval_sec before preserving it as a runtime control.
- For llm_microstructure, decide whether timeframe and enable semantics belong to the strategy profile, the registry, trading.llm_orchestration, or the bridge. Then collapse to one ownership story.

Validation gates:
- Focused Aurora entry-plan tests.
- End-to-end MD-AMR reconciliation trace from trigger source to local position repair.
- End-to-end LLM ingress trace from bridge admission to downstream emitted intent semantics.

## Phase 5. Passport and operator-document repair
Objective: regenerate docs only after ownership and wiring decisions are complete.

Surfaces:
- system_passport.md
- trading_passport.md
- aurora_math_passport.md
- AURORA_STRATEGY_CONFIG_PASSPORT.md
- md_amr_strategy_passport.md
- llm_microstructure_strategy_passport.md
- strategies_passport.md

Rules:
- Runtime truth wins over old passport wording.
- Do not document a field as live if the consumer is not proven.
- Explicitly mark metadata-only, deprecated, compatibility-only, or partially proven surfaces.

Validation gates:
- Every passport row points at the current runtime owner and current code path.
- No doc claims a single owner when the runtime still has split ownership.
- A final grep-based audit finds no contradictory operator guidance on the same surface.

## Quick wins
- Demote or explicitly mark hardening.ttl_config.* as metadata-only until a real consumer exists.
- Collapse exposure TTL guidance onto domains.execution_position.exposure_guard.* immediately after owner decision.
- Add a single drift note near global trailing min_update_interval_sec if it remains intentionally unused.
- Correct aurora_math_passport essential_features wording so it does not overstate direct OBI scoring in the quadratic kernel.

## Stop conditions
- Do not merge exposure or trailing surfaces until the chosen owner is proven by a runtime trace.
- Do not remove similarly named TTLs without proving whether they are duplicates or intentionally separate contracts.
- Do not rewrite passports first. Ownership and runtime behavior must be settled before documentation cleanup.
