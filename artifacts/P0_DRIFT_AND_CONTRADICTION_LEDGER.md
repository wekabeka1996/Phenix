# Drift and Contradiction Ledger

| Claim Source | Claim | Actual Runtime Truth | Verdict |
|---|---|---|---|
| `system_passport.md`, `system.yaml` | `system.market_data.tick_ttl_ms` handles tick freshness | `regime_detector.py` early-returns on `tf_sec == 0` before TTL checks. Tick TTL is practically inert in bar mode. | **NOT WIRED (INERT)** |
| `system_passport.md`, `system.yaml` | `hardening.ttl_config.entry_place_ttl_ms`, `bracket_place_ttl_ms`, `cancel_ttl_ms` govern API requests | Not read anywhere in the Python execution runtime. | **DECLARED-BUT-NOT-USED** |
| `trading_passport.md`, `trading.yaml` | `trading.execution.exposure.pending_ttl_sec` and `post_fill_hold_ttl_sec` control exposure guards | ExposureGuard reads from `domains.execution_position.exposure_guard`, making the `trading.*` equivalents dead inert knobs. | **DOC DRIFT / INERT KNOB** |
| `regime_detector.py` | `bar_ttl_ms` must be configured | Code uses `getattr(sys_md, "bar_ttl_ms", 10000)`. If missing, silently falls back to 10s. | **HIDDEN FALLBACK** |
| `trading_passport.md` | `trading.execution.orders.default_ttl_seconds` defines order TTL | `ExecPosFSM` miswired to read `trading.orders.default_ttl_seconds` or `root` namespace. | **MISWIRED** |
| `aurora_math_passport.md` | "Current global essentials are `obi`, `delta_price`, `macro_resid`" | `obi` is only extracted and passed to `entry_plan.py`. It does NOT feed the actual quadratic scoring kernel math. | **DOC DRIFT** |
| `mean_reversion_state_machine_passport.md` | `obi_confirm_enabled` controls if OBI is consulted | Correct, but OBI is never the sole driver; TFI missing fails closed entirely. This is correctly aligned but extremely rigid. | **ACTIVE / CORRECT** |
| `llm_microstructure` configuration | Implies standalone trading logic with strategy thresholds | Strategy is entirely bridge-driven. All intents come from IPC. Code is a Sentinel `_LlmMicrostructureSentinelHandler`. | **DOC DRIFT (Behavior mismatch)** |