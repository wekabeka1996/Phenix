# R7K Gap List

1. The restarted live app slice did not contain a non-zero position, so a real live portfolio snapshot with non-null `markPrice` was not observed directly in that slice.
2. The current core log history still contains `LOOP_DETECTED: EVT:MARKET_TICK_RECEIVED` warnings. They were present before this enablement, but they remain a residual runtime concern.
3. The live app log slice did not surface an explicit enablement info line, so the listener-registration proof comes from the bounded in-process smoke rather than from a live log line.
