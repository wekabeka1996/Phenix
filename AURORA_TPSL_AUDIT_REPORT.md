# AURORA_TPSL_AUDIT_REPORT

## AGENT_REPORT_V1
**Date:** 2026-05-02
**Subject:** Aurora PRICE_CTX / ENTRY_PLAN / LOW_VOL RR Block Audit
**Verdict:** PARTIAL_CONFIRMATION_MORE_EVIDENCE_REQUIRED (Mechanism confirmed statically, but blocked by missing runtime logs and missing entry_plan configuration)

### 1. Facts (Proven from Code & Config)
- **Aurora explicitly emits `target_price` and `stop_price`:** 
  The Aurora runtime computes TP/SL geometry natively and attaches it to the `price_ctx` payload. 
  - File: `apps/reference/domains/strategies/runtimes/aurora/decision.py` (lines 1682-1684) 
  - Code: 
    ```python
    payload["price_ctx"]["stop_price"] = str(tpsl_result["stop_price"])
    payload["price_ctx"]["target_price"] = str(tpsl_result["target_price"])
    ```
- **Geometry calculation mode is `pct_mult`, not ATR:** 
  For example, `config/aurora/strategies/aurora.yaml` under `assets.BTCUSDT.exit.regime_tpsl` explicitly uses `mode: pct_mult`.
- **The ~0.5 RR ratio is explicitly configured in Aurora strategy configs:**
  - File: `config/aurora/strategies/aurora.yaml`
  - Values for `BTCUSDT` in `LOW_VOLATILITY`: `tp_mult: 0.5` and `sl_mult: 1.27`.
  - Values for `SOLUSDT` in `LOW_VOLATILITY`: `tp_mult: 1.35` and `sl_mult: 1.1`.
- **Strategy Primacy Precedence:**
  `DecisionMaking` gateway extracts geometry via `resolve_strategy_entry_prices()` in `apps/reference/domains/decision_making/gateway/strategy_gateway.py` (line 1151). If the strategy provides valid prices, they take precedence over `EntryPlan` calculation.
- **EntryPlan Config is NULL in `domains.yaml`:**
  In `config/aurora/domains.yaml`, the `entry_plan` configuration under `aurora.decision` is explicitly `null` (line 461).

### 2. Inferences
- The hypothesis that Aurora overrides `EntryPlan` via explicit payload geometry is structurally **TRUE**. 
- The poor RR geometry (0.5) is **NOT** a hardcoded bug in python, but rather the direct result of `tp_mult: 0.5` defined in `config/aurora/strategies/aurora.yaml`.
- Removing `target_price` and `stop_price` from the Aurora payload **would fail closed** today because `entry_plan: null` in `config/aurora/domains.yaml`. If Aurora drops geometry, `EntryPlan` has no ATR parameters to fall back on.

### 3. Assumptions
- We assume that `logs/` directory jsonl files (e.g. `order_log_v1.jsonl`, `shadow_critical_event_journal_v1.jsonl`) should contain NRR rejections, but `grep` yielded no hits for `NRR-062` or `LOW_VOL_COST_FLOOR_BLOCKED`.
- We assume that the ATR-based SSOT was meant to be configured in `domains.yaml` but was left out or moved to the individual strategy configs.

### 4. Unknowns
- **Runtime Reject Evidence:** Without logs matching `NRR-062` or `LOW_VOL_COST_FLOOR`, we cannot conclusively prove that the *majority* of production/shadow rejects are caused solely by this RR geometry rather than missing direction confidence (NRR-062) or other gate failures.

### 5. Log & Reject Evidence
- **Status:** NO RUNTIME EVIDENCE FOUND.
- A comprehensive search of `logs/**/*.jsonl` for `NRR-062`, `LOW_VOL_COST_FLOOR_BLOCKED`, `LOW_VOLATILITY`, and `cost_floor` produced no exact match samples. 
- Due to the absence of empirical log data, we cannot fulfill the requirement to "Produce sample rows with rid, actual_tp_bps, actual_sl_bps, etc." 

### 6. Patch Proposal & Conclusion
**Hypothesis Status:** Partially Confirmed. The override mechanism is structurally proven. However, the proposed patch (dropping TP/SL from Aurora) is **DANGEROUS** and must be rejected until `domains.yaml` is updated to include a valid `entry_plan` configuration.

**Option B is recommended (If proceeding):**
- **Plan:** Introduce a config flag in `DecisionMaking` config (e.g. `strategy_primacy: false` under `entry_plan`) so that the gateway can enforce `EntryPlan` as the SSOT, rather than modifying the Aurora source code directly. But first, `config/aurora/domains.yaml` must be given a valid `entry_plan` config block with `tp_k_atr` and `sl_k_atr`.

**Required Tests (Before Implementation):**
- `tests/domains/decision_making/gateway/test_strategy_gateway.py`: Ensure that when `EntryPlan` is configured and `strategy_primacy=False`, the gateway ignores `price_ctx` from Aurora.
- `tests/domains/strategies/runtimes/aurora/test_tpsl.py`: Ensure Aurora skips geometry injection if disabled via config.

---
**END OF REPORT**
