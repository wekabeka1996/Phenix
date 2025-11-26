# TODO_EXECPOS_AUDIT — Execution Position Audit Backlog

Date: 2025-11-26  
Related: `docs/EXEC_POS_RUNTIME_V2_AUDIT.md`, `docs/EXEC_POS_RUNTIME_V2_AUDIT_CHECKLIST.md`

---

## P1 (High) — Adapter robustness

- [ ] **BinanceExecutionAdapterV2 error classification coverage**
  - Add unit tests for `_classify_place_error` covering all expected categories (ORDER_WOULD_TRIGGER, DUPLICATE_CLIENT_ORDER_ID, INSUFFICIENT_BALANCE, RATE_LIMIT, NETWORK_TIMEOUT, INVALID_QUANTITY, MIN_NOTIONAL_VIOLATION, PRECISION_VIOLATION, UNKNOWN_ERROR).
- [ ] **Mark‑price and filter validation paths**
  - Cover `_get_mark_price_async` success/failure, and any retry/guard logic that depends on mark price when handling filter errors (-2021, precision/step size).
- [ ] **Orders fallback ↔ ExposureGuard integration**
  - Add tests for `_enter_orders_fallback_mode` with and without `fsm.exposure_guard`, asserting logs and fallback mode transitions.

## P2 (Medium) — Runtime wiring & invariants

- [ ] **Document and guard `enable_direct_trade_intent_listener`**
  - Explicitly mark the flag as test‑only in docs/config samples; add a small test ensuring that when enabled, V2RuntimeFacade receives TRADE_INTENT but that production configs keep it disabled.
- [ ] **Additional guard‑loop scenarios**
  - Extend `test_agg_oco_races_guard_loop_vs_trade.py` with mixed reasons (`trade_executed` followed by `account_update_sync` and vice versa) to increase confidence in `BracketStatus` behavior under unusual event ordering.
- [ ] **Snapshot recovery stress tests**
  - Add synthetic tests for repeated UNKNOWN/STALE → FRESH transitions with intermittent timeouts to validate that bracket evaluation does not oscillate or leak state.

## P2 (Medium) — Coverage gaps in helpers

- [ ] **`adapter_factory.py` modes**
  - Parametrized tests for `trading_mode` in {`testnet`, `live`, `hybrid_live_data_testnet_exec`, `sim`, `shadow`, `paper`, unknown} to assert correct adapter choice or `None`.
- [ ] **`runtime_factory.py` legacy guard**
  - Test `runtime_mode="legacy"` path raising the expected `ValueError`, plus the happy path wiring for V2.
- [ ] **`drift_monitor.py` analytics**
  - Small unit tests for `ConfusionMatrix` and `Mismatch` to validate drift and accuracy calculations and exported dict structure.

## P3 (Low) — Tech debt / cleanup

- [ ] **Clarify / remove effectively dead code**
  - Decide fate of `internal_types.ExecutionResult` dataclass and `utils_event_bus.LocalBus` (mark as legacy in docs or remove in a dedicated cleanup once external dependencies are confirmed absent).
- [ ] **Increase coverage for `utils.py` price/id helpers**
  - Add round‑trip tests for `build_client_order_id` / `parse_client_order_id` / `build_bracket_client_ids` and quantization helpers to better lock in contracts.
- [ ] **Simulated adapter behavior**
  - Add basic tests for `SimulatedExecutionAdapter` (`place_order`, `cancel_order`, `get_open_positions`, `get_open_orders`) so dev/shadow setups have clearer guarantees.

