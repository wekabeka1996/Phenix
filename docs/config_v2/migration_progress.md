# Config v2 Migration Progress

| Domain     | Sections                     | Status                        | Notes                    |
|------------|------------------------------|-------------------------------|--------------------------|
| execution  | exposure, manage, brackets   | v2 primary, legacy fallback   | TASK 4.1                |
| risk       | daily_limits                 | v2 primary, legacy fallback   | TASK 4.4                |
| decision     | thresholds, qos     | v2 primary, legacy fallback   | TASK 4.6                |
| sizing     | defaults, symbols, regimes     | v2 primary, legacy fallback   | TASK 4.5                |
| features   | global, windows, features, macro_sync | v2 primary, legacy fallback   | TASK 5.4                |
| regimes    | detector, regimes, hotreload   | v2 primary, legacy fallback   | TASK 5.3 |
| modes      | profiles, domain_modes       | v2 primary, legacy fallback   | TASK 5.6 |
| tca        | ...                          | not migrated                  |                          |
| instruments| profiles, overrides          | v2 primary, legacy fallback   | TASK 4.3                |
| validator | cross-domain invariants       | implemented, tests green      | TASK 5.1                |
| meta-configs | core.yaml, symbols.yaml, modes.yaml | triaged: archive core/symbols, keep modes | TASK 5.5                |
| tests      | test_dynamic_integration.py + helpers (signals, tidy gate, resolve, config inventory) | migrated to AuroraConfig/config v2 resolvers; no legacy trading.yaml | TASK 5.8 |

> 2025-11-15 (TASK 7.6): instrument profiles/enforcers підтягнули `limits.*` overrides (max_leverage/max_position_size/min_*), `resolve_instrument_profile` завжди віддає `source="config_v2"`, валідатор блокує топ-рівневі dead-fields у overrides.
>
> 2025-11-15 (TASK 7.7): legacy `config/aurora/{system,trading}.yaml` переміщено до `config/archive/v1/`, AuroraConfig/tests більше не звертаються до них; SSOT для рантайму та тестів — `config/domains/*.yaml`, `instruments.yaml`, `overrides.yaml`, `modes.yaml`.
