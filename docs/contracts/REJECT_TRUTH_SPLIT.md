# Reject Truth Split

`TRADE_INTENT_REJECTED` currently has four shaping paths in the workspace. This
surface is frozen as-is for Package 1; unification is deferred to a dedicated
future package.

| Path | Classification | Evidence |
| --- | --- | --- |
| `apps/reference/domains/decision_making/intent_emitter.py` | canonical | WAL + event emission at lines `194-210` |
| `apps/reference/domains/decision_making/aurora_handler.py` | handler-local-WAL | direct `write_trade_intent_rejected(...)` calls at lines `833-903` |
| `apps/reference/domains/decision_making/mean_reversion_handler.py` | handler-local-WAL | direct `write_trade_intent_rejected(...)` calls at lines `1742-2000` |
| `apps/reference/domains/decision_making/md_amr_handler.py` | handler-local-emit | direct `self.fsm.emit("EVT:TRADE_INTENT_REJECTED", ...)` calls at lines `735-738` and `1178-1210` |

Status: frozen as-is; unification deferred to a dedicated future package.
