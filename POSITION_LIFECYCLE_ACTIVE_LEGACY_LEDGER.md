# POSITION_LIFECYCLE_ACTIVE_LEGACY_LEDGER

| Surface name | Owner | Status | Why |
| --- | --- | --- | --- |
| `OrderIndex` order identity + reservation | execution_position | ACTIVE | Instantiated by EP and used for correlation, terminal marking, reservation |
| `ManageFlowFSM` local position lifecycle | execution_position | ACTIVE | Holds live position/bracket state and executes max-hold, bracket, and trailing logic |
| `CloseFlowFSM` soldier close path | execution_position | ACTIVE | Still converts `CMD:CLOSE` into `DEC:CLOSE` |
| `CloseFlowFSM` autonomous close rules | execution_position | LEGACY | `_check_close_conditions()` returns `None`; comments state autonomous close removed |
| `CloseExecutor` partial/full close execution | execution_position | ACTIVE | Executes reduce-only closes and reconcile |
| `OrderGuardian` tidy/orphan cleanup | execution_position | ACTIVE | Live cleanup path with tests |
| `OrderGuardian` business close reconcile | execution_position | ACTIVE | Distinct close-reconcile event with tests |
| TP1 / TP2 / legacy TP handling | execution_position | ACTIVE | Live in `_handle_bracket_fill()` |
| Exchange-side trailing stop replacement | execution_position | ACTIVE | Live cancel+replace SL logic |
| Max-hold close | execution_position | ACTIVE | Live `DEC:CLOSE` emission from manage rules |
| Pending-entry stale regime cancel | execution_position | ACTIVE | Live pending-order cancel path |
| `ORDER_TIMEOUT` | execution_position | ACTIVE | Emitted on timed-out orders |
| `LIMIT_ORDER_TIMEOUT` | execution_position | ACTIVE | Emitted by limit monitor |
| Tidy telemetry | execution_position | ACTIVE | Explicit non-business-close cleanup surface |
| `EXECUTION_CLOSE_RECONCILED` | execution_position | ACTIVE | Explicit authoritative close reconcile surface |
| `EXIT_MATCH_ATTEMPTED` / `FAILED` | execution_position | ACTIVE | Rich exit attribution surface |
| Position-lifetime intelligence beyond max hold | none proven | UNPROVEN | No proven conviction/health owner found |
| Dynamic TP replacement / TP extension | none proven | UNPROVEN | No live runtime mutation path traced |
| Break-even after TP1 | execution_position | DECLARED-BUT-NOT-USED | TODO comment only |
| Exchange `TRAILING_STOP_MARKET.callbackRate` | trading params | DECLARED-BUT-NOT-USED | Runtime consumer not found |
| Aurora `ExitManager` post-entry evaluation | decision_making | ACTIVE | Live call while a position is open |
| Aurora `ExitManager` universal end-to-end close execution | decision_making -> execution_position | UNPROVEN | Evaluation is proven; every downstream execution branch is not |
| Regime-flip reduce-only close | decision_making | ACTIVE | Tests prove live path |
| Holding period suppression | decision_making | ACTIVE | Live strategy-side exit suppression |
| Reentry cooldown | decision_making | ACTIVE | Live strategy-side re-entry block |
| Strategy-local TP manager beyond EP brackets | strategy layer | UNPROVEN | No proven live TP replacement engine found |
| `absorption` as mature early-cut signal | feature_engineering | UNPROVEN | Shared bar schema still labels it placeholder |
| Stable cross-event `position_id` | cross-domain | UNPROVEN | `rid` and order IDs exist, but uniform position identity was not proven |
