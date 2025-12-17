# TASK19 Root-Level Extra Keys (Forensic)

Source scan: current config loader merges `system.yaml`, `trading.yaml`, and `regime.yaml` at root. With `extra='allow'`, the following non-schema keys land at root and forced permissive mode.

| Key | Source file | Why it exists |
| --- | --- | --- |
| config_version | system.yaml / regime.yaml | Version stamp for configs; not modeled in AuroraConfig. |
| sequential_tests | system.yaml | Parameters for Wald/GLR sequential tests (diagnostic/experiments). |
| risk_core | system.yaml | Core risk tuning block (CVaR thresholds, stress scenarios). |
| kelly | system.yaml | Kelly sizing metadata (separate from trading.decision.kelly). |
| calibrator | system.yaml | Calibrator state-store settings (sqlite path/retention). |
| hawkes | system.yaml | Hawkes process tuning (eta/kernel params). |
| hotreload_whitelist | system.yaml | Allowlist of hot-reloadable paths. |
| hardening | system.yaml | Reliability/WAL integrity settings. |
| position_tracking | system.yaml | Portfolio freshness TTL for bridge checks. |
| guardian | trading.yaml (root) | OrderGuardian knobs placed at root instead of execution.order_guardian. |
| _config_name / _config_dir | Injected by config_loader | Runtime diagnostic metadata added after validation. |

Resolution path: move all service/meta blocks under `system_meta` (typed) and remap `guardian` into `execution.order_guardian`; reject `_config_*` keys at loader; enable `extra='forbid'` on AuroraConfig root.
