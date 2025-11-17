# Phenix Codebase Audit Verification Log

Status: Ongoing (phase: deep cross-domain evidence collection)
Created: 2025-11-12T00:00:00Z
Maintainer: Audit/Architecture WG

## 1. Scope & Method
Objectives:
- Verify prior external audit claims against current repository state.
- Extend analysis: causal chains, cross-domain impact (latency, correctness, risk controls, DR resilience).
- Produce actionable remediation roadmap (additive-only, non-breaking, contract-first).
Evidence Collection:
- Direct file reads (apps/reference/*, vfoundation/*).
- Pattern searches (price sourcing, retry, broad exceptions, reconnection logic).
- Classification per issue: Confirmed / Refined / False / Pending.

## 2. Legend
Status Codes: CONFIRMED | REFINED | PARTIAL | FALSE | PENDING
Risk Levels: H (High), M (Medium), L (Low)
Impact Domains: LAT (Latency), COR (Correctness), RSK (Risk Mgmt), DR (Disaster Recovery), SEC (Security), OPS (Operability)

## 3. Summary Matrix
| Issue | Status | Risk | Impact | Notes |
|-------|--------|------|--------|-------|
| Global execution_position bridge via module-level vars in `main.py` | CONFIRMED | H | COR, LAT | Globals: `fsm`, `execution_position`, `_bridge_instance`; handlers dispatch through them; impedes isolation/testing & multi-instance scaling. |
| Mixed threading + asyncio (snapshot scheduler, polling loops) | CONFIRMED | H | LAT, COR, DR | `snapshot_scheduler` uses blocking `Event.wait`; market & account connectors spin new loops in threads; potential race & shutdown complexity. |
| ExecutionManagement is pass-through stub | CONFIRMED | M | COR, RSK | Only logs `EVT:TRADE_INTENT_PROPOSED`; no TCA, slippage, venue routing, or rejection metrics. |
| Feature historical structures absent (original audit claim) | REFINED | M | COR | Deques & EMAs now present; SMA/ATR still missing (limits volatility normalization). |
| Price SSOT fragmentation | PARTIAL | H | COR, RSK | Sources: feature_engineering (tick price), decision_making (`features.price`), execution_position (adapter `get_mark_price`), exposure guard uses portfolio notional (entry price approximation). Need unified `PriceService`. |
| Position tracking race conditions (no locks) | CONFIRMED | M | COR, DR | `PositionTracking._positions` mutated without locking; multiple event sources possible; risk of inconsistent equity/PnL snapshots. |
| Credentials handling & logging | REFINED | M | SEC | Adapter stores keys in memory; does not log secrets; improvement: explicit redaction & secure injection (env/KMS). |
| Reconnect logic lacking backoff (original claim) | REFINED | M | OPS, LAT | Some exponential backoff exists in `binance_execution_adapter` (WebSocket). Market data REST polling thread lacks robust retry/backoff segmentation. Need unified policy. |
| Dead / legacy code in execution_position FSM | PARTIAL | L | COR, OPS | Large file; some duplicated util imports & legacy hydration patterns; pending deeper pruning map. |
| Duplicate retry implementations | PARTIAL | M | OPS | Adapter has inline retry/backoff; bridge QoS retries in `main.py.bak`; scattered sleep-retry loops; consolidate into `vfoundation.util.retry`. |
| Broad `except Exception` usage | CONFIRMED | M | COR, DR | Numerous silent catches (feature_engineering, position_tracking, snapshot_scheduler); missing structured error taxonomy + metrics. |
| Inconsistent configuration access (dict vs attributes) | CONFIRMED | M | COR, OPS | Repeated dual-path resolution (dict vs Pydantic) increasing complexity; adopt typed config facade. |
| Exposure guard staleness / fail-closed gating | CONFIRMED | M | RSK, COR | Hard gates when equity unknown or portfolio stale; dependency on timely portfolio events; race with postfill holds. |
| Bracket race conditions (closing vs placement) | CONFIRMED | H | COR, RSK | ManageFlowFSM anti-race flags; still complex path; potential duplicate bracket placement if timing drifts. |
| Disaster Recovery snapshot disabled | CONFIRMED | M | DR | Scheduler set to `None` in `main`; WAL-only resilience; no periodic snapshots. |
| Timeout watchdog partial integration | REFINED | M | RSK, COR | Hooks set but needs full order lifecycle correlation for missed fills & stale brackets. |
| Fallback mode & clipping (soft limits) | REFINED | M | RSK | ExposureGuard has clipping & fallback; interplay with incomplete equity feeds can over-constrain or under-limit. |

## 4. Evidence Details
### 4.1 Globals & Bridge
File: `apps/reference/main.py`
- Global variables declared top-level; event handlers resolve globals then call bridge. Risk: tight coupling, test complexity.
Remediation: Dependency Injection container (lightweight) + per-domain instance registry.

### 4.2 Concurrency Mixing
Files: `snapshot_scheduler.py`, `market_data_connector.py`, `account_connector.py`, `execution_position/fsm.py`
- Threads spawn loops (`asyncio.new_event_loop()`); blocking sleeps; inconsistent cancellation strategy.
Remediation: Single primary asyncio loop; thread workers only for CPU-bound or IO requiring sync libs; structured cancellation tokens.

### 4.3 ExecutionManagement Stub
File: `execution_management.py` — logs only; no routing/latency metrics.
Remediation: Implement order pre-flight (limits, slippage bounds), cost model & exchange capability abstraction.

### 4.4 Feature Engineering
File: `feature_engineering.py` — maintains deques, EMAs, volatility state. ATR/SMA absent.
Remediation: Add ATR( n ), SMA windows using existing deques; include volatility normalization for risk sizing.

### 4.5 Price SSOT
Sources: adapter `get_mark_price`, decision uses `features.price`, position notional uses entry price approximation, exposure guard margin path.
Risk: Divergent valuations (entry vs mark vs last trade). Affect PnL, margin gating, quick profit logic.
Remediation: Introduce `PriceService` publishing unified object `{mark, last, mid, timestamp}`; domains subscribe; restrict direct adapter calls.

### 4.6 Position Tracking Races
File: `position_tracking.py` — no lock around `_positions` / `_realized_pnl` updates; WAL write then immediate mutation.
Remediation: Adopt `asyncio.Lock` (if loop) or `threading.RLock`; atomic update function; snapshot emission after lock release.

### 4.7 Credentials
File: `binance_adapter.py` — secrets only stored in instance, not logged.
Remediation: Load via env/KMS; enforce no accidental serialization (custom `__repr__`); periodic key rotation hook.

### 4.8 Reconnect & Retry
Evidence: WebSocket reconnection with backoff in `binance_execution_adapter.py` vs scattered manual retries in adapter `_request` and QoS deferrals.
Remediation: Central `RetryPolicy` (jitter, exponential, max attempts) + classification (network vs exchange error).

### 4.9 Broad Exceptions
Multiple files show `except Exception` without classification or re-raise.
Remediation: Define error taxonomy (ConfigError, AdapterTransientError, AdapterFatalError, DataIntegrityError) + metrics counters.

### 4.10 Config Inconsistency
Mixed Pydantic/dict resolution logic repeated per file.
Remediation: Provide `ConfigFacade` with safe getters + caching; ban inline try/except config traversals.

### 4.11 Exposure Guard & Brackets
Complex anti-race logic, postfill reservations, multiple cleanup paths; bracket placement parallel tasks with fallback logic.
Remediation: State machine separation: EntryFlow, BracketFlow, CloseFlow with explicit state transitions & invariants; unify bracket lifecycle events.

### 4.12 Snapshot & DR
Snapshots disabled; reliance on WAL only raises recovery time and risk of long replay windows.
Remediation: Reinstate snapshot scheduler under load-aware cadence (e.g., dynamic interval when trade volume low); embed snapshot integrity hash verification pre-replay.

## 5. Causal Chains (Early Draft)
1. Mixed concurrency → delayed portfolio updates → exposure_guard stale → fail-closed gating → missed valid entries (latency & missed PnL).
2. Price fragmentation → inconsistent margin / PnL → bracket sizing drift → premature quick profit closes or missed stops.
3. Missing snapshot cadence → WAL replay length increases → slower cold start → window where exposure gating fails (EQUITY_UNKNOWN) → increased fail-closed events.
4. Broad exceptions swallow adapter transient errors → retries not triggered → order watchdog timeouts → forced cancel → orphan cleanup overhead.
5. Position race (no lock) + bracket placement parallelism → potential emission of stale portfolio state → incorrect margin utilization metrics → false exposure rejection.

## 6. Remediation Roadmap (Phased, Additive)
### Wave 0 (Safety Hotfixes) — 1–2 days
- Introduce `PriceService` (read-through cache over adapter; publish mark/last/mid). Domains consume only service.
- Locking in `position_tracking` (single concurrency primitive) + atomic snapshot emitter.
- Reinstate snapshot scheduler with reduced interval (e.g., 120s) and adaptive skip under high latency.
- Wrap broad `except Exception` with classification + metric increment.

### Wave 1 (Architectural Stabilization) — 1–2 weeks
- Replace globals with DI container; refactor `AuroraBridge` to accept injected references; remove module-level `execution_position` variable.
- Central `RetryPolicy` module; refactor adapter `_request` and WebSocket reconnection; unify QoS deferral logic.
- Extract bracket/close logic from monolithic `execution_position/fsm.py` into smaller FSM units (EntryFSM, BracketFSM, CloseFSM) sharing a context object.
- Implement ExecutionManagement real routing & latency metrics (order path tracing, timestamp correlation).

### Wave 2 (Risk & Exposure Integrity) — 1–2 weeks
- ExposureGuard refactor: separate calculators (margin, directional ratio, clipping) + state store; subscribe to unified price feed & portfolio events.
- Introduce PnL real-time via mark price (PositionTracking uses PriceService). Enable unrealized PnL accuracy.
- Add ATR/SMA features to feature_engineering; feed volatility-adjusted sizing & bracket distances.

### Wave 3 (Resilience & Observability) — 2 weeks
- Structured error events + metrics dashboards (timeout categories, rejection reasons, clipping summary).
- Snapshot compression + incremental diff snapshots (Merkle root verification).
- Watchdog full correlation (ACK latency, Fill latency, bracket placement latency distribution).

### Wave 4 (Optimization & Clean-up) — 2–3 weeks
- Remove legacy/hydration duplication; prune unused util imports.
- Performance tuning: eliminate unnecessary thread loops; all domain tasks on single loop with cooperative scheduling.
- Credential hardening (rotation API, secret manager integration).

## 7. Success Metrics
| Metric | Baseline | Target |
|--------|----------|--------|
| Portfolio staleness rejects (per hour) | High (observed multiple fail-closed) | < 1 |
| Order timeout cancellations ratio | TBD | -50% |
| Bracket race duplicates | Present | 0 occurrences in 7d |
| Snapshot replay duration (cold start) | Long WAL scan | < 30s |
| WHY chain coverage | ~? | ≥95% |
| Test coverage (FSM core) | < target | 90% |

## 8. Implementation Ordering Justification
Wave 0 reduces immediate correctness & safety risks (price, locking, DR). Later waves increase structural clarity and long-term maintainability, preventing regression in exposure and bracket logic.

## 9. Pending Investigations
- Full dead code map in `execution_position/fsm.py` (sections after line 2000 not yet triaged).
- Market data reconnect jitter parameters (ensure no thundering herd on multi-instance).
- Unused import audit (automated lint pass pending).
- Perf profiling (event loop scheduling fairness, watchdog overhead).

## 10. Open Questions / Assumptions
- Assumed single-process deployment; no multi-worker sync currently.
- No contract-breaking changes allowed; new services (PriceService) additive only.
- KMS integration feasibility pending environment constraints.

## 11. Immediate Next Actions (Checkpoint)
1. Implement PriceService skeleton + integrate into decision_making & execution_position (entry sizing & bracket calc).
2. Add locking to `position_tracking` with minimal invasive patch.
3. Re-enable snapshot scheduler (config controlled flag) and add integrity hash metric.
4. Introduce error taxonomy + replace broad exceptions in top 5 critical domains.

## 12. Traceability & Linking
For every remediation PR:
- Update `TODO.md` task line with link at end.
- Journal entry in `JOURNAL.md` (RID, short why, artefacts).
- Contract changes documented in `docs/CENTRAL_FSM_SPEC.md` (additive-only).

## 13. Appendix: Pattern Search Tallies
- `except Exception`: multiple domains (risk_management, feature_engineering, snapshot_scheduler, position_tracking, websocket_aggregator).
- `retry`: adapter-level request logic + QoS deferral in legacy `main.py.bak`.
- `reconnect`: WebSocket adapter includes exponential backoff; documentation shows improvement claims.

---
Next update: After Wave 0 partial implementation (lock + price feed). Preserve additive constraint.

## 14. SSOT Price Contract (Draft)

Purpose: Establish a single source of truth for pricing across domains to eliminate divergence between entry/mark/last and prevent sizing/bracket drift.

Contract (v0, additive-only):
- PriceQuote: { symbol: string, mark: float|null, last: float|null, mid: float|null, ts: int (ms), source: "MARK"|"LAST"|"MID" }
- Methods:
	- get_mark(symbol, ttl_ms=250) -> PriceQuote
	- get_last(symbol, ttl_ms=250) -> PriceQuote
	- get_mid(symbol, ttl_ms=250) -> PriceQuote
	- policy: working_type default = MARK; fallback order = MARK -> LAST -> MID (configurable)
	- metrics: cache_hit, adapter_calls, latency_ms, fallback_taken, errors_by_class

Consumers Matrix (initial):
- decision_making: uses PriceService.get_mark or policy.get_current for sizing/thresholds
- execution_position Entry/Manage: bracket placement and quick-profit reference price via PriceService
- exposure_guard: valuation for margin/notional uses PriceService (no direct entry-price approximation)
- position_tracking: unrealized PnL via PriceService.mark
- feature_engineering: may continue consuming tick stream; do not act as SSOT for prices

Evidence tie-ins:
- `vfoundation/core/adapters/base.py` defines async `get_mark_price`/`get_last_price` candidates for read-through cache
- `fsm_manage.py` defaults `working_type` to MARK and falls back to `last_price`/`price` in payload; this will be centralized by service policy

Next steps:
1) Add `vfoundation/services/price_service.py` (skeleton) — see separate contract doc
2) Prepare integration PRs (feature-flagged) for decision_making and ExecPos FSM to read from service

## 15. Execution FSM Dead/Legacy Code Map (Initial)

Goal: Identify legacy compatibility paths and candidate pruning targets without breaking behavior.

Findings (non-exhaustive, based on code scan):
- `fsm_manage.py`:
	- TODO: fetch from /exchangeInfo or cache (line ~482) — missing contract-bound source, should use adapter/service
	- Legacy config support documented (lines ~575–636): fallback to legacy keys `stop_loss_bps`, `take_profit_*` — keep for now; mark deprecation window
	- Working type defaults to MARK_PRICE; payload fallback: `pld['mark_price'] or pld['last_price'] or pld['price']` (lines ~747, ~832–833)
- `exposure_guard.py`:
	- Legacy metrics carry-over (`__legacy_total`) around ~1654–1658 — retain for continuity; document migration plan

Planned actions:
- Tag legacy blocks with `@deprecated(next: v1.1)` comments and link to PriceService/ConfigFacade issues
- Extract exchange info fetch into adapter/service to resolve TODO
- Build a checklist to remove payload-level price fallbacks after PriceService adoption reaches 100%

## 16. Unused Imports Quick Pass (Triage)

Scope: execution_position FSM modules and exposure guard.

Method: manual scan + grep for obvious duplicates; full lint pass to follow in Wave 4.

Preliminary:
- Multiple legacy/compat helpers are imported for config fallbacks; usage is intertwined — defer removal until contract adoption
- Action: introduce automated linter stage (ruff/flake8) in CI with `--select F401` and whitelist for legacy blocks

Outcome:
- Marked for Wave 4 cleanup after functional stabilization.
