# POSITION_POLICY_SIDECAR_FUTURE_DESIGN_PRECONDITIONS_NOTE

## Proven Preconditions

- `ManageFlowFSM` is the current local SSOT for open-position and bracket lifecycle.
- `CloseExecutor` plus current `DEC:CLOSE` hardening already provide the safe close execution path a sidecar should reuse.
- `OrderGuardian` already separates tidy-only cleanup from authoritative close reconciliation.
- Existing events are sufficient for a first sidecar cache: `TRADE_EXECUTED`, `ORDER_FILL`, `ORDER_STATE_CHANGED`, `REGIME_DETECTED`, `FEATURES_CALCULATED`, `PORTFOLIO_STATE_UPDATED`, and `EXECUTION_CLOSE_RECONCILED`.
- Runtime contracts already expose enough feature context to discuss soft early-cut logic, including OBI, TFI, delta_price, liquidity_kappa, price_motion, and regime confidence.

## Unresolved Blockers

- Position identity is still weak across events; a stable `position_id` / lifecycle ID was not proven.
- Aurora already has overlapping post-entry evaluation in `ExitManager`; RFC work must define the relationship explicitly.
- The exact end-to-end execution effect of every `ExitManager` branch was not fully proven here.
- Current observability does not yet explain a future "position health" or "target extension" decision.

## Dangerous Assumptions

- "Watchdog already manages position life." False. It manages order timeouts.
- "There is no post-entry policy today." False. Max-hold, trailing, regime-flip close, and Aurora exit evaluation already exist.
- "Dynamic TP is already live." Unproven. Trailing stop replacement is live; TP replacement/extension is not.
- "A sidecar in decision_making is automatically cleaner." Not with current overlap against `ExitManager`, holding period, and regime-flip semantics.
- "Absorption is a mature shared-runtime signal." Not proven in the current shared bar contract.

## Minimum Extra Evidence Needed Before RFC

1. Prove or disprove how Aurora `ExitManager` branches map to actual close/reduce execution for already-open positions.
2. Choose the future output contract: recommendation only, internal observation, or close/reduce request.
3. Define how the sidecar correlates fills, closes, and reconciles without inventing a second state owner.
4. Define precedence against existing regime-flip close, max-hold close, trailing-stop mutation, and strategy-side exit evaluation.
5. Define future trace requirements before rollout: policy source, feature snapshot, position snapshot, suppression reason, and final execution outcome.

## Narrow Starting Posture

If RFC work starts now, the least-damaging initial posture is:

- location: new sidecar file inside `execution_position`
- role: additive evaluator, not state owner
- output: recommendation or close/reduce request through existing command paths
- initial scope: hold / reduce / early-close pressure for already-open positions
- explicitly out of scope at first: direct bracket mutation, TP replacement, regime mutation, and macro-context reinvention
