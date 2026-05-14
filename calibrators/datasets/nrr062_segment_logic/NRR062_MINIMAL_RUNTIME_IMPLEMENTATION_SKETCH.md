# NRR062_MINIMAL_RUNTIME_IMPLEMENTATION_SKETCH

## likely_runtime_location
- apps/reference/domains/decision_making/gates/low_vol_cost_floor.py would be the likely enforcement surface because it already owns LOW_VOL candidate blocking and exposes selected_source, selected_scale, threshold_family, side, regime, and violation metadata.
- apps/reference/config/domains/decision_making.py would be the contract review surface only if an operator later permits explicit config/schema changes. This package does not touch that model.

## existing_fields_needed
- nrr_code
- regime
- side / position_side
- selected_source
- selected_scale
- threshold_family
- violations
- gross_tp_bps
- required_gross_tp_bps_floor
- min_rr
- replay outcome proxy artifacts for offline proof only

## business_rule_risk
- Hardcoding segment logic directly in runtime would be a business-rule risk because SELL-only + direction-only + raw-signal-only selection is not currently expressible in YAML/Pydantic and would create hidden operator policy outside SSOT config.
- Any future runtime implementation should therefore be explicit, isolated, and operator-approved rather than smuggled in as an implicit branch inside the live gate.

## preferred_implementation_mode
- 2. testnet-only explicit operator override

## rollback
- If a future explicit implementation is attempted, keep it behind a testnet-only operator gate and remove that gate in one revertable change if BUY losses, dual-failure admissions, or timeout concentration worsen.
- Rollback path should be a single code-path disablement, not a threshold rewrite.

## required_tests
- unit tests for side segmentation, dual-failure exclusion, and raw-signal family matching
- import-boundary regression so apps/reference runtime still does not import calibrators
- offline replay regression showing candidate metrics remain stable on the same 153-row cohort
- future testnet-only integration tests before any operator rollout
