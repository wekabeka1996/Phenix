# Decision Making Cleanup Log

This document tracks the removal of legacy Aurora logic from `decision_making.py`.
Each removed block is verified against the new `AuroraScoringKernel` and `AuroraHandler` implementation.

## Strategy
1. Identify legacy code block.
2. Verify its logic exists in `AuroraScoringKernel` (pure logic) or `AuroraHandler` (state).
3. Log the verification result.
4. Move the code here.

---

## 1. `_make_decision_for_symbol`

**Status:** Pending Analysis
**Target:** `decision_making.py`

### Verification Matrix

| Legacy Logic | New Implementation | Verified? |
|--------------|-------------------|-----------|
| State Guard (Busy/Idempotency) | Handled by FSM/Gateway | ⏳ |
| QoS Checks (Shadow/Defer) | `AuroraHandler` + `_qos_allow` | ⏳ |
| Feature Normalization | `AuroraScoringKernel` | ⏳ |
| Liquidity Gate | `AuroraScoringKernel` | ⏳ |
| Direction Strength Score | `AuroraScoringKernel` | ⏳ |
| Feature Logging (Psi) | Legacy only (removed?) or in `AuroraHandler`? | ⏳ |
| Threshold Calculation | `AuroraScoringKernel` | ⏳ |
| Side Bias Calculation | `AuroraScoringKernel` + `AuroraHandler` (state) | ⏳ |
| Side Determination | `AuroraScoringKernel` | ⏳ |
| Crowding Filter | `decision_making.py` (Gateway?) | ⏳ |
| Signal Emission | `AuroraHandler` | ⏳ |

### Deleted Code
(To be populated)
            return True

        return False

    def _check_and_trigger_decision_for_symbol(self, symbol: str) -> None:
        if not self.latest_portfolio:
            self.logger.debug(
                f"[{symbol}] Decision deferred: global portfolio state not yet available."
            )
            return

        # Strategy registry SSOT: this method triggers the Aurora tick-based decision flow.
        # MR-only symbols must not run Aurora decision to avoid confusing "All data ready" logs.
        try:
            if hasattr(self, "_is_strategy_assigned") and (not self._is_strategy_assigned(symbol, "aurora")):
                return
        except Exception:
            # Monitoring-only: do not block decision flow on strategy registry issues.
            pass

        state = self.symbol_states[symbol]
        has_features = bool(state.get("features"))
        has_risk = bool(state.get("risk"))

        # Check features readiness with TTL
        features_ready = False
        if has_features:
            features_ready = self._features_ready(symbol, state["features"])
            if not features_ready:
                # XAI instrumentation: features not ready
                now_ts = time.time() * 1000
                features_ts = state["features"]["ts"] if "ts" in state["features"] else 0
                lag_ms = now_ts - features_ts
                ttl_ms = self.features_ttl_sec * 1000

                self.logger.warning(
                    format_why_with_details(
                        WhyCode.GUARD_RATE_LIMIT_EXCEEDED,  # closest match for stale data
                        f"features_stale symbol={symbol} rid=? now_ts={now_ts} "
                        f"last_features_ts={features_ts} lag_ms={lag_ms} ttl_ms={ttl_ms}"
                    )
                )
                inc_decision_deferred(symbol, "features_stale")

        # If we have both features and risk, make decision immediately
        # TTL gate enabled: requires fresh features within ttl_sec (default 30s)
        if has_features and has_risk and features_ready:
            rid = str(uuid.uuid4())

            feats_evt = state["features"] or {}
            if not isinstance(feats_evt, dict):
                raise ConfigContractError(path="features", why="Expected dict payload for features event")
            ts = feats_evt.get("ts")
            if ts is None:
                raise ConfigContractError(path="features.ts", why="Missing required ts in features payload", symbol=symbol)
            ts = int(ts)

            # Deduplicate rapid double-triggers caused by on_features + on_risk calling this method
            # back-to-back for the same (features.ts, risk.ts) snapshot. QoS should not be relied on
            # to prevent duplicate decisions.
            risk_evt = state["risk"] or {}
            risk_ts = int(risk_evt.get("ts", 0)) if isinstance(risk_evt, dict) else 0
            trigger_key = f"{ts}:{risk_ts}"
            now_ms = int(time.time() * 1000)
            last_key = state.get("_last_decision_trigger_key")
            last_ms_raw = state.get("_last_decision_trigger_ms", 0)
            last_ms = int(last_ms_raw) if isinstance(last_ms_raw, (int, float, str)) and str(last_ms_raw).isdigit() else 0
            if last_key == trigger_key and (now_ms - last_ms) < 250:
                self.logger.debug(
                    f"[{symbol}] Decision trigger dedupe: key={trigger_key} age_ms={now_ms - last_ms}"
                )
                return
            state["_last_decision_trigger_key"] = trigger_key
            state["_last_decision_trigger_ms"] = now_ms

            # Optional bar gating (e.g., M15) to avoid multiple decisions per bar
            if self._bar_gating_enabled:
                feats = state["features"] or {}
                ts = int(feats["ts"] if "ts" in feats else 0)
                if ts > 0 and self._bar_ms > 0:
                    bar_index = ts // self._bar_ms
                    last_idx = self._last_bar_index.get(symbol)
                    if last_idx is not None and bar_index == last_idx:
                        self.logger.info(
                            f"[{symbol}] Bar gate: already processed bar_index={bar_index}, skipping decision")
                        return
                    self._last_bar_index[symbol] = bar_index
            
            # STRATEGY-AWARE-GATES-FIX: Use strategies_registry.assignments as SSOT
            # for determining which strategy-specific gates to apply.
            # aurora.assets config is for signal weights, NOT for strategy assignment.
            aurora_assigned = self._is_strategy_assigned(symbol, "aurora")
            instr_cfg = self._get_aurora_instrument_cfg(symbol) if aurora_assigned else None
            is_aurora_symbol = bool(aurora_assigned and instr_cfg is not None and instr_cfg.enabled)

            # ========== CONTRACT v1.0: WARMUP GUARD (AURORA ONLY) ==========
            if is_aurora_symbol:
                warmup = None
                if symbol in self._per_symbol_regimes:
                    warmup = self._per_symbol_regimes[symbol].get("warmup")

                warmup_dict = warmup if isinstance(warmup, dict) else None
                warmup_full_ready = bool(
                    warmup_dict["full_ready"] if warmup_dict and "full_ready" in warmup_dict else False
                )

                if self.arming_require_regime_warmup and not warmup_full_ready:
                    now_ms = int(time.time() * 1000)
                    retry_key = self._stable_retry_key(prefix="arming", symbol=symbol, rid=rid, ts_ms=ts)
                    reason = "NRR-ARMING-NOT-READY" if warmup_dict else "NRR-ARMING-WARMUP-MISSING"
                    self.logger.warning(
                        f"[{symbol}] WARMUP_GUARD_DEFER (Aurora): {reason} warmup={bool(warmup_dict)} full_ready={warmup_full_ready}"
                    )
                    self._emit_intent_deferred_v1(
                        symbol=symbol,
                        reason=reason,
                        retry_key=retry_key,
                        next_allowed_ts=now_ms + max(0, int(self.arming_retry_backoff_ms)),
                        original_event_name="EVT:ARMING_RECHECK",
                        original_payload_min={"symbol": symbol, "rid": rid},
                        attempt=1,
                        max_attempts=int(self.arming_max_attempts),
                        why_chain=["arming_required", "warmup_not_ready"],
                        context="decision_making:_check_and_trigger_decision_for_symbol:warmup_guard",
                    )
                    self._record_blocked_intent(symbol)
                    return

                if (
                    (not self.arming_require_regime_warmup)
                    and warmup_dict
                    and (not bool(warmup_dict["full_ready"] if "full_ready" in warmup_dict else False)) # P0-2 Fix: Default False
                ):
                    ticks_seen = warmup_dict["ticks_seen"] if "ticks_seen" in warmup_dict else 0
                    self.logger.info(
                        f"[{symbol}] WARMUP_GUARD_BLOCKED (Aurora): full_ready=false (ticks_seen={ticks_seen})"
                    )
                    return

            # ========== REGIME GATING (Phase 2.2 Fix) ==========
            if instr_cfg:
                allowed_regimes = instr_cfg.allowed_regimes
                if allowed_regimes:
                    current_regime = None
                    if symbol in self._per_symbol_regimes:
                        current_regime = self._per_symbol_regimes[symbol].get("regime")

                    if not current_regime:
                        now_ms = int(time.time() * 1000)
                        retry_key = self._stable_retry_key(prefix="regime", symbol=symbol, rid=rid, ts_ms=ts)
                        self.logger.warning(
                            f"[{symbol}] REGIME_GATE_DEFER: missing regime (allowed_regimes={allowed_regimes})"
                        )
                        self._emit_intent_deferred_v1(
                            symbol=symbol,
                            reason="NRR-REGIME-MISSING",
                            retry_key=retry_key,
                            next_allowed_ts=now_ms + max(0, int(self.arming_retry_backoff_ms)),
                            original_event_name="EVT:ARMING_RECHECK",
                            original_payload_min={"symbol": symbol, "rid": rid},
                            attempt=1,
                            max_attempts=int(self.arming_max_attempts),
                            why_chain=["arming_required", "regime_missing"],
                            context="decision_making:_check_and_trigger_decision_for_symbol:regime_gate",
                        )
                        self._record_blocked_intent(symbol)
                        return

                    if current_regime not in allowed_regimes:
                        self.logger.info(
                            f"[{symbol}] REGIME_GATE_BLOCKED: {current_regime} not in {allowed_regimes}"
                        )
                        return
            # ==================================================
            self.logger.info(f"[{symbol}] ✅ All data ready! Triggering decision...")

            effective_regime = self._per_symbol_regimes.get(symbol)

            decision_context = {
                "features": state["features"],
                "risk_params": state["risk"],
                "portfolio": self.latest_portfolio,
                "regime": effective_regime,
            }
            self.dlog.write("DECISION_TRIGGER", rid, {"symbol": symbol})
            self._make_decision_for_symbol(symbol, decision_context, rid)
            return

        # If we only have features but risk was already assessed earlier, check if we can use cached risk
        if has_features and not has_risk:
            # Check if risk assessment happened recently (within last 30 seconds)
            # This handles the race condition where features arrive after risk assessment
            risk_assessment_time = state["_last_risk_time"] if "_last_risk_time" in state else 0
            current_time = time.time()
            if current_time - risk_assessment_time < 30:  # 30 second window
                cached_risk = state["_cached_risk"] if "_cached_risk" in state else None
                if cached_risk:
                    self.logger.info(
                        f"[{symbol}] ✅ Using cached risk assessment from "
                        f"{current_time - risk_assessment_time:.1f}s ago")
                    state["risk"] = cached_risk
                    
                    rid = str(uuid.uuid4())
                    feats_evt = state["features"] or {}
                    if not isinstance(feats_evt, dict):
                        raise ConfigContractError(path="features", why="Expected dict payload for features event")
                    ts = feats_evt.get("ts")
                    if ts is None:
                        raise ConfigContractError(path="features.ts", why="Missing required ts in features payload", symbol=symbol)
                    ts = int(ts)

                    # Same rapid double-trigger dedupe as the main path.
                    risk_evt = state["risk"] or {}
                    risk_ts = int(risk_evt.get("ts", 0)) if isinstance(risk_evt, dict) else 0
                    trigger_key = f"{ts}:{risk_ts}"
                    now_ms = int(time.time() * 1000)
                    last_key = state.get("_last_decision_trigger_key")
                    last_ms_raw = state.get("_last_decision_trigger_ms", 0)
                    last_ms = int(last_ms_raw) if isinstance(last_ms_raw, (int, float, str)) and str(last_ms_raw).isdigit() else 0
                    if last_key == trigger_key and (now_ms - last_ms) < 250:
                        self.logger.debug(
                            f"[{symbol}] Decision trigger dedupe: key={trigger_key} age_ms={now_ms - last_ms}"
                        )
                        return
                    state["_last_decision_trigger_key"] = trigger_key
                    state["_last_decision_trigger_ms"] = now_ms

                    effective_regime = self._per_symbol_regimes.get(symbol)

                    decision_context = {
                        "features": state["features"],
                        "risk_params": state["risk"],
                        "portfolio": self.latest_portfolio,
                        "regime": effective_regime,
                    }
                    self.dlog.write("DECISION_TRIGGER", rid, {
                                    "symbol": symbol, "cached_risk": True})
                    self._make_decision_for_symbol(
                        symbol, decision_context, rid)
                    return

        # Defer decision if we don't have required data
        self.logger.warning(
            f"[{symbol}] ⚠️ Decision deferred: features={has_features}, "
            f"risk={has_risk}, features_ready={features_ready}"
        )
        # Track decision deferrals for observability
        if not has_features and not has_risk:
            reason = "both_missing"
        elif not has_features:
            reason = "features_missing"
        elif not has_risk:
            reason = "risk_missing"
        elif not features_ready:
            reason = "features_stale"
        else:
            reason = "unknown"
        inc_decision_deferred(symbol, reason)

    def _make_decision_for_symbol(self, symbol: str, context: dict, rid: str) -> None:
        self.logger.info(
            f"[{symbol}] 🚀 _make_decision_for_symbol() START - RID: {rid}"
        )

        # STRATEGY-AWARE-GATES-FIX: Check assignment FIRST, then get config
        aurora_assigned = self._is_strategy_assigned(symbol, "aurora")
        instr_cfg = self._get_aurora_instrument_cfg(symbol) if aurora_assigned else None
        
        # Check if Aurora strategy is enabled for this symbol (only if assigned)
        if aurora_assigned and instr_cfg and hasattr(instr_cfg, 'enabled') and not instr_cfg.enabled:
            self.logger.info(
                f"[{symbol}] Aurora strategy DISABLED for this instrument. Skipping decision."
            )
            return
        
        # For MR-only symbols, skip Aurora decision flow entirely
        if not aurora_assigned:
            self.logger.debug(
                f"[{symbol}] Aurora not assigned. MR signals use strategy gateway. Skipping Aurora decision."
            )
            return

        # P0-W1: Warmup/arming gate (fail-closed when enabled).
        is_aurora_symbol = bool(instr_cfg is not None and instr_cfg.enabled)
        if self.arming_require_regime_warmup and is_aurora_symbol:
            warmup = None
            if symbol in self._per_symbol_regimes:
                warmup = self._per_symbol_regimes[symbol].get("warmup")

            warmup_dict = warmup if isinstance(warmup, dict) else None
            warmup_full_ready = bool(warmup_dict["full_ready"] if warmup_dict and "full_ready" in warmup_dict else False)
            if not warmup_full_ready:
                now_ms = int(time.time() * 1000)
                features_evt = context["features"] if "features" in context else None
                if not isinstance(features_evt, dict):
                    raise ConfigContractError(path="features", why="Missing/invalid features payload in decision context", symbol=symbol)
                features_evt_ts = features_evt.get("ts")
                if features_evt_ts is None:
                    raise ConfigContractError(path="features.ts", why="Missing required ts in features payload", symbol=symbol)
                retry_key = self._stable_retry_key(
                    prefix="arming",
                    symbol=symbol,
                    rid=rid,
                    ts_ms=int(features_evt_ts),
                )
                reason = "NRR-ARMING-NOT-READY" if warmup_dict else "NRR-ARMING-WARMUP-MISSING"
                self._emit_intent_deferred_v1(
                    symbol=symbol,
                    reason=reason,
                    retry_key=retry_key,
                    next_allowed_ts=now_ms + max(0, int(self.arming_retry_backoff_ms)),
                    original_event_name="EVT:ARMING_RECHECK",
                    original_payload_min={"symbol": symbol, "rid": rid},
                    attempt=1,
                    max_attempts=int(self.arming_max_attempts),
                    why_chain=["arming_required", "warmup_not_ready"],
                    context="decision_making:_make_decision_for_symbol:warmup_guard",
                )
                self._record_blocked_intent(symbol)
                return

        # Busy guard: prevent infinite defer loops during cooldown
        current_time_ms = int(time.time() * 1000)  # Convert to milliseconds for comparison
        next_allowed = self._qos_next_allowed_ts[symbol] if symbol in self._qos_next_allowed_ts else 0  # Already in milliseconds
        if current_time_ms < next_allowed:
            remaining_sec = (next_allowed - current_time_ms) / 1000.0  # Convert back to seconds for logging
            self.logger.warning(
                f"[{symbol}] Busy guard active: decision blocked for {remaining_sec:.1f}s (cooldown active)"
            )
            # Schedule one-time retry after cooldown expires
            self._ensure_after_cooldown_retry(symbol, context, rid)
            return

        # Idempotency guard: prevent spam on same features (SSOT)
        features_data = context["features"]["features"]
        features_evt = context["features"]
        current_features_ts = features_evt["ts"] if "ts" in features_evt else 0
        
        last_success_ts = self._last_successful_features_ts[symbol] if symbol in self._last_successful_features_ts else 0
        if current_features_ts > 0 and current_features_ts <= last_success_ts:
            # We already generated a successful intent for this feature snapshot.
            # Don't spam duplication or logs.
            # Exception: if we need to re-evaluate due to forced trigger? 
            # Assuming features are the clock signal for decisions.
            self.logger.debug(
                f"[{symbol}] Idempotency skip: features_ts={current_features_ts} <= last_success_ts={last_success_ts}"
            )
            return

        why_chain = []
        # features_data already extracted above
        risk_params = context["risk_params"]["risk_parameters"]
        portfolio = context["portfolio"]

        # FTR-07: Create typed DecisionContext for semantic feature access
        ts_ms = int(time.time() * 1000)
        ctx = create_decision_context(symbol, ts_ms, features_data)

        # P1: Degraded DecisionContext gate (opt-in).
        # Purpose: detect when "neutral" defaults are masking missing/invalid feature inputs.
        if self._degraded_context_gate_should_defer(
            symbol=symbol,
            rid=rid,
            ctx=ctx,
            features_evt=features_evt,
            strategy_id="aurora",
        ):
            return

        # QoS check (PACK EXP-4) - check rate limits and cooldowns
        qos_allowed, qos_reject_reason = self._qos_allow(
            symbol, is_exposure_block=False
        )
        if not qos_allowed:
            # Determine QoS enforcement mode
            effective_mode = self.qos_mode
            if self.qos_enforce and effective_mode == "defer":
                # Legacy enforce flag overrides defer mode
                effective_mode = "enforce"

            if effective_mode == "shadow":
                # Shadow mode: only log/metrics, continue with intent
                self.logger.warning(
                    f"[{symbol}] QoS shadow: passing intent downstream (reason: {qos_reject_reason})")
                inc_decision_deferred(symbol, "qos_shadow")
            elif effective_mode == "defer":
                # Defer mode: set busy guard and schedule one-time retry
                next_allowed_ts = self._calculate_next_allowed_time(symbol)
                next_allowed_sec = next_allowed_ts / 1000.0  # Convert to seconds

                self.logger.warning(
                    f"[{symbol}] QoS defer: setting busy guard until {next_allowed_sec} (reason: {qos_reject_reason})")

                # Set busy guard to prevent infinite defer loops
                self._qos_next_allowed_ts[symbol] = int(next_allowed_ts)

                # XAI instrumentation: qos_defer
                cooldown_left_ms = (next_allowed_ts - time.time() *
                                    1000) if next_allowed_ts > time.time() * 1000 else 0
                symbol_intent_counts: dict[str, Any] = dget(self._qos_state, "symbol_intent_counts", {})
                intent_data: dict[str, Any] = symbol_intent_counts[symbol] if symbol in symbol_intent_counts else {"count": 0}
                intent_count: int = int(intent_data["count"] if "count" in intent_data else 0)
                rate_state = f"count={intent_count}"
                self.logger.warning(
                    format_why_with_details(
                        WhyCode.GUARD_RATE_LIMIT_EXCEEDED,
                        f"cooldown_left_ms={cooldown_left_ms} rate_state={rate_state} code=NRR-012 why=qos_defer"
                    )
                )

                inc_decision_deferred(symbol, "qos_defer")

                # Update QoS state to record the deferral
                self._update_qos_state(symbol)

                # Schedule one-time retry after cooldown expires
                self._ensure_after_cooldown_retry(symbol, context, rid)

                # Log to OrderLoggerV1
                # Determine specific NRR code based on rejection reason
                if "symbol_cooldown" in str(qos_reject_reason):
                    nrr_code = NormalizedRejectReasons.SYMBOL_COOLDOWN_ACTIVE  # NRR-017
                else:
                    nrr_code = NormalizedRejectReasons.RATE_LIMIT_EXCEEDED  # NRR-012

                order_logger.write({
                    "rid": rid,
                    "timestamp": int(time.time() * 1000),
                    "event_type": "ORDER_REJECTED",
                    "symbol": symbol,
                    "source_fsm": "decision_making",
                    "nrr_code": nrr_code,  # Use NRR-017 / NRR-012 for logging
                    "why": "qos_defer",
                    "metadata": {"detail": nrr_code}
                })

                self.clear_internal_state_for_symbol(symbol)
                return
            else:  # enforce mode
                # Enforce mode: block intent (legacy behavior)
                normalized_reason = NormalizedRejectReasons.normalize(
                    qos_reject_reason or "QoS rejection"
                )
                self.logger.warning(
                    f"[{symbol}] Trade intent rejected by QoS: {normalized_reason}"
                )
                self.dlog.write(
                    "DECISION_SKIP", rid, {
                        "symbol": symbol, "reason": "QOS_RATE_LIMITED"}
                )

                # Use specific NRR codes: NRR-017 for cooldown, NRR-012 for rate limit
                if "symbol_cooldown" in str(qos_reject_reason):
                    nrr_code = NormalizedRejectReasons.SYMBOL_COOLDOWN_ACTIVE  # NRR-017
                else:
                    nrr_code = NormalizedRejectReasons.RATE_LIMIT_EXCEEDED  # NRR-012

                # Log to OrderLoggerV1
                order_logger.write({
                    "rid": rid,
                    "event_type": "ORDER_REJECTED",
                    "symbol": symbol,
                    "side": "NONE",
                    "nrr_code": nrr_code,  # Use NRR-017 / NRR-012 for logging
                    "why": qos_reject_reason[:80] if qos_reject_reason else "QoS rejection",
                    "source_fsm": "DecisionMaking",
                    "metadata": {"reject_reason": "QOS_RATE_LIMITED", "detail": nrr_code}
                })

                self.clear_internal_state_for_symbol(symbol)
                return

        # Use cached equity_free_usdt instead of portfolio equity to prevent zero-overwrite
        equity_str = (
            self._cached_equity_free_usdt
            or portfolio.get("equity_free_usdt")
            or (portfolio["equity"] if "equity" in portfolio else "0")
        )
        equity = decimal.Decimal(str(equity_str))

        self.logger.info(
            f"[{symbol}] Using equity for decision: {equity} (from cached: {self._cached_equity_free_usdt is not None})"
        )

        if equity <= 0:
            reject_reason = f"equity is zero or negative ({equity})"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            self.logger.warning(
                f"Trade intent for {symbol} rejected: {reject_reason} (NRR: {normalized_reason})"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {
                    "symbol": symbol, "reason": "ZERO_EQUITY"}
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": "NONE",
                "nrr_code": "NRR-011",  # Exposure related
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "ZERO_EQUITY", "equity": str(equity)}
            })

            self.clear_internal_state_for_symbol(symbol)
            return

        regime = context.get("regime")

        is_trading_allowed = bool(risk_params["is_trading_allowed"]) if "is_trading_allowed" in risk_params else False
        if not is_trading_allowed:
            reject_reason = "Trading not allowed by risk manager"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)

            # Record blocked intent for risk gate monitoring
            self._record_blocked_intent(symbol)

            # Check if this is an exposure block (PACK EXP-4)
            nrr_code = "NRR-011"  # Default to exposure
            if (
                "exposure_limit_exceeded" in str(risk_params).lower()
                or "exposure" in str(risk_params).lower()
            ):
                self._handle_exposure_block(symbol)
                normalized_reason = NormalizedRejectReasons.EXPOSURE_LIMIT_EXCEEDED
                nrr_code = "NRR-011"

            self.logger.info(
                f"Trade intent for {symbol} rejected: {reject_reason} (NRR: {normalized_reason})"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {
                    "symbol": symbol, "reason": "RISK_DISALLOWED"}
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": "NONE",
                "nrr_code": nrr_code,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "RISK_DISALLOWED", "risk_params": risk_params}
            })

            self.clear_internal_state_for_symbol(symbol)
            return

        # Strict Config Access
        trading_config = self.config.trading
        
        # Signal Weights:
        # 1. Try per-instrument (AuroraInstrument) - Dict[str, float]
        signal_weights = None
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg and instr_cfg.weights:
             signal_weights = instr_cfg.weights
        
        # 2. Global Fallback - SignalWeights Object -> Dict
        if not signal_weights:
             signal_weights = trading_config.decision.signal_weights.model_dump()

        # TASK54: Runtime warning for weight key mismatches (debugging aid)
        if signal_weights:
            features_keys = set(features_data.keys())
            weight_keys = set(signal_weights.keys())
            missing_in_features = weight_keys - features_keys
            if missing_in_features:
                self.logger.warning(
                    f"[{symbol}] WEIGHTS_KEY_MISMATCH: weight keys not in features: {sorted(missing_in_features)}. "
                    f"These weights contribute ZERO to signal_score. Fix config to use canonical keys."
                )

        # Compute signal score (dir/strength split) with explicit normalization mode.
        # FTR-07: Use DecisionContext for typed access to features
        psi_vector: Dict[str, Any] = {}

        signals_cfg = getattr(self.config.strategies.aurora.decision, "signals", None)
        if signals_cfg is None:
            raise ConfigContractError(
                path="strategies.aurora.decision.signals",
                why="signals config is required (SSOT)",
                symbol=symbol,
            )
        normalize_mode = str(getattr(signals_cfg, "normalize_signals_mode", "")).strip()
        if normalize_mode not in ("off", "legacy_v1", "signed_v2"):
            raise ConfigContractError(
                path="strategies.aurora.decision.signals.normalize_signals_mode",
                why=f"Invalid normalize_signals_mode={normalize_mode!r}. Expected: off|legacy_v1|signed_v2",
                symbol=symbol,
            )

        def _to_dec(val: Any) -> decimal.Decimal:
            try:
                return decimal.Decimal(str(val))
            except Exception:
                return decimal.Decimal("0")

        if normalize_mode == "legacy_v1":
            # LEGACY V1: kept only for forensic comparisons (forbidden in live by config guard).
            price_dec = ctx.price
            obi_raw = ctx.flow.obi
            tfi_raw = ctx.flow.tfi
            dp_raw = ctx.trend.delta_price
            ema_bias_phi = ctx.trend.ema_bias
            volume_spike_phi = ctx.volatility.volume_spike
            volatility_state_phi = ctx.volatility.volatility_state
            depth_imbalance_phi = ctx.liquidity.depth_imbalance
            macro_sync_phi = _to_dec(features_data["macro_sync"]) if "macro_sync" in features_data else decimal.Decimal("0")

            def _norm_m11_to_01(x: decimal.Decimal) -> decimal.Decimal:
                try:
                    if x >= 0 and x <= 1:
                        return x
                    return (x + 1) / 2
                except Exception:
                    return decimal.Decimal("0")

            obi_phi = _norm_m11_to_01(obi_raw)
            tfi_phi = _norm_m11_to_01(tfi_raw)
            dp_pct = (abs(dp_raw) / price_dec) if price_dec > 0 else decimal.Decimal("0")
            dp_cap_pct_norm = decimal.Decimal(str(signals_cfg.delta_price_cap_pct))
            dp_pct = max(decimal.Decimal("0"), min(dp_pct, dp_cap_pct_norm))
            dp_phi = dp_pct / dp_cap_pct_norm if dp_cap_pct_norm > 0 else decimal.Decimal("0")

            phi_map = {
                "obi": obi_phi,
                "tfi": tfi_phi,
                "delta_price": dp_phi,
                "ema_bias": ema_bias_phi,
                "volume_spike": volume_spike_phi,
                "volatility_state": volatility_state_phi,
                "depth_imbalance": depth_imbalance_phi,
                "macro_sync": macro_sync_phi,
            }
            signal_score = sum(
                decimal.Decimal(str(dget(phi_map, f, 0))) * decimal.Decimal(str(w))
                for f, w in signal_weights.items()
            )

            psi_vector = {
                "normalize_mode": "legacy_v1",
                "phi_OBI": float(obi_phi),
                "phi_TFI": float(tfi_phi),
                "phi_DeltaP": float(dp_phi),
                "phi_EMA_Bias": float(ema_bias_phi),
                "phi_Volume_Spike": float(volume_spike_phi),
                "phi_Volatility_State": float(volatility_state_phi),
                "phi_Depth_Imbalance": float(depth_imbalance_phi),
                "phi_Macro_Sync": float(macro_sync_phi),
                "weights": {k: float(v) for k, v in signal_weights.items()},
            }
        else:
            # NOTE: FeatureEngineering emits delta_price as absolute price delta (USD),
            # which makes the signal scale asset-price dependent (BTC >> alts).
            # Normalize to signed, clamped pct-of-price in [-1, 1] for stability.
            price_dec = ctx.price
            dp_raw = ctx.trend.delta_price
            dp_cap_pct = decimal.Decimal(str(signals_cfg.delta_price_cap_pct))
            if price_dec > 0 and dp_cap_pct > 0:
                dp_pct = dp_raw / price_dec
                if dp_pct > dp_cap_pct:
                    dp_pct = dp_cap_pct
                elif dp_pct < -dp_cap_pct:
                    dp_pct = -dp_cap_pct
                dp_norm = dp_pct / dp_cap_pct  # [-1, 1]
            else:
                dp_pct = decimal.Decimal("0")
                dp_norm = decimal.Decimal("0")

            psi_vector = {
                "normalize_mode": normalize_mode,
                "delta_price_raw": float(dp_raw),
                "delta_price_pct": float(dp_pct),
                "delta_price_norm": float(dp_norm),
            }

            scoring_ver = getattr(instr_cfg, "scoring_version", None) or getattr(
                self.config.strategies.aurora.decision, "scoring_version", "v1"
            )
            if scoring_ver != "v2":
                raise ConfigContractError(
                    path="strategies.aurora.decision.scoring_version",
                    why=f"scoring_version '{scoring_ver}' is not supported. Only 'v2' is allowed.",
                    symbol=symbol,
                )

            feature_neutrals = getattr(instr_cfg, "feature_neutrals", None) or getattr(
                self.config.strategies.aurora.decision, "feature_neutrals", {}
            )
            essential_features = getattr(instr_cfg, "essential_features", None) or getattr(
                self.config.strategies.aurora.decision, "essential_features", []
            )

            # Liquidity Gate Config (ScoreV2 prerequisite)
            liq_gate_cfg = getattr(instr_cfg, "liquidity_gate", None) or getattr(
                self.config.strategies.aurora.decision, "liquidity_gate", None
            )
            if liq_gate_cfg and liq_gate_cfg.enabled:
                # NO SILENT FALLBACKS: Missing key → explicit DEFER
                if "liquidity_kappa" not in features_data:
                    self.logger.warning(
                        f"[{symbol}] DEFER: liquidity_kappa MISSING from features (no silent fallback)"
                    )
                    self._emit_nrr(
                        symbol=symbol,
                        reason=NormalizedRejectReasons.LIQUIDITY_NOT_READY,
                        why="LIQUIDITY_KAPPA_MISSING:no_silent_fallback",
                    )
                    self._record_blocked_intent(symbol)
                    return
                
                kappa_val = _to_dec(features_data["liquidity_kappa"])
                if kappa_val < decimal.Decimal(str(liq_gate_cfg.kappa_min)):
                    self.logger.info(
                        f"[{symbol}] BLOCKED by Liquidity Gate: {kappa_val:.4f} < {liq_gate_cfg.kappa_min}"
                    )
                    self._emit_nrr(
                        symbol=symbol,
                        reason=NormalizedRejectReasons.LIQUIDITY_LOW,
                        why=f"LIQUIDITY_GATE:kappa={kappa_val:.4f}<min={liq_gate_cfg.kappa_min}",
                    )
                    self._record_blocked_intent(symbol)
                    return

            # Build v2 feature map (raw + normalized delta_price)
            v2_features = dict(features_data)
            v2_features["delta_price"] = dp_norm

            readiness_map = features_evt.get("warmup", {}).get("ready", {})

            # ═══════════════════════════════════════════════════════════════════
            # P0-0: MISSING_READY_KEYS Detection (config/code drift guard)
            # ═══════════════════════════════════════════════════════════════════
            # If essential features are in config but NOT in readiness_map keys,
            # we have config/code drift → DEFER with explicit NRR
            essential_set = set(essential_features)
            missing_ready_keys = essential_set - set(readiness_map.keys())
            
            if missing_ready_keys:
                self.logger.warning(
                    f"[{symbol}] P0-0 MISSING_READY_KEYS: essential features {missing_ready_keys} "
                    f"not in warmup.ready → DEFER. This is likely config/code drift."
                )
                # NRR with explicit reason
                self._emit_nrr(
                    symbol=symbol,
                    reason=NormalizedRejectReasons.MISSING_READY_KEYS,
                    why=f"MISSING_READY_KEYS:{','.join(sorted(missing_ready_keys))}",
                )
                self._record_blocked_intent(symbol)
                return


            ds_cfg = getattr(self.config.strategies.aurora.decision, "direction_strength_scoring", None)
            if ds_cfg is None:
                raise ConfigContractError(
                    path="strategies.aurora.decision.direction_strength_scoring",
                    why="direction_strength_scoring is required (SSOT)",
                    symbol=symbol,
                )

            ds_score = compute_direction_strength_score(
                features=v2_features,
                weights=signal_weights,
                neutrals=feature_neutrals,
                readiness=readiness_map,
                essential_features=set(essential_features),
                normalize_mode=normalize_mode,
                directional_features=list(ds_cfg.directional_features),
                strength_features=list(ds_cfg.strength_features),
                strength_alpha=float(ds_cfg.strength_alpha),
                strength_cap=float(ds_cfg.strength_cap),
                symbol=symbol,
            )
            if ds_score.deferred:
                deny = str(ds_score.deny_reason or "direction_strength_deferred")
                if deny == "NRR-NO-DIRECTIONAL-FEATURES-ACTIVE":
                    reject_reason = "no_directional_features_active"
                    nrr_code = NormalizedRejectReasons.NO_DIRECTIONAL_FEATURES_ACTIVE
                elif deny == "NRR-FEATURES-MISSING":
                    reject_reason = "features_missing_for_direction"
                    nrr_code = NormalizedRejectReasons.FEATURES_MISSING
                elif deny == "NRR-FEATURES-NOT-READY":
                    reject_reason = "features_not_ready_for_direction"
                    nrr_code = NormalizedRejectReasons.FEATURES_NOT_READY
                else:
                    reject_reason = deny
                    nrr_code = NormalizedRejectReasons.normalize(reject_reason)

                self._record_blocked_intent(symbol)
                self.logger.info(
                    f"Trade intent for {symbol} rejected: {reject_reason} (NRR: {nrr_code})"
                )
                self.dlog.write(
                    "DECISION_SKIP", rid, {"symbol": symbol, "reason": "DIR_STRENGTH_DEFERRED", "nrr": nrr_code}
                )
                order_logger.write(
                    {
                        "rid": rid,
                        "event_type": "ORDER_REJECTED",
                        "symbol": symbol,
                        "side": "NONE",
                        "nrr_code": nrr_code,
                        "why": reject_reason[:80],
                        "source_fsm": "DecisionMaking",
                        "metadata": {"reject_reason": "DIR_STRENGTH_DEFERRED", "deny_reason": deny},
                    }
                )
                return

            signal_score = ds_score.final_score

            psi_vector.update(
                {
                    "dir_score": float(ds_score.dir_score),
                    "strength_score": float(ds_score.strength_score),
                    "final_score": float(ds_score.final_score),
                    "dir_raw": float(ds_score.dir_result.score_raw),
                    "dir_wabs": float(ds_score.dir_result.wabs),
                    "dir_contribs": ds_score.dir_result.contribs,
                    "strength_raw": float(ds_score.strength_result.score_raw),
                    "strength_wabs": float(ds_score.strength_result.wabs),
                    "strength_contribs": ds_score.strength_result.contribs,
                }
            )

        # Trigger fix: added implicitly by repair loop next line connection

        # Base decision threshold (SSOT: strategies.aurora.decision.signal_threshold, with per-instrument override).
        base_threshold = self._get_signal_threshold(symbol)

        # Regime-based threshold multiplier (Δθ); defaults to 1.0 if not configured or regime missing
        # Phase A1: Per-instrument regime thresholds with global fallback
        regime_thresholds_cfg = self._get_regime_thresholds(symbol)
        regime_name = (regime or {}).get("regime") if regime else None
        try:
            # Use regime_threshold_multipliers config (already loaded above as regime_thresholds_cfg)
            if regime_name and regime_name in regime_thresholds_cfg:
                factor_str = str(regime_thresholds_cfg.get(regime_name))
            elif "DEFAULT" in regime_thresholds_cfg:
                factor_str = str(regime_thresholds_cfg.get("DEFAULT"))
            else:
                 # P1 FIX: No hardcoded "1.0" fallback if DEFAULT missing.
                 # If config is present but missing keys, we must block/fail to prevent unintended trading.
                 raise ConfigContractError(
                     path=f"regime.thresholds.{regime_name}", 
                     why="Missing regime threshold and no DEFAULT",
                     symbol=symbol
                 )
            
            threshold_factor = decimal.Decimal(factor_str)
        except Exception as e:
            # Propagate error to inhibit signal (Fail Closed)
            self.logger.error(f"Regime threshold error: {e}")
            return None # Stop signal generation
        signal_threshold = base_threshold * threshold_factor

        # EXP-DIRECTION: Calculate side-bias penalty (Δθ_bias)
        # Phase A1: Per-instrument side_bias with global fallback
        current_time = time.time()
        sell_bias_penalty_factor_raw, bias_window_sec, sell_target_ratio, min_intents = self._get_side_bias_params(symbol)
        sell_bias_penalty_factor = decimal.Decimal(str(sell_bias_penalty_factor_raw))

        # Track intents per side (you can also extract from order_logger if needed)
        side_intent_window = aget(self, "_side_intent_window", None)
        if side_intent_window is None:
            side_intent_window = {}
            self._side_intent_window = side_intent_window
        if symbol not in side_intent_window:
            side_intent_window[symbol] = {"buys": [], "sells": []}

        window_data = side_intent_window[symbol]
        # Remove old entries outside the window
        window_data["buys"] = [ts for ts in window_data["buys"]
                               if current_time - ts < bias_window_sec]
        window_data["sells"] = [ts for ts in window_data["sells"]
                                if current_time - ts < bias_window_sec]

        buy_count = len(window_data["buys"])
        sell_count = len(window_data["sells"])
        total_count = buy_count + sell_count

        # Asymmetric side-bias thresholds with Linear Ramp:
        # - If overheated, penalty scales linearly with excess beyond target.
        # - Activates only if total_count >= min_intents (noise filtering).
        buy_bias_mult = decimal.Decimal("1.0")
        sell_bias_mult = decimal.Decimal("1.0")
        sell_share: decimal.Decimal | None = None

        if total_count >= min_intents:
            sell_share = decimal.Decimal(str(sell_count)) / decimal.Decimal(str(total_count))
            target = decimal.Decimal(str(sell_target_ratio))
            
            if sell_share > target:
                # Too many SELLs -> Ramp penalty on SELL threshold
                excess = sell_share - target
                max_excess = decimal.Decimal("1.0") - target
                scaling = excess / max_excess if max_excess > 0 else decimal.Decimal("1.0")
                penalty = sell_bias_penalty_factor * scaling
                
                sell_bias_mult += penalty
                self.logger.info(
                    f"[{symbol}] SIDE_BIAS_PENALTY (SELL): sell_share={float(sell_share):.2%} > "
                    f"target={float(target):.2%}, excess={float(excess):.2f}, "
                    f"ramp_scaling={float(scaling):.2f}, raising SELL threshold by {float(penalty):.1%}"
                )
            elif sell_share < (decimal.Decimal("1.0") - target):
                # Too many BUYs -> Ramp penalty on BUY threshold
                buy_share = decimal.Decimal("1.0") - sell_share
                excess = buy_share - target
                max_excess = decimal.Decimal("1.0") - target
                scaling = excess / max_excess if max_excess > 0 else decimal.Decimal("1.0")
                penalty = sell_bias_penalty_factor * scaling
                
                buy_bias_mult += penalty
                self.logger.info(
                    f"[{symbol}] SIDE_BIAS_PENALTY (BUY): buy_share={float(buy_share):.2%} > "
                    f"target={float(target):.2%}, excess={float(excess):.2f}, "
                    f"ramp_scaling={float(scaling):.2f}, raising BUY threshold by {float(penalty):.1%}"
                )
        else:
            self.logger.debug(
                f"[{symbol}] SIDE_BIAS_SKIP: Not enough history ({total_count} < {min_intents}) in window ({bias_window_sec}s)"
            )


        thr_buy = signal_threshold * buy_bias_mult
        thr_sell = signal_threshold * sell_bias_mult

        side = ""
        if signal_score >= thr_buy:
            side = "buy"
        elif signal_score <= -thr_sell:
            side = "sell"
        else:
            reject_reason = (
                f"Neutral signal score {signal_score:.4f} "
                f"(thr_buy={thr_buy:.4f}, thr_sell={thr_sell:.4f})"
            )
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            msg = ("Trade intent for {} rejected: {} "
                   "(NRR: {})".format(symbol, reject_reason, normalized_reason))  # noqa: E501
            self.logger.info(msg)
            self.dlog.write(
                "DECISION_SKIP", rid, {
                    "symbol": symbol, "reason": "NEUTRAL_SIGNAL"}
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": "NONE",
                "nrr_code": None,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {
                    "reject_reason": "NEUTRAL_SIGNAL",
                    "signal_score": float(signal_score),
                    "threshold_base": float(signal_threshold),
                    "thr_buy": float(thr_buy),
                    "thr_sell": float(thr_sell),
                    "sell_share": float(sell_share) if sell_share is not None else None,
                    "buy_bias_mult": float(buy_bias_mult),
                    "sell_bias_mult": float(sell_bias_mult),
                }
            })

            self.clear_internal_state_for_symbol(symbol)
            return

        # FTR-07: Crowding Filter using DecisionContext (V2 Futures features)
        # Block entries into crowded positions to reduce adverse selection
        if side == "buy" and ctx.crowding.is_crowded_long:
            reject_reason = "crowding_filter_long_crowded"
            self.logger.warning(
                f"[{symbol}] Trade intent ({side}) rejected: funding rate indicates crowded LONG "
                f"(funding_normalized={ctx.crowding.funding_rate_normalized})"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {
                    "symbol": symbol, "reason": "CROWDING_FILTER", "side": side,
                    "funding_normalized": str(ctx.crowding.funding_rate_normalized)}
            )
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": side.upper(),
                "nrr_code": None,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "CROWDING_FILTER_LONG"}
            })
            self.clear_internal_state_for_symbol(symbol)
            return

        if side == "sell" and ctx.crowding.is_crowded_short:
            reject_reason = "crowding_filter_short_crowded"
            self.logger.warning(
                f"[{symbol}] Trade intent ({side}) rejected: funding rate indicates crowded SHORT "
                f"(funding_normalized={ctx.crowding.funding_rate_normalized})"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {
                    "symbol": symbol, "reason": "CROWDING_FILTER", "side": side,
                    "funding_normalized": str(ctx.crowding.funding_rate_normalized)}
            )
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": side.upper(),
                "nrr_code": None,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "CROWDING_FILTER_SHORT"}
            })
            self.clear_internal_state_for_symbol(symbol)
            return

        # FTR-07: Liquidity Filter using DecisionContext
        # Block trades in illiquid markets
        if ctx.liquidity.is_illiquid:
            reject_reason = "liquidity_filter_illiquid_market"
            self.logger.warning(
                f"[{symbol}] Trade intent ({side}) rejected: market is illiquid "
                f"(kappa={ctx.liquidity.liquidity_kappa}, spread={ctx.liquidity.effective_spread}bps)"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {
                    "symbol": symbol, "reason": "LIQUIDITY_FILTER", "side": side,
                    "kappa": str(ctx.liquidity.liquidity_kappa)}
            )
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": side.upper(),
                "nrr_code": None,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "LIQUIDITY_FILTER"}
            })
            self.clear_internal_state_for_symbol(symbol)
            return

        # Record this intent side for future bias tracking
        window_data[f"{'sells' if side == 'sell' else 'buys'}"].append(
            current_time)

        # Attach PSI snapshot and regime info for explainability
        if self.latest_regime:
            try:
                regime_conf_raw = regime["confidence"] if (isinstance(regime, dict) and "confidence" in regime) else 0
                psi_vector.update({
                    "regime": regime.get("regime") if regime else None,
                    "regime_conf": float(decimal.Decimal(str(regime_conf_raw)))
                })
            except Exception:
                pass
        self.dlog.write(
            "DECISION_EVAL",
            rid,
            {
                "symbol": symbol,
                "signal_score": float(signal_score),
                "signal_threshold": float(signal_threshold),
                "psi": psi_vector,
                "regime_threshold_factor": float(threshold_factor),
            },
        )

        if regime and regime.get("symbol") == symbol:
            current_regime = regime.get("regime")
            # Optional behavior FSM gate: allow entry only in IdleFlat
            if self._behavior_enabled:
                beh = self._behavior_state[symbol] if symbol in self._behavior_state else "IdleFlat"
                if beh != "IdleFlat":
                    reject_reason = f"behavior_gate_{beh}_disallows_entry"
                    normalized_reason = NormalizedRejectReasons.normalize(
                        reject_reason)
                    self.logger.info(
                        f"Trade intent for {symbol} ({side}) rejected: {reject_reason} (NRR: {normalized_reason})"
                    )
                    self.dlog.write(
                        "DECISION_SKIP", rid, {
                            "symbol": symbol, "reason": "BEHAVIOR_GATE", "behavior_state": beh}
                    )
                    self.clear_internal_state_for_symbol(symbol)
                    return
            if (current_regime == "TREND_UP" and side == "sell") or (
                current_regime == "TREND_DOWN" and side == "buy"
            ):
                reject_reason = (
                    f"rejected by regime filter (current regime: {current_regime})"
                )
                normalized_reason = NormalizedRejectReasons.normalize(
                    reject_reason)
                self.logger.info(
                    f"Trade intent for {symbol} ({side}) rejected: {reject_reason} (NRR: {normalized_reason})"
                )
                self.dlog.write(
                    "DECISION_SKIP", rid, {
                        "symbol": symbol, "reason": "REGIME_FILTER"}
                )

                # Log to OrderLoggerV1
                order_logger.write({
                    "rid": rid,
                    "event_type": "ORDER_REJECTED",
                    "symbol": symbol,
                    "side": side.upper(),
                    "nrr_code": None,
                    "why": reject_reason[:80],
                    "source_fsm": "DecisionMaking",
                    "metadata": {"reject_reason": "REGIME_FILTER", "regime": current_regime}
                })

                self.clear_internal_state_for_symbol(symbol)
                return

        price_ref_str = features_data.get("price")
        if not price_ref_str:
            reject_reason = "No valid price reference"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            self.logger.error(
                f"CRITICAL: {reject_reason} for {symbol}. Cannot make trading decision. (NRR: {normalized_reason})"
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": "NONE",
                "nrr_code": None,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "NO_PRICE_REFERENCE"}
            })

            self.clear_internal_state_for_symbol(symbol)
            return
        price_ref = decimal.Decimal(str(price_ref_str))

        # Prepare sizing meta: Kelly fraction (optional)
        sizing_meta: dict[str, Any] = {}
        # Kelly fraction (optional): derive from per-symbol config (must never block intent emission).
        kelly_cfg = getattr(self.config.strategies.aurora.decision, "kelly", None)
        if kelly_cfg is not None and getattr(kelly_cfg, "base_probability", None) is not None:
            try:
                base_p = decimal.Decimal(str(kelly_cfg.base_probability))
                cap = decimal.Decimal(str(kelly_cfg.kelly_cap))
                alpha = decimal.Decimal(str(kelly_cfg.kelly_alpha))

                aurora_assets = self.config.strategies.aurora.assets
                instr_cfg = aurora_assets.get(symbol) if aurora_assets else None
                if instr_cfg is None:
                    raise ConfigContractError(
                        path=f"strategies.aurora.assets.{symbol}",
                        why="Per-symbol config missing for Kelly sizing",
                        symbol=symbol,
                    )

                exit_cfg = getattr(instr_cfg, "exit", None)
                if exit_cfg is None or exit_cfg.sl_pct is None:
                    raise ConfigContractError(
                        path=f"strategies.aurora.assets.{symbol}.exit.sl_pct",
                        why="sl_pct required for Kelly sizing",
                        symbol=symbol,
                    )
                sl_pct = decimal.Decimal(str(exit_cfg.sl_pct))
                if sl_pct <= 0:
                    raise ConfigContractError(
                        path=f"strategies.aurora.assets.{symbol}.exit.sl_pct",
                        why="sl_pct invalid <= 0",
                        symbol=symbol,
                    )

                tp_cfg = getattr(instr_cfg, "take_profit", None)
                if tp_cfg is None or tp_cfg.tp_low_ratio is None:
                    raise ConfigContractError(
                        path=f"strategies.aurora.assets.{symbol}.take_profit.tp_low_ratio",
                        why="tp_low_ratio required for Kelly sizing",
                        symbol=symbol,
                    )
                payoff_r = decimal.Decimal(str(tp_cfg.tp_low_ratio))

                # Get Kelly bounds from config (FAIL-CLOSED: no hardcoded fallback)
                p_min = decimal.Decimal(str(kelly_cfg.p_min))
                p_max = decimal.Decimal(str(kelly_cfg.p_max))
                uplift_factor = decimal.Decimal(str(kelly_cfg.uplift_factor))

                score_01 = signal_score
                if score_01 < 0:
                    score_01 = decimal.Decimal("0")
                elif score_01 > 1:
                    score_01 = decimal.Decimal("1")

                # p = base_p + uplift_factor * (score - 0.5)
                p = base_p + (uplift_factor * (score_01 - decimal.Decimal("0.5")))
                p = max(decimal.Decimal("0"), min(decimal.Decimal("1"), p))
                p = max(p_min, min(p_max, p))

                full_kelly = decimal.Decimal("0") if payoff_r == 0 else p - (decimal.Decimal("1") - p) / payoff_r
                if full_kelly < 0:
                    full_kelly = decimal.Decimal("0")

                kelly_fraction = full_kelly * alpha
                kelly_fraction = max(decimal.Decimal("0"), min(cap, kelly_fraction))
                sizing_meta["kelly_fraction"] = kelly_fraction
            except Exception as e:
                self.logger.warning(f"Kelly calculation error: {e}")

        # FTR-07: Use DecisionContext for volatility state in sizing
        if ctx.volatility.is_high_volatility:
            sizing_meta["volatility_state"] = "HIGH_VOL"
        elif ctx.volatility.is_low_volatility:
            sizing_meta["volatility_state"] = "LOW_VOL"
        else:
            sizing_meta["volatility_state"] = "NORMAL"

        # Call sizing with optional meta
        context["_sizing_meta"] = sizing_meta
        qty, why_sizing, sizing_reject_reason, sizing_dbg = self._calculate_position_size(
            symbol, price_ref, side, context
        )
        why_chain.append(why_sizing)

        if not qty or qty <= 0:
            reject_reason = f"quantity is zero or negative. Why: {why_sizing}"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            self.logger.warning(
                f"Trade intent for {symbol} rejected: {reject_reason} (NRR: {normalized_reason})"
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": side.upper(),
                "quantity": float(qty) if qty else 0,
                "nrr_code": None,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {
                    "reject_reason": sizing_reject_reason or "ZERO_QUANTITY",
                    "why_sizing": why_sizing,
                    **(sizing_dbg or {}),
                },
            })

            self.clear_internal_state_for_symbol(symbol)
            return

        # Update QoS state for successful decision
        self._update_qos_state(symbol)

        self.dlog.write(
            "INTENT_PROPOSED",
            rid,
            {
                "symbol": symbol,
                "side": side,
                "qty": str(qty),
                "price_ref": str(price_ref),
            },
        )

        # ✅ EXPOSURE_CACHE_PRECHECK: Check exposure limits before proposing intent
        notional_usd = float(qty * price_ref)
        if not self._precheck_exposure_cache(symbol, side, notional_usd):
            reject_reason = "exposure_limit_exceeded_cache_precheck"
            normalized_reason = NormalizedRejectReasons.EXPOSURE_LIMIT_EXCEEDED
            self.logger.warning(
                f"[{symbol}] Trade intent rejected by exposure cache precheck: {reject_reason} (NRR: {normalized_reason})"
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": side.upper(),
                "quantity": float(qty),
                "nrr_code": "NRR-011",
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "EXPOSURE_CACHE_BLOCK", "notional_usd": notional_usd}
            })

            self.clear_internal_state_for_symbol(symbol)
            return

        # === Strict Sequential Contract (Commit 4) ===
        # Replaces ETAP4 logic. Handles Flattening, Anti-Pyramiding, and Flip Orchestration.
        pld_for_flip = {
            "symbol": symbol,
            "side": side,
            "rid": rid,
            "why_chain": why_chain,
            # Flip hysteresis (optional): pass score context if available in this scope.
            "signal_score": float(signal_score) if "signal_score" in locals() and signal_score is not None else None,
            "thr_buy": float(thr_buy) if "thr_buy" in locals() and thr_buy is not None else None,
            "thr_sell": float(thr_sell) if "thr_sell" in locals() and thr_sell is not None else None,
            # Pass full context for potential reconstruction
            "context_ref": "decision_making_aurora" 
        }
        flip_result = self._handle_flip_orchestration(
            symbol=symbol,
            intent_side=side,
            original_pld=pld_for_flip,
            source="aurora"
        )

        if flip_result:
            if flip_result == "ANTI_PYRAMIDING_BLOCK":
                reject_reason = f"anti_pyramiding_active_position_{symbol}_{side.lower()}"
                self.logger.info(
                    f"[{symbol}] DECISION NRR: {reject_reason} (existing position, blocking new entry)"
                )
                order_logger.write(
                    {
                        "rid": rid,
                        "event_type": "ORDER_REJECTED",
                        "symbol": symbol,
                        "side": side.upper(),
                        "quantity": float(qty),
                        "nrr_code": "NRR-020",
                        "why": reject_reason[:80],
                        "source_fsm": "DecisionMaking",
                        "metadata": {"reject_reason": "ANTI_PYRAMIDING_BLOCK"},
                    }
                )
            elif flip_result == "FLIP_CLOSE_PENDING":
                # Close intent and Deferral event already emitted by helper
                self.logger.info(f"[{symbol}] DECISION: Flip initiated. Open deferred.")
            elif flip_result == "NRR-FLIP-CLOSE-QTY-INVALID":
                # Fail-closed: CLOSE could not be emitted (invalid/missing qty in portfolio)
                self.logger.warning(
                    f"[{symbol}] DECISION: Flip fail-closed (invalid CLOSE qty). Open deferred."
                )
            elif flip_result == "FLIP_HYSTERESIS_BLOCK":
                reject_reason = "flip_hysteresis_block"
                order_logger.write(
                    {
                        "rid": rid,
                        "event_type": "ORDER_REJECTED",
                        "symbol": symbol,
                        "side": side.upper(),
                        "quantity": float(qty),
                        "nrr_code": None,
                        "why": reject_reason[:80],
                        "source_fsm": "DecisionMaking",
                        "metadata": {
                            "reject_reason": "FLIP_HYSTERESIS_BLOCK",
                            "signal_score": pld_for_flip.get("signal_score"),
                            "thr_buy": pld_for_flip.get("thr_buy"),
                            "thr_sell": pld_for_flip.get("thr_sell"),
                            "hysteresis_mult": float(getattr(self, "flip_hysteresis_mult", 1.0)),
                        },
                    }
                )
            elif flip_result == "NRR-PORTFOLIO-UNKNOWN":
                # Fail-closed
                pass

            self.clear_internal_state_for_symbol(symbol)
            return

        self._propose_trade_intent(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price_ref,
            why_chain=why_chain,
            rid=rid,
            reduce_only=False,
            strategy_id="aurora",  # CFG-STRATEGIES-SSOT-01: _make_decision_for_symbol is AURORA-only
            decision_ts_ms=int(current_features_ts) if current_features_ts else None,
        )

        # Update idempotency guard (SUCCESS)
        if current_features_ts > 0:
            self._last_successful_features_ts[symbol] = current_features_ts



# Verification Notes

## _check_and_trigger_decision_for_symbol
- **Status**: Removed.
- **Migration**:
  - **Warmup Guard**: Logic moved to `AuroraHandler._check_warmup`.
  - **Busy Guard**: Logic handled by `AuroraHandler` rate limiting and `DecisionMaking` QoS gateway.
  - **Idempotency**: Logic handled by `AuroraHandler` (checks timestamp against `last_decision_ts`).
  - **Trigger**: `AuroraHandler` subscribes directly to `EVT:FEATURES_CALCULATED` via `_AuroraHandlerWrapper`.

## _make_decision_for_symbol
- **Status**: Removed.
- **Migration**:
  - **Scoring**: Loop and normalization moved to `AuroraScoringKernel.compute`.
  - **Thresholds**: Regime and Side Bias thresholds moved to `AuroraScoringKernel.compute`.
  - **Gates**:
    - **Risk Gate**: Handled in `_on_strategy_signal_gateway` (checks `latest_risk`).
    - **QoS Gate**: Handled in `_on_strategy_signal_gateway` via `_qos_allow`.
    - **Exposure Gate**: Handled in `_on_strategy_signal_gateway` via `_precheck_exposure_cache`.
    - **Liquidity/Crowding**: Checked within `AuroraScoringKernel` (via features) or Gateway.
  - **Sizing**: Handled by `_on_strategy_signal_gateway` calling `_calculate_position_size`.
  - **Execution**: Intent emission via `_propose_trade_intent` called by `_on_strategy_signal_gateway`.

## Helper Methods (Retry Loop)
- **Status**: Removed.
- **Methods**: `_ensure_after_cooldown_retry`, `_retry_decision_after_cooldown`.
- **Migration**:
  - Replaced by `AuroraHandler` emitting `readiness=False` or Gateway emitting `INTENT_DEFERRED` with `next_allowed_ts`.
