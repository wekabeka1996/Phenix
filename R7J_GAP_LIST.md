# R7J Gap List

- No captured log line shows PositionTracking actually handling EVT:MARKET_TICK_RECEIVED in the runtime slice. The code path exists, but the evidence is indirect because the listener gate is disabled.
- The runtime has repeated EVT:MARKET_TICK_RECEIVED loop-detection warnings in [logs/aurora_core.log.9](logs/aurora_core.log.9#L1254), so the safe follow-up is a narrow smoke test before enabling the subscription in the live profile.
- PORTFOLIO_STATE_UPDATED and EXPOSURE_SUMMARY_UPDATED are not the same carrier. The registry and docs still place portfolio snapshots in position_tracking, but the execution-position journal also carries portfolio_state, so the carrier split should be audited separately if downstream consumers are reading the wrong verb.
