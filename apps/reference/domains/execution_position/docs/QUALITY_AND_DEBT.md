# Execution Position Quality and Debt

## Hotspots

- `fsm.py` remains a large root orchestration anchor. That is an accepted
  architectural constraint, not pending Phase 8 migration work.
- `support/utils_event_bus.py` still subclasses a generic LocalBus and allows
  synchronous publish. Refactoring it to strict async queues is postponed.

## Technical Debt Roadmap

| Component | Debt Type | Priority |
| :--- | :--- | :--- |
| `state/truth_hardening.py` | Excessive duplicate fill hardening | Medium |
| `adapters/ledger_store_adapter.py` | Sync disk I/O in path of event dispatch | High |
| `adapters/watchdog.py` | Polling latency on order cancellation | Low |
| `support/utils_event_bus.py` | Convert to strict async write queue in future runtime work | Low |

## Notes

- Compatibility stubs from Phase 8 remain in place by design.
- Root anchors (`fsm.py`, `contracts.py`, `reasons.py`, `utils.py`) are
  intentional public API or facade surfaces.

### Phase 9V Blocker Provenance
- Compatibility stubs from Phase 8 are retained intentionally as facades.
- No ordinary runtime, test, or documentation old-path debt remains for `execution_position`.
- Remaining blockers for removing kept candidate stubs are exclusively classified as root-anchor dependencies (`fsm.py`), major release-boundary policy holds, operator-confirmation debt, or historical-record-only citations.