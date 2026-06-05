# Regime-Based Trade Lockout — Corrected Implementation Plan

Block new entries for a symbol after the first terminal losing trade **opened in the current regime epoch**. Reset the block only upon a regime change.

> [!CAUTION]
> This is a corrected plan. The V1 plan had a **causal defect**: it latched on close-time regime, which would poison a new regime with losses from trades opened in a previous regime. This plan latches on **entry-time regime** using `structural_regime_ref` as the epoch identifier.

---

## Evidence Summary

### FACTS

| # | Finding | Source |
|---|---------|--------|
| F1 | At order placement, `open_executor.py` stamps `{regime, regime_confidence, regime_provenance}` from `decision.pld` into `_open_regime_by_symbol[symbol]`. | [open_executor.py:L1025–L1042](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/open_executor.py#L1025-L1042) |
| F2 | On terminal close, `_open_regime_by_symbol.pop(sym, {})` returns the entry-time regime snapshot into `_pos_close_regime`, used only for a log line, then **discarded**. | [event_handlers.py:L243–L271](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/event_handlers.py#L243-L271) |
| F3 | `regime_provenance.detector_event.structural_regime_ref` has format `"structural:SYMBOL:TS_MS"` — a monotonic, per-transition epoch identifier already present in the regime provenance dict. | [runtime_regime_layers.py:L86–L87](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_regime_layers.py#L86-L87) |
| F4 | DM caches `structural_regime_ref` in `_per_symbol_regimes[symbol]["structural_regime_ref"]` on every `EVT:REGIME_DETECTED`. | [event_handlers.py:L554](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/event_handlers.py#L554) |
| F5 | `changed = (last_regime is None) or (last_regime != stable_regime)` — the detector only sets `changed=True` on stable label transitions, producing a new `structural_regime_ref` each time. | [regime_detector.py:L834–L835](file:///c:/Users/user/Music/Phenix/apps/reference/domains/regime_detector/regime_detector.py#L834-L835) |
| F6 | `_open_strategy_by_symbol.pop(sym, None)` at L261 **discards** the strategy_id. Currently not captured. | [event_handlers.py:L261](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/event_handlers.py#L261) |
| F7 | `EVT:POSITION_CLOSED` exists in verb_registry (`owner: unknown`, `status: experimental`, `schema: null`). Not emitted as a bus event. | [verb_registry_v1.yaml:L390–L394](file:///c:/Users/user/Music/Phenix/apps/reference/dictionaries/verb_registry_v1.yaml#L390-L394) |
| F8 | EP `domain_dict.json` does NOT list `EVT:POSITION_CLOSED` in exports. DM `domain_dict.json` does NOT list it in imports. Neocortex `domain.yaml` already declares it as a required import. | [EP domain_dict.json](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/domain_dict.json), [DM domain_dict.json](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/domain_dict.json), [neocortex domain.yaml:L258](file:///c:/Users/user/Music/Phenix/apps/reference/domains/neocortex/domain.yaml#L258) |
| F9 | Next available NRR code is `NRR-061`. | [normalized_reject_reasons.py:L108](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/normalized_reject_reasons.py#L108) |
| F10 | `risk_skew_guard` pattern (`dm.symbol_states[symbol]`, checked at L517–L550 in gateway) is the canonical template. | [strategy_gateway.py:L517–L550](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/strategy_gateway.py#L517-L550) |
| F11 | Bus listener registration is at `decision_making.py:L275–L285` via `self.fsm.listen(...)`. | [decision_making.py:L275–L285](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/decision_making.py#L275-L285) |

### UNKNOWNS

| # | Unknown | Decision |
|---|---------|----------|
| U1 | Per-symbol vs per-symbol-per-strategy scope | **Per-symbol** (user confirmed). Implementation keyed by symbol only, but `strategy_id` in event enables future `scope: symbol_strategy`. |

---

## Proposed Changes

### Component 1: EP — Capture strategy_id and forward entry-regime into `EVT:POSITION_CLOSED`

#### [MODIFY] [event_handlers.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/event_handlers.py)

**Change 1a** (L261): Capture `_open_strategy_by_symbol.pop()` result into a local variable:

```diff
-                    try:
-                        self._fsm._open_strategy_by_symbol.pop(sym, None)
-                    except Exception:
-                        pass
+                    _open_strategy_id = None
+                    try:
+                        _open_strategy_id = self._fsm._open_strategy_by_symbol.pop(sym, None)
+                    except Exception:
+                        pass
```

**Change 1b** (after L336, after `order_logger.write`): Emit the bus event with causal fields:

```python
                        # EVT:POSITION_CLOSED bus emission (additive, best-effort)
                        try:
                            _entry_structural_ref = None
                            _prov = _pos_close_regime.get("regime_provenance")
                            if isinstance(_prov, dict):
                                _det = _prov.get("detector_event")
                                if isinstance(_det, dict):
                                    _entry_structural_ref = _det.get("structural_regime_ref")

                            from vfoundation.core.fsm_emit_compat import Message as _Msg, emit_compat as _emit
                            _pc_msg = _Msg(
                                op="EVT",
                                verb="POSITION_CLOSED",
                                src="execution_position",
                                dst="decision_making",
                                rid=str(rid_for_sym) if 'rid_for_sym' in locals() and rid_for_sym else f"position_close:{sym}:{int(closed_at * 1000)}",
                                pld={
                                    # Identity
                                    "symbol": sym,
                                    "lifecycle_id": self._fsm._last_lifecycle_ikey_by_symbol.get(sym, ""),
                                    "trade_id": self._fsm._last_trade_id_by_symbol.get(sym, ""),
                                    "rid": str(rid_for_sym) if 'rid_for_sym' in locals() and rid_for_sym else "",
                                    # Trade metadata
                                    "side": self._fsm._last_entry_side_by_symbol.get(sym, "N/A"),
                                    "close_reason": close_reason,
                                    "close_ts_ms": int(closed_at * 1000),
                                    # PnL truth
                                    "realized_pnl": pos_pnl,
                                    "realized_pnl_net": pos_pnl - _pos_fees,
                                    "fees": _pos_fees,
                                    # Causal regime fields (from entry time)
                                    "entry_regime_label": _pos_close_regime.get("regime"),
                                    "entry_regime_structural_ref": _entry_structural_ref,
                                    "entry_regime_confidence": _pos_close_regime.get("regime_confidence"),
                                    # Strategy attribution
                                    "strategy_id": str(_open_strategy_id) if _open_strategy_id else None,
                                },
                                why="terminal_position_closed",
                            )
                            _loop = self._fsm._get_async_loop()
                            if _loop:
                                self._fsm._submit_async(_emit(self._fsm.fsm, _pc_msg, logger=LOG), _loop)
                            else:
                                LOG.debug("No event loop for EVT:POSITION_CLOSED emission")
                        except Exception as _pc_e:
                            LOG.warning(f"Failed to emit EVT:POSITION_CLOSED: {_pc_e}")
```

> [!NOTE]
> This is purely a **forwarding change**: the data already exists in `_pos_close_regime` (popped at L243) and `_open_strategy_id` (captured above). No new state, no new stamps. The emit is best-effort wrapped in try/except and placed **after** the order_logger write to preserve existing behavior.

---

### Component 2: Registry & Schema

#### [MODIFY] [verb_registry_v1.yaml](file:///c:/Users/user/Music/Phenix/apps/reference/dictionaries/verb_registry_v1.yaml)

Update L390–L394:
```yaml
- op: EVT
  verb: POSITION_CLOSED
  owner: execution_position
  status: active
  schema: apps/reference/domains/execution_position/schemas/position_closed_v1.json
  since: '2026-01-08'
  note: "Terminal full-close event with entry-regime causal fields. Consumed by decision_making (loss embargo) and neocortex (reward)."
```

#### [NEW] [position_closed_v1.json](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/schemas/position_closed_v1.json)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "EVT:POSITION_CLOSED",
  "description": "Emitted on terminal full position close (prev_amt >= epsilon, now_amt < epsilon).",
  "type": "object",
  "required": ["symbol", "close_reason", "realized_pnl_net", "close_ts_ms"],
  "properties": {
    "symbol": { "type": "string" },
    "lifecycle_id": { "type": "string" },
    "trade_id": { "type": "string" },
    "rid": { "type": "string" },
    "side": { "type": "string", "enum": ["BUY", "SELL", "N/A"] },
    "close_reason": { "type": "string" },
    "close_ts_ms": { "type": "integer" },
    "realized_pnl": { "type": "number" },
    "realized_pnl_net": { "type": "number" },
    "fees": { "type": "number" },
    "entry_regime_label": { "type": ["string", "null"] },
    "entry_regime_structural_ref": { "type": ["string", "null"] },
    "entry_regime_confidence": { "type": ["string", "number", "null"] },
    "strategy_id": { "type": ["string", "null"] }
  }
}
```

#### [MODIFY] [EP domain_dict.json](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/domain_dict.json)

Add to `exports`:
```json
{"event_name": "EVT:POSITION_CLOSED", "target_domains": ["decision_making", "neocortex", "monitoring"]}
```

#### [MODIFY] [DM domain_dict.json](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/domain_dict.json)

Add to `imports`:
```json
{"event_name": "EVT:POSITION_CLOSED", "source_domain": "execution_position"}
```

---

### Component 3: DM — Loss embargo latch + regime reset

#### [MODIFY] [event_handlers.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/event_handlers.py)

**3a. New method `on_position_closed()`**: Latch on entry-regime causality.

```python
def on_position_closed(self, event: Message) -> None:
    """Latch regime loss embargo on terminal losing trade within current regime epoch."""
    pld = event.pld or {}
    symbol = pld.get("symbol")
    if not symbol:
        return

    # PnL truth
    realized_pnl_net = pld.get("realized_pnl_net")
    if realized_pnl_net is None:
        return
    try:
        net = float(realized_pnl_net)
    except (TypeError, ValueError):
        return

    # Config gate
    try:
        embargo_cfg = self._config.domains.decision_making.regime_loss_embargo
        if not embargo_cfg.enabled:
            return
    except Exception:
        return  # No config = feature disabled

    # Threshold check: skip if loss is below configured epsilon
    min_loss = float(getattr(embargo_cfg, "min_loss_threshold_net", 0.0))
    if net >= -abs(min_loss):
        return  # Winning, breakeven, or below epsilon — no embargo

    # Causal regime check: does this loss belong to the CURRENT regime epoch?
    entry_structural_ref = pld.get("entry_regime_structural_ref")
    current_regime_data = self._per_symbol_regimes.get(symbol) or {}
    current_structural_ref = current_regime_data.get("structural_regime_ref")

    if entry_structural_ref is None or current_structural_ref is None:
        self.logger.warning(
            "[%s] REGIME_LOSS_EMBARGO: skipped — missing structural_regime_ref "
            "(entry=%s, current=%s)", symbol, entry_structural_ref, current_structural_ref,
        )
        return

    if entry_structural_ref != current_structural_ref:
        # Loss from a previous regime epoch — do NOT poison current regime
        self.logger.info(
            "[%s] REGIME_LOSS_EMBARGO: skipped — loss belongs to previous regime epoch "
            "(entry_ref=%s != current_ref=%s)", symbol, entry_structural_ref, current_structural_ref,
        )
        return

    # Check if already latched
    ss = self._symbol_states[symbol]
    embargo = ss.get("regime_loss_embargo") or {}
    if embargo.get("latched") and embargo.get("structural_ref") == current_structural_ref:
        return  # Already latched for this epoch

    # LATCH
    mode = str(getattr(embargo_cfg, "mode", "shadow"))
    ss["regime_loss_embargo"] = {
        "latched": True,
        "structural_ref": current_structural_ref,
        "regime_label": current_regime_data.get("regime"),
        "latched_ts_ms": self._clock.now_ms(),
        "trigger_pnl_net": net,
        "trigger_close_reason": pld.get("close_reason"),
        "trigger_strategy_id": pld.get("strategy_id"),
        "mode": mode,
    }
    self.logger.warning(
        "[%s] REGIME_LOSS_EMBARGO: LATCHED (mode=%s) pnl_net=%.4f regime=%s "
        "structural_ref=%s strategy=%s close_reason=%s",
        symbol, mode, net,
        current_regime_data.get("regime"), current_structural_ref,
        pld.get("strategy_id"), pld.get("close_reason"),
    )
```

**3b. Reset in `on_regime()`**: After `_per_symbol_regimes[symbol]` is updated and `_handle_regime_flip()` is called (L586–L587), add:

```python
                # Regime loss embargo: reset on epoch change
                if event.pld.get("changed"):
                    _embargo = self._symbol_states.get(symbol, {}).get("regime_loss_embargo")
                    if _embargo and _embargo.get("latched"):
                        self.logger.info(
                            "[%s] REGIME_LOSS_EMBARGO: RESET on regime change "
                            "old_ref=%s -> new_ref=%s (was regime=%s)",
                            symbol, _embargo.get("structural_ref"),
                            detector_structural_ref,
                            _embargo.get("regime_label"),
                        )
                        self._symbol_states[symbol]["regime_loss_embargo"] = {
                            "latched": False,
                            "structural_ref": detector_structural_ref,
                            "regime_label": regime_val,
                            "reset_ts_ms": cache_write_ts_ms,
                        }
```

> [!IMPORTANT]
> The reset keys on `changed == True` (only true on stable label transitions) AND uses `structural_regime_ref` comparison, not label comparison. This prevents jitter and distinguishes same-label consecutive epochs.

---

### Component 4: DM — Listener registration

#### [MODIFY] [decision_making.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/decision_making.py)

After L285 (`EVT:SYSTEM_STRESS_STATE_UPDATED` listener):

```python
        # Regime loss embargo: terminal position close listener
        self.fsm.listen("EVT:POSITION_CLOSED", self._evt.on_position_closed)
```

---

### Component 5: DM — Gate 0.7 in StrategyGateway

#### [MODIFY] [strategy_gateway.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/strategy_gateway.py)

Insert after L550 (end of `risk_skew_guard` until_refresh check), before L552 (`=== GATE 1: RISK GATE ===`):

```python
            # === GATE 0.7: REGIME LOSS EMBARGO ===
            try:
                _embargo_cfg = getattr(
                    getattr(self.config.domains, "decision_making", None),
                    "regime_loss_embargo", None)
                if _embargo_cfg and _embargo_cfg.enabled:
                    _embargo = dm.symbol_states.get(symbol, {}).get("regime_loss_embargo") or {}
                    if _embargo.get("latched"):
                        _embargo_ref = _embargo.get("structural_ref")
                        _current_ref = (dm._per_symbol_regimes.get(symbol) or {}).get("structural_regime_ref")
                        # Verify still in the same regime epoch (defense-in-depth;
                        # regime change should have already cleared the latch via on_regime)
                        if _current_ref == _embargo_ref or _current_ref is None:
                            _embargo_mode = str(_embargo.get("mode", "enforce"))
                            if _embargo_mode == "shadow":
                                self.logger.warning(
                                    "[%s] REGIME_LOSS_EMBARGO: SHADOW would reject (regime=%s ref=%s pnl=%.4f)",
                                    symbol, _embargo.get("regime_label"),
                                    _embargo_ref, _embargo.get("trigger_pnl_net", 0),
                                )
                            else:
                                self._reject(
                                    symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
                                    reason_code=NormalizedRejectReasons.REGIME_LOSS_EMBARGO,
                                    reason="EMBARGO",
                                    context=f"strategy_signal_gateway:regime_loss_embargo:{_embargo.get('regime_label')}",
                                    why_chain=(why_chain or []) + [
                                        "regime_loss_embargo",
                                        f"embargo_regime={_embargo.get('regime_label')}",
                                        f"structural_ref={_embargo_ref}",
                                        f"trigger_pnl_net={_embargo.get('trigger_pnl_net')}",
                                    ],
                                    details={
                                        "embargo_regime": _embargo.get("regime_label"),
                                        "structural_ref": _embargo_ref,
                                        "trigger_pnl_net": _embargo.get("trigger_pnl_net"),
                                        "trigger_close_reason": _embargo.get("trigger_close_reason"),
                                        "trigger_strategy_id": _embargo.get("trigger_strategy_id"),
                                        "latched_ts_ms": _embargo.get("latched_ts_ms"),
                                    },
                                )
                                return
                        else:
                            # Defense-in-depth: regime changed but latch wasn't cleared yet
                            dm.symbol_states[symbol]["regime_loss_embargo"] = {
                                "latched": False,
                                "structural_ref": str(_current_ref),
                                "regime_label": (dm._per_symbol_regimes.get(symbol) or {}).get("regime"),
                                "reset_ts_ms": self._clock.now_ms(),
                            }
            except Exception as _emb_e:
                self.logger.debug("REGIME_LOSS_EMBARGO gate error: %s", _emb_e, exc_info=True)
```

---

### Component 6: NRR + Config

#### [MODIFY] [normalized_reject_reasons.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/normalized_reject_reasons.py)

After L108 (`MICROSTRUCTURE_VETO = "NRR-060"`):
```python
    # Regime Loss Embargo: terminal loss in current regime epoch blocks new entries
    REGIME_LOSS_EMBARGO = "NRR-061"
```

Add to `PATTERNS` dict:
```python
        REGIME_LOSS_EMBARGO: [
            r"regime.*loss.*embargo",
            r"loss.*embargo.*regime",
        ],
```

Add to `get_description()`:
```python
            cls.REGIME_LOSS_EMBARGO: "New entries blocked after terminal loss in current regime epoch (resets on regime change)",
```

#### [MODIFY] [config_models.py](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py)

Add to `DecisionMakingConfig`:
```python
class RegimeLossEmbargoConfig(BaseModel):
    enabled: bool = False                # Master kill switch
    mode: str = "shadow"                 # "shadow" (log only) | "enforce" (reject)
    min_loss_threshold_net: float = 0.01 # Minimum net loss (USD) to trigger
    scope: str = "symbol"                # "symbol" (all strategies) — future: "symbol_strategy"
    apply_to_strategies: list[str] = []  # Empty = all strategies

regime_loss_embargo: RegimeLossEmbargoConfig = RegimeLossEmbargoConfig()
```

---

## Verification Plan

### Automated Tests

| # | Test | Assertion |
|---|------|-----------|
| T1 | `on_position_closed` with `realized_pnl_net < -min_threshold` and `entry_regime_structural_ref == current_ref` | `regime_loss_embargo.latched == True` |
| T2 | `on_position_closed` with `realized_pnl_net >= 0` | Embargo NOT set |
| T3 | `on_position_closed` with `entry_regime_structural_ref != current_ref` | Embargo NOT set — loss belongs to previous epoch |
| T4 | `on_position_closed` with `net < 0` but `abs(net) < min_loss_threshold_net` | Embargo NOT set — below epsilon |
| T5 | Set embargo, then fire `on_regime` with `changed=True` | `latched == False`, `structural_ref` updated |
| T6 | Set embargo, then fire `on_regime` with `changed=False` | `latched == True` (unchanged) |
| T7 | Set embargo (mode=enforce), route signal through `process_signal()` | `TRADE_INTENT_REJECTED` with `NRR-061` |
| T8 | Set embargo (mode=shadow), route signal through `process_signal()` | Signal **passes through**, warning log emitted |
| T9 | Set embargo for ref X, but `_per_symbol_regimes` shows ref Y | Gate clears stale latch, signal passes through |

### Manual Verification

1. Deploy to testnet with `enabled: true`, `mode: shadow`
2. Monitor logs for `REGIME_LOSS_EMBARGO: LATCHED` and `REGIME_LOSS_EMBARGO: RESET`
3. Cross-reference with order_logger to confirm `entry_regime_structural_ref` matches intent regime
4. After 24h with zero false positives, promote to `mode: enforce`
