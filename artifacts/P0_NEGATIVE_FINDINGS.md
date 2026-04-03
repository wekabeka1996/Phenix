# Negative Findings

This document explicitly lists where OBI/TFI are **NOT** live consumers and where claimed behavior was proven false by runtime code.

## 1. Aurora Strategy Core Does NOT Consume OBI/TFI for Scoring
- **Inspection:** `apps/reference/domains/decision_making/aurora_decision.py` and `quadratic_scoring_kernel.py`.
- **Verdict:** OBI and TFI are entirely absent from the `quadratic_scoring_kernel.py` math. The scoring relies purely on `linear_score` (from `pillar_sum` or upstream models) and `volatility`. `obi` is merely extracted from the `features` dictionary and passed transparently to `build_entry_plan` for offset calculation.

## 2. LLM Microstructure Does NOT Consume OBI/TFI
- **Inspection:** `apps/reference/domains/strategies/plugins/llm_microstructure.py` and `apps/reference/domains/shadow_telemetry/main_bridge.py`.
- **Verdict:** The `llm_microstructure` strategy handler is a pure sentinel (`_LlmMicrostructureSentinelHandler`). It performs no computation and reads no features. All decisions arrive asynchronously via the IPC bridge (`CMD:LLM_INTENT_SUBMIT_V1`), making the strategy effectively OBI/TFI-blind internally.

## 3. MD-AMR Does NOT Consume TFI
- **Inspection:** `apps/reference/domains/decision_making/md_amr_handler.py`.
- **Verdict:** While `obi_close` is extracted and passed to the entry plan, `tfi` is neither extracted, nor used as a veto, nor applied to any mathematical formula within the core strategy handler.

## 4. `trading.execution.orders.default_ttl_seconds` Is Often Ignored
- **Inspection:** `apps/reference/domains/execution_position/fsm.py` and config loaders.
- **Verdict:** The code frequently miswires this TTL, resolving from the wrong config namespace (`trading.orders` instead of `trading.execution.orders`), rendering the YAML tuning knob ineffective in those cases.

## 5. `hardening.ttl_config` Is Dead Config
- **Inspection:** Entire codebase search for `entry_place_ttl_ms`, `cancel_ttl_ms`.
- **Verdict:** These fields exist in the YAML structure but have absolutely zero wiring to any runtime execution loop. They provide a false sense of security regarding API request timeouts.